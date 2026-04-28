from __future__ import annotations

import os
import sys


def main() -> int:
    # Headless (no display) → just print version and exit cleanly.
    if not (os.environ.get("DISPLAY") or sys.platform in {"win32", "darwin"}):
        from . import __version__

        print(f"ytwall {__version__}")
        print("No display detected. ytwall is a Windows desktop GUI application.")
        return 0

    from .app import run

    return run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
