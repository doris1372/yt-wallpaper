"""Entry point: run with `python -m ytwall` or via the frozen PyInstaller exe.

We use absolute imports so the same module works in both modes:
- `python -m ytwall` → imported as `ytwall.__main__` (package context)
- frozen .exe → executed as `__main__` (no package context)
PyInstaller bundles the whole `ytwall` package, so `from ytwall.app import run`
resolves correctly in both cases.
"""

from __future__ import annotations

import os
import sys

from ytwall import __version__
from ytwall.app import run


def main() -> int:
    if not (os.environ.get("DISPLAY") or sys.platform in {"win32", "darwin"}):
        print(f"ytwall {__version__}")
        print("No display detected. ytwall is a Windows desktop GUI application.")
        return 0
    return run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
