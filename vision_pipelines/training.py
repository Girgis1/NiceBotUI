"""Utilities for persisting training samples from live pipelines."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict

from .base import VisionResult, np

try:  # Optional dependency
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - optional
    cv2 = None  # type: ignore

DATA_ROOT = Path(__file__).resolve().parent.parent / "data" / "vision_training"


def record_training_sample(camera_name: str, frame: "np.ndarray", result: VisionResult) -> None:
    """Persist frames, masks, and metadata for future model training."""

    if not result.metadata.get("record_training", False):
        return

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    sample_dir = DATA_ROOT / camera_name
    sample_dir.mkdir(parents=True, exist_ok=True)

    meta: Dict = {
        "pipeline_id": result.pipeline_id,
        "camera": camera_name,
        "label": result.label,
        "detected": result.detected,
        "confidence": result.confidence,
        "metadata": result.metadata,
        "timestamp": timestamp,
    }

    meta_path = sample_dir / f"{timestamp}_{result.pipeline_id}.json"
    with meta_path.open("w", encoding="utf-8") as handle:
        json.dump(meta, handle, indent=2)

    if np is None or frame is None:
        return

    frame_path = sample_dir / f"{timestamp}_{result.pipeline_id}.png"

    if cv2 is not None:
        cv2.imwrite(str(frame_path), frame)
    else:  # pragma: no cover - fallback without OpenCV
        try:
            from PIL import Image  # type: ignore

            Image.fromarray(frame).save(frame_path)
        except Exception:
            return

    if result.overlay is not None:
        overlay = result.overlay
        overlay_path = sample_dir / f"{timestamp}_{result.pipeline_id}_mask.png"
        if cv2 is not None:
            cv2.imwrite(str(overlay_path), overlay)
        else:  # pragma: no cover - fallback
            try:
                from PIL import Image  # type: ignore

                Image.fromarray(overlay).save(overlay_path)
            except Exception:
                return


__all__ = ["record_training_sample"]
