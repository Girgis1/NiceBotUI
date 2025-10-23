"""Hand safety monitoring utilities using lightweight hand tracking."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, List, Optional, Tuple, Union

import cv2  # type: ignore
import numpy as np  # type: ignore

try:  # pragma: no cover - optional dependency
    import mediapipe as mp  # type: ignore

    _HAVE_MEDIAPIPE = True
except Exception:  # pragma: no cover - handled gracefully at runtime
    mp = None
    _HAVE_MEDIAPIPE = False

CameraIdentifier = Union[int, str]
CameraSource = Tuple[str, CameraIdentifier]


@dataclass
class DetectionResult:
    """Result from a single detection pass."""

    detected: bool
    confidence: float
    camera_label: str


DEFAULT_FRAME_SIZE = (320, 240)


def build_camera_sources(config: dict, selection: str) -> List[CameraSource]:
    """Build camera sources list from configuration.

    Args:
        config: Global configuration dictionary.
        selection: Which cameras to use ("front", "wrist", "both").

    Returns:
        List of (label, identifier) tuples suitable for cv2.VideoCapture.
    """

    cameras = config.get("cameras", {}) if isinstance(config, dict) else {}
    if not isinstance(cameras, dict):
        cameras = {}

    selection = (selection or "front").lower()

    if selection == "both":
        camera_names: Iterable[str] = cameras.keys()
    else:
        camera_names = [selection]

    sources: List[CameraSource] = []
    for name in camera_names:
        camera_cfg = cameras.get(name)
        if not isinstance(camera_cfg, dict):
            continue
        identifier: CameraIdentifier = camera_cfg.get("index_or_path", 0)
        if isinstance(identifier, str):
            identifier = identifier.strip()
            if identifier.isdigit():
                identifier = int(identifier)
        sources.append((name, identifier))

    # Fall back to any configured camera if requested camera missing
    if not sources:
        for name, camera_cfg in cameras.items():
            if not isinstance(camera_cfg, dict):
                continue
            identifier = camera_cfg.get("index_or_path", 0)
            if isinstance(identifier, str) and identifier.isdigit():
                identifier = int(identifier)
            sources.append((name, identifier))
            break

    return sources


class HandSafetyMonitor:
    """Monitor camera feeds and emit callbacks when hands are detected."""

    def __init__(
        self,
        camera_sources: List[CameraSource],
        *,
        model_name: str = "mediapipe-hands",
        resume_delay: float = 0.5,
        detection_interval: float = 0.12,
        frame_size: Tuple[int, int] = DEFAULT_FRAME_SIZE,
        test_mode: bool = False,
        log_func: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self.camera_sources = camera_sources
        self.model_name = model_name.lower().strip() if model_name else "mediapipe-hands"
        self.resume_delay = max(0.0, float(resume_delay))
        self.detection_interval = max(0.05, float(detection_interval))
        self.frame_size = frame_size
        self.test_mode = test_mode
        self.log = log_func or (lambda level, message: None)

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._active = False
        self._resume_deadline: Optional[float] = None
        self._pause_callback: Optional[Callable[[str, float], None]] = None
        self._resume_callback: Optional[Callable[[], None]] = None
        self._status_callback: Optional[Callable[[DetectionResult], None]] = None
        self._captures: List[Tuple[str, CameraIdentifier, Any]] = []

        self._detector = self._create_detector()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_callbacks(
        self,
        pause_callback: Optional[Callable[[str, float], None]] = None,
        resume_callback: Optional[Callable[[], None]] = None,
        status_callback: Optional[Callable[[DetectionResult], None]] = None,
    ) -> None:
        self._pause_callback = pause_callback
        self._resume_callback = resume_callback
        self._status_callback = status_callback

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        if not self.camera_sources:
            self.log("warning", "[SAFETY] Hand monitor enabled but no camera sources configured")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="HandSafetyMonitor", daemon=True)
        self._thread.start()
        self.log(
            "info",
            f"[SAFETY] Hand safety monitor started ({len(self.camera_sources)} camera(s), model={self.model_name})",
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None
        self._release_cameras()
        self._active = False
        self._resume_deadline = None
        self.log("info", "[SAFETY] Hand safety monitor stopped")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _create_detector(self):
        """Create detector backend based on requested model."""

        if self.model_name.startswith("mediapipe"):
            if not _HAVE_MEDIAPIPE:
                self.log("warning", "[SAFETY] Mediapipe not available – falling back to skin heuristic")
                return None
            return mp.solutions.hands.Hands(  # type: ignore[attr-defined]
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=0.45,
                min_tracking_confidence=0.35,
            )

        # Future: add other detectors keyed by model_name
        return None

    def _open_cameras(self) -> None:
        self._release_cameras()
        for label, identifier in self.camera_sources:
            try:
                cap = cv2.VideoCapture(identifier)
                if not cap or not cap.isOpened():
                    self.log("warning", f"[SAFETY] Could not open camera '{label}' ({identifier})")
                    continue

                width, height = self.frame_size
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                cap.set(cv2.CAP_PROP_FPS, 15)
                self._captures.append((label, identifier, cap))
            except Exception as exc:  # pragma: no cover - device failure
                self.log("warning", f"[SAFETY] Camera '{label}' init failed: {exc}")

    def _release_cameras(self) -> None:
        for _, _, cap in self._captures:
            try:
                cap.release()
            except Exception:
                pass
        self._captures.clear()

    def _run_loop(self) -> None:
        self._open_cameras()
        if not self._captures:
            self.log("warning", "[SAFETY] No cameras available for hand monitoring")
            return

        while not self._stop_event.is_set():
            result = self._evaluate_cameras()
            self._handle_detection_result(result)
            time.sleep(self.detection_interval)

    def _evaluate_cameras(self) -> DetectionResult:
        best_confidence = 0.0
        best_label = ""

        for index, (label, identifier, cap) in enumerate(list(self._captures)):
            ret, frame = cap.read()
            if not ret or frame is None:
                self.log("warning", f"[SAFETY] Camera '{label}' frame grab failed – retrying")
                # Attempt to reopen once
                cap.release()
                new_cap = cv2.VideoCapture(identifier)
                if new_cap and new_cap.isOpened():
                    width, height = self.frame_size
                    new_cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                    new_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                    new_cap.set(cv2.CAP_PROP_FPS, 15)
                    self._captures[index] = (label, identifier, new_cap)
                else:
                    self.log("warning", f"[SAFETY] Camera '{label}' reconnect failed")
                continue

            resized = cv2.resize(frame, self.frame_size)
            detected, confidence = self._detect_hand(resized)
            if detected and confidence >= best_confidence:
                best_confidence = confidence
                best_label = label

        detected_any = best_label != ""
        return DetectionResult(detected_any, best_confidence, best_label)

    def _detect_hand(self, frame) -> Tuple[bool, float]:
        if self._detector and _HAVE_MEDIAPIPE:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self._detector.process(rgb)
            if results and getattr(results, "multi_hand_landmarks", None):
                confidence = 0.8
                handedness = getattr(results, "multi_handedness", None)
                if handedness:
                    confidence = max(
                        (classification.score for hand in handedness for classification in hand.classification),
                        default=confidence,
                    )
                return True, float(confidence)

        # Fallback heuristic using HSV skin detection
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower_a = np.array([0, 40, 60], dtype=np.uint8)
        upper_a = np.array([20, 150, 255], dtype=np.uint8)
        lower_b = np.array([170, 40, 60], dtype=np.uint8)
        upper_b = np.array([180, 150, 255], dtype=np.uint8)

        mask_a = cv2.inRange(hsv, lower_a, upper_a)
        mask_b = cv2.inRange(hsv, lower_b, upper_b)
        mask = cv2.bitwise_or(mask_a, mask_b)
        mask = cv2.GaussianBlur(mask, (5, 5), 0)
        mask = cv2.erode(mask, np.ones((3, 3), np.uint8), iterations=1)
        mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)

        ratio = float(np.count_nonzero(mask)) / float(mask.size)
        detected = ratio > 0.045
        return detected, ratio

    def _handle_detection_result(self, result: DetectionResult) -> None:
        if self._status_callback:
            try:
                self._status_callback(result)
            except Exception:
                pass

        if result.detected:
            self._resume_deadline = None
            if not self._active:
                self._active = True
                if self.test_mode:
                    self.log(
                        "info",
                        f"[SAFETY] Test mode: hand detected on {result.camera_label} (confidence {result.confidence:.2f})",
                    )
                elif self._pause_callback:
                    self.log(
                        "warning",
                        f"[SAFETY] Hand detected on {result.camera_label} (confidence {result.confidence:.2f})",
                    )
                    try:
                        self._pause_callback(result.camera_label, result.confidence)
                    except Exception as exc:
                        self.log("error", f"[SAFETY] Pause callback error: {exc}")
        else:
            if self._active:
                if self._resume_deadline is None:
                    self._resume_deadline = time.time() + self.resume_delay
                elif time.time() >= self._resume_deadline:
                    self._active = False
                    self._resume_deadline = None
                    if self.test_mode:
                        self.log("info", "[SAFETY] Test mode: hand clear")
                    elif self._resume_callback:
                        self.log("info", "[SAFETY] Workspace clear – resuming robot")
                        try:
                            self._resume_callback()
                        except Exception as exc:
                            self.log("error", f"[SAFETY] Resume callback error: {exc}")

