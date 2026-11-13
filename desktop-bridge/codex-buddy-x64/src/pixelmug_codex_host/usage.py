"""Codex quota and local token usage monitoring.

The scanner is intentionally best-effort. It reads local Codex session logs and
low-frequency quota metadata without letting usage telemetry block hook status.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _codex_home() -> Path:
    value = os.environ.get("CODEX_HOME", "").strip()
    if value:
        return Path(value).expanduser()
    return Path.home() / ".codex"


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone()


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _token_total(usage: dict[str, Any] | None) -> int | None:
    if not isinstance(usage, dict):
        return None
    explicit = _number(usage.get("total_tokens"))
    if explicit is not None:
        return max(int(explicit), 0)

    total = 0
    found = False
    for key in (
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
        "reasoning_output_tokens",
    ):
        value = _number(usage.get(key))
        if value is not None:
            total += int(value)
            found = True
    return max(total, 0) if found else None


def _day_key(moment: datetime) -> str:
    return moment.astimezone().date().isoformat()


def _reset_date(timestamp: int | None) -> str | None:
    if not timestamp:
        return None
    try:
        return datetime.fromtimestamp(timestamp).astimezone().strftime("%m-%d")
    except (OSError, OverflowError, ValueError):
        return None


@dataclass(frozen=True)
class CodexQuotaWindow:
    remaining_percent: float
    used_percent: float
    window_minutes: int | None = None
    resets_at: int | None = None
    observed_at: int | None = None


@dataclass(frozen=True)
class CodexUsageSnapshot:
    today_tokens: int = 0
    week_tokens: int = 0
    month_tokens: int = 0
    quota_5h_remaining_percent: float | None = None
    quota_5h_used_percent: float | None = None
    quota_5h_resets_at: int | None = None
    quota_7d_remaining_percent: float | None = None
    quota_7d_used_percent: float | None = None
    quota_7d_resets_at: int | None = None
    updated_at: int = 0

    def as_packet_fields(self) -> dict[str, Any]:
        usage: dict[str, Any] = {
            "today_tokens": self.today_tokens,
            "week_tokens": self.week_tokens,
            "month_tokens": self.month_tokens,
            "updated_at": self.updated_at,
        }
        if self.quota_5h_remaining_percent is not None:
            usage["quota_5h_remaining_percent"] = round(self.quota_5h_remaining_percent, 1)
            usage["quota_5h_used_percent"] = round(self.quota_5h_used_percent or 0, 1)
            if self.quota_5h_resets_at:
                usage["quota_5h_resets_at"] = self.quota_5h_resets_at
        if self.quota_7d_remaining_percent is not None:
            usage["quota_7d_remaining_percent"] = round(self.quota_7d_remaining_percent, 1)
            usage["quota_7d_used_percent"] = round(self.quota_7d_used_percent or 0, 1)
            if self.quota_7d_resets_at:
                usage["quota_7d_resets_at"] = self.quota_7d_resets_at
                reset_date = _reset_date(self.quota_7d_resets_at)
                if reset_date:
                    usage["quota_7d_reset_date"] = reset_date
        return usage


@dataclass
class _Credentials:
    access_token: str
    refresh_token: str = ""
    account_id: str | None = None
    source: str = "oauth"


@dataclass
class CodexUsageMonitor:
    log_refresh_sec: float = 60.0
    quota_refresh_sec: float = 600.0
    session_root: Path | None = None
    auth_file: Path | None = None
    _snapshot: CodexUsageSnapshot = field(default_factory=CodexUsageSnapshot, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="PixelMugCodexUsage", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def snapshot(self) -> CodexUsageSnapshot:
        with self._lock:
            return self._snapshot

    def refresh_once(self, include_network: bool = False) -> CodexUsageSnapshot:
        token_totals, quota_from_logs = scan_local_usage(self.session_root)
        quota = quota_from_logs
        if include_network:
            try:
                quota = fetch_remote_quota(self.auth_file) or quota
            except Exception:
                pass
        snapshot = _snapshot_from_totals(token_totals, quota)
        with self._lock:
            snapshot = _carry_forward_quota(snapshot, self._snapshot)
            self._snapshot = snapshot
        return snapshot

    def _loop(self) -> None:
        next_log = 0.0
        next_quota = 0.0
        while not self._stop_event.is_set():
            now = time.monotonic()
            include_network = now >= next_quota
            if now >= next_log or include_network:
                self.refresh_once(include_network=include_network)
                next_log = now + self.log_refresh_sec
                if include_network:
                    next_quota = now + self.quota_refresh_sec
            self._stop_event.wait(1.0)


def scan_local_usage(session_root: Path | None = None, now: datetime | None = None) -> tuple[dict[str, int], dict[str, CodexQuotaWindow]]:
    root = session_root or (_codex_home() / "sessions")
    now = now or datetime.now().astimezone()
    start_day = (now - timedelta(days=29)).date()
    totals: dict[str, int] = {}
    quota: dict[str, CodexQuotaWindow] = {}
    if not root.exists():
        return totals, quota

    for path in root.rglob("*.jsonl"):
        try:
            if datetime.fromtimestamp(path.stat().st_mtime).date() < start_day:
                continue
        except OSError:
            continue
        _scan_session_file(path, start_day=start_day, totals=totals, quota=quota)
    return totals, quota


def _scan_session_file(path: Path, start_day: Any, totals: dict[str, int], quota: dict[str, CodexQuotaWindow]) -> None:
    previous_total: int | None = None
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if "token_count" not in line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "event_msg":
                    continue
                payload = obj.get("payload")
                if not isinstance(payload, dict) or payload.get("type") != "token_count":
                    continue
                timestamp = _parse_time(obj.get("timestamp"))
                if timestamp is None or timestamp.date() < start_day:
                    continue
                info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
                day = _day_key(timestamp)
                last_total = _token_total(info.get("last_token_usage") if isinstance(info, dict) else None)
                cumulative_total = _token_total(info.get("total_token_usage") if isinstance(info, dict) else None)
                delta = _usage_delta(previous_total, cumulative_total, last_total)
                if cumulative_total is not None:
                    previous_total = cumulative_total
                if delta:
                    totals[day] = totals.get(day, 0) + delta
                found_quota = _quota_from_payload(payload, timestamp)
                for key, window in found_quota.items():
                    current = quota.get(key)
                    if current is None or (window.observed_at or 0) >= (current.observed_at or 0):
                        quota[key] = window
    except OSError:
        return


def _usage_delta(previous_total: int | None, cumulative_total: int | None, last_total: int | None) -> int:
    if cumulative_total is not None:
        if previous_total is None:
            return max(last_total or cumulative_total, 0)
        delta = cumulative_total - previous_total
        if delta > 0:
            return delta
        if last_total is not None and cumulative_total < previous_total:
            return last_total
        return 0
    return max(last_total or 0, 0)


def _quota_from_payload(payload: dict[str, Any], timestamp: datetime) -> dict[str, CodexQuotaWindow]:
    rate_limits = payload.get("rate_limits")
    if not isinstance(rate_limits, dict):
        return {}
    found: dict[str, CodexQuotaWindow] = {}
    for key in ("primary", "secondary"):
        raw = rate_limits.get(key)
        window = _quota_window(raw, timestamp)
        if window is None:
            continue
        label = _window_label(window.window_minutes)
        if label:
            found[label] = window
    return found


def _quota_window(raw: Any, timestamp: datetime | None = None) -> CodexQuotaWindow | None:
    if not isinstance(raw, dict):
        return None
    used = _number(raw.get("used_percent") if "used_percent" in raw else raw.get("usedPercent"))
    if used is None:
        return None
    if 0 < used <= 1:
        used *= 100
    used = min(max(used, 0), 100)
    seconds = _number(raw.get("limit_window_seconds") if "limit_window_seconds" in raw else raw.get("limitWindowSeconds"))
    minutes = _number(raw.get("window_minutes") if "window_minutes" in raw else raw.get("windowDurationMins"))
    window_minutes = int(seconds / 60) if seconds else int(minutes) if minutes else None
    reset = _number(raw.get("reset_at") if "reset_at" in raw else raw.get("resetsAt"))
    if reset is None:
        reset = _number(raw.get("resets_at"))
    return CodexQuotaWindow(
        remaining_percent=100 - used,
        used_percent=used,
        window_minutes=window_minutes,
        resets_at=int(reset) if reset else None,
        observed_at=int(timestamp.timestamp()) if timestamp else None,
    )


def _window_label(minutes: int | None) -> str | None:
    if minutes is None:
        return None
    if 240 <= minutes <= 360:
        return "5h"
    if 9000 <= minutes <= 11000:
        return "7d"
    return None


def fetch_remote_quota(auth_file: Path | None = None) -> dict[str, CodexQuotaWindow]:
    credentials = _load_credentials(auth_file)
    url = _usage_url(auth_file)
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {credentials.access_token}",
            "Accept": "application/json",
            "User-Agent": "PixelMugCodex",
        },
    )
    if credentials.account_id:
        request.add_header("ChatGPT-Account-Id", credentials.account_id)

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code not in (401, 403) or not credentials.refresh_token:
            raise
        credentials = _refresh_credentials(credentials, auth_file)
        request.add_header("Authorization", f"Bearer {credentials.access_token}")
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))

    return _quota_from_usage_response(data)


def _load_credentials(auth_file: Path | None = None) -> _Credentials:
    path = auth_file or (_codex_home() / "auth.json")
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    api_key = str(data.get("OPENAI_API_KEY") or "").strip()
    if api_key:
        return _Credentials(access_token=api_key, source="api_key")
    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        raise ValueError("missing Codex auth tokens")
    access_token = str(tokens.get("access_token") or tokens.get("accessToken") or "").strip()
    if not access_token:
        raise ValueError("missing Codex access token")
    return _Credentials(
        access_token=access_token,
        refresh_token=str(tokens.get("refresh_token") or tokens.get("refreshToken") or "").strip(),
        account_id=str(tokens.get("account_id") or tokens.get("accountId") or "").strip() or None,
    )


def _refresh_credentials(credentials: _Credentials, auth_file: Path | None = None) -> _Credentials:
    if not credentials.refresh_token:
        return credentials
    body = json.dumps(
        {
            "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
            "grant_type": "refresh_token",
            "refresh_token": credentials.refresh_token,
            "scope": "openid profile email",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://auth.openai.com/oauth/token",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "PixelMugCodex"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    refreshed = _Credentials(
        access_token=str(data.get("access_token") or credentials.access_token),
        refresh_token=str(data.get("refresh_token") or credentials.refresh_token),
        account_id=str(data.get("account_id") or credentials.account_id or "") or None,
    )
    _save_refreshed_credentials(refreshed, auth_file)
    return refreshed


def _save_refreshed_credentials(credentials: _Credentials, auth_file: Path | None = None) -> None:
    path = auth_file or (_codex_home() / "auth.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
        tokens["access_token"] = credentials.access_token
        tokens["refresh_token"] = credentials.refresh_token
        if credentials.account_id:
            tokens["account_id"] = credentials.account_id
        data["tokens"] = tokens
        data["last_refresh"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def _usage_url(auth_file: Path | None = None) -> str:
    config = (auth_file or (_codex_home() / "auth.json")).parent / "config.toml"
    base = "https://chatgpt.com/backend-api"
    try:
        for raw_line in config.read_text(encoding="utf-8").splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line.startswith("chatgpt_base_url"):
                continue
            _, value = line.split("=", 1)
            base = value.strip().strip("'\"")
            break
    except (OSError, ValueError):
        pass
    base = base.rstrip("/")
    if base.startswith(("https://chatgpt.com", "https://chat.openai.com")) and "/backend-api" not in base:
        base += "/backend-api"
    path = "/wham/usage" if "/backend-api" in base else "/api/codex/usage"
    return base + path


def _quota_from_usage_response(data: dict[str, Any]) -> dict[str, CodexQuotaWindow]:
    """Normalize legacy HTTP and current app-server quota snapshots.

    Pro accounts may expose only the weekly window, so missing 5h data is
    intentionally left absent instead of being treated as zero.
    """
    rate_limit = data.get("rateLimits") or data.get("rate_limits") or data.get("rate_limit")
    if not isinstance(rate_limit, dict):
        return {}
    windows: list[dict[str, Any]] = []
    by_limit = data.get("rateLimitsByLimitId") or data.get("rate_limits_by_limit_id")
    if isinstance(by_limit, dict):
        for snapshot in by_limit.values():
            if isinstance(snapshot, dict):
                windows.append(snapshot)
    windows.append(rate_limit)
    found: dict[str, CodexQuotaWindow] = {}
    observed_at = datetime.now().astimezone()
    for snapshot in windows:
        candidates = (
            snapshot.get("primary"),
            snapshot.get("secondary"),
            snapshot.get("primary_window"),
            snapshot.get("secondary_window"),
        )
        for raw in candidates:
            window = _quota_window(raw, observed_at)
            if window is None:
                continue
            label = _window_label(window.window_minutes)
            if label and (label not in found or (window.observed_at or 0) >= (found[label].observed_at or 0)):
                found[label] = window
    return found


def _snapshot_from_totals(totals: dict[str, int], quota: dict[str, CodexQuotaWindow]) -> CodexUsageSnapshot:
    now = datetime.now().astimezone()
    today = now.date()

    def sum_days(days: int) -> int:
        start = today - timedelta(days=days - 1)
        return sum(tokens for day, tokens in totals.items() if start <= datetime.fromisoformat(day).date() <= today)

    five_hour = quota.get("5h")
    seven_day = quota.get("7d")
    return CodexUsageSnapshot(
        today_tokens=sum_days(1),
        week_tokens=sum_days(7),
        month_tokens=sum_days(30),
        quota_5h_remaining_percent=five_hour.remaining_percent if five_hour else None,
        quota_5h_used_percent=five_hour.used_percent if five_hour else None,
        quota_5h_resets_at=five_hour.resets_at if five_hour else None,
        quota_7d_remaining_percent=seven_day.remaining_percent if seven_day else None,
        quota_7d_used_percent=seven_day.used_percent if seven_day else None,
        quota_7d_resets_at=seven_day.resets_at if seven_day else None,
        updated_at=int(time.time()),
    )


def _carry_forward_quota(current: CodexUsageSnapshot, previous: CodexUsageSnapshot) -> CodexUsageSnapshot:
    if previous.updated_at <= 0:
        return current
    five_hour_remaining = current.quota_5h_remaining_percent
    five_hour_used = current.quota_5h_used_percent
    five_hour_reset = current.quota_5h_resets_at
    seven_day_remaining = current.quota_7d_remaining_percent
    seven_day_used = current.quota_7d_used_percent
    seven_day_reset = current.quota_7d_resets_at

    if five_hour_remaining is None:
        five_hour_remaining = previous.quota_5h_remaining_percent
        five_hour_used = previous.quota_5h_used_percent
        five_hour_reset = previous.quota_5h_resets_at
    if seven_day_remaining is None:
        seven_day_remaining = previous.quota_7d_remaining_percent
        seven_day_used = previous.quota_7d_used_percent
        seven_day_reset = previous.quota_7d_resets_at

    return CodexUsageSnapshot(
        today_tokens=current.today_tokens,
        week_tokens=current.week_tokens,
        month_tokens=current.month_tokens,
        quota_5h_remaining_percent=five_hour_remaining,
        quota_5h_used_percent=five_hour_used,
        quota_5h_resets_at=five_hour_reset,
        quota_7d_remaining_percent=seven_day_remaining,
        quota_7d_used_percent=seven_day_used,
        quota_7d_resets_at=seven_day_reset,
        updated_at=current.updated_at,
    )
