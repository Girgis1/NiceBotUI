#!/bin/bash
# LeRobot Operator Console Setup Script
# Tested on Ubuntu 22.04 / JetPack 5.x for NVIDIA Jetson and standard x86 Ubuntu

set -euo pipefail

print_heading() {
    echo "========================================="
    echo "LeRobot Operator Console Setup"
    echo "========================================="
    echo ""
}

if [[ $EUID -eq 0 ]]; then
    SUDO=""
else
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        echo "This script requires root privileges or the sudo command."
        echo "Please run as root or install sudo."
        exit 1
    fi
fi

APT_PACKAGES=(
    "python3"
    "python3-venv"
    "python3-pip"
    "python3-dev"
    "git"
    "build-essential"
    "cmake"
    "pkg-config"
    "libffi-dev"
    "libssl-dev"
    "libjpeg-dev"
    "zlib1g-dev"
    "libopenblas-dev"
    "libatlas-base-dev"
    "liblapack-dev"
    "libgl1"
    "libegl1"
    "libglib2.0-0"
    "v4l-utils"
    "gstreamer1.0-tools"
    "gstreamer1.0-plugins-base"
    "gstreamer1.0-plugins-good"
)

JETSON=0
if [[ -f /etc/nv_tegra_release ]]; then
    JETSON=1
fi

print_heading

echo "Updating apt package index..."
${SUDO} apt-get update

echo "Installing system dependencies..."
${SUDO} apt-get install -y "${APT_PACKAGES[@]}"

if [[ $JETSON -eq 1 ]]; then
    echo "Detected NVIDIA Jetson platform."
    # Jetson wheels are provided through NVIDIA's extra index. We set this up for the current shell.
    export PIP_EXTRA_INDEX_URL="https://developer.download.nvidia.com/compute/redist/jp/v51"
    echo "Configured NVIDIA Python wheel index: $PIP_EXTRA_INDEX_URL"
fi

PYTHON_VERSION=$(python3 --version 2>/dev/null | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "Python version: ${PYTHON_VERSION:-unknown}"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
else
    echo "Virtual environment already exists."
fi

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Upgrading pip, setuptools, and wheel..."
python -m pip install --upgrade pip setuptools wheel

if [[ $JETSON -eq 1 ]]; then
    echo "Ensuring Jetson-compatible PyTorch is installed..."
    python - <<'PYTORCH'
import importlib
import subprocess
import sys

def has_package(name):
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False

required = {
    "torch": "torch",
    "torchvision": "torchvision",
}

packages_to_install = [pkg for pkg in required.values() if not has_package(pkg)]

if packages_to_install:
    subprocess.check_call([
        sys.executable,
        "-m",
        "pip",
        "install",
        "--extra-index-url",
        "https://developer.download.nvidia.com/compute/redist/jp/v51",
        *packages_to_install,
    ])
PYTORCH
fi

echo "Installing Python dependencies (including LeRobot)..."
pip install -r requirements.txt

if [[ $JETSON -eq 1 ]]; then
    echo "Installing Jetson multimedia Python bindings if missing..."
    python - <<'JETSON'
import importlib
import importlib.util
import subprocess
import sys

optional_packages = [
    ("pycuda", "pycuda"),
    ("jetson_utils", "jetson-utils"),
]

to_install = [pkg for module, pkg in optional_packages if importlib.util.find_spec(module) is None]

if to_install:
    subprocess.check_call([sys.executable, "-m", "pip", "install", *to_install])
JETSON
fi

# udev rules
if [ -d "udev" ] && [ -f "udev/99-so100.rules" ]; then
    echo ""
    echo "Installing udev rules for serial port access..."
    ${SUDO} cp udev/99-so100.rules /etc/udev/rules.d/
    ${SUDO} udevadm control --reload-rules
    ${SUDO} udevadm trigger
    echo "✓ udev rules installed"
fi

# Add user to dialout group
echo ""
echo "Adding user to dialout group for serial access..."
${SUDO} usermod -aG dialout "$USER"
echo "✓ User added to dialout group"

echo ""
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "IMPORTANT: Log out and back in for group changes to take effect."
if [[ $JETSON -eq 1 ]]; then
    echo "NOTE: On Jetson devices a reboot is recommended after installing new CUDA/PyTorch wheels."
fi
echo ""
echo "To run the application:"
echo "  1. source .venv/bin/activate"
echo "  2. python app.py"
echo ""
echo "Or simply run:"
echo "  .venv/bin/python app.py"
echo ""


