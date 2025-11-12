#!/bin/bash
# Sync LerobotGUI to Nvidia Jetson
# Usage: ./sync_to_jetson.sh [--dry-run]

# Directories/files that should never be pushed from the dev machine
# (they are generated on the Jetson and synced back separately).
JETSON_OWNED=(
    "data/"
    "logs/"
    "runtime/"
    ".cache/"
)

EXCLUDE_PATTERNS=(
    ".venv"
    "__pycache__"
    "*.pyc"
    ".git"
    "*.log"
    ".DS_Store"
    "node_modules"
    "${JETSON_OWNED[@]}"
)

# Build exclude arguments
EXCLUDE_ARGS=""
for pattern in "${EXCLUDE_PATTERNS[@]}"; do
    EXCLUDE_ARGS="$EXCLUDE_ARGS --exclude='$pattern'"
done

# Check for dry-run flag
DRY_RUN=""
if [[ "$1" == "--dry-run" ]]; then
    DRY_RUN="-n"
    echo "🔍 DRY RUN MODE - No files will be transferred"
    echo ""
fi

# Show what we're doing
echo "📦 Syncing NiceBotUI to Jetson..."
echo "Source: ~/NiceBotUI/"
echo "Destination: jetson:~/NiceBotUI/"
echo ""

# Run rsync
eval rsync -avz $DRY_RUN $EXCLUDE_ARGS ~/NiceBotUI/ jetson:~/NiceBotUI/

echo ""
echo "✅ Sync complete!"
