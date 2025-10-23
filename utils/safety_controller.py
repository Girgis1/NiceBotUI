"""Hand safety monitoring and pause coordination for the robot."""

from __future__ import annotations

import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

import cv2

from .hand_detection import HandDetector, HandDetectionResult


class HandSafetyMonitor(threading.Thread):
    """Background thread that performs lightweight hand detection."""

    def __init__(
        self,
        config: dict,
        on_detect: Callable[[float], None],
        on_clear: Callable[[], None],
    ) -> None:
        super().__init__(daemon=True)
        self._config = config
        self._on_detect = on_detect
        self._on_clear = on_clear
        self._stop_event = threading.Event()
        self._capture_lock = threading.Lock()
        self._captures: Dict[str, cv2.VideoCapture] = {}
        self._hand_detector = HandDetector()
        self._hand_present = False
        self._last_detect_time = 0.0

    def stop(self) -> None:
        self._stop_event.set()
        self.join(timeout=1.0)
        self._release_captures()
        self._hand_detector.close()

    def run(self) -> None:
        while not self._stop_event.is_set():
            enabled = self._config.get("safety", {}).get("hand_detection_enabled", False)
            if not enabled:
                time.sleep(0.5)
                continue

            if not self._captures:
                self._open_captures()
                if not self._captures:
                    time.sleep(1.0)
                    continue

            detected, confidence = self._scan_cameras()
            now = time.time()

            if detected:
                self._last_detect_time = now
                if not self._hand_present:
                    self._hand_present = True
                    self._on_detect(confidence)
            elif self._hand_present:
                resume_delay = self._config.get("safety", {}).get("hand_resume_delay_s", 0.5)
                if now - self._last_detect_time >= max(0.1, resume_delay):
                    self._hand_present = False
                    self._on_clear()

            time.sleep(0.05)

        self._release_captures()

    def update_config(self, config: dict) -> None:
        self._config = config
        if self._hand_present:
            self._hand_present = False
            self._on_clear()
        with self._capture_lock:
            self._release_captures()

    def _scan_cameras(self) -> Tuple[bool, float]:
        confidence = 0.0
        detected = False
        with self._capture_lock:
            for name, cap in list(self._captures.items()):
                ret, frame = cap.read()
                if not ret or frame is None:
                    cap.release()
                    self._captures.pop(name, None)
                    continue

                frame_small = cv2.resize(frame, (320, 240)) if frame.shape[1] > 320 else frame
                result: HandDetectionResult = self._hand_detector.detect(frame_small)
                if result.detected:
                    detected = True
                    confidence = max(confidence, result.confidence)

        return detected, confidence

    def _open_captures(self) -> None:
        camera_choice = self._config.get("safety", {}).get("hand_detection_camera", "front")
        cameras_cfg = self._config.get("cameras", {})
        candidates: List[Tuple[str, dict]] = []

        if camera_choice in ("front", "both") and "front" in cameras_cfg:
            candidates.append(("front", cameras_cfg["front"]))
        if camera_choice in ("wrist", "both") and "wrist" in cameras_cfg:
            candidates.append(("wrist", cameras_cfg["wrist"]))
        if not candidates and cameras_cfg:
            candidates.extend(list(cameras_cfg.items()))

        with self._capture_lock:
            self._release_captures()
            for name, cfg in candidates:
                index_or_path = cfg.get("index_or_path", 0)
                cap = cv2.VideoCapture(index_or_path)
                if not cap.isOpened():
                    cap.release()
                    continue
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
                cap.set(cv2.CAP_PROP_FPS, 15)
                self._captures[name] = cap

    def _release_captures(self) -> None:
        with self._capture_lock:
            for cap in self._captures.values():
                try:
                    cap.release()
                except Exception:
                    pass
            self._captures.clear()


class SafetyController:
    """Coordinates hand safety monitor with robot execution."""

    def __init__(self, config: dict) -> None:
        self._config = config
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._monitor: Optional[HandSafetyMonitor] = None
        self._monitor_lock = threading.Lock()
        self._active = False
        self._hold_enabled = bool(config.get("safety", {}).get("hand_hold_position", True))
        self._last_confidence = 0.0
        self._start_monitor_if_enabled()

    def update_config(self, config: dict) -> None:
        self._config = config
        self._hold_enabled = bool(config.get("safety", {}).get("hand_hold_position", True))
        enabled = bool(config.get("safety", {}).get("hand_detection_enabled", False))
        with self._monitor_lock:
            if enabled:
                if self._monitor is None:
                    self._start_monitor_locked()
                else:
                    self._monitor.update_config(config)
            else:
                self._stop_monitor_locked()
                self._pause_event.set()

    def is_active(self) -> bool:
        return self._active

    def is_paused(self) -> bool:
        return self._active and not self._pause_event.is_set()

    def should_hold_position(self) -> bool:
        return self._hold_enabled

    def wait_until_clear(self) -> bool:
        if not self._active:
            return False
        waited = False
        while not self._pause_event.wait(timeout=0.05):
            waited = True
        return waited

    def force_release(self) -> None:
        self._pause_event.set()

    def _start_monitor_if_enabled(self) -> None:
        if self._config.get("safety", {}).get("hand_detection_enabled", False):
            with self._monitor_lock:
                self._start_monitor_locked()

    def _start_monitor_locked(self) -> None:
        if self._monitor is not None:
            return
        self._monitor = HandSafetyMonitor(self._config, self._handle_detect, self._handle_clear)
        self._monitor.start()
        self._active = True
        print("[SAFETY] Hand safety monitor started")

    def _stop_monitor_locked(self) -> None:
        monitor = self._monitor
        if monitor is not None:
            monitor.stop()
        self._monitor = None
        self._active = False
        self._pause_event.set()
        print("[SAFETY] Hand safety monitor stopped")

    def _handle_detect(self, confidence: float) -> None:
        self._last_confidence = confidence
        self._pause_event.clear()
        print(f"[SAFETY] Hand detected (confidence={confidence:.2f}) - pausing robot")

    def _handle_clear(self) -> None:
        self._pause_event.set()
        print("[SAFETY] Hand cleared - resuming robot")

