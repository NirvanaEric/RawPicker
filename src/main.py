"""Entry point: construct the app and run the Tk mainloop."""
from __future__ import annotations

import sys


def main() -> int:
    from .app import App
    App().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
