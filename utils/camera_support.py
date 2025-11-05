"""Utilities for platform-aware camera configuration.

This module centralises logic for picking the optimal OpenCV backend on
platforms such as NVIDIA Jetson boards where GStreamer pipelines are common.
All helpers are lightweight and avoid importing OpenCV so they can be used in
modules that are imported before optional dependencies are available.
"""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

CameraSource = Union[int, str]


def is_jetson_platform() -> bool:
    """Return ``True`` when running on a NVIDIA Jetson device."""

    machine = platform.machine().lower()
    if machine not in {"aarch64", "armv8", "arm64"}:
        return False

    if Path("/etc/nv_tegra_release").exists():
        return True

    try:
        model_path = Path("/sys/firmware/devicetree/base/model")
        if model_path.exists():
            contents = model_path.read_text(errors="ignore").lower()
            if "nvidia jetson" in contents:
                return True
    except Exception:
        # Access can fail inside containers; fall back to False.
        pass

    return False


def coerce_backend(value: Optional[str]) -> Optional[str]:
    """Normalise backend names to the variants understood by OpenCV."""

    if value is None:
        return None

    normalized = str(value).strip().lower()
    if not normalized or normalized in {"auto", "default", "any"}:
        return None
    if normalized in {"gstreamer", "gst"}:
        return "gstreamer"
    if normalized in {"v4l2", "video4linux", "video4linux2"}:
        return "v4l2"
    if normalized == "ffmpeg":
        return "ffmpeg"
    return normalized


def looks_like_gstreamer_pipeline(source: CameraSource) -> bool:
    """Best-effort heuristic to detect GStreamer pipeline strings."""

    if not isinstance(source, str):
        return False

    pipeline = source.strip().lower()
    if not pipeline:
        return False

    if pipeline.startswith((
        "nvarguscamerasrc",
        "v4l2src",
        "rtspsrc",
        "udpsrc",
        "filesrc",
        "appsrc",
    )):
        return True

    if pipeline.startswith(("rtsp://", "http://", "https://", "file://")):
        return True

    return " ! " in pipeline


def _normalize_source_type(source: CameraSource) -> CameraSource:
    if isinstance(source, str):
        stripped = source.strip()
        if stripped and stripped.isdigit():
            return int(stripped)
    return source


def build_jetson_csi_pipeline(sensor_id: int, width: int, height: int, fps: int) -> str:
    """Construct a GStreamer pipeline for Jetson CSI cameras."""

    width = max(1, int(width) if width else 1280)
    height = max(1, int(height) if height else 720)
    fps = max(1, int(fps) if fps else 30)

    return (
        f"nvarguscamerasrc sensor-id={sensor_id} ! "
        f"video/x-raw(memory:NVMM), width={width}, height={height}, "
        f"framerate={fps}/1, format=NV12 ! "
        "nvvidconv flip-method=0 ! "
        f"video/x-raw, width={width}, height={height}, format=BGRx ! "
        "videoconvert ! video/x-raw, format=BGR ! appsink drop=true max-buffers=1"
    )


def resolve_jetson_csi_source(
    source: CameraSource,
    width: int,
    height: int,
    fps: float,
) -> Tuple[CameraSource, Optional[str]]:
    """Expand ``csi://`` shorthand to a GStreamer pipeline when possible."""

    if not isinstance(source, str):
        return source, None

    text = source.strip()
    lower = text.lower()
    if not lower.startswith(("csi://", "csi:", "jetson_csi://", "jetson_csi:")):
        return source, None

    suffix = lower.split(":", 1)[1].lstrip("/")
    try:
        sensor_part = suffix.split("/", 1)[0]
        sensor_id = int(sensor_part) if sensor_part else 0
    except ValueError:
        sensor_id = 0

    fps_int = max(1, int(round(fps))) if fps else 30
    pipeline = build_jetson_csi_pipeline(sensor_id, width, height, fps_int)
    return pipeline, "gstreamer"


def choose_backend(explicit_backend: Optional[str], source: CameraSource) -> Optional[str]:
    """Pick the most suitable backend for the provided source."""

    backend = coerce_backend(explicit_backend)
    if backend:
        return backend

    if isinstance(source, int):
        return "v4l2"

    if isinstance(source, str):
        stripped = source.strip()
        if stripped.isdigit():
            return "v4l2"
        if looks_like_gstreamer_pipeline(stripped):
            return "gstreamer"

    return None


def prepare_camera_source(
    camera_cfg: Dict[str, Any],
    width: int,
    height: int,
    fps: float,
) -> Tuple[CameraSource, Optional[str]]:
    """Resolve camera config into a VideoCapture source and backend."""

    cfg = camera_cfg or {}
    source: CameraSource = cfg.get("index_or_path", 0)
    source = _normalize_source_type(source)

    pipeline = cfg.get("gstreamer_pipeline")
    backend_hint = coerce_backend(cfg.get("backend"))

    if pipeline:
        source = pipeline
        pipeline_backend = coerce_backend(cfg.get("pipeline_backend") or "gstreamer")
        backend_hint = pipeline_backend or backend_hint

    source, csi_backend = resolve_jetson_csi_source(source, width, height, fps)
    backend_hint = backend_hint or csi_backend

    backend = choose_backend(backend_hint, source)
    return source, backend


__all__ = [
    "CameraSource",
    "build_jetson_csi_pipeline",
    "choose_backend",
    "coerce_backend",
    "is_jetson_platform",
    "looks_like_gstreamer_pipeline",
    "prepare_camera_source",
    "resolve_jetson_csi_source",
]
