from __future__ import annotations

import os
import sys

from . import __version__
from .app import run


def main() -> int:
    if not (os.environ.get("DISPLAY") or sys.platform in {"win32", "darwin"}):
        print(f"ytwall {__version__}")
        print("No display detected. ytwall is a Windows desktop GUI application.")
        return 0
    return run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
