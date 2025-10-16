#!/bin/bash
# Robot Control Kiosk Startup Script
# Verifies dependencies and launches kiosk mode

set -e

echo "================================"
echo "Robot Control Kiosk"
echo "================================"
echo ""

# Check if virtual environment exists
if [ -d ".venv" ]; then
    echo "✓ Found virtual environment"
    source .venv/bin/activate
else
    echo "⚠ No virtual environment found"
    echo "  Run ./setup.sh first"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
echo "✓ Python $PYTHON_VERSION"

# Check for PySide6
if python -c "import PySide6" 2>/dev/null; then
    echo "✓ PySide6 installed"
else
    echo "✗ PySide6 not found"
    echo "  Installing PySide6..."
    pip install PySide6
fi

# Check for OpenCV
if python -c "import cv2" 2>/dev/null; then
    echo "✓ OpenCV installed"
else
    echo "⚠ OpenCV not found (camera detection disabled)"
fi

# Check for config file
if [ -f "config.json" ]; then
    echo "✓ Configuration file found"
else
    echo "⚠ No config.json found (will create default)"
fi

echo ""
echo "Starting kiosk mode..."
echo "Press Escape, Ctrl+Q, or Alt+F4 to exit"
echo ""

# Parse arguments
ARGS=""
if [ "$1" == "--windowed" ] || [ "$1" == "-w" ]; then
    ARGS="--windowed"
    echo "Running in windowed mode"
else
    echo "Running in fullscreen mode"
fi

# Launch NiceBot
python NiceBot.py $ARGS


