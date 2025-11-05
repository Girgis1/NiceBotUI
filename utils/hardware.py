"""Helpers for detecting available hardware accelerators.

The Jetson builds often ship with CUDA-capable GPUs, but the application
previously defaulted to CPU inference unless the user manually edited the
configuration.  These helpers centralise the detection logic so that other
modules can request a best-effort torch device without duplicating checks or
crashing when CUDA is unavailable.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple


@lru_cache(maxsize=1)
def _cuda_available() -> bool:
    """Return True if a CUDA device is available via PyTorch."""
    try:
        import torch  # type: ignore

        return torch.cuda.is_available()
    except Exception:
        return False


@lru_cache(maxsize=1)
def running_on_jetson() -> bool:
    """Best-effort detection for NVIDIA Jetson hardware."""
    possible_paths = (
        Path("/sys/firmware/devicetree/base/model"),
        Path("/proc/device-tree/model"),
    )

    for path in possible_paths:
        try:
            if path.exists():
                contents = path.read_text(errors="ignore").lower()
                if "jetson" in contents:
                    return True
        except Exception:
            continue
    return False


def resolve_torch_device(configured: Optional[str]) -> Tuple[str, Optional[str]]:
    """Resolve a user-configured torch device string with safe fallbacks.

    Args:
        configured: Device string from configuration (e.g. "cuda", "cpu", "auto").

    Returns:
        Tuple of (device, warning). Warning is None when no fallback occurred.
    """

    normalized = (configured or "").strip().lower()

    # Auto-detect when not specified or explicitly requested.
    if not normalized or normalized in {"auto", "autodetect", "detect", "gpu"}:
        return ("cuda" if _cuda_available() else "cpu", None)

    # Allow explicit CUDA device declarations, but fall back safely when unavailable.
    if normalized.startswith("cuda"):
        if _cuda_available():
            return ((configured or "cuda").strip(), None)
        return ("cpu", "CUDA requested but no CUDA runtime detected; falling back to CPU.")

    # Honour explicit CPU requests.
    if normalized == "cpu":
        return ("cpu", None)

    # Pass through other device identifiers untouched (e.g. "mps")
    # with best-effort CUDA fallback when appropriate.
    if normalized.startswith("gpu"):
        if _cuda_available():
            return ("cuda", None)
        return ("cpu", "GPU requested but CUDA runtime unavailable; using CPU instead.")

    return ((configured or "cpu").strip(), None)
