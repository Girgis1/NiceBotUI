#!/usr/bin/env bash
# Turn a clean Ubuntu box into a ready-to-run NiceBot UI workstation.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

info() { printf "\033[1;32m[INFO]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[WARN]\033[0m %s\n" "$*"; }
err() { printf "\033[1;31m[ERR ]\033[0m %s\n" "$*"; }

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        err "Missing required command '$1'. Install it and re-run this script."
        exit 1
    fi
}

if [[ $(id -u) -eq 0 ]]; then
    SUDO=""
else
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        err "This script needs to install system packages. Please install sudo or run as root."
        exit 1
    fi
fi

if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    if [[ ${ID} != "ubuntu" && ${ID_LIKE:-} != *"ubuntu"* ]]; then
        warn "This script targets Ubuntu. Detected '${NAME}'. Proceeding anyway."
    fi
else
    warn "Cannot detect OS. Assuming Ubuntu-compatible system."
fi

APT_PKGS=(
    python3
    python3-venv
    python3-pip
    git
    build-essential
    libopencv-dev
    libatlas-base-dev
    libv4l-dev
    v4l-utils
    ffmpeg
    pkg-config
)

info "Updating apt package index..."
$SUDO apt-get update -y
info "Installing system dependencies..."
$SUDO apt-get install -y "${APT_PKGS[@]}"

DIALOUT_NOTICE="false"
if ! id -nG "$USER" | tr ' ' '\n' | grep -qx "dialout"; then
    info "Adding '$USER' to dialout group for serial access..."
    $SUDO usermod -aG dialout "$USER"
    DIALOUT_NOTICE="true"
fi

VENV_DIR="${REPO_ROOT}/.venv"
if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating Python virtual environment (.venv)..."
    python3 -m venv "$VENV_DIR"
else
    info "Reusing existing virtual environment (.venv)."
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip setuptools wheel >/dev/null
info "Installing Python dependencies (this can take a few minutes)..."
pip install --upgrade -r requirements.txt

info "Stamping default config (config.json)..."
python3 - <<'PY'
from app.config import load_config
load_config()
PY

deactivate >/dev/null || true

info "All set!"
printf "\nNext steps:\n"
printf "  1. %s\n" "${VENV_DIR}/bin/python app.py --windowed  # start the UI"
if [[ "$DIALOUT_NOTICE" == "true" ]]; then
    printf "  2. Log out and back in so the new dialout permissions take effect.\n"
fi
printf "\nHappy robotics!\n"
