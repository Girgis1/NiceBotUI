"""
Hand safety monitoring system for robot operations.

This module provides CRITICAL SAFETY monitoring that detects hands in the robot
workspace and EMERGENCY STOPS the robot to prevent injury.

Key Features:
- MediaPipe hand detection (primary, most reliable)
- HSV skin tone fallback (when MediaPipe unavailable)
- Configurable FPS (default 8 FPS for lightweight operation)
- Multi-camera support
- Automatic camera recovery
- Emergency stop integration (NOT pause - STOP for safety!)
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple, Union

try:
    import cv2
    HAVE_CV2 = True
except ImportError:
    cv2 = None
    HAVE_CV2 = False

try:
    import numpy as np
    HAVE_NUMPY = True
except ImportError:
    np = None
    HAVE_NUMPY = False

try:
    import mediapipe as mp
    HAVE_MEDIAPIPE = True
except ImportError:
    mp = None
    HAVE_MEDIAPIPE = False


CameraIdentifier = Union[int, str]
CameraSource = Tuple[str, CameraIdentifier]


@dataclass
class SafetyConfig:
    """Configuration for hand safety monitoring."""
    
    enabled: bool = False
    cameras: List[CameraSource] = None
    detection_fps: float = 8.0  # Lower FPS for resource efficiency
    frame_width: int = 320
    frame_height: int = 240
    detection_confidence: float = 0.45  # MediaPipe confidence threshold
    tracking_confidence: float = 0.35  # MediaPipe tracking threshold
    resume_delay_s: float = 1.0  # Delay before resuming after hand cleared
    skin_threshold: float = 0.045  # HSV fallback threshold
    use_mediapipe: bool = True  # Prefer MediaPipe when available
    
    def __post_init__(self):
        if self.cameras is None:
            self.cameras = []


@dataclass
class SafetyEvent:
    """Information about a safety detection event."""
    
    detected: bool
    confidence: float
    camera_label: str
    timestamp: float
    detection_method: str  # "mediapipe" or "hsv"


class HandSafetyMonitor:
    """
    Background thread that monitors camera feeds for hands and triggers emergency stops.
    
    SAFETY CRITICAL: This monitor STOPS the robot (not pauses) when hands are detected
    to prevent injury. The robot must be manually restarted after a safety stop.
    """
    
    def __init__(
        self,
        config: SafetyConfig,
        on_hand_detected: Callable[[SafetyEvent], None],
        on_hand_cleared: Callable[[SafetyEvent], None],
        log_callback: Optional[Callable[[str, str], None]] = None,
    ):
        """
        Initialize the hand safety monitor.
        
        Args:
            config: Safety configuration
            on_hand_detected: Callback when hand detected (should trigger EMERGENCY STOP)
            on_hand_cleared: Callback when hand cleared
            log_callback: Optional logging callback (level, message)
        """
        if not HAVE_CV2 or not HAVE_NUMPY:
            raise RuntimeError(
                "OpenCV and NumPy are required for safety monitoring. "
                "Install with: pip install opencv-python numpy"
            )
        
        self.config = config
        self._on_hand_detected = on_hand_detected
        self._on_hand_cleared = on_hand_cleared
        self._log = log_callback or (lambda level, msg: print(f"[{level.upper()}] {msg}"))
        
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._hand_active = False
        self._last_detection_time = 0.0
        self._captures: List[Tuple[str, CameraIdentifier, cv2.VideoCapture]] = []
        self._capture_lock = threading.Lock()
        
        # Initialize hand detector
        self._detector = None
        self._detection_method = "none"
        self._init_detector()
    
    def _init_detector(self):
        """Initialize hand detection backend."""
        if self.config.use_mediapipe and HAVE_MEDIAPIPE:
            try:
                self._detector = mp.solutions.hands.Hands(
                    static_image_mode=False,
                    model_complexity=0,  # Lightweight model
                    max_num_hands=2,
                    min_detection_confidence=self.config.detection_confidence,
                    min_tracking_confidence=self.config.tracking_confidence,
                )
                self._detection_method = "mediapipe"
                self._log("info", "[SAFETY] Initialized MediaPipe hand detection (LIGHTWEIGHT MODE)")
            except Exception as e:
                self._log("warning", f"[SAFETY] Failed to initialize MediaPipe: {e}, falling back to HSV")
                self._detector = None
                self._detection_method = "hsv"
        else:
            self._detection_method = "hsv"
            self._log("info", "[SAFETY] Using HSV skin-tone detection (MediaPipe not available)")
    
    def start(self):
        """Start the safety monitoring thread."""
        if self._thread and self._thread.is_alive():
            self._log("warning", "[SAFETY] Monitor already running")
            return
        
        if not self.config.enabled:
            self._log("info", "[SAFETY] Monitor disabled in config")
            return
        
        if not self.config.cameras:
            self._log("warning", "[SAFETY] No cameras configured for monitoring")
            return
        
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_monitor, name="HandSafetyMonitor", daemon=True)
        self._thread.start()
        
        self._log(
            "info",
            f"[SAFETY] ⚠️  EMERGENCY STOP MONITORING ACTIVE ⚠️\n"
            f"         Cameras: {len(self.config.cameras)}, "
            f"Method: {self._detection_method}, "
            f"FPS: {self.config.detection_fps:.1f}"
        )
    
    def stop(self):
        """Stop the safety monitoring thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._thread = None
        self._release_cameras()
        self._hand_active = False
        
        if self._detector and self._detection_method == "mediapipe":
            try:
                self._detector.close()
            except:
                pass
        
        self._log("info", "[SAFETY] Monitor stopped")
    
    def update_config(self, config: SafetyConfig):
        """Update configuration (requires restart)."""
        was_running = self._thread and self._thread.is_alive()
        if was_running:
            self.stop()
        
        self.config = config
        self._init_detector()
        
        if was_running and config.enabled:
            self.start()
    
    def _run_monitor(self):
        """Main monitoring loop (runs in background thread)."""
        try:
            self._open_cameras()
            
            if not self._captures:
                self._log("error", "[SAFETY] ❌ NO CAMERAS AVAILABLE - SAFETY MONITORING DISABLED!")
                return
            
            detection_interval = 1.0 / self.config.detection_fps
            
            while not self._stop_event.is_set():
                loop_start = time.time()
                
                # Check all cameras for hands
                detection_result = self._check_all_cameras()
                
                # Handle detection state
                if detection_result.detected:
                    self._last_detection_time = detection_result.timestamp
                    if not self._hand_active:
                        self._hand_active = True
                        self._log(
                            "critical",
                            f"[SAFETY] 🚨 HAND DETECTED ON {detection_result.camera_label} 🚨 "
                            f"(confidence: {detection_result.confidence:.2f}, method: {detection_result.detection_method})"
                        )
                        self._on_hand_detected(detection_result)
                else:
                    # Check if enough time has passed since last detection
                    if self._hand_active:
                        time_since_detection = time.time() - self._last_detection_time
                        if time_since_detection >= self.config.resume_delay_s:
                            self._hand_active = False
                            clear_event = SafetyEvent(
                                detected=False,
                                confidence=0.0,
                                camera_label="all",
                                timestamp=time.time(),
                                detection_method=self._detection_method
                            )
                            self._log("info", f"[SAFETY] ✓ Workspace clear for {time_since_detection:.1f}s - Ready to resume")
                            self._on_hand_cleared(clear_event)
                
                # Maintain target FPS
                elapsed = time.time() - loop_start
                sleep_time = max(0, detection_interval - elapsed)
                if sleep_time > 0:
                    self._stop_event.wait(timeout=sleep_time)
                
        except Exception as e:
            self._log("error", f"[SAFETY] Monitor loop error: {e}")
        finally:
            self._release_cameras()
    
    def _check_all_cameras(self) -> SafetyEvent:
        """Check all cameras for hand detection."""
        best_confidence = 0.0
        best_camera = "none"
        detected_any = False
        
        with self._capture_lock:
            for idx, (label, identifier, cap) in enumerate(list(self._captures)):
                ret, frame = cap.read()
                
                if not ret or frame is None:
                    # Try to recover camera
                    self._log("warning", f"[SAFETY] Camera '{label}' failed, attempting recovery...")
                    cap.release()
                    new_cap = self._open_single_camera(identifier)
                    if new_cap:
                        self._captures[idx] = (label, identifier, new_cap)
                        continue
                    else:
                        self._captures.pop(idx)
                        continue
                
                # Detect hands in frame
                detected, confidence = self._detect_hand(frame)
                
                if detected and confidence > best_confidence:
                    detected_any = True
                    best_confidence = confidence
                    best_camera = label
        
        return SafetyEvent(
            detected=detected_any,
            confidence=best_confidence,
            camera_label=best_camera,
            timestamp=time.time(),
            detection_method=self._detection_method
        )
    
    def _detect_hand(self, frame) -> Tuple[bool, float]:
        """
        Detect hands in a frame using the configured method.
        
        Returns:
            (detected: bool, confidence: float)
        """
        # Resize frame for efficiency
        if frame.shape[1] > self.config.frame_width:
            frame = cv2.resize(frame, (self.config.frame_width, self.config.frame_height))
        
        if self._detection_method == "mediapipe" and self._detector:
            return self._detect_mediapipe(frame)
        else:
            return self._detect_hsv(frame)
    
    def _detect_mediapipe(self, frame) -> Tuple[bool, float]:
        """Detect hands using MediaPipe."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        
        try:
            results = self._detector.process(rgb)
            
            if results and results.multi_hand_landmarks:
                # Calculate confidence from hand size/position
                confidence = 0.8  # Default confidence
                
                if results.multi_handedness:
                    # Get highest confidence from detected hands
                    for hand_info in results.multi_handedness:
                        for classification in hand_info.classification:
                            confidence = max(confidence, classification.score)
                
                return True, float(confidence)
        except Exception as e:
            self._log("warning", f"[SAFETY] MediaPipe detection error: {e}")
        
        return False, 0.0
    
    def _detect_hsv(self, frame) -> Tuple[bool, float]:
        """Detect hands using HSV skin-tone heuristic (fallback method)."""
        try:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            
            # Skin tone ranges (optimized for various lighting conditions)
            lower_a = np.array([0, 40, 60], dtype=np.uint8)
            upper_a = np.array([20, 150, 255], dtype=np.uint8)
            lower_b = np.array([170, 40, 60], dtype=np.uint8)
            upper_b = np.array([180, 150, 255], dtype=np.uint8)
            
            # Create masks
            mask_a = cv2.inRange(hsv, lower_a, upper_a)
            mask_b = cv2.inRange(hsv, lower_b, upper_b)
            mask = cv2.bitwise_or(mask_a, mask_b)
            
            # Noise reduction
            mask = cv2.GaussianBlur(mask, (5, 5), 0)
            mask = cv2.erode(mask, np.ones((3, 3), np.uint8), iterations=1)
            mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
            
            # Calculate skin pixel ratio
            ratio = float(np.count_nonzero(mask)) / float(mask.size)
            detected = ratio >= self.config.skin_threshold
            
            return detected, ratio
        except Exception as e:
            self._log("warning", f"[SAFETY] HSV detection error: {e}")
            return False, 0.0
    
    def _open_cameras(self):
        """Open all configured cameras."""
        self._release_cameras()
        
        with self._capture_lock:
            for label, identifier in self.config.cameras:
                cap = self._open_single_camera(identifier)
                if cap:
                    self._captures.append((label, identifier, cap))
                    self._log("info", f"[SAFETY] Opened camera '{label}' ({identifier})")
                else:
                    self._log("warning", f"[SAFETY] Failed to open camera '{label}' ({identifier})")
    
    def _open_single_camera(self, identifier: CameraIdentifier) -> Optional[cv2.VideoCapture]:
        """Open a single camera with proper configuration."""
        try:
            cap = cv2.VideoCapture(identifier)
            if not cap or not cap.isOpened():
                if cap:
                    cap.release()
                return None
            
            # Configure camera for lightweight operation
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.frame_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.frame_height)
            cap.set(cv2.CAP_PROP_FPS, 15)  # Camera FPS (lower than detection FPS)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize latency
            
            return cap
        except Exception as e:
            self._log("warning", f"[SAFETY] Camera open error: {e}")
            return None
    
    def _release_cameras(self):
        """Release all camera resources."""
        with self._capture_lock:
            for _, _, cap in self._captures:
                try:
                    cap.release()
                except:
                    pass
            self._captures.clear()


def build_camera_sources_from_config(config: dict, camera_selection: str = "front") -> List[CameraSource]:
    """
    Build camera source list from application config.
    
    Args:
        config: Application configuration dictionary
        camera_selection: Which cameras to use ("front", "wrist", "both", "all")
    
    Returns:
        List of (label, identifier) tuples
    """
    cameras_cfg = config.get("cameras", {})
    if not isinstance(cameras_cfg, dict):
        return []
    
    sources: List[CameraSource] = []
    selection = camera_selection.lower().strip()
    
    if selection == "both" or selection == "all":
        # Use all configured cameras
        for name, cam_cfg in cameras_cfg.items():
            if isinstance(cam_cfg, dict):
                identifier = cam_cfg.get("index_or_path", 0)
                if isinstance(identifier, str) and identifier.isdigit():
                    identifier = int(identifier)
                sources.append((name, identifier))
    else:
        # Use specific camera
        if selection in cameras_cfg:
            cam_cfg = cameras_cfg[selection]
            if isinstance(cam_cfg, dict):
                identifier = cam_cfg.get("index_or_path", 0)
                if isinstance(identifier, str) and identifier.isdigit():
                    identifier = int(identifier)
                sources.append((selection, identifier))
        else:
            # Fallback: use first available camera
            for name, cam_cfg in cameras_cfg.items():
                if isinstance(cam_cfg, dict):
                    identifier = cam_cfg.get("index_or_path", 0)
                    if isinstance(identifier, str) and identifier.isdigit():
                        identifier = int(identifier)
                    sources.append((name, identifier))
                    break
    
    return sources

