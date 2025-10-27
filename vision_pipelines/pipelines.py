"""Concrete pipeline implementations."""

from __future__ import annotations

import math
import time
from typing import Any, Dict

from .base import VisionPipeline, VisionResult, np

try:  # Optional dependency
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - handled gracefully
    cv2 = None  # type: ignore


class HandDetectionPipeline(VisionPipeline):
    """Lightweight skin-tone driven hand detector."""

    pipeline_type = "hand_detection"

    def process(self, frame: "np.ndarray", timestamp: float) -> VisionResult:
        if np is None or frame is None:
            return VisionResult(
                pipeline_id=self.pipeline_id,
                label="Hand Detection",
                detected=False,
                confidence=0.0,
                overlay=None,
                metadata={
                    "pipeline_type": self.pipeline_type,
                    "dashboard_indicator": self.config.get("dashboard_indicator", True),
                    "record_training": False,
                },
            )

        min_conf = float(self.config.get("min_confidence", 0.35))
        debug_overlay = bool(self.config.get("debug_overlay", False))
        dashboard_indicator = bool(self.config.get("dashboard_indicator", True))

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV) if cv2 is not None else None
        mask = None
        if hsv is not None:
            lower = np.array([0, 30, 60], dtype=np.uint8)
            upper = np.array([20, 150, 255], dtype=np.uint8)
            mask = cv2.inRange(hsv, lower, upper)
            mask = cv2.medianBlur(mask, 5)
            coverage = float(np.sum(mask > 0) / mask.size)
        else:
            # Fallback heuristic using RGB variance
            diff = np.std(frame.astype("float32")) if np is not None else 0.0
            coverage = min(1.0, max(0.0, diff / 100.0))

        detected = coverage >= min_conf
        confidence = float(min(1.0, coverage * 1.5))

        overlay = None
        if debug_overlay and mask is not None and cv2 is not None:
            overlay = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)

        return VisionResult(
            pipeline_id=self.pipeline_id,
            label="Hand Detection",
            detected=detected,
            confidence=confidence,
            overlay=overlay,
            metadata={
                "pipeline_type": self.pipeline_type,
                "dashboard_indicator": dashboard_indicator,
                "record_training": False,
                "coverage": coverage,
                "debug_overlay": debug_overlay,
            },
        )


class BeautyProductSegmentationPipeline(VisionPipeline):
    """Professional beauty product detection using YOLO instance segmentation."""

    pipeline_type = "beauty_segmentation"

    def __init__(self, pipeline_id: str, camera_name: str, config: Dict[str, Any]):
        super().__init__(pipeline_id, camera_name, config)
        
        # Import here to avoid circular dependencies
        try:
            from .beauty_detector import BeautyProductDetector
            
            # Initialize detector with config
            model_version = str(config.get("model_version", "11"))
            model_size = config.get("model_size", "small")
            confidence = float(config.get("min_confidence", 0.25))
            device = config.get("device", "cpu")
            custom_model = config.get("custom_model_path")
            
            self.detector = BeautyProductDetector(
                model_version=model_version,
                model_size=model_size,
                confidence_threshold=confidence,
                device=device,
                custom_model_path=custom_model,
            )
            self._initialized = True
            
        except Exception as e:
            print(f"[BEAUTY_PIPELINE][ERROR] Failed to initialize detector: {e}")
            self.detector = None
            self._initialized = False

    def process(self, frame: "np.ndarray", timestamp: float) -> VisionResult:
        if not self._initialized or self.detector is None or frame is None:
            return VisionResult(
                pipeline_id=self.pipeline_id,
                label="Beauty Products",
                detected=False,
                confidence=0.0,
                overlay=None,
                metadata={
                    "pipeline_type": self.pipeline_type,
                    "record_training": True,
                    "persist_mask": True,
                    "error": "Detector not initialized",
                },
            )

        # Get configuration
        show_boxes = bool(self.config.get("show_boxes", True))
        show_masks = bool(self.config.get("show_masks", True))
        show_labels = bool(self.config.get("show_labels", True))
        show_confidence = bool(self.config.get("show_confidence", True))
        mask_alpha = float(self.config.get("mask_alpha", 0.4))
        record_training = bool(self.config.get("record_training", True))
        filter_classes = self.config.get("filter_classes")  # Optional list
        
        # Run detection
        result = self.detector.detect(frame, filter_classes=filter_classes)
        
        # Determine if anything was detected
        detected = result.total_detected > 0
        confidence = 0.0
        
        if detected:
            # Use highest confidence detection
            confidences = [d.confidence for d in result.detections]
            confidence = max(confidences) if confidences else 0.0
        
        # Create overlay
        overlay = None
        if show_boxes or show_masks:
            overlay = self.detector.visualize(
                frame,
                result,
                show_boxes=show_boxes,
                show_masks=show_masks,
                show_labels=show_labels,
                show_confidence=show_confidence,
                mask_alpha=mask_alpha,
            )
        
        return VisionResult(
            pipeline_id=self.pipeline_id,
            label="Beauty Products",
            detected=detected,
            confidence=confidence,
            overlay=overlay,
            metadata={
                "pipeline_type": self.pipeline_type,
                "record_training": record_training,
                "persist_mask": True,
                "total_detected": result.total_detected,
                "inference_time_ms": result.inference_time_ms,
                "fps": self.detector.get_average_fps(),
                "show_boxes": show_boxes,
                "show_masks": show_masks,
                "show_labels": show_labels,
                "show_confidence": show_confidence,
                "detections": [
                    {
                        "class": d.class_name,
                        "confidence": d.confidence,
                        "box": d.box,
                    }
                    for d in result.detections
                ],
            },
        )


