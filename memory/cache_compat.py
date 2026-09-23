"""Read older cache names while writing only the current Jev-Mem schema.

Historical project names belong here, not in the public API or new outputs.
"""
import json
from pathlib import Path


def memory_config_path(directory):
    """Prefer the current configuration filename when both versions exist."""
    directory = Path(directory)
    current = directory / "jev_mem_config.json"
    return current if current.exists() else directory / "sys1mem_config.json"


def normalize_metadata(metadata):
    """Copy metadata and migrate historical controller keys without data loss."""
    result = dict(metadata)
    legacy = result.pop("sys1mem", None)
    if legacy is not None:
        # Explicit current-format fields take precedence in a mixed cache.
        result["jev_mem"] = {**legacy, **result.get("jev_mem", {})}
    if result.get("source") == "sys1mem_consolidation":
        result["source"] = "jev_mem_consolidation"
    if result.get("controller") in ("sys1mem", "sys1-mem"):
        result["controller"] = "jev-mem"
    return result


def validate_reuse_memory(path, config):
    """Permit retrieval tuning on an existing graph with matching write settings."""
    from .jev_mem_config import JevMemConfig
    path = Path(path)
    for name in ("graph.json", "vectors", "keyword_index.json"):
        if not (path / name).exists():
            raise ValueError(f"Reuse cache is missing {name}: {path}")
    config_path = memory_config_path(path)
    if not config_path.exists():
        raise ValueError(f"Reuse cache is missing Jev-Mem configuration: {path}")
    saved = json.loads(config_path.read_text())
    # Older caches omitted this field while admission was mandatory.
    saved.setdefault("admission_enabled", True)
    saved.setdefault("decision_schema_version", "noul-choice-v2")
    old = JevMemConfig(**saved).to_dict()
    current = config.to_dict()
    fields = ("write_enabled", "admission_enabled", "jev_mock", "jev_model", "decision_schema_version",
              "relation_threshold", "candidate_top_k", "consolidation_interval", "consolidation_threshold")
    if config.admission_enabled:
        fields += ("admission_threshold", "admission_weights")
    differences = [key for key in fields if json.dumps(old[key]) != json.dumps(current[key])]
    if differences:
        raise ValueError("Reuse cache has different construction settings: " + ", ".join(differences))
    return path
