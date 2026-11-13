#!/usr/bin/env bash
set -euo pipefail

DELETE_CONFIG=""
DELETE_LOGS=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --delete-config) DELETE_CONFIG="--delete-config" ;;
    --delete-logs) DELETE_LOGS="--delete-logs" ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

if [[ -x /usr/local/bin/pixelmug-codex ]]; then
  /usr/local/bin/pixelmug-codex uninstall $DELETE_CONFIG $DELETE_LOGS || true
fi

sudo rm -rf "/Applications/PixelMug Codex.app"
sudo rm -f /usr/local/bin/pixelmug-codex

echo "PixelMug Codex program files removed. Pairing config/logs are kept unless you passed --delete-config/--delete-logs."
