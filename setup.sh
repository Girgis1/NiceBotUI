#!/bin/bash
# LeRobot Operator Console Setup Script
# For Ubuntu/Debian/Jetson

set -e

echo "========================================="
echo "LeRobot Operator Console Setup"
echo "========================================="
echo ""

# Detect Jetson devices (JetPack exposes /etc/nv_tegra_release)
IS_JETSON=0
if [ -f /etc/nv_tegra_release ] || grep -qi "jetson" /proc/device-tree/model 2>/dev/null; then
    IS_JETSON=1
fi

# Install system dependencies when apt is available
if command -v apt-get >/dev/null 2>&1; then
    echo "Installing system packages (sudo password may be required)..."
    sudo apt-get update
    sudo apt-get install -y \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        build-essential \
        git \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        libxkbcommon-x11-0 \
        libxi6 \
        libxtst6 \
        libxrender1 \
        libxcb-render-util0 \
        libxcb-shape0 \
        libxcb-xfixes0 \
        libxcb1 \
        libxcb-keysyms1 \
        libxcb-icccm4 \
        libxcb-image0 \
        libxcb-randr0 \
        libxcb-xinerama0 \
        libegl1 \
        libopengl0

    if [ "$IS_JETSON" -eq 1 ]; then
        sudo apt-get install -y libatlas-base-dev gfortran
    fi
else
    echo "apt-get not found. Skipping system package installation."
fi

# Check Python version
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "Python version: $PYTHON_VERSION"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
else
    echo "Virtual environment already exists."
fi

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Upgrading pip and build tools..."
pip install --upgrade pip setuptools wheel

if [ "$IS_JETSON" -eq 1 ]; then
    echo "Detected NVIDIA Jetson platform. Adding NVIDIA Python wheels..."
    if [ -z "${PIP_EXTRA_INDEX_URL}" ]; then
        export PIP_EXTRA_INDEX_URL="https://pypi.ngc.nvidia.com"
    else
        export PIP_EXTRA_INDEX_URL="https://pypi.ngc.nvidia.com ${PIP_EXTRA_INDEX_URL}"
    fi
    pip install --upgrade --extra-index-url https://pypi.ngc.nvidia.com \
        torch torchvision torchaudio
fi

echo "Installing Python dependencies..."
pip install -r requirements.txt

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


