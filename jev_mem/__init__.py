"""Public Jev-Mem API, loaded lazily to avoid initializing model providers."""
from importlib import import_module

__version__ = "0.1.0"
__all__ = ["JevMemSystem", "JevMemConfig", "MemoryBuilder", "MemoryStore", "QueryEngine"]

_EXPORTS = {
    "JevMemSystem": "jev_mem.system",
    "JevMemConfig": "memory.jev_mem_config",
    "MemoryBuilder": "memory.memory_builder",
    "MemoryStore": "jev_mem.store",
    "QueryEngine": "memory.query_engine",
}


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module(_EXPORTS[name]), name)
    globals()[name] = value
    return value
