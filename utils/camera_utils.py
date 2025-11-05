"""Utilities for camera source normalisation and backend selection."""

from __future__ import annotations

from typing import Optional, Tuple, Union

try:  # Optional dependency (import mirrors other modules)
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - handled gracefully by callers
    cv2 = None  # type: ignore

CameraIdentifier = Union[int, str]


def _is_gstreamer_pipeline(identifier: str) -> bool:
    """Heuristically determine whether a source string is a GStreamer pipeline."""
    lowered = identifier.strip().lower()
    if not lowered:
        return False

    if "nvarguscamerasrc" in lowered:
        return True
    if " appsink" in lowered or "!" in identifier:
        return True
    if lowered.startswith(("rtsp://", "rtsps://", "rtmp://", "http://", "https://")):
        return True
    return False


def normalize_identifier(identifier: CameraIdentifier) -> CameraIdentifier:
    """Convert numeric strings to integers while leaving other sources untouched."""
    if isinstance(identifier, str):
        stripped = identifier.strip()
        if stripped.isdigit():
            try:
                return int(stripped)
            except ValueError:
                return stripped
        return stripped
    return identifier


def select_capture_source(identifier: CameraIdentifier) -> Tuple[CameraIdentifier, Optional[int]]:
    """Return a normalised identifier and the preferred OpenCV backend."""
    normalized = normalize_identifier(identifier)

    if cv2 is None:  # pragma: no cover - consumers guard against missing cv2
        return normalized, None

    if isinstance(normalized, int):
        return normalized, cv2.CAP_V4L2

    backend = cv2.CAP_ANY
    if isinstance(normalized, str) and _is_gstreamer_pipeline(normalized):
        backend = cv2.CAP_GSTREAMER

    return normalized, backend


def configure_low_latency(capture: "cv2.VideoCapture") -> None:  # type: ignore[name-defined]
    """Apply best-effort low-latency settings to a VideoCapture handle."""
    if cv2 is None or capture is None:  # pragma: no cover - guard rails
        return

    for prop in (getattr(cv2, "CAP_PROP_BUFFERSIZE", None), getattr(cv2, "CAP_PROP_FRAME_BUFFER_SIZE", None)):
        if prop is None:
            continue
        try:
            capture.set(prop, 1)
        except Exception:
            continue
