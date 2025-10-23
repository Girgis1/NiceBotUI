"""Hand detection utilities for safety monitoring and testing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

try:  # pragma: no cover - optional dependency handling
    import cv2  # type: ignore
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore

try:  # pragma: no cover - optional dependency handling
    import numpy as np  # type: ignore
except ImportError:  # pragma: no cover
    np = None  # type: ignore


@dataclass
class HandDetectionResult:
    """Structured result returned by :class:`HandDetector`."""

    detected: bool
    confidence: float
    annotated_frame: Optional["np.ndarray"]
    detail: str


class HandDetector:
    """Unified interface for real-time hand detection.

    The detector prioritises lightweight, production-safe inference. If the
    requested model is available (currently ``mediapipe``), it is used. When
    unavailable, the detector transparently falls back to a conservative
    skin-tone heuristic so safety checks can still run, albeit with reduced
    fidelity.
    """

    _MEDIAPIPE_MODELS = {"mediapipe", "mediapipe-hands", "mediapipe_hands"}

    def __init__(
        self,
        model_name: str = "mediapipe-hands",
        max_hands: int = 1,
        detection_confidence: float = 0.5,
        tracking_confidence: float = 0.5,
    ) -> None:
        self.model_name = model_name
        self._mode: str = "disabled"
        self.available: bool = False
        self.detail: str = "Detector disabled"

        if cv2 is None or np is None:
            self.detail = "OpenCV/NumPy not available"
            return

        normalized_name = model_name.lower()
        if normalized_name in self._MEDIAPIPE_MODELS:
            try:
                import mediapipe as mp  # type: ignore

                self._mp_hands = mp.solutions.hands.Hands(
                    model_complexity=0,
                    max_num_hands=max_hands,
                    min_detection_confidence=detection_confidence,
                    min_tracking_confidence=tracking_confidence,
                )
                self._mp_draw = mp.solutions.drawing_utils
                self._mp_connections = mp.solutions.hands.HAND_CONNECTIONS
                self._mode = "mediapipe"
                self.available = True
                self.detail = "MediaPipe Hands (model_complexity=0)"
                return
            except Exception as exc:  # pragma: no cover - mediapipe optional
                self.detail = f"Failed to load MediaPipe ({exc})"

        # Fallback to skin heuristic when mediapipe unavailable or not requested
        self._mode = "skin"
        self.available = True
        self.detail = "Skin-tone heuristic"

    def detect(self, frame: "np.ndarray", annotate: bool = False) -> HandDetectionResult:
        """Detect hands in a BGR frame.

        Args:
            frame: Frame in BGR colour space.
            annotate: If ``True``, overlay detection results on a copy of the
                frame.

        Returns:
            :class:`HandDetectionResult` describing the detection state.
        """

        if not self.available or cv2 is None or np is None:
            return HandDetectionResult(False, 0.0, frame if annotate else None, self.detail)

        if self._mode == "mediapipe":
            return self._detect_mediapipe(frame, annotate)

        # Skin heuristic fallback
        return self._detect_skin(frame, annotate)

    # ------------------------------------------------------------------
    # Detection backends
    # ------------------------------------------------------------------
    def _detect_mediapipe(self, frame: "np.ndarray", annotate: bool) -> HandDetectionResult:
        """Run MediaPipe Hands on the provided frame."""

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        results = self._mp_hands.process(rgb)  # type: ignore[attr-defined]

        annotated = frame.copy() if annotate else None
        detected = False
        confidence = 0.0
        detail = "No hands"

        if results.multi_hand_landmarks:
            detected = True
            detail = f"Hands detected: {len(results.multi_hand_landmarks)}"
            for hand_landmarks in results.multi_hand_landmarks:
                xs = [lm.x for lm in hand_landmarks.landmark]
                ys = [lm.y for lm in hand_landmarks.landmark]
                min_x, max_x = max(min(xs), 0.0), min(max(xs), 1.0)
                min_y, max_y = max(min(ys), 0.0), min(max(ys), 1.0)
                area = max(0.0, (max_x - min_x) * (max_y - min_y))
                confidence = max(confidence, area)
                if annotated is not None:
                    self._mp_draw.draw_landmarks(  # type: ignore[attr-defined]
                        annotated,
                        hand_landmarks,
                        self._mp_connections,  # type: ignore[attr-defined]
                        self._mp_draw.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2),
                        self._mp_draw.DrawingSpec(color=(255, 255, 255), thickness=2),
                    )

        if annotated is not None:
            text = f"Hand: {'YES' if detected else 'NO'}"
            if detected:
                text += f" area {confidence * 100:.1f}%"
            cv2.putText(
                annotated,
                text,
                (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

        return HandDetectionResult(detected, confidence, annotated, detail)

    def _detect_skin(self, frame: "np.ndarray", annotate: bool) -> HandDetectionResult:
        """Fallback heuristic based on skin-tone segmentation."""

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
        detail = f"Skin ratio: {ratio:.3f}"

        annotated = None
        if annotate:
            overlay = frame.copy()
            overlay[mask > 0] = (0, 0, 255)
            annotated = cv2.addWeighted(overlay, 0.4, frame, 0.6, 0)
            cv2.putText(
                annotated,
                f"Hand: {'YES' if detected else 'NO'} ({ratio * 100:.1f}% skin)",
                (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

        return HandDetectionResult(detected, ratio, annotated, detail)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------
    def close(self) -> None:
        """Release any underlying model resources."""

        if self._mode == "mediapipe" and hasattr(self, "_mp_hands"):
            self._mp_hands.close()  # type: ignore[attr-defined]


__all__ = ["HandDetector", "HandDetectionResult"]
