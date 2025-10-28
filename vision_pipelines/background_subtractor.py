"""
Background subtraction for detecting new objects in scene.

This module provides foreground/background segmentation to identify:
- New objects appearing in the scene
- Changed objects (moved, added, removed)
- Motion detection

Perfect for: "What's new?" detection in robot cells where most of the
scene is static (robot arm, table, walls) and you only care about new products.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

try:
    import cv2
    import numpy as np
    HAVE_DEPS = True
except ImportError:
    cv2 = None
    np = None
    HAVE_DEPS = False


@dataclass
class BackgroundSubtractionResult:
    """Result from background subtraction"""
    foreground_mask: Optional[np.ndarray] = None  # Binary mask of changed regions
    foreground_count: int = 0  # Number of foreground pixels
    foreground_percent: float = 0.0  # Percentage of frame that's foreground
    has_new_objects: bool = False  # True if significant change detected
    overlay: Optional[np.ndarray] = None  # Visualization


class BackgroundSubtractor:
    """
    Detect new objects by subtracting a learned background.
    
    Features:
    - Automatic background learning
    - Adaptive to lighting changes
    - Noise filtering
    - Morphological processing for clean masks
    
    Use cases:
    - Detect when new product arrives in robot cell
    - Ignore static background (robot, table, walls)
    - Trigger actions only when scene changes
    - Focus YOLO detection on changed regions only (saves compute)
    """
    
    def __init__(
        self,
        learning_rate: float = 0.001,
        threshold: int = 30,
        min_foreground_percent: float = 0.5,
        blur_kernel_size: int = 5,
        morph_kernel_size: int = 3,
        use_adaptive: bool = True,
    ):
        """
        Initialize background subtractor.
        
        Args:
            learning_rate: How fast to adapt to lighting changes (0.001 = slow, 0.1 = fast)
            threshold: Pixel difference threshold (lower = more sensitive)
            min_foreground_percent: Minimum % of frame to consider "new object" (0.5%)
            blur_kernel_size: Gaussian blur size for noise reduction
            morph_kernel_size: Morphology kernel for cleaning mask
            use_adaptive: Use adaptive threshold (better for lighting changes)
        """
        if not HAVE_DEPS:
            raise RuntimeError("OpenCV and NumPy required for background subtraction")
        
        self.learning_rate = learning_rate
        self.threshold = threshold
        self.min_foreground_percent = min_foreground_percent
        self.blur_kernel_size = blur_kernel_size
        self.morph_kernel_size = morph_kernel_size
        self.use_adaptive = use_adaptive
        
        self.background: Optional[np.ndarray] = None
        self._initialized = False
        
        # Create morphology kernel
        self.morph_kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (morph_kernel_size, morph_kernel_size)
        )
    
    def reset(self):
        """Reset background model"""
        self.background = None
        self._initialized = False
    
    def learn_background(self, frame: np.ndarray, num_frames: int = 30) -> bool:
        """
        Learn background from static scene.
        
        Call this when the scene is empty (no products), and the robot is not moving.
        
        Args:
            frame: Input frame
            num_frames: Number of frames to average (default 30)
        
        Returns:
            True if learning complete
        """
        if frame is None:
            return False
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (self.blur_kernel_size, self.blur_kernel_size), 0)
        
        if self.background is None:
            self.background = gray.astype(np.float32)
            return False
        else:
            # Accumulate
            cv2.accumulateWeighted(gray, self.background, 1.0 / num_frames)
            return True
    
    def detect_foreground(
        self,
        frame: np.ndarray,
        auto_update_background: bool = True,
    ) -> BackgroundSubtractionResult:
        """
        Detect foreground (new objects) in frame.
        
        Args:
            frame: Input frame
            auto_update_background: Automatically adapt to slow lighting changes
        
        Returns:
            BackgroundSubtractionResult
        """
        if frame is None:
            return BackgroundSubtractionResult()
        
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (self.blur_kernel_size, self.blur_kernel_size), 0)
        
        # Initialize background if needed
        if self.background is None:
            self.background = gray.astype(np.float32)
            self._initialized = False
            return BackgroundSubtractionResult()
        
        if not self._initialized:
            # Need more frames to build stable background
            cv2.accumulateWeighted(gray, self.background, 0.1)
            if np.std(self.background) > 10:  # Check if background has enough variation
                self._initialized = True
            return BackgroundSubtractionResult()
        
        # Compute difference
        diff = cv2.absdiff(gray, self.background.astype(np.uint8))
        
        # Threshold
        if self.use_adaptive:
            mask = cv2.adaptiveThreshold(
                diff,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                11,
                -self.threshold,
            )
        else:
            _, mask = cv2.threshold(diff, self.threshold, 255, cv2.THRESH_BINARY)
        
        # Morphological operations to clean up noise
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.morph_kernel)  # Remove noise
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.morph_kernel)  # Fill holes
        
        # Calculate foreground statistics
        foreground_pixels = np.sum(mask > 0)
        total_pixels = mask.size
        foreground_percent = (foreground_pixels / total_pixels) * 100
        
        has_new_objects = foreground_percent >= self.min_foreground_percent
        
        # Update background (slowly adapt to lighting changes)
        if auto_update_background and not has_new_objects:
            cv2.accumulateWeighted(gray, self.background, self.learning_rate)
        
        return BackgroundSubtractionResult(
            foreground_mask=mask,
            foreground_count=int(foreground_pixels),
            foreground_percent=foreground_percent,
            has_new_objects=has_new_objects,
        )
    
    def visualize(
        self,
        frame: np.ndarray,
        result: BackgroundSubtractionResult,
        color: Tuple[int, int, int] = (0, 255, 0),  # Green
        alpha: float = 0.5,
    ) -> np.ndarray:
        """
        Visualize foreground detection.
        
        Args:
            frame: Original frame
            result: Detection result
            color: Overlay color (BGR)
            alpha: Transparency (0-1)
        
        Returns:
            Annotated frame
        """
        if frame is None or result.foreground_mask is None:
            return frame
        
        # Create overlay
        overlay = frame.copy()
        foreground_color = np.array(color, dtype=np.uint8)
        overlay[result.foreground_mask > 0] = foreground_color
        
        # Blend
        annotated = cv2.addWeighted(frame, 1 - alpha, overlay, alpha, 0)
        
        # Add text
        status_text = "NEW OBJECT!" if result.has_new_objects else "No change"
        color_text = (0, 255, 0) if result.has_new_objects else (200, 200, 200)
        
        cv2.putText(
            annotated,
            status_text,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            color_text,
            2,
            cv2.LINE_AA,
        )
        
        cv2.putText(
            annotated,
            f"Changed: {result.foreground_percent:.1f}%",
            (10, 70),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        
        return annotated
    
    def get_foreground_bbox(self, mask: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """
        Get bounding box of foreground region.
        
        Args:
            mask: Foreground mask
        
        Returns:
            (x, y, w, h) or None if no foreground
        """
        if mask is None:
            return None
        
        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return None
        
        # Get bounding box of all contours
        x_min, y_min = mask.shape[1], mask.shape[0]
        x_max, y_max = 0, 0
        
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            x_min = min(x_min, x)
            y_min = min(y_min, y)
            x_max = max(x_max, x + w)
            y_max = max(y_max, y + h)
        
        if x_max > x_min and y_max > y_min:
            return (x_min, y_min, x_max - x_min, y_max - y_min)
        
        return None


# ============================================================
# Integration with YOLO detector
# ============================================================

def detect_new_objects_with_yolo(
    frame: np.ndarray,
    bg_subtractor: BackgroundSubtractor,
    yolo_detector,  # BeautyProductDetector
    use_roi: bool = True,
) -> Tuple[BackgroundSubtractionResult, any]:
    """
    Combine background subtraction with YOLO for efficient detection.
    
    Strategy:
    1. Use background subtraction to find WHERE things changed
    2. Only run YOLO on the changed region (saves compute)
    3. Return both results
    
    Args:
        frame: Input frame
        bg_subtractor: BackgroundSubtractor instance
        yolo_detector: BeautyProductDetector instance
        use_roi: Only run YOLO on changed region (faster)
    
    Returns:
        (BackgroundSubtractionResult, YOLODetectionResult)
    """
    # First pass: background subtraction (very fast)
    bg_result = bg_subtractor.detect_foreground(frame)
    
    if not bg_result.has_new_objects:
        # Nothing changed, skip YOLO
        return bg_result, None
    
    # Second pass: YOLO on changed region only
    if use_roi and bg_result.foreground_mask is not None:
        bbox = bg_subtractor.get_foreground_bbox(bg_result.foreground_mask)
        if bbox:
            x, y, w, h = bbox
            # Add padding
            pad = 20
            x = max(0, x - pad)
            y = max(0, y - pad)
            w = min(frame.shape[1] - x, w + 2 * pad)
            h = min(frame.shape[0] - y, h + 2 * pad)
            
            # Crop to ROI
            roi = frame[y:y+h, x:x+w]
            yolo_result = yolo_detector.detect(roi)
            
            # Adjust detection coordinates back to full frame
            for det in yolo_result.detections:
                box = list(det.box)
                box[0] += x  # x1
                box[1] += y  # y1
                box[2] += x  # x2
                box[3] += y  # y2
                det.box = tuple(box)
            
            return bg_result, yolo_result
    
    # Run YOLO on full frame
    yolo_result = yolo_detector.detect(frame)
    return bg_result, yolo_result


__all__ = [
    "BackgroundSubtractor",
    "BackgroundSubtractionResult",
    "detect_new_objects_with_yolo",
]

