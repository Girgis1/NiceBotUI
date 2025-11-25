#!/bin/bash
# Quick launcher for motor dropout diagnostics on Jetson
# Usage: ./start_motor_diagnostics.sh [duration_in_seconds]

cd "$(dirname "$0")/.."

# Check if running on Jetson (look for tegrastats)
if ! command -v tegrastats &> /dev/null; then
    echo "⚠️  Warning: tegrastats not found. Are you running on the Jetson?"
    echo "   Power monitoring will be disabled."
    echo ""
fi

# Check for sudo (needed for dmesg -w)
if ! sudo -n true 2>/dev/null; then
    echo "🔐 This script needs sudo access for dmesg monitoring"
    echo "   You may be prompted for your password..."
    echo ""
fi

DURATION=""
if [ -n "$1" ]; then
    DURATION="--duration $1"
    echo "⏱️  Running diagnostics for $1 seconds"
else
    echo "⏱️  Running diagnostics until Ctrl+C"
fi

echo ""
echo "🎯 Motor Dropout Diagnostics"
echo "================================"
echo ""
echo "This tool will monitor:"
echo "  • USB device connects/disconnects"
echo "  • System power consumption"
echo "  • Motor controller ports (/dev/ttyACM*)"
echo ""
echo "When you see the motor dropout:"
echo "  1. Note the time"
echo "  2. Let it run for ~30 more seconds"
echo "  3. Press Ctrl+C"
echo "  4. Check the log file shown at the end"
echo ""
echo "================================"
echo ""

# Run with sudo for dmesg access
sudo python3 tools/motor_dropout_diagnostics.py $DURATION --log-dir logs

echo ""
echo "✅ Diagnostics complete!"
echo ""
echo "To view the log locally, run:"
echo "  ./sync_from_jetson.sh --logs-only"
echo "  cat logs/motor_dropout_diag_*.log | less"

