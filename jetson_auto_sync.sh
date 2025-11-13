#!/bin/bash
# Jetson-side auto sync script.
# Copies runtime-generated assets (data, logs, runtime, calibration caches)
# back to the developer machine at a regular cadence (default: every 60s).
#
# Usage examples (run on the Jetson):
#   DEV_HOST=my-dev-pc ./jetson_auto_sync.sh          # loop forever
#   DEV_HOST=my-dev-pc ./jetson_auto_sync.sh --once   # single sync pass
#   DEV_HOST=my-dev-pc DEV_PATH=/work/NiceBotUI ./jetson_auto_sync.sh
#
# Requirements:
#   * Passwordless SSH from the Jetson to the dev machine (alias DEV_HOST)
#   * The repo checked out at ~/NiceBotUI on both machines (override via DEV_PATH)

set -euo pipefail

DEV_HOST="${DEV_HOST:-devpc}"
DEV_PATH="${DEV_PATH:-~/NiceBotUI}"
JETSON_REPO="${JETSON_REPO:-$HOME/NiceBotUI}"
SYNC_INTERVAL="${SYNC_INTERVAL:-60}"

REPO_FOLDERS=(
    "data"
    "logs"
    "runtime"
)

REPO_FILES=(
    "config.json"
)

HOME_FOLDERS=(
    ".cache/huggingface/lerobot/calibration"
    ".cache/huggingface/lerobot/local"
)

sync_repo_folder() {
    local rel="$1"
    local src="${JETSON_REPO}/${rel}"
    local dst="${DEV_HOST}:${DEV_PATH}/${rel}"
    if [[ ! -d "$src" ]]; then
        return
    fi
    rsync -az --delete "$src"/ "$dst"/
}

sync_repo_file() {
    local rel="$1"
    local src="${JETSON_REPO}/${rel}"
    local dst="${DEV_HOST}:${DEV_PATH}/${rel}"
    if [[ ! -f "$src" ]]; then
        return
    fi
    rsync -az "$src" "$dst"
}

sync_home_folder() {
    local rel="$1"
    local src="$HOME/${rel}"
    local dst="${DEV_HOST}:~/${rel}"
    if [[ ! -d "$src" ]]; then
        return
    fi
    rsync -az --delete "$src"/ "$dst"/
}

sync_once() {
    echo "🔄 Syncing Jetson assets to ${DEV_HOST}..."
    for folder in "${REPO_FOLDERS[@]}"; do
        sync_repo_folder "$folder"
    done
    for file in "${REPO_FILES[@]}"; do
        sync_repo_file "$file"
    done
    for folder in "${HOME_FOLDERS[@]}"; do
        sync_home_folder "$folder"
    done
    echo "✅ Sync completed at $(date)"
}

if [[ "${1:-}" == "--once" ]]; then
    sync_once
    exit 0
fi

while true; do
    sync_once
    sleep "$SYNC_INTERVAL"
done
