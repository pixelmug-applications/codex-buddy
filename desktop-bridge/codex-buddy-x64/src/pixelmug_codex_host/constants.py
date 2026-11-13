APP_NAME = "PixelMug Codex"
APP_ID = "PixelMugCodex"
APP_VERSION = "0.2.0"
HOOK_ID = "pixelmug-codex"
HOOK_STATUS_MESSAGE = "PixelMug Codex"

PROTOCOL_VERSION = 1
LOCAL_HOST = "127.0.0.1"
LOCAL_HOOK_PORT = 39216
STATUS_PORT = 39217
PAIR_PORT = 39218

PAIR_MESSAGE_TYPE = "pixelmug_pair"
STATUS_MESSAGE_TYPE = "pixelmug_codex_status"
LOCAL_MESSAGE_TYPE = "pixelmug_codex_local"
CONTROL_MESSAGE_TYPE = "pixelmug_codex_control"

BROADCAST_ADDR = "255.255.255.255"
PAIR_TTL_SECONDS = 60
DISCOVER_TIMEOUT_SEC = 10.0
PAIR_TIMEOUT_SEC = 10.0
UDP_PACKET_MAX = 1024
TEXT_MAX_LEN = 64
CODEX_HOOK_TIMEOUT_SEC = 10

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

RUN_REG_NAME = "PixelMugCodexBridge"
LOG_FILE_NAME = "bridge.log"
HOOK_LOG_FILE_NAME = "hook.log"
CONFIG_FILE_NAME = "config.json"
