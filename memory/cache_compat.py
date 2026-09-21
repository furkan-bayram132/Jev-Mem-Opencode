"""Read older cache names while writing only the current Jev-Mem schema.

Historical project names belong here, not in the public API or new outputs.
"""
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
