"""Compatibility entry point; use python -m jev_mem or jev_mem.system."""
import sys
from jev_mem import cli as _implementation

if __name__ == "__main__":
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation
