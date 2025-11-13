"""Centralised helpers for choosing OpenCV camera backends."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional, Tuple

from utils.logging_utils import log_exception

try:  # Optional dependency - consumers should handle absence gracefully
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - OpenCV not installed on host
    cv2 = None  # type: ignore


BACKEND_ALIASES = {
    "gst": "gstreamer",
    "gstreamer": "gstreamer",
    "v4l2": "v4l2",
    "video4linux": "v4l2",
    "video4linux2": "v4l2",
    "ffmpeg": "ffmpeg",
}


def _normalize_backend(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    key = str(name).strip().lower()
    if not key or key in {"auto", "default", "any"}:
        return "default"
    return BACKEND_ALIASES.get(key, key)


@lru_cache(maxsize=1)
def _backend_flags() -> dict:
    flags = {}
    if cv2 is None:
        return flags
    flags["gstreamer"] = getattr(cv2, "CAP_GSTREAMER", None)
    flags["v4l2"] = getattr(cv2, "CAP_V4L2", None)
    flags["ffmpeg"] = getattr(cv2, "CAP_FFMPEG", None)
    return flags


def _backend_flag(name: Optional[str]) -> Optional[int]:
    if name is None or name == "default":
        return None
    return _backend_flags().get(name)


def build_backend_priority(preferred: Optional[str] = None) -> List[str]:
    order: List[str] = []

    def add(candidate: Optional[str]) -> None:
        normalized = _normalize_backend(candidate)
        if not normalized:
            return
        if normalized != "default" and _backend_flag(normalized) is None:
            return
        if normalized not in order:
            order.append(normalized)

    add(preferred)

    if os.name == "posix":
        add("v4l2")
        add("gstreamer")

    add("ffmpeg")
    add("default")
    return order


def open_capture(source, *, preferred_backend: Optional[str] = None) -> Tuple[Optional[str], Optional["cv2.VideoCapture"]]:
    """Open a ``cv2.VideoCapture`` with a consistent backend priority.

    Args:
        source: Camera index, path, or GStreamer pipeline.
        preferred_backend: Optional backend hint (``v4l2``, ``gstreamer``, ``ffmpeg``).

    Returns:
        ``(backend_name, capture)`` where ``backend_name`` is ``None`` when the
        default backend was used. When no backend succeeds, ``(None, None)`` is
        returned.
    """

    if cv2 is None:  # pragma: no cover - handled by callers
        return None, None

    for backend in build_backend_priority(preferred_backend):
        cap = None
        try:
            flag = _backend_flag(backend)
            if flag is None:
                cap = cv2.VideoCapture(source)
                backend_label = None
            else:
                cap = cv2.VideoCapture(source, flag)
                backend_label = backend
            if not cap or not cap.isOpened():
                if cap:
                    cap.release()
                continue
            return backend_label, cap
        except Exception as exc:  # pragma: no cover - depends on hardware
            log_exception("CameraBackend: backend open failed", exc, level="debug")
            if cap:
                cap.release()
    return None, None


__all__ = [
    "build_backend_priority",
    "open_capture",
]
