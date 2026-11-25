import json
from datetime import datetime, timezone

from src.protocol import make_auth_check_message, make_status_packet, normalize_hook_payload, truncate_text
from src.usage import (
    CodexUsageSnapshot,
    _carry_forward_quota,
    _quota_from_payload,
    _quota_from_usage_response,
    scan_local_usage,
)


def test_prompt_is_redacted():
    msg = normalize_hook_payload({"event": "UserPromptSubmit", "prompt": "very long secret prompt"})
    assert msg["state"] == "prompt"
    assert msg["text"] == "prompt submitted"


def test_bash_mapping():
    msg = normalize_hook_payload({"event": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "idf.py build"}})
    assert msg["state"] == "bash"
    assert msg["text"] == "idf.py build"


def test_secret_redaction():
    assert "SECRET" not in truncate_text("TOKEN=SECRET")


def test_compact_and_subagent_mapping():
    assert normalize_hook_payload({"event": "PreCompact"})["state"] == "compact"
    assert normalize_hook_payload({"event": "PostCompact"})["state"] == "compact_done"
    assert normalize_hook_payload({"event": "SubagentStart"})["state"] == "subagent"
    assert normalize_hook_payload({"event": "SubagentStop"})["state"] == "tool_done"


def test_status_packet_includes_usage():
    packet = make_status_packet(
        {"state": "idle", "event": "UsageRefresh", "ts": 1},
        token="t",
        seq=1,
        usage={"today_tokens": 10, "week_tokens": 20, "month_tokens": 30, "updated_at": 2},
    )
    assert packet["usage"]["today_tokens"] == 10


def test_auth_check_message_shape():
    packet = make_auth_check_message("bridge-1", "mug-1", "token", request_id="req-1")

    assert packet == {
        "type": "pixelmug_pair",
        "v": 1,
        "cmd": "auth_check",
        "request_id": "req-1",
        "bridge_id": "bridge-1",
        "device_id": "mug-1",
        "token": "token",
    }


def test_scan_local_usage_reads_token_count_and_quota(tmp_path):
    sessions = tmp_path / "sessions" / "2026" / "06"
    sessions.mkdir(parents=True)
    log = sessions / "session.jsonl"
    now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    rows = [
        {
            "timestamp": "2026-06-24T12:00:00Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {"input_tokens": 7, "output_tokens": 3},
                    "total_token_usage": {"total_tokens": 10},
                },
                "rate_limits": {
                    "primary": {"used_percent": 25, "reset_at": 1_800_000_000, "limit_window_seconds": 18_000},
                    "secondary": {"used_percent": 40, "reset_at": 1_800_010_000, "limit_window_seconds": 604_800},
                },
            },
        },
        {
            "timestamp": "2026-06-24T12:01:00Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {"input_tokens": 5, "output_tokens": 5},
                    "total_token_usage": {"total_tokens": 20},
                },
            },
        },
    ]
    log.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    totals, quota = scan_local_usage(sessions, now=now)

    assert totals["2026-06-24"] == 20
    assert quota["5h"].remaining_percent == 75
    assert quota["7d"].remaining_percent == 60


def test_weekly_only_quota_at_or_below_one_percent():
    timestamp = datetime.now().astimezone()
    for used in (0, 0.5, 1, 100):
        local = _quota_from_payload({
            "rate_limits": {
                "primary": {"used_percent": used, "window_minutes": 10080},
                "secondary": None,
            },
        }, timestamp)
        remote = _quota_from_usage_response({
            "rateLimits": {
                "primary": {"usedPercent": used, "windowDurationMins": 10080},
                "secondary": None,
            },
        })
        for quota in (local, remote):
            assert set(quota) == {"7d"}
            assert quota["7d"].remaining_percent == 100 - used


def test_usage_refresh_carries_forward_quota():
    current = CodexUsageSnapshot(today_tokens=1, week_tokens=2, month_tokens=3, updated_at=20)
    previous = CodexUsageSnapshot(
        today_tokens=0,
        week_tokens=0,
        month_tokens=0,
        quota_5h_remaining_percent=80,
        quota_5h_used_percent=20,
        quota_5h_resets_at=100,
        quota_7d_remaining_percent=60,
        quota_7d_used_percent=40,
        quota_7d_resets_at=200,
        updated_at=10,
    )

    merged = _carry_forward_quota(current, previous)

    assert merged.today_tokens == 1
    assert merged.quota_5h_remaining_percent == 80
    assert merged.quota_7d_remaining_percent == 60
