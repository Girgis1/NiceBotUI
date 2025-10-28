"""
FastSAM (Fast Segment Anything Model) detector for beauty products.

FastSAM provides better segmentation masks than YOLO while maintaining
real-time performance (~18 FPS on CPU, ~90 FPS on GPU).

Based on: https://docs.ultralytics.com/models/fast-sam/
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

try:
    import cv2
    import numpy as np
    from ultralytics import FastSAM
    HAVE_DEPS = True
except ImportError:
    cv2 = None
    np = None
    FastSAM = None
    HAVE_DEPS = False


@dataclass
class FastSAMDetection:
    """Single detection result from FastSAM"""
    mask: np.ndarray  # Segmentation mask
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float
    area: int  # Mask area in pixels


@dataclass
class FastSAMResult:
    """Complete detection result for a frame"""
    detections: List[FastSAMDetection]
    frame_overlay: Optional[np.ndarray] = None
    inference_time_ms: float = 0.0
    total_detected: int = 0


class FastSAMDetector:
    """
    FastSAM detector for beauty products.
    
    Features:
    - 18 FPS on CPU (2x slower than YOLO but better masks)
    - 90 FPS on GPU
    - Better segmentation quality than YOLO
    - Auto mode: Detect everything, filter by size
    - Region mode: Detect only in specific area (coming soon)
    - Interactive mode: Click to segment (coming soon)
    """
    
    # Default model weights directory
    MODELS_DIR = Path(__file__).parent.parent / "models" / "vision"
    
    # Available model sizes
    MODEL_SIZES = {
        'small': 's',   # FastSAM-s: 23.7 MB, ~18 FPS CPU
        'large': 'x',   # FastSAM-x: Larger but slower
    }
    
    def __init__(
        self,
        model_size: str = "small",  # "small" or "large"
        confidence_threshold: float = 0.4,
        iou_threshold: float = 0.9,
        device: str = "cpu",  # "cpu" or "cuda"
        selection_mode: str = "all",  # "all", "largest", "center_region", "point_click"
        min_object_size: int = 50,  # Minimum object size in pixels
        max_object_size: int = 50000,  # Maximum object size in pixels
        center_region_percent: float = 50.0,  # For center_region mode (% of frame)
        retina_masks: bool = True,  # High-quality masks
        imgsz: int = 1024,  # Input image size
    ):
        """
        Initialize FastSAM detector.
        
        Args:
            model_size: Model size ("small" or "large")
            confidence_threshold: Minimum confidence (0-1)
            iou_threshold: IoU threshold for filtering
            device: Device to run on ("cpu" or "cuda")
            selection_mode: Object selection mode:
                - "all": Return all detected objects
                - "largest": Return only largest object
                - "center_region": Return objects in center region
                - "point_click": Return object at clicked point
            min_object_size: Filter out objects smaller than this
            max_object_size: Filter out objects larger than this
            center_region_percent: Size of center region (0-100%)
            retina_masks: Use high-quality masks (True recommended)
            imgsz: Input image size (1024 recommended)
        """
        if not HAVE_DEPS:
            raise RuntimeError(
                "Missing dependencies. Install: pip install ultralytics opencv-python numpy"
            )
        
        self.model_size = model_size
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.device = device
        self.selection_mode = selection_mode
        self.min_object_size = min_object_size
        self.max_object_size = max_object_size
        self.center_region_percent = center_region_percent
        self.retina_masks = retina_masks
        self.imgsz = imgsz
        
        # For point click mode
        self.last_click_point: Optional[Tuple[int, int]] = None
        
        self.model: Optional[FastSAM] = None
        self._load_model()
        
        # Performance tracking
        self.inference_times: List[float] = []
        self.max_history = 30
    
    def _load_model(self):
        """Load FastSAM model"""
        try:
            size_code = self.MODEL_SIZES.get(self.model_size, 's')
            model_name = f"FastSAM-{size_code}.pt"
            
            # Check if model exists locally
            local_path = self.MODELS_DIR / model_name
            if local_path.exists():
                print(f"[FASTSAM] Loading local model: {local_path}")
                self.model = FastSAM(str(local_path))
            else:
                # Download from Ultralytics
                print(f"[FASTSAM] Downloading model: {model_name}")
                self.model = FastSAM(model_name)
                
                # Save to local directory for future use
                self.MODELS_DIR.mkdir(parents=True, exist_ok=True)
            
            print(f"[FASTSAM] Model loaded successfully on {self.device}")
            
        except Exception as e:
            print(f"[FASTSAM][ERROR] Failed to load model: {e}")
            self.model = None
    
    def set_click_point(self, x: int, y: int):
        """
        Set click point for point_click mode.
        
        Args:
            x: X coordinate
            y: Y coordinate
        """
        self.last_click_point = (x, y)
    
    def detect(
        self,
        frame: np.ndarray,
        click_point: Optional[Tuple[int, int]] = None,
    ) -> FastSAMResult:
        """
        Run detection on a frame.
        
        Args:
            frame: Input BGR image
            click_point: Optional click point for point_click mode (x, y)
        
        Returns:
            FastSAMResult with selected detection(s) based on selection_mode
        """
        # Update click point if provided
        if click_point is not None:
            self.last_click_point = click_point
        if self.model is None or frame is None:
            return FastSAMResult(detections=[], total_detected=0)
        
        start_time = time.perf_counter()
        
        try:
            # Run FastSAM inference (everything mode)
            results = self.model(
                frame,
                device=self.device,
                retina_masks=self.retina_masks,
                imgsz=self.imgsz,
                conf=self.confidence_threshold,
                iou=self.iou_threshold,
                verbose=False,
            )
            
            inference_time = (time.perf_counter() - start_time) * 1000
            self._update_inference_time(inference_time)
            
            # Parse results
            detections: List[FastSAMDetection] = []
            
            if len(results) > 0:
                result = results[0]  # First image
                
                if hasattr(result, 'masks') and result.masks is not None:
                    masks = result.masks.data.cpu().numpy()
                    boxes = result.boxes.xyxy.cpu().numpy()
                    confidences = result.boxes.conf.cpu().numpy()
                    
                    for idx in range(len(masks)):
                        mask = masks[idx]
                        bbox = tuple(boxes[idx].astype(int).tolist())
                        confidence = float(confidences[idx])
                        
                        # Calculate mask area
                        h, w = frame.shape[:2]
                        mask_resized = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)
                        mask_binary = mask_resized > 0.5
                        area = int(np.sum(mask_binary))
                        
                        # Filter by size
                        if area < self.min_object_size or area > self.max_object_size:
                            continue
                        
                        detections.append(FastSAMDetection(
                            mask=mask_binary,
                            bbox=bbox,
                            confidence=confidence,
                            area=area,
                        ))
            
            # Apply selection mode filters
            detections = self._apply_selection_mode(detections, frame)
            
            return FastSAMResult(
                detections=detections,
                inference_time_ms=inference_time,
                total_detected=len(detections),
            )
        
        except Exception as e:
            print(f"[FASTSAM][ERROR] Detection failed: {e}")
            return FastSAMResult(detections=[], total_detected=0)
    
    def _apply_selection_mode(
        self,
        detections: List[FastSAMDetection],
        frame: np.ndarray,
    ) -> List[FastSAMDetection]:
        """
        Apply selection mode filtering to detections.
        
        Args:
            detections: List of all detections
            frame: Input frame (for region calculations)
        
        Returns:
            Filtered detections based on selection_mode
        """
        if not detections:
            return detections
        
        h, w = frame.shape[:2]
        
        # Mode 1: All objects (no filtering)
        if self.selection_mode == "all":
            return detections
        
        # Mode 2: Largest object only
        elif self.selection_mode == "largest":
            # Find detection with largest area
            largest = max(detections, key=lambda d: d.area)
            return [largest]
        
        # Mode 3: Center region only
        elif self.selection_mode == "center_region":
            # Calculate center region bounds
            region_size = self.center_region_percent / 100.0
            margin = (1.0 - region_size) / 2.0
            
            x1 = int(w * margin)
            y1 = int(h * margin)
            x2 = int(w * (1.0 - margin))
            y2 = int(h * (1.0 - margin))
            
            # Filter detections by center point in region
            filtered = []
            for det in detections:
                bx1, by1, bx2, by2 = det.bbox
                center_x = (bx1 + bx2) / 2
                center_y = (by1 + by2) / 2
                
                if x1 <= center_x <= x2 and y1 <= center_y <= y2:
                    filtered.append(det)
            
            return filtered
        
        # Mode 4: Point click - return object at clicked point
        elif self.selection_mode == "point_click":
            if self.last_click_point is None:
                # No click yet, return largest as fallback
                largest = max(detections, key=lambda d: d.area)
                return [largest]
            
            click_x, click_y = self.last_click_point
            
            # Find detection that contains the click point
            for det in detections:
                # Check if click point is in bbox first (fast check)
                bx1, by1, bx2, by2 = det.bbox
                if bx1 <= click_x <= bx2 and by1 <= click_y <= by2:
                    # Check if point is actually in mask (precise check)
                    if click_y < det.mask.shape[0] and click_x < det.mask.shape[1]:
                        if det.mask[click_y, click_x]:
                            return [det]
            
            # No object at click point, return closest to click
            def distance_to_click(det):
                bx1, by1, bx2, by2 = det.bbox
                center_x = (bx1 + bx2) / 2
                center_y = (by1 + by2) / 2
                return ((center_x - click_x)**2 + (center_y - click_y)**2)**0.5
            
            closest = min(detections, key=distance_to_click)
            return [closest]
        
        # Unknown mode, return all
        return detections
    
    def visualize(
        self,
        frame: np.ndarray,
        result: FastSAMResult,
        show_boxes: bool = True,
        show_masks: bool = True,
        show_confidence: bool = True,
        mask_alpha: float = 0.5,
        box_thickness: int = 2,
        font_scale: float = 0.6,
    ) -> np.ndarray:
        """
        Draw detection results on frame.
        
        Args:
            frame: Input frame
            result: Detection result
            show_boxes: Draw bounding boxes
            show_masks: Draw segmentation masks
            show_confidence: Show confidence scores
            mask_alpha: Mask transparency (0-1)
            box_thickness: Box line thickness
            font_scale: Label font size
        
        Returns:
            Annotated frame
        """
        if frame is None:
            return frame
        
        annotated = frame.copy()
        
        # Color palette (bright colors for visibility)
        colors = [
            (255, 68, 51),   # Red
            (51, 255, 153),  # Green
            (51, 153, 255),  # Blue
            (255, 153, 51),  # Orange
            (255, 51, 255),  # Magenta
            (51, 255, 255),  # Cyan
            (153, 51, 255),  # Purple
            (255, 255, 51),  # Yellow
        ]
        
        for idx, detection in enumerate(result.detections):
            color = colors[idx % len(colors)]
            
            # Draw mask
            if show_masks:
                annotated = self._draw_mask(annotated, detection.mask, color, alpha=mask_alpha)
            
            # Draw box
            if show_boxes:
                x1, y1, x2, y2 = detection.bbox
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, box_thickness)
            
            # Draw confidence
            if show_confidence:
                label = f"{detection.confidence:.2f}"
                x1, y1, _, _ = detection.bbox
                self._draw_label(annotated, label, (x1, y1), color, font_scale=font_scale)
        
        # Draw selection mode indicators
        self._draw_mode_indicators(annotated)
        
        # Draw performance info
        if len(self.inference_times) > 0:
            avg_time = sum(self.inference_times) / len(self.inference_times)
            fps = 1000.0 / avg_time if avg_time > 0 else 0
            mode_name = self.selection_mode.replace("_", " ").title()
            info_text = f"FastSAM ({mode_name}): {fps:.1f} FPS | {avg_time:.1f}ms | Objects: {result.total_detected}"
            
            cv2.putText(
                annotated,
                info_text,
                (10, annotated.shape[0] - 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                1,
                cv2.LINE_AA,
            )
        
        return annotated
    
    def _draw_mode_indicators(self, frame: np.ndarray):
        """Draw visual indicators for current selection mode"""
        h, w = frame.shape[:2]
        
        # Draw center region box for center_region mode
        if self.selection_mode == "center_region":
            region_size = self.center_region_percent / 100.0
            margin = (1.0 - region_size) / 2.0
            
            x1 = int(w * margin)
            y1 = int(h * margin)
            x2 = int(w * (1.0 - margin))
            y2 = int(h * (1.0 - margin))
            
            # Draw semi-transparent overlay outside region
            overlay = frame.copy()
            overlay[:] = overlay * 0.5  # Darken
            frame[:y1, :] = overlay[:y1, :]  # Top
            frame[y2:, :] = overlay[y2:, :]  # Bottom
            frame[y1:y2, :x1] = overlay[y1:y2, :x1]  # Left
            frame[y1:y2, x2:] = overlay[y1:y2, x2:]  # Right
            
            # Draw region box
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
            cv2.putText(
                frame,
                f"Center Region ({self.center_region_percent:.0f}%)",
                (x1 + 10, y1 + 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )
        
        # Draw click point for point_click mode
        elif self.selection_mode == "point_click" and self.last_click_point is not None:
            cx, cy = self.last_click_point
            # Draw crosshair
            cv2.drawMarker(
                frame,
                (cx, cy),
                (0, 255, 255),
                cv2.MARKER_CROSS,
                30,
                3,
            )
            # Draw circle
            cv2.circle(frame, (cx, cy), 15, (0, 255, 255), 2)
            # Draw label
            cv2.putText(
                frame,
                "Click Point",
                (cx + 20, cy - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )
    
    def _draw_mask(
        self,
        frame: np.ndarray,
        mask: np.ndarray,
        color: Tuple[int, int, int],
        alpha: float = 0.5,
    ) -> np.ndarray:
        """Draw segmentation mask on frame"""
        try:
            # Ensure mask is right size
            if mask.shape[:2] != frame.shape[:2]:
                mask = cv2.resize(
                    mask.astype(np.uint8),
                    (frame.shape[1], frame.shape[0]),
                    interpolation=cv2.INTER_LINEAR
                ) > 0.5
            
            # Create colored mask
            colored_mask = np.zeros_like(frame)
            colored_mask[mask] = color
            
            # Blend with frame
            frame = cv2.addWeighted(frame, 1.0, colored_mask, alpha, 0)
            
        except Exception as e:
            print(f"[FASTSAM][WARN] Failed to draw mask: {e}")
        
        return frame
    
    def _draw_label(
        self,
        frame: np.ndarray,
        text: str,
        position: Tuple[int, int],
        color: Tuple[int, int, int],
        font_scale: float = 0.6,
    ):
        """Draw text label with background"""
        font = cv2.FONT_HERSHEY_SIMPLEX
        thickness = 2
        
        # Get text size
        (text_width, text_height), baseline = cv2.getTextSize(
            text, font, font_scale, thickness
        )
        
        x, y = position
        
        # Draw background rectangle
        cv2.rectangle(
            frame,
            (x, y - text_height - 8),
            (x + text_width + 8, y),
            color,
            -1,  # Filled
        )
        
        # Draw text
        cv2.putText(
            frame,
            text,
            (x + 4, y - 4),
            font,
            font_scale,
            (255, 255, 255),
            thickness,
            cv2.LINE_AA,
        )
    
    def _update_inference_time(self, time_ms: float):
        """Track inference time for FPS calculation"""
        self.inference_times.append(time_ms)
        if len(self.inference_times) > self.max_history:
            self.inference_times.pop(0)
    
    def get_average_fps(self) -> float:
        """Get average FPS over recent inferences"""
        if not self.inference_times:
            return 0.0
        avg_time = sum(self.inference_times) / len(self.inference_times)
        return 1000.0 / avg_time if avg_time > 0 else 0.0
    
    @classmethod
    def list_available_models(cls) -> List[Dict[str, Any]]:
        """List all available FastSAM models"""
        models = []
        for size_name, size_code in cls.MODEL_SIZES.items():
            model_name = f"FastSAM-{size_code}"
            local_path = cls.MODELS_DIR / f"{model_name}.pt"
            
            fps_estimate = "18 FPS (CPU)" if size_name == "small" else "12 FPS (CPU)"
            
            models.append({
                "name": model_name,
                "size": size_name,
                "path": str(local_path),
                "exists": local_path.exists(),
                "description": f"FastSAM {size_name.title()} - Better masks than YOLO ({fps_estimate})",
            })
        
        return models
    
    @classmethod
    def download_model(cls, size: str = "small") -> bool:
        """
        Download a specific FastSAM model.
        
        Args:
            size: Model size ("small" or "large")
        
        Returns:
            True if successful
        """
        try:
            size_code = cls.MODEL_SIZES.get(size, 's')
            model_name = f"FastSAM-{size_code}.pt"
            
            print(f"[FASTSAM] Downloading {model_name}...")
            model = FastSAM(model_name)
            
            # Save to models directory
            cls.MODELS_DIR.mkdir(parents=True, exist_ok=True)
            print(f"[FASTSAM] Model downloaded successfully")
            
            return True
            
        except Exception as e:
            print(f"[FASTSAM][ERROR] Failed to download model: {e}")
            return False


__all__ = [
    "FastSAMDetector",
    "FastSAMDetection",
    "FastSAMResult",
]

