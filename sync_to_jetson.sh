#!/bin/bash
# Sync NiceBotUI to the Nvidia Jetson without clobbering its runtime configs.
# Usage: ./sync_to_jetson.sh [--dry-run] [--push-config] [--skip-config-pull]

set -euo pipefail

DEV_REPO="${DEV_REPO:-$HOME/NiceBotUI}"
JETSON_HOST="${JETSON_HOST:-jetson}"
JETSON_PATH="${JETSON_PATH:-~/NiceBotUI}"
JETSON_TARGET="${JETSON_HOST}:${JETSON_PATH}"

# Directories that are considered Jetson-owned (generated on-device).
JETSON_OWNED_DIRS=(
    "data/"
    "logs/"
    "runtime/"
    ".cache/"
)

# Individual files that should stay owned by the Jetson unless explicitly pushed.
JETSON_STATE_FILES=(
    "config.json"
)

EXCLUDE_PATTERNS=(
    ".venv"
    "__pycache__"
    "*.pyc"
    ".git"
    "*.log"
    ".DS_Store"
    "node_modules"
    "${JETSON_OWNED_DIRS[@]}"
)

usage() {
    cat <<'EOF'
Usage: ./sync_to_jetson.sh [options]

Options:
  --dry-run            Show what would change without transferring files
  --push-config        Upload Jetson-owned config files (overwrites Jetson copy)
  --skip-config-pull   Do not pull Jetson configs back after pushing code
  -h, --help           Show this help text
EOF
}

DRY_RUN=false
PUSH_CONFIG=false
PULL_CONFIG=true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            ;;
        --push-config)
            PUSH_CONFIG=true
            ;;
        --skip-config-pull)
            PULL_CONFIG=false
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo ""
            usage
            exit 1
            ;;
    esac
    shift
done

if [[ "$PUSH_CONFIG" == true ]]; then
    # If we intentionally push configs, no need to pull them back right away.
    PULL_CONFIG=false
fi

RSYNC_ARGS=(-avz)
PULL_ARGS=(-avz)

if [[ "$DRY_RUN" == true ]]; then
    echo "🔍 DRY RUN MODE - No files will be transferred"
    echo ""
    RSYNC_ARGS+=(-n)
    PULL_ARGS+=(-n)
fi

for pattern in "${EXCLUDE_PATTERNS[@]}"; do
    RSYNC_ARGS+=(--exclude="$pattern")
done

if [[ "$PUSH_CONFIG" != true ]]; then
    for file in "${JETSON_STATE_FILES[@]}"; do
        RSYNC_ARGS+=(--exclude="$file")
    done
fi

echo "📦 Syncing NiceBotUI to Jetson..."
echo "Source: ${DEV_REPO}/"
echo "Destination: ${JETSON_TARGET}/"
echo ""

pull_state_files() {
    [[ "${#JETSON_STATE_FILES[@]}" -eq 0 ]] && return

    echo ""
    echo "🔄 Pulling Jetson-managed config files back to local workspace..."
    for file in "${JETSON_STATE_FILES[@]}"; do
        rsync "${PULL_ARGS[@]}" --ignore-missing-args \
            "${JETSON_HOST}:${JETSON_PATH%/}/$file" "${DEV_REPO%/}/$file"
    done
}

rsync "${RSYNC_ARGS[@]}" "${DEV_REPO}/" "${JETSON_TARGET}/"

if [[ "$PULL_CONFIG" == true ]]; then
    pull_state_files
fi

echo ""
echo "✅ Sync complete!"
