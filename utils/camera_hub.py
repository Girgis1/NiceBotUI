"""
Shared camera hub for coordinating access to physical cameras.

This module owns the physical `cv2.VideoCapture` handles so downstream
consumers (dashboard preview, vision triggers, etc.) can read frames without
fighting over device ownership.  It exposes two
variants of each frame:

* Full-resolution (as configured in settings) for high-priority clients.
* Preview-resolution (~320 px width, throttled to a few FPS) for UI use.

The hub spins a lightweight thread per camera that reads frames at the
camera's native rate and stores the latest copies in RAM.  Consumers simply
pull snapshots; no additional buffering or queues are required.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Dict, Iterator, Optional, Tuple

try:  # Optional dependency
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except ImportError:  # pragma: no cover
    cv2 = None
    np = None

from utils.camera_backend import open_capture
from utils.camera_support import CameraSource, prepare_camera_source
from utils.logging_utils import log_exception


@dataclass
class FrameBundle:
    """Latest frames cached by a `CameraStream`."""

    full: Optional["np.ndarray"] = None
    preview: Optional["np.ndarray"] = None
    full_timestamp: float = 0.0
    preview_timestamp: float = 0.0


class CameraStream:
    """Background reader for a single physical camera."""

    def __init__(
        self,
        name: str,
        source: CameraSource,
        resolution: Tuple[int, int],
        fps: float,
        preview_width: int = 320,
        preview_fps: float = 5.0,
    ) -> None:
        self.name = name
        self.source = source
        self.target_width, self.target_height = resolution
        self.target_fps = max(1.0, float(fps or 30.0))
        self.preview_width = preview_width
        self.preview_fps = max(0.5, preview_fps)
        self.backend_name: Optional[str] = None

        self._lock = threading.Lock()
        self._frames = FrameBundle()

        self._capture: Optional["cv2.VideoCapture"] = None if cv2 is not None else None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Lifecycle

    def start(self) -> None:
        if cv2 is None:  # pragma: no cover - handled by caller
            return

        with self._lock:
            if self._thread and self._thread.is_alive():
                return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, name=f"{self.name}_camera", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None
        if self._capture is not None:
            try:
                self._capture.release()
            except Exception as exc:  # pragma: no cover - best effort cleanup
                log_exception(f"CameraStream[{self.name}]: release failed", exc, level="debug")
            self._capture = None

    # ------------------------------------------------------------------
    # Frame access

    def get_frame(self, preview: bool, copy: bool = True) -> Optional["np.ndarray"]:
        if np is None:  # pragma: no cover
            return None

        with self._lock:
            frame = self._frames.preview if preview else self._frames.full
            if frame is None:
                return None
            return frame.copy() if copy else frame

    def get_frame_with_timestamp(self, preview: bool) -> Tuple[Optional["np.ndarray"], float]:
        if np is None:  # pragma: no cover
            return None, 0.0

        with self._lock:
            if preview:
                return (
                    self._frames.preview.copy() if self._frames.preview is not None else None,
                    self._frames.preview_timestamp,
                )
            return (
                self._frames.full.copy() if self._frames.full is not None else None,
                self._frames.full_timestamp,
            )

    # ------------------------------------------------------------------
    # Internal helpers

    def _open_capture(self) -> bool:
        if cv2 is None:  # pragma: no cover
            return False

        # Release any stale handle first
        if self._capture is not None:
            try:
                self._capture.release()
            except Exception:
                pass
            self._capture = None

        backend, cap = open_capture(self.source, preferred_backend=self.backend_name)
        if not cap or not cap.isOpened():
            if cap:
                cap.release()
            self._capture = None
            return False
        self.backend_name = backend

        # Apply requested settings when available
        if self.target_width:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self.target_width))
        if self.target_height:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self.target_height))
        if self.target_fps:
            cap.set(cv2.CAP_PROP_FPS, float(self.target_fps))

        # Trim capture buffers when the backend supports it to keep latency low.
        try:
            buffer_prop = getattr(cv2, "CAP_PROP_BUFFERSIZE", None)
            if buffer_prop is not None:
                cap.set(buffer_prop, 1)
        except Exception as exc:  # pragma: no cover - backend dependent
            log_exception(f"CameraStream[{self.name}]: buffer tuning failed", exc, level="debug")

        self._capture = cap
        return True

    def _capture_loop(self) -> None:
        if cv2 is None:  # pragma: no cover
            return

        if not self._open_capture():
            # Retry later so we can recover from hot-plug or conflicting owners.
            self._schedule_retry(delay=1.0)
            return

        preview_interval = 1.0 / self.preview_fps
        next_preview_ts = time.time()

        while not self._stop_event.is_set():
            assert self._capture is not None
            ok, frame = self._capture.read()
            timestamp = time.time()

            if not ok or frame is None:
                time.sleep(0.05)
                if timestamp - self._frames.full_timestamp > 2.0:
                    # Likely camera dropped; attempt reconnect.
                    if self._open_capture():
                        continue
                else:
                    continue

            with self._lock:
                self._frames.full = frame.copy()
                self._frames.full_timestamp = timestamp

                if timestamp >= next_preview_ts:
                    # Downsample while respecting aspect ratio.
                    preview_frame = self._downsample(frame)
                    self._frames.preview = preview_frame
                    self._frames.preview_timestamp = timestamp
                    next_preview_ts = timestamp + preview_interval

        # Cleanup on exit
        if self._capture is not None:
            try:
                self._capture.release()
            except Exception as exc:
                log_exception(f"CameraStream[{self.name}]: release on exit failed", exc, level="debug")
            self._capture = None

    def _schedule_retry(self, delay: float) -> None:
        """Retry connecting after a delay to survive temporary conflicts."""
        def _retry() -> None:
            if self._stop_event.is_set():
                return
            self._capture_loop()

        timer = threading.Timer(delay, _retry)
        timer.daemon = True
        timer.start()

    def _downsample(self, frame: "np.ndarray") -> "np.ndarray":
        if np is None or cv2 is None:  # pragma: no cover
            return frame

        height, width = frame.shape[:2]
        if width <= self.preview_width:
            return frame.copy()

        scale = self.preview_width / float(width)
        preview_height = max(1, int(height * scale))
        return cv2.resize(frame, (self.preview_width, preview_height), interpolation=cv2.INTER_AREA)


class CameraStreamHub:
    """Singleton manager orchestrating all camera streams."""

    _instance: Optional["CameraStreamHub"] = None
    _instance_lock = threading.Lock()

    def __init__(self, config: dict):
        if cv2 is None or np is None:  # pragma: no cover
            raise RuntimeError("OpenCV and NumPy are required for CameraStreamHub.")

        self._config = config
        self._streams: Dict[str, CameraStream] = {}
        self._streams_lock = threading.Lock()
        self._paused = False

    # ------------------------------------------------------------------
    # Singleton helpers

    @classmethod
    def instance(cls, config: dict) -> "CameraStreamHub":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls(config)
        return cls._instance

    @classmethod
    def peek(cls) -> Optional["CameraStreamHub"]:
        """Return the singleton without instantiating a new hub."""

        with cls._instance_lock:
            return cls._instance

    # ------------------------------------------------------------------
    # Stream access

    def get_stream(self, camera_name: str) -> Optional[CameraStream]:
        with self._streams_lock:
            stream = self._streams.get(camera_name)
            if stream:
                return stream

            camera_cfg = self._config.get("cameras", {}).get(camera_name)
            if not camera_cfg:
                return None

            width = int(camera_cfg.get("width", 640))
            height = int(camera_cfg.get("height", 480))
            fps = float(camera_cfg.get("fps", 30))

            source, backend = prepare_camera_source(camera_cfg, width, height, fps)

            stream = CameraStream(
                camera_name,
                source,
                (width, height),
                fps,
                preview_width=min(400, width),
                preview_fps=5.0,
            )
            stream.backend_name = backend
            stream.start()
            self._streams[camera_name] = stream
            return stream

    def get_frame(self, camera_name: str, preview: bool = False) -> Optional["np.ndarray"]:
        stream = self.get_stream(camera_name)
        if not stream:
            return None
        return stream.get_frame(preview=preview)

    def get_frame_with_timestamp(
        self, camera_name: str, preview: bool = False
    ) -> Tuple[Optional["np.ndarray"], float]:
        stream = self.get_stream(camera_name)
        if not stream:
            return None, 0.0
        return stream.get_frame_with_timestamp(preview=preview)

    def shutdown(self) -> None:
        with self._streams_lock:
            for stream in self._streams.values():
                try:
                    stream.stop()
                except Exception as exc:
                    log_exception("CameraStreamHub: error stopping stream during shutdown", exc, level="warning")
            self._streams.clear()
        self._paused = False

    def pause_all(self) -> bool:
        """Temporarily stop all camera threads.

        Returns:
            bool: True if this call transitioned the hub into a paused state.
        """
        with self._streams_lock:
            if self._paused:
                return False
            for stream in self._streams.values():
                try:
                    stream.stop()
                except Exception as exc:
                    log_exception("CameraStreamHub: pause stop failed", exc, level="warning")
            self._paused = True
            return True

    def resume_all(self) -> bool:
        """Restart camera threads after a pause.

        Returns:
            bool: True if this call resumed an actively paused hub.
        """
        with self._streams_lock:
            if not self._paused:
                return False
            for stream in self._streams.values():
                try:
                    stream.start()
                except Exception as exc:
                    log_exception("CameraStreamHub: resume start failed", exc, level="warning")
            self._paused = False
            return True

    def reset_streams(self, camera_name: Optional[str] = None) -> None:
        """Drop cached streams so that new handles are opened on next use."""

        to_stop = []
        with self._streams_lock:
            if camera_name is None:
                to_stop = list(self._streams.values())
                self._streams.clear()
            else:
                stream = self._streams.pop(camera_name, None)
                if stream:
                    to_stop.append(stream)

        for stream in to_stop:
            try:
                stream.stop()
            except Exception as exc:
                log_exception("CameraStreamHub: reset stream stop failed", exc, level="warning")

    @classmethod
    def reset(cls, camera_name: Optional[str] = None) -> None:
        """Convenience helper to reset streams on the active hub."""

        instance = cls.peek()
        if instance is not None:
            instance.reset_streams(camera_name)

    @classmethod
    @contextmanager
    def paused(cls, release_delay: float = 0.1, resume_delay: float = 0.02) -> Iterator[bool]:
        """Context manager that pauses the hub while an exclusive operation runs."""

        instance = cls.peek()
        if instance is None:
            yield False
            return

        transitioned = instance.pause_all()
        if transitioned and release_delay > 0:
            time.sleep(release_delay)

        try:
            yield transitioned
        finally:
            if transitioned:
                if resume_delay > 0:
                    time.sleep(resume_delay)
                instance.resume_all()


def shutdown_camera_hub() -> None:
    """Helper to stop the singleton when the app exits."""
    if CameraStreamHub._instance is not None:
        CameraStreamHub._instance.shutdown()
        CameraStreamHub._instance = None
