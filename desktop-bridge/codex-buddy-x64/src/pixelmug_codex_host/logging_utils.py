from __future__ import annotations

import logging
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .paths import ensure_dirs


def _add_rotating_file_handler(logger: logging.Logger, path: Path) -> bool:
    if any(isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", None) == str(path) for h in logger.handlers):
        return True

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=512 * 1024, backupCount=3, encoding="utf-8")
    except OSError:
        return False

    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    return True


def configure_file_logger(name: str, path: Path, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    try:
        ensure_dirs()
    except OSError:
        pass

    if _add_rotating_file_handler(logger, path):
        return logger

    fallback = Path(tempfile.gettempdir()) / "PixelMugCodex" / "logs" / path.name
    if _add_rotating_file_handler(logger, fallback):
        logger.warning("primary log path unavailable; logging to %s", fallback)
        return logger

    if not any(isinstance(h, logging.NullHandler) for h in logger.handlers):
        logger.addHandler(logging.NullHandler())

    return logger
