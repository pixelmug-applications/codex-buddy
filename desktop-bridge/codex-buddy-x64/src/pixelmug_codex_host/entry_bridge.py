from __future__ import annotations

import tempfile
import traceback
from pathlib import Path


def _write_startup_error() -> None:
    try:
        log_dir = Path(tempfile.gettempdir()) / "PixelMugCodex"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "startup-error.log").write_text(traceback.format_exc(), encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    try:
        from pixelmug_codex_host.bridge import main

        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        _write_startup_error()
        raise