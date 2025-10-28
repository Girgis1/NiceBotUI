"""Base classes and dataclasses for vision pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class VisionResult:
    """Result returned by a vision pipeline."""

    pipeline_id: str
    label: str
    detected: bool
    confidence: float = 0.0
    overlay: Optional["np.ndarray"] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class VisionPipeline:
    """Abstract base class for camera pipelines."""

    pipeline_type: str = "base"

    def __init__(self, pipeline_id: str, camera_name: str, config: Dict[str, Any]):
        self.pipeline_id = pipeline_id
        self.camera_name = camera_name
        self.config = config

    def process(self, frame: "np.ndarray", timestamp: float) -> VisionResult:
        """Process a frame and return a :class:`VisionResult`.

        Subclasses should override this method. The default implementation
        returns a negative result with zero confidence.
        """

        return VisionResult(
            pipeline_id=self.pipeline_id,
            label=self.config.get("label", self.pipeline_type.title()),
            detected=False,
            confidence=0.0,
            overlay=None,
            metadata={"pipeline_type": self.pipeline_type},
        )


try:  # Optional dependencies
    import numpy as np  # type: ignore
except ImportError:  # pragma: no cover - handled gracefully at runtime
    np = None  # type: ignore
