"""Runtime hand detection safety monitor."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple, Union

try:  # pragma: no cover - optional dependency handling
    import cv2  # type: ignore
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore

from .hand_detection import HandDetector

CameraSource = Tuple[str, Union[int, str]]


@dataclass
class SafetyEvent:
    """Information about a safety trigger."""

    camera_label: str
    confidence: float
    detail: str


class HandSafetyMonitor:
    """Low-resolution safety layer running in parallel to robot motion."""

    def __init__(
        self,
        sources: List[CameraSource],
        model_name: str,
        on_hand_detected: Callable[[SafetyEvent], None],
        on_hand_cleared: Callable[[SafetyEvent], None],
        frame_width: int = 320,
        poll_interval: float = 0.08,
        detection_cooldown: float = 0.35,
    ) -> None:
        if cv2 is None:
            raise RuntimeError("OpenCV is required for safety monitoring")

        self.sources = sources
        self.model_name = model_name
        self.on_hand_detected = on_hand_detected
        self.on_hand_cleared = on_hand_cleared
        self.frame_width = frame_width
        self.poll_interval = poll_interval
        self.detection_cooldown = detection_cooldown

        self._detector = HandDetector(model_name=model_name)
        self._captures: Dict[str, cv2.VideoCapture] = {}
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._active = False
        self._last_detection: Optional[SafetyEvent] = None
        self._last_seen: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        if not self.sources:
            raise RuntimeError("No camera sources configured for safety monitoring")
        if not self._detector.available:
            raise RuntimeError(f"Hand detector unavailable: {self._detector.detail}")
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="HandSafetyMonitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        self._thread = None
        self._release_all()
        self._detector.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _run(self) -> None:
        try:
            self._open_sources()
            while not self._stop_event.is_set():
                frame_time = time.time()
                any_detected = False
                latest_event: Optional[SafetyEvent] = None

                for label, cap in list(self._captures.items()):
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        continue

                    processed = self._prepare_frame(frame)
                    result = self._detector.detect(processed, annotate=False)

                    if result.detected:
                        any_detected = True
                        event = SafetyEvent(label, result.confidence, result.detail)
                        self._last_seen[label] = frame_time
                        latest_event = event

                if any_detected and not self._active:
                    self._active = True
                    self._last_detection = latest_event
                    if latest_event:
                        self.on_hand_detected(latest_event)
                elif not any_detected and self._active:
                    if self._is_clear(frame_time):
                        self._active = False
                        event = self._last_detection or SafetyEvent("unknown", 0.0, "Cleared")
                        self.on_hand_cleared(event)
                        self._last_detection = None

                # Release stale cameras and reopen lazily if needed
                self._refresh_sources()

                remaining = self.poll_interval - (time.time() - frame_time)
                if remaining > 0:
                    self._stop_event.wait(timeout=remaining)
        finally:
            self._release_all()

    def _prepare_frame(self, frame):
        h, w = frame.shape[:2]
        if w <= 0 or h <= 0:
            return frame
        scale = self.frame_width / float(w)
        if scale < 1.0:
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        return frame

    def _is_clear(self, now: float) -> bool:
        for last_time in self._last_seen.values():
            if now - last_time < self.detection_cooldown:
                return False
        return True

    def _open_sources(self) -> None:
        for label, identifier in self.sources:
            if label in self._captures:
                continue
            cap = cv2.VideoCapture(identifier)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self.frame_width * 0.75))
                cap.set(cv2.CAP_PROP_FPS, 15)
                self._captures[label] = cap
            else:
                cap.release()

    def _refresh_sources(self) -> None:
        # Remove sources that failed
        to_remove = [label for label, cap in self._captures.items() if not cap.isOpened()]
        for label in to_remove:
            cap = self._captures.pop(label)
            cap.release()
            self._last_seen.pop(label, None)
        # Attempt to reopen missing sources periodically
        if len(self._captures) < len(self.sources):
            for label, identifier in self.sources:
                if label in self._captures:
                    continue
                cap = cv2.VideoCapture(identifier)
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self.frame_width * 0.75))
                    cap.set(cv2.CAP_PROP_FPS, 15)
                    self._captures[label] = cap
                else:
                    cap.release()

    def _release_all(self) -> None:
        for cap in self._captures.values():
            try:
                cap.release()
            except Exception:
                pass
        self._captures.clear()


__all__ = ["HandSafetyMonitor", "SafetyEvent"]
