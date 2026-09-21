"""Compatibility entry point; use jev_mem.demo instead."""
import sys
from jev_mem import demo as _implementation

if __name__ == "__main__":
    raise SystemExit(_implementation.main())
else:
    # Preserve class identity, module globals, and legacy monkeypatch targets.
    sys.modules[__name__] = _implementation
