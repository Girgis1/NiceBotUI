#!/bin/bash
# Helper script for logging on the Jetson
# Copy this to your Jetson: scp jetson_helpers.sh jetson:~/
# Then on Jetson: source ~/jetson_helpers.sh

# Create logs directory if it doesn't exist
mkdir -p ~/NiceBotUI/logs

# Function to run a command and log both to file and terminal
# Usage: run_logged "python app.py"
run_logged() {
    local timestamp=$(date +"%Y%m%d_%H%M%S")
    local logfile="$HOME/NiceBotUI/logs/jetson_${timestamp}.log"
    
    echo "📝 Logging to: $logfile"
    echo "🚀 Running: $@"
    echo ""
    echo "========================================" | tee -a "$logfile"
    echo "Started at: $(date)" | tee -a "$logfile"
    echo "Command: $@" | tee -a "$logfile"
    echo "========================================" | tee -a "$logfile"
    echo "" | tee -a "$logfile"
    
    # Run the command with output to both terminal and log file
    "$@" 2>&1 | tee -a "$logfile"
    
    local exit_code=${PIPESTATUS[0]}
    
    echo "" | tee -a "$logfile"
    echo "========================================" | tee -a "$logfile"
    echo "Finished at: $(date)" | tee -a "$logfile"
    echo "Exit code: $exit_code" | tee -a "$logfile"
    echo "========================================" | tee -a "$logfile"
    
    return $exit_code
}

# Function to tail the latest log
# Usage: tail_latest_log
tail_latest_log() {
    local latest_log=$(ls -t ~/NiceBotUI/logs/jetson_*.log 2>/dev/null | head -1)
    if [ -n "$latest_log" ]; then
        echo "📋 Tailing: $latest_log"
        tail -f "$latest_log"
    else
        echo "❌ No Jetson logs found"
    fi
}

# Function to list all logs
# Usage: list_logs
list_logs() {
    echo "📁 Available logs:"
    ls -lht ~/NiceBotUI/logs/*.log 2>/dev/null | head -20
}

echo "✅ Jetson helper functions loaded!"
echo ""
echo "Available commands:"
echo "  run_logged <command>  - Run command with logging"
echo "  tail_latest_log       - View the latest log in real-time"
echo "  list_logs             - List available log files"
echo ""
echo "Example: run_logged python app.py"

