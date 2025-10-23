"""Hand safety monitoring with lightweight hand detection."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Sequence, Union

from PySide6.QtCore import QThread, Signal

try:  # Optional dependency handling
    import cv2  # type: ignore
except Exception:  # pragma: no cover - OpenCV not installed
    cv2 = None  # type: ignore


@dataclass
class HandSafetySettings:
    """Configuration for the hand safety monitor."""

    sources: Sequence[Union[int, str]]
    frame_width: int = 320
    frame_height: int = 240
    detection_confidence: float = 0.45
    tracking_confidence: float = 0.35
    trigger_frames: int = 2
    clear_frames: int = 6
    poll_interval_s: float = 0.03


class HandSafetyMonitor(QThread):
    """Runs lightweight hand detection in a background thread."""

    hand_detected = Signal()
    hand_cleared = Signal()
    status_message = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, settings: HandSafetySettings):
        super().__init__()
        self.settings = settings
        self._stop_requested = False
        self._hand_active = False
        self._present_frames = 0
        self._absent_frames = 0
        self._captures: List["cv2.VideoCapture"] = []

    def stop(self):
        """Request the monitoring thread to stop."""
        self._stop_requested = True
        self.wait(500)

    # pylint: disable=too-many-branches,too-many-locals
    def run(self):  # pragma: no cover - requires camera hardware
        if cv2 is None:
            self.error_occurred.emit(
                "OpenCV is not available. Install requirements.txt dependencies."
            )
            return

        try:
            import mediapipe as mp  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            self.error_occurred.emit(
                f"Mediapipe is required for hand safety monitoring: {exc}"
            )
            return

        mp_hands = mp.solutions.hands
        self._open_captures()

        if not self._captures:
            self.error_occurred.emit("No camera sources available for hand monitoring.")
            return

        self.status_message.emit(
            f"Hand safety active on {len(self._captures)} camera(s)"
        )

        try:
            with mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=1,
                min_detection_confidence=self.settings.detection_confidence,
                min_tracking_confidence=self.settings.tracking_confidence,
            ) as detector:
                while not self._stop_requested:
                    detected = self._process_all_cameras(detector)
                    self._update_state(detected)
                    time.sleep(self.settings.poll_interval_s)
        finally:
            for cap in self._captures:
                try:
                    cap.release()
                except Exception:
                    pass
            self._captures.clear()

    def _open_captures(self):  # pragma: no cover - hardware interaction
        for source in self.settings.sources:
            cap = cv2.VideoCapture(source)
            if not cap or not cap.isOpened():
                if cap:
                    cap.release()
                continue

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self.settings.frame_width))
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self.settings.frame_height))
            cap.set(cv2.CAP_PROP_FPS, 15)
            self._captures.append(cap)

    def _process_all_cameras(self, detector) -> bool:  # pragma: no cover
        for cap in self._captures:
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            resized = cv2.resize(
                frame,
                (self.settings.frame_width, self.settings.frame_height),
                interpolation=cv2.INTER_LINEAR,
            )
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            result = detector.process(rgb)
            if result.multi_hand_landmarks:
                return True
        return False

    def _update_state(self, detected: bool):
        if detected:
            self._present_frames += 1
            self._absent_frames = 0
            if (
                not self._hand_active
                and self._present_frames >= self.settings.trigger_frames
            ):
                self._hand_active = True
                self.status_message.emit("Hand detected — pausing robot")
                self.hand_detected.emit()
        else:
            self._present_frames = 0
            if self._hand_active:
                self._absent_frames += 1
                if self._absent_frames >= self.settings.clear_frames:
                    self._hand_active = False
                    self.status_message.emit("Hand cleared — preparing to resume")
                    self.hand_cleared.emit()

