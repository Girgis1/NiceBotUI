#!/bin/bash
# NiceBot UI Launcher Script

cd ~/NiceBotUI

# Create logs directory if it doesn't exist
mkdir -p logs

# Log file with timestamp
LOGFILE="logs/nicebot_$(date +%Y%m%d_%H%M%S).log"

# Print startup message
echo "Starting NiceBot UI..." | tee $LOGFILE
echo "Log file: $LOGFILE" | tee -a $LOGFILE
echo "" | tee -a $LOGFILE

# Run the app and log output
python3 app.py 2>&1 | tee -a $LOGFILE
