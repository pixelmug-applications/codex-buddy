from __future__ import annotations

import json
import sys

from .logging_utils import configure_file_logger
from .paths import hook_log_path
from .protocol import make_local_codex_message, send_local_hook_message


def _write_codex_hook_response(event_name: str) -> None:
    """
    Keep stdout empty for all events.

    This hook only mirrors status to PixelMug. Stop hooks have stricter stdout
    schema validation in Codex, and an empty response is the safest no-op.
    """
    _ = event_name


def run_hook() -> int:
    logger = configure_file_logger("pixelmug_codex_hook", hook_log_path())
    event_name = ""

    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}

        if not isinstance(event, dict):
            raise ValueError("hook stdin JSON is not an object")

        event_name = str(event.get("hook_event_name") or event.get("event") or "")

        msg = make_local_codex_message(event)
        send_local_hook_message(msg)

        logger.info(
            "sent local hook event=%s state=%s tool=%s",
            msg.get("event"),
            msg.get("state"),
            msg.get("tool"),
        )

    except Exception as exc:
        # Hook must never break Codex. Log and return success.
        logger.exception("hook failed but returned success: %s", exc)

    # Important: only Stop emits valid JSON. Other hooks remain silent.
    _write_codex_hook_response(event_name)
    return 0


def main() -> int:
    return run_hook()