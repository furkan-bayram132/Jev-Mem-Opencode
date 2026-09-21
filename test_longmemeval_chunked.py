"""Compatibility entry point; use jev_mem.benchmarks.longmemeval instead."""
import sys
from jev_mem.benchmarks import longmemeval as _implementation

if __name__ == "__main__":
    raise SystemExit(_implementation.main())
else:
    # Preserve class identity, module globals, and legacy monkeypatch targets.
    sys.modules[__name__] = _implementation
