#!/bin/bash
# LeRobot Operator Console Setup Script
# Primary target: NVIDIA Jetson boards (JetPack)
# Also works on Ubuntu/Debian PCs

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

print_section() {
    echo ""
    echo "========================================="
    echo "$1"
    echo "========================================="
    echo ""
}

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Error: required command '$1' not found. Install it and re-run this script." >&2
        exit 1
    fi
}

is_jetson() {
    if [ "$(uname -m)" != "aarch64" ]; then
        return 1
    fi
    if [ -f /etc/nv_tegra_release ]; then
        return 0
    fi
    if grep -qi "jetson" /proc/device-tree/model 2>/dev/null; then
        return 0
    fi
    return 1
}

SUDO=""
if [ "${EUID}" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        echo "This script requires elevated privileges for system packages and udev rules."
        echo "Install 'sudo' or re-run as root." >&2
        exit 1
    fi
fi

print_section "LeRobot Operator Console Setup"

require_command python3

ARCH="$(uname -m)"
JETSON=0
if is_jetson; then
    JETSON=1
    echo "Detected NVIDIA Jetson platform (architecture: ${ARCH})"
else
    echo "Detected architecture: ${ARCH}"
fi

# System dependencies
if command -v apt-get >/dev/null 2>&1; then
    print_section "Installing system dependencies via apt-get"
    ${SUDO} apt-get update
    BASE_PACKAGES=(
        python3 python3-venv python3-pip python3-dev
        build-essential git cmake pkg-config
        libffi-dev libssl-dev libjpeg-dev zlib1g-dev
        libgl1 libegl1 libglib2.0-0
        libxkbcommon-x11-0 libxi6 libxtst6 libxrender1 libxext6 libsm6
        libxcb1 libxcb-render-util0 libxcb-shape0 libxcb-xfixes0
        libxcb-keysyms1 libxcb-icccm4 libxcb-image0 libxcb-randr0 libxcb-xinerama0
        ffmpeg
    )

    if [ "${JETSON}" -eq 1 ]; then
        EXTRA_JETSON_PACKAGES=(
            python3-opencv
            gstreamer1.0-tools
            gstreamer1.0-plugins-base
            gstreamer1.0-plugins-good
            gstreamer1.0-plugins-bad
            gstreamer1.0-libav
            v4l-utils
            libgtk-3-0
            libasound2 libpulse0
        )
        ${SUDO} apt-get install -y "${BASE_PACKAGES[@]}" "${EXTRA_JETSON_PACKAGES[@]}"
    else
        ${SUDO} apt-get install -y "${BASE_PACKAGES[@]}"
    fi
else
    echo "apt-get not found; skipping system package installation."
fi

print_section "Python virtual environment"
if [ ! -d ".venv" ]; then
    if [ "${JETSON}" -eq 1 ]; then
        echo "Creating virtual environment (with system site packages for Jetson)..."
        python3 -m venv .venv --system-site-packages
    else
        echo "Creating virtual environment..."
        python3 -m venv .venv
    fi
else
    echo "Virtual environment already exists."
fi

# shellcheck disable=SC1091
source .venv/bin/activate

print_section "Upgrading pip tooling"
python -m pip install --upgrade pip setuptools wheel

if [ "${JETSON}" -eq 1 ]; then
    print_section "Installing Jetson PyTorch wheels (best effort)"
    if ! python -c "import torch" >/dev/null 2>&1; then
        TORCH_INSTALLED=0
        for INDEX_URL in "https://pypi.nvidia.com" "https://pypi.ngc.nvidia.com"; do
            if pip install --extra-index-url "${INDEX_URL}" torch torchvision torchaudio; then
                TORCH_INSTALLED=1
                break
            fi
        done
        if [ "${TORCH_INSTALLED}" -eq 0 ]; then
            echo "Warning: Failed to install Jetson-optimised torch packages automatically." >&2
            echo "         Install the appropriate wheels manually if GPU acceleration is required." >&2
        fi
    else
        echo "PyTorch already available in the environment; skipping."
    fi
fi

print_section "Installing Python dependencies"
if [ "${JETSON}" -eq 1 ]; then
    TEMP_REQ="$(mktemp)"
    trap 'rm -f "${TEMP_REQ}"' EXIT
    if [ -f requirements.txt ]; then
        grep -v '^opencv-python' requirements.txt > "${TEMP_REQ}"
        pip install -r "${TEMP_REQ}"
    else
        echo "requirements.txt not found; skipping dependency installation." >&2
    fi
else
    if [ -f requirements.txt ]; then
        pip install -r requirements.txt
    else
        echo "requirements.txt not found; skipping dependency installation." >&2
    fi
fi

print_section "Applying udev rules (if available)"
if [ -d "udev" ] && [ -f "udev/99-so100.rules" ]; then
    ${SUDO} cp udev/99-so100.rules /etc/udev/rules.d/
    ${SUDO} udevadm control --reload-rules
    ${SUDO} udevadm trigger
    echo "✓ udev rules installed"
else
    echo "No udev rules to install."
fi

print_section "Configuring serial port access"
if command -v usermod >/dev/null 2>&1; then
    TARGET_USER="${SUDO_USER:-$USER}"
    ${SUDO} usermod -aG dialout "${TARGET_USER}"
    echo "✓ Added ${TARGET_USER} to dialout group"
else
    echo "usermod not available; please add your user to the 'dialout' group manually."
fi

print_section "Setup Complete"
echo "Python interpreter: $(which python)"
echo "Virtual environment: ${SCRIPT_DIR}/.venv"
echo ""
echo "IMPORTANT: Log out and back in (or reboot) so group membership changes take effect."
if [ "${JETSON}" -eq 1 ]; then
    echo "NOTE: Jetson users may need to reboot after installing new CUDA/PyTorch components."
fi
echo ""
echo "To run the application:"
echo "  source .venv/bin/activate"
echo "  python app.py"
echo ""
