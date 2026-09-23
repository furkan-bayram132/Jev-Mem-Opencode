#!/usr/bin/env python3
"""Expose Jev-Mem's System-One memory to any MCP client over stdio.

The client's own model is System Two: it sends a query and receives the
observations Jev selected, never the graph itself. Nothing here calls an
answer model.
"""
import argparse
import logging
import os
import sys

# Keep stdout clean: the MCP framing shares it with nothing else.
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

logger = logging.getLogger("jev_mem.mcp")


def build_server(store):
    """Wire the store to MCP tools. Descriptions decide when a model calls them."""
    try:
        from mcp.server import MCPServer as Server
    except ImportError:  # mcp 1.x
        from mcp.server.fastmcp import FastMCP as Server

    server = Server("jev-mem")

    @server.tool()
    def memory_recall(query: str, top_k: int = 8, output_format: str = "compact") -> dict:
        """Search long-term memory for evidence about past facts, preferences, and decisions.

        Call this before answering anything that depends on earlier sessions, or
        whenever the user refers to something previously agreed, chosen, or
        established. You do not search: send the question and the memory
        controller routes it across semantic, temporal, causal, and entity
        relations, then returns only the observations it selected.

        Returns evidence text plus the raw observations and a short decision
        trace. It returns evidence, not an answer -- you write the answer.

        Args:
            query: The question, in natural language.
            top_k: How many observations to return (1-25, default 8).
            output_format: "compact" for plain ranked lines, "qa" for the
                benchmark-style block with relevance markers.
        """
        return store.recall(query, top_k=top_k, output_format=output_format)

    @server.tool()
    def memory_remember(text: str, timestamp: str | None = None,
                        source: str | None = None, tags: list[str] | None = None) -> dict:
        """Store one observation worth recalling in a later session.

        Use it for durable things: a stated preference, a decision and its
        reason, a constraint, a fact about the project or the person. Do not use
        it for transient conversation detail or for content already in the
        repository. Write one self-contained observation per call, phrased so it
        still makes sense months later without this conversation.

        Args:
            text: The observation, as a complete sentence.
            timestamp: ISO 8601 time it refers to. Defaults to now.
            source: Where it came from, e.g. "opencode" or a file path.
            tags: Optional labels for later filtering.
        """
        metadata = {}
        if source:
            metadata["source"] = source
        if tags:
            metadata["entities"] = list(tags)
        return store.remember(text, timestamp=timestamp, metadata=metadata)

    @server.tool()
    def memory_stats() -> dict:
        """Report memory size, the active Jev profile, and the decision log path."""
        return store.stats()

    return server


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", default="./.jev-mem",
                        help="Directory holding the graph, vectors, and decision log")
    parser.add_argument("--jev-config",
                        help="Jev-Mem profile JSON (default: config/jev_mem.json). "
                             "Use config/jev_mem_openrouter.json to reach Jev through OpenRouter.")
    parser.add_argument("--embedding-model", default="minilm", choices=["minilm", "openai"])
    parser.add_argument("--jev-mock", action="store_true",
                        help="Deterministic mock decisions; no TYPESAFE_API_KEY needed")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    from dotenv import load_dotenv
    load_dotenv()
    from .store import MemoryStore
    store = MemoryStore(args.cache_dir, jev_config_path=args.jev_config,
                        embedding_model=args.embedding_model, jev_mock=args.jev_mock)
    server = build_server(store)
    try:
        server.run()
    finally:
        store.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
