"""Pipeline registry and metadata used by the UI and runtime."""

from __future__ import annotations

from typing import Dict, List

from .pipelines import PIPELINE_CLASS_MAP
from .base import VisionPipeline

PIPELINE_DEFINITIONS: Dict[str, Dict] = {
    "hand_detection": {
        "display_name": "Hand Detection",
        "description": "Detect operator hands without rendering boxes in production mode.",
        "default": {
            "enabled": True,
            "label": "Hand Detection",
            "min_confidence": 0.35,
            "debug_overlay": False,
            "dashboard_indicator": True,
            "record_training": False,
            "frequency_hz": 5.0,
        },
        "fields": [
            {"name": "min_confidence", "type": "float", "label": "Min Confidence", "min": 0.05, "max": 1.0, "step": 0.05},
            {"name": "dashboard_indicator", "type": "bool", "label": "Dashboard Indicator"},
            {"name": "debug_overlay", "type": "bool", "label": "Debug Overlay"},
        ],
    },
    "beauty_segmentation": {
        "display_name": "Beauty Product Masking",
        "description": "Segment beauty products and persist masks for training.",
        "default": {
            "enabled": True,
            "label": "Beauty Products",
            "min_confidence": 0.25,
            "mask_color": "#33FFAA",
            "record_training": True,
            "debug_overlay": True,
            "frequency_hz": 3.0,
        },
        "fields": [
            {"name": "min_confidence", "type": "float", "label": "Min Confidence", "min": 0.05, "max": 1.0, "step": 0.05},
            {"name": "mask_color", "type": "color", "label": "Mask Color"},
            {"name": "record_training", "type": "bool", "label": "Record for Training"},
            {"name": "debug_overlay", "type": "bool", "label": "Preview Mask"},
        ],
    },
    "defect_detection": {
        "display_name": "Product Defect Detection",
        "description": "Flag texture anomalies on the line.",
        "default": {
            "enabled": True,
            "label": "Defect Detection",
            "sensitivity": 0.35,
            "record_training": True,
            "debug_overlay": False,
            "frequency_hz": 2.0,
        },
        "fields": [
            {"name": "sensitivity", "type": "float", "label": "Sensitivity", "min": 0.1, "max": 1.0, "step": 0.05},
            {"name": "record_training", "type": "bool", "label": "Record for Training"},
            {"name": "debug_overlay", "type": "bool", "label": "Heatmap Overlay"},
        ],
    },
    "label_reading": {
        "display_name": "Label Reading",
        "description": "Assess label legibility and flag mismatches.",
        "default": {
            "enabled": True,
            "label": "Label Reading",
            "min_confidence": 0.45,
            "expected_pattern": "",
            "record_training": True,
            "debug_overlay": False,
            "frequency_hz": 2.0,
        },
        "fields": [
            {"name": "min_confidence", "type": "float", "label": "Min Coverage", "min": 0.05, "max": 1.0, "step": 0.05},
            {"name": "expected_pattern", "type": "text", "label": "Expected Pattern"},
            {"name": "record_training", "type": "bool", "label": "Record for Training"},
            {"name": "debug_overlay", "type": "bool", "label": "Show Threshold"},
        ],
    },
}


def create_pipeline(pipeline_type: str, pipeline_id: str, camera_name: str, config: Dict) -> VisionPipeline:
    definition = PIPELINE_DEFINITIONS.get(pipeline_type, {})
    merged = dict(definition.get("default", {}))
    options = dict(config.get("options", {})) if isinstance(config, dict) else {}
    merged.update(options)
    cls = PIPELINE_CLASS_MAP.get(pipeline_type)
    if cls is None:
        raise ValueError(f"Unknown pipeline type: {pipeline_type}")
    return cls(pipeline_id=pipeline_id, camera_name=camera_name, config=merged)


def get_pipeline_options() -> List[Dict]:
    return [
        {"type": key, "display_name": meta["display_name"], "description": meta["description"]}
        for key, meta in PIPELINE_DEFINITIONS.items()
    ]


__all__ = ["PIPELINE_DEFINITIONS", "create_pipeline", "get_pipeline_options"]
