#!/bin/bash
# Jetson-specific installer for the LeRobot Operator Console

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "${SCRIPT_DIR}"

section() {
    echo ""
    echo "========================================="
    echo "$1"
    echo "========================================="
    echo ""
}

JETSON_DETECTED=false
if [[ -f /etc/nv_tegra_release ]] && [[ "$(uname -m)" == "aarch64" ]]; then
    JETSON_DETECTED=true
fi

if [[ "${JETSON_OVERRIDE:-}" == "1" ]]; then
    JETSON_DETECTED=true
fi

if [[ "${JETSON_DETECTED}" != "true" ]]; then
    echo "This installer is intended for NVIDIA Jetson devices running JetPack."
    echo "Run ./setup.sh for non-Jetson environments."
    exit 1
fi

if [[ ${EUID} -eq 0 ]]; then
    echo "Please run this script as a regular user with sudo privileges, not as root."
    exit 1
fi

if ! command -v sudo >/dev/null 2>&1; then
    echo "sudo is required to install system packages."
    exit 1
fi

section "Detected Jetson Environment"
cat /etc/nv_tegra_release

section "Installing system dependencies via apt"
if ! command -v apt-get >/dev/null 2>&1; then
    echo "apt-get not found. This script expects Ubuntu-based JetPack."
    exit 1
fi

sudo apt-get update
sudo apt-get install -y \
    python3-venv \
    python3-pip \
    git \
    build-essential \
    pkg-config \
    libffi-dev \
    libssl-dev \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libfontconfig1 \
    libxkbcommon-x11-0 \
    libgtk-3-0 \
    libasound2-dev \
    libpulse0 \
    ffmpeg \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-good \
    gstreamer1.0-libav \
    curl \
    wget \
    python3-opencv

section "Creating Python virtual environment"
if [ ! -d ".venv" ]; then
    python3 -m venv --system-site-packages .venv
else
    echo "Virtual environment already exists."
    if [ -f ".venv/pyvenv.cfg" ] && ! grep -q "^include-system-site-packages = true" .venv/pyvenv.cfg; then
        echo "Enabling access to system site-packages (needed for python3-opencv)..."
        sed -i 's/include-system-site-packages = false/include-system-site-packages = true/' .venv/pyvenv.cfg || true
        if ! grep -q "^include-system-site-packages = true" .venv/pyvenv.cfg; then
            echo "include-system-site-packages = true" >> .venv/pyvenv.cfg
        fi
    fi
fi

source .venv/bin/activate

section "Upgrading pip"
pip install --upgrade pip setuptools wheel

# Jetson PyTorch wheels come from NVIDIA's index.
TORCH_INDEX_URL=${TORCH_INDEX_URL:-https://developer.download.nvidia.com/compute/redist/jp/v512}
TORCH_VERSION=${TORCH_VERSION:-2.1.0+nv23.10}
TORCHVISION_VERSION=${TORCHVISION_VERSION:-0.16.0+nv23.10}
TORCHAUDIO_VERSION=${TORCHAUDIO_VERSION:-2.1.0+nv23.10}

section "Installing PyTorch from NVIDIA"
export PIP_EXTRA_INDEX_URL="${TORCH_INDEX_URL}"

pip install --extra-index-url "${TORCH_INDEX_URL}" "torch==${TORCH_VERSION}"
pip install --extra-index-url "${TORCH_INDEX_URL}" "torchvision==${TORCHVISION_VERSION}"
if ! pip install --extra-index-url "${TORCH_INDEX_URL}" "torchaudio==${TORCHAUDIO_VERSION}"; then
    echo "torchaudio wheel not available for this JetPack release. Continuing without it."
fi

section "Installing Python dependencies"
TEMP_REQ=$(mktemp)
trap 'rm -f "${TEMP_REQ}"' EXIT
# Use system OpenCV instead of attempting to build the wheel on aarch64.
grep -v '^opencv-python' requirements.txt > "${TEMP_REQ}"
pip install -r "${TEMP_REQ}"

if ! python - <<'PY'
import cv2
print("Detected OpenCV version:", cv2.__version__)
PY
then
    echo "Failed to import OpenCV inside the virtual environment."
    echo "Ensure python3-opencv is installed and rerun this script."
    exit 1
fi

section "Installing udev rules"
if [ -d "udev" ] && [ -f "udev/99-so100.rules" ]; then
    sudo cp udev/99-so100.rules /etc/udev/rules.d/
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    echo "✓ udev rules installed"
else
    echo "No udev rules directory found; skipping."
fi

section "Adding user to dialout group"
sudo usermod -aG dialout "$USER"

echo ""
echo "Setup complete! Log out and back in for group changes to take effect."
echo "To start the console:"
echo "  source .venv/bin/activate"
echo "  python app.py"
echo ""
