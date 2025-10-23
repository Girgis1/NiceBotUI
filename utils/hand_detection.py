"""Lightweight hand detection utilities shared by safety systems and tests."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np

try:
    import mediapipe as mp  # type: ignore
except Exception:  # pragma: no cover - mediapipe optional
    mp = None  # Fallback handled in HandDetector


@dataclass
class HandDetectionResult:
    """Result returned from :class:`HandDetector`."""

    detected: bool
    confidence: float
    annotated_frame: Optional[np.ndarray] = None


class HandDetector:
    """Wrapper around MediaPipe Hands with graceful fallback."""

    def __init__(
        self,
        model_complexity: int = 0,
        min_detection_confidence: float = 0.4,
        min_tracking_confidence: float = 0.3,
        max_num_hands: int = 2,
        annotate: bool = False,
    ) -> None:
        self._lock = threading.Lock()
        self._annotate_default = annotate
        self._backend = None
        self._hands = None
        self._mp_draw = None
        self._min_detection_confidence = min_detection_confidence
        self._min_tracking_confidence = min_tracking_confidence
        self._max_num_hands = max_num_hands

        if mp is not None:
            self._backend = "mediapipe"
            self._hands = mp.solutions.hands.Hands(
                model_complexity=model_complexity,
                min_detection_confidence=min_detection_confidence,
                min_tracking_confidence=min_tracking_confidence,
                max_num_hands=max_num_hands,
            )
            self._mp_draw = mp.solutions.drawing_utils
        else:
            self._backend = "hsv"

    @property
    def backend(self) -> str:
        return self._backend or "unknown"

    def close(self) -> None:
        if self._hands is not None:
            self._hands.close()
            self._hands = None

    def detect(
        self,
        frame: np.ndarray,
        annotate: Optional[bool] = None,
    ) -> HandDetectionResult:
        """Detect hands within a BGR frame."""

        if annotate is None:
            annotate = self._annotate_default

        if self._backend == "mediapipe" and self._hands is not None:
            return self._detect_mediapipe(frame, annotate)

        return self._detect_hsv(frame, annotate)

    def _detect_mediapipe(self, frame: np.ndarray, annotate: bool) -> HandDetectionResult:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        with self._lock:
            results = self._hands.process(rgb) if self._hands else None

        detected = bool(results and results.multi_hand_landmarks)
        confidence = 0.0
        annotated = frame if annotate else None

        if detected and results and results.multi_handedness:
            confidence = max(h.classification[0].score for h in results.multi_handedness)

        if detected and annotate and results and self._mp_draw:
            annotated = frame.copy()
            for hand_landmarks in results.multi_hand_landmarks:
                self._mp_draw.draw_landmarks(
                    annotated,
                    hand_landmarks,
                    mp.solutions.hands.HAND_CONNECTIONS,
                    landmark_drawing_spec=self._mp_draw.DrawingSpec(color=(0, 255, 0), thickness=2),
                    connection_drawing_spec=self._mp_draw.DrawingSpec(color=(0, 120, 255), thickness=1),
                )
            cv2.putText(
                annotated,
                f"Hand: YES ({confidence:.2f})",
                (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
        elif annotate:
            annotated = frame.copy()
            cv2.putText(
                annotated,
                f"Hand: {'YES' if detected else 'NO'} ({confidence:.2f})",
                (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

        return HandDetectionResult(detected=detected, confidence=confidence, annotated_frame=annotated)

    def _detect_hsv(self, frame: np.ndarray, annotate: bool) -> HandDetectionResult:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower_a = np.array([0, 30, 60], dtype=np.uint8)
        upper_a = np.array([20, 150, 255], dtype=np.uint8)
        lower_b = np.array([170, 30, 60], dtype=np.uint8)
        upper_b = np.array([180, 150, 255], dtype=np.uint8)

        mask_a = cv2.inRange(hsv, lower_a, upper_a)
        mask_b = cv2.inRange(hsv, lower_b, upper_b)
        mask = cv2.bitwise_or(mask_a, mask_b)
        mask = cv2.GaussianBlur(mask, (7, 7), 0)
        mask = cv2.erode(mask, np.ones((3, 3), np.uint8), iterations=1)
        mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=1)

        ratio = float(cv2.countNonZero(mask)) / float(mask.size)
        detected = ratio >= 0.04
        confidence = float(min(1.0, max(0.0, ratio * 2.0)))

        annotated = frame.copy() if annotate else None
        if annotate and annotated is not None:
            overlay = frame.copy()
            overlay[mask > 0] = (0, 0, 255)
            annotated = cv2.addWeighted(overlay, 0.4, frame, 0.6, 0)
            cv2.putText(
                annotated,
                f"Hand: {'YES' if detected else 'NO'} ({confidence:.2f})",
                (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

        return HandDetectionResult(detected=detected, confidence=confidence, annotated_frame=annotated)