class DefectDetectionPipeline(VisionPipeline):
    """Detect surface defects based on texture variance."""

    pipeline_type = "defect_detection"

    def process(self, frame: "np.ndarray", timestamp: float) -> VisionResult:
        if np is None or frame is None:
            return VisionResult(
                pipeline_id=self.pipeline_id,
                label="Defect Detection",
                detected=False,
                confidence=0.0,
                overlay=None,
                metadata={
                    "pipeline_type": self.pipeline_type,
                    "record_training": True,
                },
            )

        sensitivity = float(self.config.get("sensitivity", 0.35))
        record_training = bool(self.config.get("record_training", True))
        debug_overlay = bool(self.config.get("debug_overlay", False))

        if cv2 is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            lap = cv2.Laplacian(gray, cv2.CV_64F)
        else:
            gray = frame.astype("float32").mean(axis=2)
            gx = np.gradient(gray, axis=0)
            gy = np.gradient(gray, axis=1)
            lap = np.sqrt(gx**2 + gy**2)
        variance = float(lap.var())
        normalized = math.tanh(variance / 400.0)
        detected = normalized >= sensitivity
        confidence = float(min(1.0, normalized))

        overlay = None
        if debug_overlay and cv2 is not None:
            heatmap = cv2.normalize(np.abs(lap), None, 0, 255, cv2.NORM_MINMAX)
            overlay = cv2.applyColorMap(heatmap.astype("uint8"), cv2.COLORMAP_INFERNO)

        return VisionResult(
            pipeline_id=self.pipeline_id,
            label="Defect Detection",
            detected=detected,
            confidence=confidence,
            overlay=overlay,
            metadata={
                "pipeline_type": self.pipeline_type,
                "record_training": record_training,
                "variance": variance,
                "debug_overlay": debug_overlay,
            },
        )


class LabelReadingPipeline(VisionPipeline):
    """Approximate OCR quality scoring without heavy dependencies."""

    pipeline_type = "label_reading"

    def process(self, frame: "np.ndarray", timestamp: float) -> VisionResult:
        if np is None or frame is None:
            return VisionResult(
                pipeline_id=self.pipeline_id,
                label="Label Reading",
                detected=False,
                confidence=0.0,
                overlay=None,
                metadata={
                    "pipeline_type": self.pipeline_type,
                    "record_training": True,
                    "recognized_text": "",
                },
            )

        min_conf = float(self.config.get("min_confidence", 0.45))
        record_training = bool(self.config.get("record_training", True))
        expected_pattern = self.config.get("expected_pattern", "")
        debug_overlay = bool(self.config.get("debug_overlay", False))

        if cv2 is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (5, 5), 0)
            thresh = cv2.adaptiveThreshold(
                blur.astype("uint8"),
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV,
                31,
                7,
            )
            coverage = float(np.sum(thresh > 0) / thresh.size)
        else:
            gray = frame.astype("float32").mean(axis=2)
            norm = (gray - gray.min()) / (gray.max() - gray.min() + 1e-5)
            thresh = (norm > 0.6).astype("uint8") * 255
            coverage = float(np.sum(thresh > 0) / thresh.size)
        detected = coverage >= min_conf
        confidence = float(min(1.0, coverage * 1.1))

        recognized_text = "LEGIBLE" if detected else "ILLEGIBLE"
        if expected_pattern and detected:
            normalized_pattern = expected_pattern.strip().upper()
            if normalized_pattern and normalized_pattern not in recognized_text:
                recognized_text += " (pattern mismatch)"
                detected = False
                confidence *= 0.6

        overlay = None
        if debug_overlay:
            if cv2 is not None:
                overlay = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)
            else:
                overlay = np.dstack([thresh, thresh, thresh])

        return VisionResult(
            pipeline_id=self.pipeline_id,
            label="Label Reading",
            detected=detected,
            confidence=confidence,
            overlay=overlay,
            metadata={
                "pipeline_type": self.pipeline_type,
                "record_training": record_training,
                "recognized_text": recognized_text,
                "debug_overlay": debug_overlay,
            },
        )


