"""
Training data capture utility for fine-tuning YOLO models on beauty products.

This module helps capture and label images for creating custom training datasets.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import cv2
    import numpy as np
    HAVE_DEPS = True
except ImportError:
    cv2 = None
    np = None
    HAVE_DEPS = False


class TrainingDataCapture:
    """
    Capture and label training data for YOLO fine-tuning.
    
    Creates datasets in YOLO format:
    - images/ directory with captured frames
    - labels/ directory with YOLO annotation files
    - data.yaml with class definitions
    """
    
    def __init__(self, dataset_path: str, class_names: List[str]):
        """
        Initialize training data capture.
        
        Args:
            dataset_path: Root directory for the dataset
            class_names: List of class names (e.g. ["lipstick", "mascara", "foundation"])
        """
        if not HAVE_DEPS:
            raise RuntimeError("OpenCV and NumPy required for training capture")
        
        self.dataset_path = Path(dataset_path)
        self.class_names = class_names
        self.class_to_id = {name: idx for idx, name in enumerate(class_names)}
        
        # Create directory structure
        self.images_dir = self.dataset_path / "images"
        self.labels_dir = self.dataset_path / "labels"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.labels_dir.mkdir(parents=True, exist_ok=True)
        
        self.capture_count = 0
        self._create_data_yaml()
    
    def _create_data_yaml(self):
        """Create YOLO data.yaml configuration file"""
        data_yaml = {
            "path": str(self.dataset_path.absolute()),
            "train": "images",
            "val": "images",
            "names": {idx: name for idx, name in enumerate(self.class_names)}
        }
        
        yaml_path = self.dataset_path / "data.yaml"
        with open(yaml_path, 'w') as f:
            # Write YAML manually (avoid dependency)
            f.write(f"path: {data_yaml['path']}\n")
            f.write(f"train: {data_yaml['train']}\n")
            f.write(f"val: {data_yaml['val']}\n")
            f.write("names:\n")
            for idx, name in enumerate(self.class_names):
                f.write(f"  {idx}: {name}\n")
    
    def capture_frame(
        self,
        frame: np.ndarray,
        detections: List[Dict],
        auto_save: bool = True,
    ) -> Optional[str]:
        """
        Capture a frame with detection annotations.
        
        Args:
            frame: Input image
            detections: List of detections, each with:
                - class_name: str
                - box: (x1, y1, x2, y2) in pixels
                - confidence: float
                - mask: Optional numpy array
            auto_save: Automatically save (True) or return data for manual save (False)
        
        Returns:
            Filename if saved, None otherwise
        """
        if frame is None:
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"capture_{timestamp}_{self.capture_count:04d}"
        
        # Save image
        image_path = self.images_dir / f"{filename}.jpg"
        cv2.imwrite(str(image_path), frame)
        
        # Convert detections to YOLO format
        h, w = frame.shape[:2]
        yolo_annotations = []
        
        for det in detections:
            class_name = det.get("class_name", det.get("class"))
            if class_name not in self.class_to_id:
                continue
            
            class_id = self.class_to_id[class_name]
            box = det["box"]  # x1, y1, x2, y2
            
            # Convert to YOLO format: class_id x_center y_center width height (normalized)
            x1, y1, x2, y2 = box
            x_center = ((x1 + x2) / 2) / w
            y_center = ((y1 + y2) / 2) / h
            box_width = (x2 - x1) / w
            box_height = (y2 - y1) / h
            
            # If mask is available, could export segmentation here
            # For now, just export bounding boxes
            yolo_annotations.append(
                f"{class_id} {x_center:.6f} {y_center:.6f} {box_width:.6f} {box_height:.6f}"
            )
        
        # Save label file
        label_path = self.labels_dir / f"{filename}.txt"
        with open(label_path, 'w') as f:
            f.write("\n".join(yolo_annotations))
        
        self.capture_count += 1
        
        return filename
    
    def capture_from_detector_result(
        self,
        frame: np.ndarray,
        detector_result,  # DetectionResult from BeautyProductDetector
    ) -> Optional[str]:
        """
        Convenience method to capture from BeautyProductDetector result.
        
        Args:
            frame: Input image
            detector_result: DetectionResult object
        
        Returns:
            Filename if saved
        """
        detections = []
        for det in detector_result.detections:
            detections.append({
                "class_name": det.class_name,
                "box": det.box,
                "confidence": det.confidence,
                "mask": det.mask,
            })
        
        return self.capture_frame(frame, detections)
    
    def get_stats(self) -> Dict:
        """Get dataset statistics"""
        image_count = len(list(self.images_dir.glob("*.jpg")))
        label_count = len(list(self.labels_dir.glob("*.txt")))
        
        # Count annotations per class
        class_counts = {name: 0 for name in self.class_names}
        for label_file in self.labels_dir.glob("*.txt"):
            with open(label_file, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if parts:
                        class_id = int(parts[0])
                        if class_id < len(self.class_names):
                            class_counts[self.class_names[class_id]] += 1
        
        return {
            "dataset_path": str(self.dataset_path),
            "image_count": image_count,
            "label_count": label_count,
            "class_counts": class_counts,
            "classes": self.class_names,
        }
    
    @staticmethod
    def create_default_dataset(base_dir: Optional[str] = None) -> 'TrainingDataCapture':
        """
        Create a default beauty products dataset.
        
        Args:
            base_dir: Base directory for datasets (default: ./training_data)
        
        Returns:
            TrainingDataCapture instance
        """
        if base_dir is None:
            base_dir = Path.cwd() / "training_data"
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dataset_path = Path(base_dir) / f"beauty_products_{timestamp}"
        
        # Common beauty product classes
        default_classes = [
            "bottle",
            "lipstick",
            "mascara",
            "foundation",
            "compact",
            "tube",
            "jar",
            "pump_bottle",
        ]
        
        return TrainingDataCapture(str(dataset_path), default_classes)


def quick_capture_session(
    camera_index: int = 0,
    class_names: Optional[List[str]] = None,
    capture_interval_seconds: float = 2.0,
    max_captures: int = 100,
) -> Dict:
    """
    Quick capture session using live camera feed.
    
    Press SPACE to capture, ESC to exit.
    
    Args:
        camera_index: Camera device index
        class_names: List of class names (uses defaults if None)
        capture_interval_seconds: Minimum time between captures
        max_captures: Maximum number of captures
    
    Returns:
        Dataset statistics
    """
    if not HAVE_DEPS:
        raise RuntimeError("OpenCV required for quick capture session")
    
    capture = TrainingDataCapture.create_default_dataset()
    if class_names:
        capture.class_names = class_names
        capture.class_to_id = {name: idx for idx, name in enumerate(class_names)}
        capture._create_data_yaml()
    
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera {camera_index}")
    
    print(f"[TRAINING] Quick capture session started")
    print(f"[TRAINING] Dataset: {capture.dataset_path}")
    print(f"[TRAINING] Press SPACE to capture, ESC to exit")
    
    last_capture_time = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # Display frame
        display = frame.copy()
        cv2.putText(
            display,
            f"Captures: {capture.capture_count}/{max_captures}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
        )
        cv2.putText(
            display,
            "SPACE: Capture | ESC: Exit",
            (10, display.shape[0] - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )
        
        cv2.imshow("Training Capture", display)
        
        key = cv2.waitKey(1) & 0xFF
        
        if key == 27:  # ESC
            break
        elif key == 32:  # SPACE
            current_time = time.time()
            if current_time - last_capture_time >= capture_interval_seconds:
                # Create dummy detection (user will label manually later)
                # Or integrate with live detector here
                capture.capture_frame(frame, [])
                last_capture_time = current_time
                print(f"[TRAINING] Captured frame {capture.capture_count}")
                
                if capture.capture_count >= max_captures:
                    print(f"[TRAINING] Reached max captures ({max_captures})")
                    break
    
    cap.release()
    cv2.destroyAllWindows()
    
    stats = capture.get_stats()
    print(f"[TRAINING] Session complete:")
    print(f"[TRAINING] Total images: {stats['image_count']}")
    print(f"[TRAINING] Dataset: {stats['dataset_path']}")
    
    return stats


__all__ = [
    "TrainingDataCapture",
    "quick_capture_session",
]

