"""
Shared camera hub for coordinating access to physical cameras.

This module owns the physical `cv2.VideoCapture` handles so downstream
consumers (dashboard preview, safety hand tracking, vision triggers, etc.)
can read frames without fighting over device ownership.  It exposes two
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
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Union

try:  # Optional dependency
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except ImportError:  # pragma: no cover
    cv2 = None
    np = None


CameraSource = Union[int, str]


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
            except Exception:  # pragma: no cover - best effort cleanup
                pass
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

        backends_to_try = []
        if isinstance(self.source, str):
            backends_to_try.append(cv2.CAP_ANY)
        else:
            # Prefer V4L2 where available but gracefully fall back when unsupported
            if hasattr(cv2, "CAP_V4L2"):
                backends_to_try.append(cv2.CAP_V4L2)
            backends_to_try.append(cv2.CAP_ANY)

        cap = None
        for backend in backends_to_try:
            try:
                cap = cv2.VideoCapture(self.source, backend)
            except TypeError:
                # Older OpenCV builds may not accept the backend argument
                cap = cv2.VideoCapture(self.source)

            if cap and cap.isOpened():
                break

            if cap:
                cap.release()
            cap = None

        if not cap or not cap.isOpened():
            self._capture = None
            return False

        # Apply requested settings when available
        if self.target_width:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self.target_width))
        if self.target_height:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self.target_height))
        if self.target_fps:
            cap.set(cv2.CAP_PROP_FPS, float(self.target_fps))

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
            except Exception:
                pass
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

            index_or_path = camera_cfg.get("index_or_path", 0)
            if isinstance(index_or_path, str) and index_or_path.isdigit():
                source: CameraSource = int(index_or_path)
            else:
                source = index_or_path

            width = int(camera_cfg.get("width", 640))
            height = int(camera_cfg.get("height", 480))
            fps = float(camera_cfg.get("fps", 30))

            stream = CameraStream(
                camera_name,
                source,
                (width, height),
                fps,
                preview_width=min(400, width),
                preview_fps=5.0,
            )
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
                stream.stop()
            self._streams.clear()
        self._paused = False

    def pause_all(self) -> None:
        """Temporarily stop all camera threads (e.g., when another process needs exclusive access)."""
        with self._streams_lock:
            if self._paused:
                return
            for stream in self._streams.values():
                stream.stop()
            self._paused = True

    def resume_all(self) -> None:
        """Restart camera threads after a pause."""
        with self._streams_lock:
            if not self._paused:
                return
            for stream in self._streams.values():
                stream.start()
            self._paused = False


def shutdown_camera_hub() -> None:
    """Helper to stop the singleton when the app exits."""
    if CameraStreamHub._instance is not None:
        CameraStreamHub._instance.shutdown()
        CameraStreamHub._instance = None
