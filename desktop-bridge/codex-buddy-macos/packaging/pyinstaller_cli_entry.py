"""PyInstaller entrypoint for the pixelmug-codex CLI."""
from __future__ import annotations

import sys


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "hook":
        from src.hook import main as hook_main

        raise SystemExit(hook_main(sys.argv[2:]))

    from src.__main__ import main

    raise SystemExit(main())
