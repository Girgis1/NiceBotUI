"""
Presence Detector - Background subtraction + blob detection

Fast, lightweight detector for presence/absence detection.
Perfect for:
- Idle standby mode
- Object arrival detection
- Works well with static backgrounds (MDF, white acrylic)
"""

import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional
from collections import deque

from utils.logging_utils import log_exception

try:
    from .base import BaseDetector, DetectionResult
    from ..zone import Zone
except ImportError:
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent))
    from detectors.base import BaseDetector, DetectionResult
    from zone import Zone


class PresenceDetector(BaseDetector):
    """Detect object presence using background subtraction"""
    
    def __init__(
        self,
        min_blob_area: int = 1200,
        learning_rate: float = 0.001,
        var_threshold: int = 16,
        detect_shadows: bool = False,
        stability_frames: int = 2,
        history: int = 50
    ):
        """
        Initialize presence detector
        
        Args:
            min_blob_area: Minimum object area in pixels²
            learning_rate: Background model learning rate (lower = more stable)
            var_threshold: Detection sensitivity threshold
            detect_shadows: Enable shadow detection (slower)
            stability_frames: Frames required to confirm stability
            history: Background model history size
        """
        super().__init__()
        self.min_blob_area = min_blob_area
        self.learning_rate = learning_rate
        self.var_threshold = var_threshold
        self.detect_shadows = detect_shadows
        self.stability_frames = stability_frames
        self.history = history
        
        # Background subtractor (MOG2)
        self.bg_subtractor = None
        
        # Morphological kernel for cleanup
        self.morph_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        
        # Frame buffer for stability checking
        self.frame_buffer = deque(maxlen=stability_frames)
        
        # Statistics
        self.frames_processed = 0
        self.last_detection_count = 0
    
    def initialize(self) -> bool:
        """Initialize background subtractor"""
        try:
            self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
                history=self.history,
                varThreshold=self.var_threshold,
                detectShadows=self.detect_shadows
            )
            
            # Set learning rate
            self.bg_subtractor.setBackgroundRatio(self.learning_rate)
            
            self.initialized = True
            print("[PRESENCE] ✓ Detector initialized")
            return True
        
        except Exception as exc:
            log_exception("PresenceDetector: initialization error", exc)
            return False
    
    def detect(self, frame: np.ndarray, zones: List[Dict]) -> List[DetectionResult]:
        """
        Detect objects in zones
        
        Args:
            frame: Input BGR image
            zones: List of zone dicts
        
        Returns:
            List of DetectionResult, one per zone
        """
        if not self.initialized:
            self.initialize()
        
        self.frames_processed += 1
        results = []
        
        try:
            # Apply background subtraction
            fg_mask = self.bg_subtractor.apply(frame, learningRate=self.learning_rate)
            
            # Morphological operations to clean up noise
            fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, self.morph_kernel)
            fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, self.morph_kernel)
            
            # Find contours
            contours, _ = cv2.findContours(
                fg_mask,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )
            
            # Filter by area and get bounding boxes
            all_boxes = []
            for contour in contours:
                area = cv2.contourArea(contour)
                if area >= self.min_blob_area:
                    x, y, w, h = cv2.boundingRect(contour)
                    all_boxes.append((x, y, w, h))
            
            # Check each zone
            for zone_dict in zones:
                zone = Zone.from_dict(zone_dict) if not isinstance(zone_dict, Zone) else zone_dict
                
                # Find boxes that overlap with this zone
                zone_boxes = []
                for box in all_boxes:
                    x, y, w, h = box
                    # Check if box center is in zone
                    center_x = x + w // 2
                    center_y = y + h // 2
                    
                    if zone.point_in_polygon(center_x, center_y):
                        zone_boxes.append(box)
                
                # Create result
                detected = len(zone_boxes) > 0
                confidence = min(1.0, len(zone_boxes) * 0.3 + 0.4) if detected else 0.0
                
                result = DetectionResult(
                    detected=detected,
                    boxes=zone_boxes,
                    confidence=confidence,
                    metadata={
                        "zone_id": zone.zone_id,
                        "zone_name": zone.name,
                        "object_count": len(zone_boxes),
                        "total_blobs": len(all_boxes)
                    }
                )
                
                results.append(result)
            
            self.last_detection_count = len(all_boxes)
            
        except Exception as exc:
            log_exception("PresenceDetector: detection error", exc, level="warning")
            # Return empty results on error
            for zone_dict in zones:
                zone = Zone.from_dict(zone_dict) if not isinstance(zone_dict, Zone) else zone_dict
                results.append(DetectionResult(
                    detected=False,
                    boxes=[],
                    confidence=0.0,
                    metadata={"zone_id": zone.zone_id, "error": str(e)}
                ))
        
        return results
    
    def check_stability(self, current_boxes: List[Tuple[int, int, int, int]]) -> bool:
        """
        Check if detected objects are stationary
        
        Args:
            current_boxes: Current frame's detection boxes
        
        Returns:
            True if objects are stable across frames
        """
        # Add current frame to buffer
        self.frame_buffer.append(current_boxes)
        
        # Need full buffer to check stability
        if len(self.frame_buffer) < self.stability_frames:
            return False
        
        # Check if roughly same number of objects across frames
        counts = [len(boxes) for boxes in self.frame_buffer]
        if max(counts) - min(counts) > 1:
            return False
        
        # Check if box positions are similar
        # (Simple check: compare centers of first and last frame)
        if len(current_boxes) == 0:
            return False
        
        first_boxes = self.frame_buffer[0]
        if len(first_boxes) != len(current_boxes):
            return False
        
        # Compare box centers (allowing some movement tolerance)
        tolerance = 20  # pixels
        for i in range(len(current_boxes)):
            x1, y1, w1, h1 = first_boxes[i]
            x2, y2, w2, h2 = current_boxes[i]
            
            center1 = (x1 + w1 // 2, y1 + h1 // 2)
            center2 = (x2 + w2 // 2, y2 + h2 // 2)
            
            distance = np.sqrt((center1[0] - center2[0])**2 + (center1[1] - center2[1])**2)
            if distance > tolerance:
                return False
        
        return True
    
    def reset(self):
        """Reset background model and buffers"""
        if self.bg_subtractor:
            # Recreate background subtractor
            self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
                history=self.history,
                varThreshold=self.var_threshold,
                detectShadows=self.detect_shadows
            )
            self.bg_subtractor.setBackgroundRatio(self.learning_rate)
        
        self.frame_buffer.clear()
        self.frames_processed = 0
        print("[PRESENCE] Background model reset")
    
    def cleanup(self):
        """Cleanup resources"""
        self.bg_subtractor = None
        self.frame_buffer.clear()
        self.initialized = False
        print("[PRESENCE] Detector cleaned up")
    
    def get_stats(self) -> Dict:
        """Get detector statistics"""
        return {
            "frames_processed": self.frames_processed,
            "last_detection_count": self.last_detection_count,
            "buffer_size": len(self.frame_buffer),
            "initialized": self.initialized
        }


# Test the presence detector
if __name__ == "__main__":
    print("=== Presence Detector Tests ===\n")
    
    # Test 1: Initialize detector
    print("1. Initializing detector...")
    detector = PresenceDetector(min_blob_area=1200)
    success = detector.initialize()
    print(f"   Result: {'✓' if success else '✗'}\n")
    
    # Test 2: Create test frame (640x480 gray image)
    print("2. Creating test frames...")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame.fill(128)  # Gray background
    
    # Add a white rectangle (simulated object)
    cv2.rectangle(frame, (200, 150), (350, 300), (255, 255, 255), -1)
    
    print(f"   Frame shape: {frame.shape}")
    print(f"   Frame dtype: {frame.dtype}\n")
    
    # Test 3: Create test zone
    print("3. Creating test zone...")
    test_zone = {
        "zone_id": "test_zone",
        "name": "Test Area",
        "type": "trigger",
        "polygon": [[100, 100], [400, 100], [400, 350], [100, 350]],
        "enabled": True,
        "notes": ""
    }
    zones = [test_zone]
    print(f"   Zone: {test_zone['name']}\n")
    
    # Test 4: Process frames to build background
    print("4. Building background model...")
    for i in range(10):
        # Feed empty frames first
        empty_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        empty_frame.fill(128)
        detector.detect(empty_frame, zones)
    print(f"   Processed 10 background frames\n")
    
    # Test 5: Detect object
    print("5. Detecting object in frame...")
    results = detector.detect(frame, zones)
    
    for result in results:
        print(f"   Zone: {result.metadata['zone_name']}")
        print(f"   Detected: {result.detected}")
        print(f"   Objects: {result.metadata['object_count']}")
        print(f"   Boxes: {len(result.boxes)}")
        print(f"   Confidence: {result.confidence:.2f}\n")
    
    # Test 6: Check stability
    print("6. Testing stability detection...")
    # Process same frame multiple times
    for i in range(3):
        results = detector.detect(frame, zones)
        if results[0].detected:
            stable = detector.check_stability(results[0].boxes)
            print(f"   Frame {i+1}: Stable = {stable}")
    print()
    
    # Test 7: Get stats
    print("7. Getting detector stats...")
    stats = detector.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")
    print()
    
    # Test 8: Reset and cleanup
    print("8. Testing reset and cleanup...")
    detector.reset()
    detector.cleanup()
    print("   ✓ Reset and cleanup complete\n")
    
    print("✓ Presence detector tests complete!")
