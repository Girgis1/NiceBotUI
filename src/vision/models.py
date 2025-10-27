"""Lightweight vision models and registry for configurable pipelines."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

import time

try:  # Optional heavy dependencies
    import numpy as np  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    np = None  # type: ignore

try:  # OpenCV is also optional in the UI environment
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    cv2 = None  # type: ignore


@dataclass
class VisionModelResult:
    """Result returned by a single model evaluation."""

    alert: bool = False
    status_text: Optional[str] = None
    overlay: Optional["np.ndarray"] = None
    mask: Optional["np.ndarray"] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class VisionModelBase:
    """Common base class for all lightweight vision helpers."""

    def __init__(self, camera_name: str, slot_config: Dict[str, Any], settings: Dict[str, Any]):
        self.camera_name = camera_name
        self.slot_config = dict(slot_config)
        self.settings = dict(settings)

    # ------------------------------------------------------------------
    # Lifecycle helpers

    def update_config(self, slot_config: Dict[str, Any], settings: Dict[str, Any]) -> None:
        """Update model configuration in-place."""
        self.slot_config = dict(slot_config)
        self.settings = dict(settings)

    # ------------------------------------------------------------------
    # Runtime interface

    def process(self, frame: "np.ndarray", timestamp: float) -> VisionModelResult:  # pragma: no cover - implemented in subclasses
        raise NotImplementedError


class HandPresenceModel(VisionModelBase):
    """Detect rapid visual changes that typically map to hands entering view."""

    def __init__(self, camera_name: str, slot_config: Dict[str, Any], settings: Dict[str, Any]):
        super().__init__(camera_name, slot_config, settings)
        self._baseline: Optional[float] = None
        self._last_update_ts: float = 0.0

    def process(self, frame: "np.ndarray", timestamp: float) -> VisionModelResult:  # pragma: no cover - depends on numpy availability
        if np is None:
            return VisionModelResult(alert=False, status_text="Unavailable", metadata={"reason": "numpy_missing"})

        gray = frame if frame.ndim == 2 else frame.mean(axis=2)
        current = float(np.mean(gray)) / 255.0
        threshold = float(self.settings.get("delta_threshold", 0.18))
        decay = float(self.settings.get("baseline_decay", 0.12))

        if self._baseline is None:
            self._baseline = current
        else:
            delta_time = max(timestamp - self._last_update_ts, 0.0)
            smoothing = decay * min(delta_time * 30.0, 1.0)
            self._baseline = (1.0 - smoothing) * self._baseline + smoothing * current

        self._last_update_ts = timestamp
        delta = abs(current - (self._baseline or current))
        detected = delta >= threshold

        overlay = None
        if detected and self.slot_config.get("debug_overlay") and np is not None:
            overlay = frame.copy()
            overlay[..., 2] = np.clip(overlay[..., 2] + 80, 0, 255)  # Tint red

        status = "Hand detected" if detected else "Clear"
        metadata = {
            "mean_intensity": current,
            "baseline": self._baseline,
            "delta": delta,
            "threshold": threshold,
        }
        return VisionModelResult(alert=detected, status_text=status, overlay=overlay, metadata=metadata)


class BeautyProductMaskModel(VisionModelBase):
    """Simple color segmentation to highlight beauty products for training."""

    def process(self, frame: "np.ndarray", timestamp: float) -> VisionModelResult:  # pragma: no cover - depends on numpy
        if np is None:
            return VisionModelResult(alert=False, metadata={"reason": "numpy_missing"})

        confidence = float(self.settings.get("mask_confidence", 0.55))
        blur_kernel = int(self.settings.get("blur_kernel", 3)) or 1

        work = frame.astype(np.float32) / 255.0
        intensity = work.mean(axis=2)

        if blur_kernel > 1 and cv2 is not None:
            intensity = cv2.GaussianBlur(intensity, (blur_kernel | 1, blur_kernel | 1), 0)

        mask = (intensity >= confidence).astype(np.uint8) * 255
        coverage = float(mask.mean() / 255.0)

        overlay = None
        if self.slot_config.get("show_overlay") and np is not None:
            overlay = frame.copy()
            tint = np.zeros_like(overlay)
            tint[..., 1] = 220  # Green mask
            overlay = np.where(mask[..., None] > 0, overlay * 0.5 + tint * 0.5, overlay).astype(np.uint8)

        status = "Products" if coverage > 0.02 else "None"
        metadata = {"coverage": coverage, "confidence": confidence}
        return VisionModelResult(alert=coverage > 0.01, status_text=status, overlay=overlay, mask=mask, metadata=metadata)


class ProductDefectModel(VisionModelBase):
    """Detect abrupt texture changes that could indicate product defects."""

    def process(self, frame: "np.ndarray", timestamp: float) -> VisionModelResult:  # pragma: no cover - depends on numpy
        if np is None:
            return VisionModelResult()

        sensitivity = float(self.settings.get("sensitivity", 0.6))
        gray = frame if frame.ndim == 2 else frame.mean(axis=2)

        if cv2 is not None:
            laplacian = cv2.Laplacian(gray, cv2.CV_32F)
        else:
            laplacian = np.gradient(gray.astype(np.float32))[0]

        score = float(np.mean(np.abs(laplacian))) / 255.0
        alert = score >= sensitivity

        overlay = None
        if alert and self.slot_config.get("show_overlay") and np is not None:
            overlay = frame.copy()
            overlay[..., 0] = np.clip(overlay[..., 0] + 90, 0, 255)  # Add blue tint for defects

        status = "Defects" if alert else "OK"
        metadata = {"edge_score": score, "threshold": sensitivity}
        return VisionModelResult(alert=alert, status_text=status, overlay=overlay, metadata=metadata)


class LabelReaderModel(VisionModelBase):
    """Heuristic OCR quality signal for label validation."""

    def __init__(self, camera_name: str, slot_config: Dict[str, Any], settings: Dict[str, Any]):
        super().__init__(camera_name, slot_config, settings)
        self._last_result: Optional[str] = None

    def process(self, frame: "np.ndarray", timestamp: float) -> VisionModelResult:  # pragma: no cover - depends on numpy
        if np is None:
            return VisionModelResult(metadata={"reason": "numpy_missing"})

        gray = frame if frame.ndim == 2 else frame.mean(axis=2)
        mean_intensity = float(np.mean(gray)) / 255.0
        contrast = float(np.std(gray)) / 255.0

        min_brightness = float(self.settings.get("min_brightness", 0.18))
        min_contrast = float(self.settings.get("min_contrast", 0.08))
        expected_prefix = self.settings.get("expected_prefix") or ""

        illegible = mean_intensity < min_brightness or contrast < min_contrast

        recognised_text = expected_prefix or "OK"
        if illegible:
            recognised_text = "Illegible"
        elif expected_prefix:
            recognised_text = f"{expected_prefix}-OK"

        self._last_result = recognised_text

        alert = illegible
        status = "Label issue" if illegible else "Label ok"

        overlay = None
        if self.slot_config.get("show_overlay") and np is not None:
            overlay = frame.copy()
            if illegible:
                overlay[..., 2] = np.clip(overlay[..., 2] + 100, 0, 255)
            else:
                overlay[..., 1] = np.clip(overlay[..., 1] + 100, 0, 255)

        metadata = {
            "mean_intensity": mean_intensity,
            "contrast": contrast,
            "text": recognised_text,
            "expected_prefix": expected_prefix,
        }
        return VisionModelResult(alert=alert, status_text=status, overlay=overlay, metadata=metadata)


@dataclass(frozen=True)
class VisionModelSpec:
    """Describe a single vision helper available to operators."""

    key: str
    name: str
    description: str
    factory: Callable[[str, Dict[str, Any], Dict[str, Any]], VisionModelBase]
    default_slot: Dict[str, Any]
    default_settings: Dict[str, Any]
    supports_overlay: bool = False
    supports_masks: bool = False
    supports_training: bool = False
    has_debug_toggle: bool = False

    def instantiate(self, camera_name: str, slot_config: Dict[str, Any], settings: Dict[str, Any]) -> VisionModelBase:
        merged_slot = dict(self.default_slot)
        merged_slot.update(slot_config)
        merged_settings = dict(self.default_settings)
        merged_settings.update(settings)
        return self.factory(camera_name, merged_slot, merged_settings)


MODEL_REGISTRY: Dict[str, VisionModelSpec] = {
    "hand_presence": VisionModelSpec(
        key="hand_presence",
        name="Hand Presence Monitor",
        description="Detects hands entering the workspace and updates the dashboard indicator.",
        factory=HandPresenceModel,
        default_slot={
            "enabled": True,
            "show_overlay": False,
            "save_to_training": False,
            "debug_overlay": False,
            "dashboard_indicator": True,
        },
        default_settings={"delta_threshold": 0.18, "baseline_decay": 0.12},
        supports_overlay=True,
        supports_training=False,
        has_debug_toggle=True,
    ),
    "beauty_product_mask": VisionModelSpec(
        key="beauty_product_mask",
        name="Beauty Product Masking",
        description="Segments beauty products and saves masks for training.",
        factory=BeautyProductMaskModel,
        default_slot={"enabled": True, "show_overlay": True, "save_to_training": True},
        default_settings={"mask_confidence": 0.55, "blur_kernel": 3},
        supports_overlay=True,
        supports_masks=True,
        supports_training=True,
    ),
    "product_defect": VisionModelSpec(
        key="product_defect",
        name="Product Defect Inspection",
        description="Highlights texture changes that could correspond to defects.",
        factory=ProductDefectModel,
        default_slot={"enabled": False, "show_overlay": True, "save_to_training": True},
        default_settings={"sensitivity": 0.6},
        supports_overlay=True,
        supports_training=True,
    ),
    "label_reader": VisionModelSpec(
        key="label_reader",
        name="Label Quality Monitor",
        description="Flags illegible or low-contrast labels for manual review.",
        factory=LabelReaderModel,
        default_slot={"enabled": False, "show_overlay": False, "save_to_training": True},
        default_settings={"min_brightness": 0.18, "min_contrast": 0.08, "expected_prefix": ""},
        supports_overlay=True,
        supports_training=True,
    ),
}

