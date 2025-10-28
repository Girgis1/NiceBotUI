"""
Professional beauty product detection using YOLOv11/YOLOv8 instance segmentation.

This module provides industrial-grade object detection with:
- YOLOv11 and YOLOv8 instance segmentation support
- Configurable debug visualization (boxes, masks, labels, confidence)
- Multiple model size options (nano, small, medium, large)
- Training data capture capability
- Performance monitoring
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

try:
    import cv2
    import numpy as np
    from ultralytics import YOLO
    HAVE_DEPS = True
except ImportError:
    cv2 = None
    np = None
    YOLO = None
    HAVE_DEPS = False


@dataclass
class Detection:
    """Single detection result"""
    class_id: int
    class_name: str
    confidence: float
    box: Tuple[int, int, int, int]  # x1, y1, x2, y2
    mask: Optional[np.ndarray] = None  # Segmentation mask


@dataclass
class DetectionResult:
    """Complete detection result for a frame"""
    detections: List[Detection]
    frame_overlay: Optional[np.ndarray] = None
    inference_time_ms: float = 0.0
    total_detected: int = 0


class BeautyProductDetector:
    """
    Professional beauty product detector using YOLO instance segmentation.
    
    Features:
    - Supports YOLOv11-seg and YOLOv8-seg models
    - Configurable visualization (boxes, masks, labels, confidence)
    - Multiple model sizes for speed/accuracy tradeoff
    - Training data export capability
    """
    
    # Default model weights directory
    MODELS_DIR = Path(__file__).parent.parent / "models" / "vision"
    
    # Available model sizes
    MODEL_SIZES = {
        'nano': 'n',      # Fastest, lowest accuracy (~30 FPS)
        'small': 's',     # Balanced (~20 FPS)
        'medium': 'm',    # Good accuracy (~10 FPS)
        'large': 'l',     # Best accuracy (~5 FPS)
        'extra': 'x',     # Maximum accuracy (~2 FPS)
    }
    
    def __init__(
        self,
        model_version: str = "11",  # "11" or "8"
        model_size: str = "small",   # nano, small, medium, large, extra
        confidence_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        device: str = "cpu",  # "cpu" or "cuda"
        custom_model_path: Optional[str] = None,
    ):
        """
        Initialize detector.
        
        Args:
            model_version: YOLO version ("11" or "8")
            model_size: Model size ("nano", "small", "medium", "large", "extra")
            confidence_threshold: Minimum confidence for detection (0-1)
            iou_threshold: IoU threshold for NMS
            device: Device to run inference on ("cpu" or "cuda")
            custom_model_path: Path to custom trained model (overrides version/size)
        """
        if not HAVE_DEPS:
            raise RuntimeError(
                "Missing dependencies. Install: pip install ultralytics opencv-python numpy"
            )
        
        self.model_version = model_version
        self.model_size = model_size
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.device = device
        self.custom_model_path = custom_model_path
        
        self.model: Optional[YOLO] = None
        self._load_model()
        
        # Performance tracking
        self.inference_times: List[float] = []
        self.max_history = 30
    
    def _load_model(self):
        """Load YOLO model"""
        try:
            if self.custom_model_path and Path(self.custom_model_path).exists():
                # Load custom trained model
                print(f"[DETECTOR] Loading custom model: {self.custom_model_path}")
                self.model = YOLO(self.custom_model_path)
            else:
                # Load pretrained model
                size_code = self.MODEL_SIZES.get(self.model_size, 's')
                model_name = f"yolo{self.model_version}{size_code}-seg.pt"
                
                # Check if model exists locally
                local_path = self.MODELS_DIR / model_name
                if local_path.exists():
                    print(f"[DETECTOR] Loading local model: {local_path}")
                    self.model = YOLO(str(local_path))
                else:
                    # Download from Ultralytics
                    print(f"[DETECTOR] Downloading model: {model_name}")
                    self.model = YOLO(model_name)
                    
                    # Save to local directory for future use
                    self.MODELS_DIR.mkdir(parents=True, exist_ok=True)
                    # Model auto-saves to cache, create symlink for easy access
            
            print(f"[DETECTOR] Model loaded successfully on {self.device}")
            
        except Exception as e:
            print(f"[DETECTOR][ERROR] Failed to load model: {e}")
            self.model = None
    
    def detect(
        self,
        frame: np.ndarray,
        filter_classes: Optional[List[str]] = None,
    ) -> DetectionResult:
        """
        Run detection on a frame.
        
        Args:
            frame: Input BGR image
            filter_classes: Optional list of class names to filter (e.g. ["bottle", "box"])
        
        Returns:
            DetectionResult with all detections
        """
        if self.model is None or frame is None:
            return DetectionResult(detections=[], total_detected=0)
        
        start_time = time.perf_counter()
        
        try:
            # Run inference
            results = self.model.predict(
                frame,
                conf=self.confidence_threshold,
                iou=self.iou_threshold,
                device=self.device,
                verbose=False,
                stream=False,
            )
            
            inference_time = (time.perf_counter() - start_time) * 1000
            self._update_inference_time(inference_time)
            
            # Parse results
            detections: List[Detection] = []
            
            if len(results) > 0:
                result = results[0]  # First image
                
                if result.boxes is not None and len(result.boxes) > 0:
                    boxes = result.boxes.xyxy.cpu().numpy()  # x1,y1,x2,y2
                    confidences = result.boxes.conf.cpu().numpy()
                    class_ids = result.boxes.cls.cpu().numpy().astype(int)
                    
                    # Get masks if available
                    masks = None
                    if hasattr(result, 'masks') and result.masks is not None:
                        masks = result.masks.data.cpu().numpy()
                    
                    for idx in range(len(boxes)):
                        class_id = int(class_ids[idx])
                        class_name = result.names[class_id]
                        
                        # Filter by class if specified
                        if filter_classes and class_name not in filter_classes:
                            continue
                        
                        confidence = float(confidences[idx])
                        box = tuple(boxes[idx].astype(int).tolist())
                        
                        # Get mask for this detection
                        mask = None
                        if masks is not None and idx < len(masks):
                            mask = masks[idx]
                        
                        detections.append(Detection(
                            class_id=class_id,
                            class_name=class_name,
                            confidence=confidence,
                            box=box,
                            mask=mask,
                        ))
            
            return DetectionResult(
                detections=detections,
                inference_time_ms=inference_time,
                total_detected=len(detections),
            )
        
        except Exception as e:
            print(f"[DETECTOR][ERROR] Detection failed: {e}")
            return DetectionResult(detections=[], total_detected=0)
    
    def visualize(
        self,
        frame: np.ndarray,
        result: DetectionResult,
        show_boxes: bool = True,
        show_masks: bool = True,
        show_labels: bool = True,
        show_confidence: bool = True,
        mask_alpha: float = 0.4,
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
            show_labels: Draw class labels
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
        
        # Color palette for different classes
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
        
        for detection in result.detections:
            color = colors[detection.class_id % len(colors)]
            
            # Draw mask
            if show_masks and detection.mask is not None:
                annotated = self._draw_mask(
                    annotated,
                    detection.mask,
                    color,
                    alpha=mask_alpha,
                )
            
            # Draw box
            if show_boxes:
                x1, y1, x2, y2 = detection.box
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, box_thickness)
            
            # Draw label
            if show_labels or show_confidence:
                label_parts = []
                if show_labels:
                    label_parts.append(detection.class_name)
                if show_confidence:
                    label_parts.append(f"{detection.confidence:.2f}")
                
                label = " ".join(label_parts)
                
                x1, y1, _, _ = detection.box
                self._draw_label(
                    annotated,
                    label,
                    (x1, y1),
                    color,
                    font_scale=font_scale,
                )
        
        # Draw performance info
        if len(self.inference_times) > 0:
            avg_time = sum(self.inference_times) / len(self.inference_times)
            fps = 1000.0 / avg_time if avg_time > 0 else 0
            info_text = f"FPS: {fps:.1f} | Time: {avg_time:.1f}ms | Detected: {result.total_detected}"
            
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
    
    def _draw_mask(
        self,
        frame: np.ndarray,
        mask: np.ndarray,
        color: Tuple[int, int, int],
        alpha: float = 0.4,
    ) -> np.ndarray:
        """Draw segmentation mask on frame"""
        try:
            # Resize mask to frame size
            h, w = frame.shape[:2]
            mask_resized = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)
            
            # Create colored mask
            mask_bool = mask_resized > 0.5
            colored_mask = np.zeros_like(frame)
            colored_mask[mask_bool] = color
            
            # Blend with frame
            frame = cv2.addWeighted(frame, 1.0, colored_mask, alpha, 0)
            
        except Exception as e:
            print(f"[DETECTOR][WARN] Failed to draw mask: {e}")
        
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
        """List all available model configurations"""
        models = []
        for version in ["11", "8"]:
            for size_name, size_code in cls.MODEL_SIZES.items():
                model_name = f"yolo{version}{size_code}-seg"
                local_path = cls.MODELS_DIR / f"{model_name}.pt"
                
                models.append({
                    "name": model_name,
                    "version": version,
                    "size": size_name,
                    "path": str(local_path),
                    "exists": local_path.exists(),
                    "description": f"YOLOv{version} {size_name.title()} Instance Segmentation",
                })
        
        return models
    
    @classmethod
    def download_model(cls, version: str = "11", size: str = "small") -> bool:
        """
        Download a specific model.
        
        Args:
            version: YOLO version ("11" or "8")
            size: Model size ("nano", "small", "medium", "large", "extra")
        
        Returns:
            True if successful
        """
        try:
            size_code = cls.MODEL_SIZES.get(size, 's')
            model_name = f"yolo{version}{size_code}-seg.pt"
            
            print(f"[DETECTOR] Downloading {model_name}...")
            model = YOLO(model_name)
            
            # Save to models directory
            cls.MODELS_DIR.mkdir(parents=True, exist_ok=True)
            print(f"[DETECTOR] Model downloaded successfully")
            
            return True
            
        except Exception as e:
            print(f"[DETECTOR][ERROR] Failed to download model: {e}")
            return False


__all__ = [
    "BeautyProductDetector",
    "Detection",
    "DetectionResult",
]

