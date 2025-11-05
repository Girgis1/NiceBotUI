"""Platform detection helpers for runtime optimizations."""

from __future__ import annotations

import functools
import platform
from pathlib import Path


@functools.lru_cache(maxsize=1)
def is_jetson() -> bool:
    """Return True when running on an NVIDIA Jetson platform."""
    if platform.system() != "Linux":
        return False

    # `/etc/nv_tegra_release` exists on Jetson platforms.
    if Path("/etc/nv_tegra_release").exists():
        return True

    # Older releases expose the board name in the device tree model string.
    try:
        model_path = Path("/proc/device-tree/model")
        if model_path.exists():
            model = model_path.read_text(errors="ignore")
            return "NVIDIA Jetson" in model
    except OSError:
        pass

    return False


__all__ = ["is_jetson"]