class FastSAMSegmentationPipeline(VisionPipeline):
    """Professional FastSAM segmentation - Better masks than YOLO, still real-time."""

    pipeline_type = "fastsam_segmentation"

    def __init__(self, pipeline_id: str, camera_name: str, config: Dict[str, Any]):
        super().__init__(pipeline_id, camera_name, config)
        
        # Import here to avoid circular dependencies
        try:
            from .fastsam_detector import FastSAMDetector
            
            # Initialize detector with config
            model_size = config.get("model_size", "small")
            confidence = float(config.get("min_confidence", 0.4))
            device = config.get("device", "cpu")
            selection_mode = config.get("selection_mode", "all")
            min_size = int(config.get("min_object_size", 50))
            max_size = int(config.get("max_object_size", 50000))
            center_region = float(config.get("center_region_percent", 50.0))
            
            self.detector = FastSAMDetector(
                model_size=model_size,
                confidence_threshold=confidence,
                device=device,
                selection_mode=selection_mode,
                min_object_size=min_size,
                max_object_size=max_size,
                center_region_percent=center_region,
            )
            self._initialized = True
            
        except Exception as e:
            print(f"[FASTSAM_PIPELINE][ERROR] Failed to initialize detector: {e}")
            self.detector = None
            self._initialized = False

    def process(self, frame: "np.ndarray", timestamp: float) -> VisionResult:
        if not self._initialized or self.detector is None or frame is None:
            return VisionResult(
                pipeline_id=self.pipeline_id,
                label="FastSAM",
                detected=False,
                confidence=0.0,
                overlay=None,
                metadata={
                    "pipeline_type": self.pipeline_type,
                    "record_training": True,
                    "persist_mask": True,
                    "error": "Detector not initialized",
                },
            )

        # Get configuration
        show_boxes = bool(self.config.get("show_boxes", True))
        show_masks = bool(self.config.get("show_masks", True))
        show_confidence = bool(self.config.get("show_confidence", True))
        mask_alpha = float(self.config.get("mask_alpha", 0.5))
        record_training = bool(self.config.get("record_training", True))
        
        # Run detection
        result = self.detector.detect(frame)
        
        # Determine if anything was detected
        detected = result.total_detected > 0
        confidence = 0.0
        
        if detected:
            # Use highest confidence detection
            confidences = [d.confidence for d in result.detections]
            confidence = max(confidences) if confidences else 0.0
        
        # Create overlay
        overlay = None
        if show_boxes or show_masks:
            overlay = self.detector.visualize(
                frame,
                result,
                show_boxes=show_boxes,
                show_masks=show_masks,
                show_confidence=show_confidence,
                mask_alpha=mask_alpha,
            )
        
        return VisionResult(
            pipeline_id=self.pipeline_id,
            label="FastSAM",
            detected=detected,
            confidence=confidence,
            overlay=overlay,
            metadata={
                "pipeline_type": self.pipeline_type,
                "record_training": record_training,
                "persist_mask": True,
                "total_detected": result.total_detected,
                "inference_time_ms": result.inference_time_ms,
                "fps": self.detector.get_average_fps(),
                "show_boxes": show_boxes,
                "show_masks": show_masks,
                "show_confidence": show_confidence,
                "detections": [
                    {
                        "area": d.area,
                        "confidence": d.confidence,
                        "bbox": d.bbox,
                    }
                    for d in result.detections
                ],
            },
        )


PIPELINE_CLASS_MAP: Dict[str, type[VisionPipeline]] = {
    HandDetectionPipeline.pipeline_type: HandDetectionPipeline,
    BeautyProductSegmentationPipeline.pipeline_type: BeautyProductSegmentationPipeline,
    FastSAMSegmentationPipeline.pipeline_type: FastSAMSegmentationPipeline,
    DefectDetectionPipeline.pipeline_type: DefectDetectionPipeline,
    LabelReadingPipeline.pipeline_type: LabelReadingPipeline,
}


__all__ = [
    "HandDetectionPipeline",
    "BeautyProductSegmentationPipeline",
    "FastSAMSegmentationPipeline",
    "DefectDetectionPipeline",
    "LabelReadingPipeline",
    "PIPELINE_CLASS_MAP",
]
