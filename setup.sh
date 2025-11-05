#!/bin/bash
# LeRobot Operator Console Setup Script
# For Ubuntu/Debian/Jetson

set -e

echo "========================================="
echo "LeRobot Operator Console Setup"
echo "========================================="
echo ""

# Platform detection (Jetson optimisation)
ARCH=$(uname -m)
IS_JETSON=0
if [ "$ARCH" = "aarch64" ] && { [ -f /etc/nv_tegra_release ] || grep -qi "jetson" /proc/device-tree/model 2>/dev/null; }; then
    IS_JETSON=1
    echo "Detected NVIDIA Jetson platform (architecture: $ARCH)"
    echo "Applying Jetson-specific dependency optimisations"
    echo ""
fi

# Check Python version
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "Python version: $PYTHON_VERSION"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    if [ "$IS_JETSON" -eq 1 ]; then
        python3 -m venv .venv --system-site-packages
    else
        python3 -m venv .venv
    fi
else
    echo "Virtual environment already exists."
fi

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Upgrading pip..."
pip install --upgrade pip

if [ "$IS_JETSON" -eq 1 ]; then
    echo ""
    echo "Installing system packages for OpenCV/GStreamer..."
    sudo apt-get update
    sudo apt-get install -y python3-opencv gstreamer1.0-tools gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav v4l-utils
fi

echo "Installing Python dependencies..."
REQ_FILE="requirements.txt"
if [ "$IS_JETSON" -eq 1 ]; then
    REQ_FILE="requirements-jetson.txt"
fi
pip install -r "$REQ_FILE"

if [ "$IS_JETSON" -eq 1 ]; then
    echo ""
    echo "Reminder: install the Jetson-optimised PyTorch build before running YOLO safety checks."
    echo "Example: pip install --extra-index-url https://developer.download.nvidia.com/compute/redist/jp/v60 torch torchvision torchaudio"
fi

# udev rules
if [ -d "udev" ] && [ -f "udev/99-so100.rules" ]; then
    echo ""
    echo "Installing udev rules for serial port access..."
    sudo cp udev/99-so100.rules /etc/udev/rules.d/
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    echo "✓ udev rules installed"
fi

# Add user to dialout group
echo ""
echo "Adding user to dialout group for serial access..."
sudo usermod -aG dialout $USER
echo "✓ User added to dialout group"

echo ""
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "IMPORTANT: Log out and back in for group changes to take effect."
echo ""
echo "To run the application:"
echo "  1. source .venv/bin/activate"
echo "  2. python app.py"
echo ""
echo "Or simply run:"
echo "  .venv/bin/python app.py"
echo ""


