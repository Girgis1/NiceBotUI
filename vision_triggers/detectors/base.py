"""
Base Detector - Abstract interface for object detectors
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Tuple, Optional
import numpy as np


class DetectionResult:
    """Result from a detection operation"""
    
    def __init__(
        self,
        detected: bool,
        boxes: List[Tuple[int, int, int, int]],
        confidence: float = 1.0,
        metadata: Optional[Dict] = None
    ):
        """
        Initialize detection result
        
        Args:
            detected: Whether objects were detected
            boxes: List of bounding boxes (x, y, width, height)
            confidence: Detection confidence (0.0 to 1.0)
            metadata: Additional detection metadata
        """
        self.detected = detected
        self.boxes = boxes
        self.confidence = confidence
        self.metadata = metadata or {}
    
    def __repr__(self) -> str:
        return f"DetectionResult(detected={self.detected}, boxes={len(self.boxes)}, conf={self.confidence:.2f})"


class BaseDetector(ABC):
    """Abstract base class for object detectors"""
    
    def __init__(self):
        self.initialized = False
    
    @abstractmethod
    def initialize(self) -> bool:
        """Initialize the detector (load models, setup, etc.)"""
        pass
    
    @abstractmethod
    def detect(self, frame: np.ndarray, zones: List[Dict]) -> List[DetectionResult]:
        """
        Detect objects in frame within specified zones
        
        Args:
            frame: Input image (BGR format)
            zones: List of zone dicts with polygon data
        
        Returns:
            List of DetectionResult, one per zone
        """
        pass
    
    @abstractmethod
    def reset(self):
        """Reset detector state (e.g., clear background model)"""
        pass
    
    @abstractmethod
    def cleanup(self):
        """Cleanup resources"""
        pass

