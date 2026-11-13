"""Logging setup. Tokens are deliberately not logged."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .paths import ensure_user_dirs, log_file

_LOGGER_NAME = "pixelmug_codex"


def get_logger(name: str | None = None) -> logging.Logger:
    ensure_user_dirs()
    logger_name = _LOGGER_NAME if name is None else f"{_LOGGER_NAME}.{name}"
    logger = logging.getLogger(logger_name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = RotatingFileHandler(log_file(), maxBytes=512 * 1024, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.INFO)
    logger.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.setLevel(logging.WARNING)
    logger.addHandler(console)

    return logger
