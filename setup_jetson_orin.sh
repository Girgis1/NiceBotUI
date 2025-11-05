#!/usr/bin/env bash
# Jetson Orin Nano first-time setup helper for LeRobot Operator Console
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

if ! command -v apt-get >/dev/null 2>&1; then
    echo "This script requires apt-get (Debian/Ubuntu/Jetson)." >&2
    exit 1
fi

if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
else
    SUDO=""
fi

if [[ "$(uname -m)" != "aarch64" ]]; then
    echo "[Warning] This setup script is intended for Jetson devices (aarch64)." >&2
fi

echo "========================================="
echo "LeRobot Operator Console - Jetson Setup"
echo "========================================="

APT_PACKAGES=(
    python3
    python3-dev
    python3-venv
    python3-pip
    build-essential
    git
    cmake
    pkg-config
    libffi-dev
    libssl-dev
    libjpeg-dev
    zlib1g-dev
    libgl1
    libglib2.0-0
    libsm6
    libxext6
    ffmpeg
)

echo "Updating apt package index..."
$SUDO apt-get update

echo "Installing required system packages..."
$SUDO apt-get install -y "${APT_PACKAGES[@]}"

echo ""
echo "Preparing Python virtual environment..."
if [[ ! -d .venv ]]; then
    python3 -m venv .venv
else
    echo "Virtual environment already exists at .venv"
fi

# shellcheck source=/dev/null
source .venv/bin/activate

pip install --upgrade pip wheel setuptools

detect_jetpack_series() {
    local nv_release
    if [[ -f /etc/nv_tegra_release ]]; then
        nv_release=$(</etc/nv_tegra_release)
        if [[ $nv_release =~ R([0-9]+) ]]; then
            echo "${BASH_REMATCH[1]}"
            return 0
        fi
    fi
    echo "" # Unknown
}

install_jetson_torch() {
    if python -c "import torch" >/dev/null 2>&1; then
        echo "PyTorch already installed, skipping Jetson wheel installation."
        return 0
    fi

    local jetpack_series
    jetpack_series=$(detect_jetpack_series)
    local -a candidate_sets=()

    # JetPack 6.x (L4T R36)
    if [[ $jetpack_series == "36" ]]; then
        candidate_sets+=("torch==2.3.0+nv24.05 torchvision==0.18.0+nv24.05 torchaudio==2.3.0+nv24.05")
        candidate_sets+=("torch==2.2.0+nv24.03 torchvision==0.17.0+nv24.03 torchaudio==2.2.0+nv24.03")
    fi

    # JetPack 5.x (L4T R35)
    candidate_sets+=("torch==2.1.0+nv23.06 torchvision==0.16.0+nv23.06 torchaudio==2.1.0+nv23.06")

    echo "Installing NVIDIA optimized PyTorch wheels for Jetson..."
    for combo in "${candidate_sets[@]}"; do
        read -r -a packages <<< "$combo"
        if pip install --extra-index-url https://pypi.ngc.nvidia.com "${packages[@]}"; then
            echo "✓ Installed PyTorch packages: ${packages[*]}"
            return 0
        fi
        echo "Attempt to install ${packages[*]} failed, trying next option..."
    done

    echo "Failed to install Jetson PyTorch packages automatically." >&2
    echo "Please install torch/torchvision/torchaudio manually for your JetPack version." >&2
    return 1
}

if [[ "$(uname -m)" == "aarch64" ]]; then
    if ! install_jetson_torch; then
        echo "PyTorch installation did not complete successfully." >&2
        echo "Resolve the issue above and rerun this script." >&2
        exit 1
    fi
fi

echo "Installing Python requirements (including LeRobot)..."
pip install --extra-index-url https://pypi.ngc.nvidia.com -r requirements.txt

echo ""
if [[ -d udev && -f udev/99-so100.rules ]]; then
    echo "Installing udev rules for serial port access..."
    $SUDO cp udev/99-so100.rules /etc/udev/rules.d/
    $SUDO udevadm control --reload-rules
    $SUDO udevadm trigger
    echo "✓ udev rules installed"
else
    echo "[Info] udev rules directory not found, skipping."
fi

target_user="${SUDO_USER:-$USER}"
if [[ -n $target_user ]]; then
    echo "Adding user '$target_user' to dialout group for serial access..."
    $SUDO usermod -aG dialout "$target_user"
    echo "✓ User added to dialout group"
fi

echo ""
echo "========================================="
echo "Jetson setup complete!"
echo "========================================="
echo "Log out/in for group changes to take effect."
echo "To run the app:"
echo "  source .venv/bin/activate"
echo "  python app.py"
echo ""
