"""Transport-independent System-One memory store.

Jev controls writing and retrieval; the caller's own model is System Two and
never sees the graph. `recall` returns only the selected observations, so the
context handed to an external agent stays bounded as the memory grows.
"""
from datetime import datetime
import logging
import os
from pathlib import Path
import threading

logger = logging.getLogger("jev_mem.store")

DEFAULT_PROFILE = Path(__file__).resolve().parents[1] / "config" / "jev_mem.json"
MAXIMUM_TOP_K = 25
TRACE_FIELDS = ("controller", "stopping_decision", "nodes_visited", "edges_examined",
                "jev_calls", "jev_cache_hits", "llm_calls", "retrieval_depth",
                "latency_seconds", "top_k_returned", "fallback_events")


def parse_timestamp(value):
    """Accept ISO 8601 text or a datetime; None means the store assigns none."""
    if value is None or isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError("timestamp must be ISO 8601 text or null")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class MemoryStore:
    """One Jev-Mem graph on disk, opened lazily and shared by all callers."""

    def __init__(self, cache_dir, jev_config_path=None, embedding_model="minilm",
                 jev_mock=False, encoder=None):
        self.cache_dir = Path(cache_dir)
        self.jev_config_path = Path(jev_config_path) if jev_config_path else DEFAULT_PROFILE
        self.embedding_model = embedding_model
        self.jev_mock = jev_mock
        self.encoder = encoder
        self.lock = threading.RLock()
        self.builder = None
        self.engine = None
        self.config = None

    # Startup -----------------------------------------------------------------

    def _ensure_ready(self):
        """Load the encoder and graph on first use, not at import or handshake."""
        if self.builder is not None:
            return
        from dataclasses import replace
        from memory.cache_compat import validate_reuse_memory
        from memory.jev_mem_config import JevMemConfig
        from memory.memory_builder import MemoryBuilder
        from memory.query_engine import QueryEngine

        path = str(self.jev_config_path) if self.jev_config_path.exists() else None
        config = JevMemConfig.load(path, write_enabled=True, read_enabled=True,
                                   jev_mock=True if self.jev_mock else None)
        if not config.audit_path:
            config = replace(config, audit_path=str(self.cache_dir / "decisions.jsonl"))
        self.config = config

        builder_kwargs = {"jev_config": config, "llm_enabled": False,
                          "embedding_model": self.embedding_model}
        if self.encoder is not None:
            from memory.trg_memory import TemporalResonanceGraphMemory
            from memory.vector_db import NumpyVectorDB
            builder_kwargs["trg_memory"] = TemporalResonanceGraphMemory(
                vector_db=NumpyVectorDB(self.encoder.dimension), encoder=self.encoder, llm_backend=None)
        builder = MemoryBuilder(str(self.cache_dir), **builder_kwargs)
        if self.encoder is not None:
            builder.trg.persist_dir = self.cache_dir
            builder.trg.vector_db.persist_path = str(self.cache_dir / "vectors")

        if (self.cache_dir / "graph.json").exists():
            # Refuse a graph built under different write settings instead of
            # silently mixing two memories in one directory.
            validate_reuse_memory(self.cache_dir, config)
            builder.load()

        self.builder = builder
        self.engine = QueryEngine(builder.trg, builder.node_index,
                                  jev_config=config, jev_client=builder.jev)
        if not config.jev_mock and not os.getenv(config.jev_api_key_env):
            logger.warning("%s is not set; Jev decisions fall back to heuristics",
                           config.jev_api_key_env)
        logger.info("Memory ready at %s (%d nodes)", self.cache_dir, len(builder.trg.graph_db.nodes))

    # Tools -------------------------------------------------------------------

    def remember(self, text, timestamp=None, metadata=None):
        """Store one observation through the System-One write path."""
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string")
        metadata = dict(metadata or {})
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be an object")
        when = parse_timestamp(timestamp)
        with self.lock:
            self._ensure_ready()
            node = self.builder.build(text, when, metadata)
            if node is None:
                return {"stored": False, "reason": "rejected_by_admission"}
            self.builder.save()
            decisions = node.attributes.get("jev_mem", {})
            return {"stored": True, "node_id": node.node_id,
                    "memory_type": decisions.get("memory_type", {}),
                    "controller": decisions.get("controller", "jev-mem")}

    def recall(self, query, top_k=8, output_format="compact"):
        """Retrieve evidence for a query. No System-Two model is called here."""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        if output_format not in ("compact", "qa"):
            raise ValueError("output_format must be 'compact' or 'qa'")
        top_k = max(1, min(int(top_k), MAXIMUM_TOP_K))
        with self.lock:
            self._ensure_ready()
            if not self.builder.trg.graph_db.nodes:
                return {"evidence": "", "observations": [], "trace": {"stopping_decision": "empty_memory"}}
            context, qa_evidence = self.engine.query(query, top_k=top_k)
        observations = [self._describe(node) for node in context.anchor_nodes]
        evidence = self._compact(observations) if output_format == "compact" else qa_evidence
        trace = {key: context.metadata[key] for key in TRACE_FIELDS if key in context.metadata}
        return {"evidence": evidence, "observations": observations, "trace": trace}

    def stats(self):
        with self.lock:
            self._ensure_ready()
            graph = self.builder.trg.graph_db
            return {"cache_dir": str(self.cache_dir), "observations": len(graph.nodes),
                    "links": len(graph.links), "jev_model": self.config.jev_model,
                    "jev_mock": self.config.jev_mock, "profile": str(self.jev_config_path),
                    "audit_log": self.config.audit_path}

    def flush(self):
        with self.lock:
            if self.builder is not None:
                self.builder.save()

    # Formatting --------------------------------------------------------------

    @staticmethod
    def _describe(node):
        attributes = getattr(node, "attributes", {}) or {}
        text = (attributes.get("original_text") or attributes.get("raw_content")
                or getattr(node, "content_narrative", ""))
        item = {"text": text, "node_id": node.node_id}
        if getattr(node, "timestamp", None):
            item["date"] = node.timestamp.strftime("%Y-%m-%d")
        for key in ("speaker", "source"):
            if attributes.get(key):
                item[key] = attributes[key]
        return item

    @staticmethod
    def _compact(observations):
        """Plain ranked lines. The benchmark formatter repeats each excerpt in a
        trailing section, which only costs tokens in an agent's context."""
        lines = []
        for position, item in enumerate(observations, 1):
            prefix = "".join(f"[{item[key]}] " for key in ("date", "speaker", "source") if key in item)
            lines.append(f"{position}. {prefix}{item['text']}")
        return "\n".join(lines)
