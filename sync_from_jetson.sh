#!/bin/bash
# Sync LerobotGUI from Nvidia Jetson back to local
# Usage: ./sync_from_jetson.sh [--dry-run] [--logs-only]

EXCLUDE_PATTERNS=(
    ".venv"
    "__pycache__"
    "*.pyc"
    ".git"
    ".DS_Store"
    "node_modules"
)

# Build exclude arguments
EXCLUDE_ARGS=""
for pattern in "${EXCLUDE_PATTERNS[@]}"; do
    EXCLUDE_ARGS="$EXCLUDE_ARGS --exclude='$pattern'"
done

# Check for flags
DRY_RUN=""
LOGS_ONLY=""
for arg in "$@"; do
    case $arg in
        --dry-run)
            DRY_RUN="-n"
            echo "🔍 DRY RUN MODE - No files will be transferred"
            echo ""
            ;;
        --logs-only)
            LOGS_ONLY="true"
            ;;
    esac
done

# Show what we're doing
if [[ "$LOGS_ONLY" == "true" ]]; then
    echo "📋 Syncing LOGS ONLY from Jetson..."
    echo "Source: jetson:~/NiceBotUI/logs/"
    echo "Destination: ~/NiceBotUI/logs/"
    echo ""
    rsync -avz $DRY_RUN jetson:~/NiceBotUI/logs/ ~/NiceBotUI/logs/
else
    echo "📦 Syncing NiceBotUI from Jetson..."
    echo "Source: jetson:~/NiceBotUI/"
    echo "Destination: ~/NiceBotUI/"
    echo ""
    eval rsync -avz $DRY_RUN $EXCLUDE_ARGS jetson:~/NiceBotUI/ ~/NiceBotUI/
fi

echo ""
echo "✅ Sync complete!"
