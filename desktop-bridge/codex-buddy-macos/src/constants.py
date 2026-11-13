"""Shared constants for PixelMug Codex host integration."""

APP_NAME = "PixelMugCodex"
DISPLAY_NAME = "PixelMug Codex"
BUNDLE_ID = "com.pixelmug.codex"
LAUNCH_AGENT_ID = "com.pixelmug.codex.bridge"

PROTOCOL_VERSION = 1
LOCAL_HOST = "127.0.0.1"
LOCAL_HOOK_PORT = 39216
PIXELMUG_STATUS_PORT = 39217
PIXELMUG_PAIR_PORT = 39218
BROADCAST_ADDR = "255.255.255.255"

MAX_TEXT_CHARS = 64
MAX_UDP_PACKET_BYTES = 1024
DEFAULT_PAIR_TTL_SEC = 60
DISCOVER_TIMEOUT_SEC = 10.0
PAIR_TIMEOUT_SEC = 10.0
STATUS_IDLE_TIMEOUT_SEC = 60
CODEX_HOOK_TIMEOUT_SEC = 10

LOCAL_MSG_TYPE = "pixelmug_codex_local"
CONTROL_MSG_TYPE = "pixelmug_codex_control"
PAIR_MSG_TYPE = "pixelmug_pair"
STATUS_MSG_TYPE = "pixelmug_codex_status"

HOOK_ID = "pixelmug-codex"
HOOK_STATUS_MESSAGE = "PixelMug Codex"

SUPPORTED_HOOK_EVENTS = (
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PreCompact",
    "PostCompact",
    "SubagentStart",
    "SubagentStop",
    "Stop",
)

TOOL_MATCHER = "Bash|functions.exec_command|apply_patch"
