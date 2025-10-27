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
        "display_name": "Beauty Product Detection (YOLO)",
        "description": "Professional YOLO-based instance segmentation for beauty products.",
        "default": {
            "enabled": True,
            "label": "Beauty Products",
            "model_version": "11",
            "model_size": "small",
            "min_confidence": 0.25,
            "device": "cpu",
            "show_boxes": True,
            "show_masks": True,
            "show_labels": True,
            "show_confidence": True,
            "mask_alpha": 0.4,
            "record_training": True,
            "frequency_hz": 3.0,
        },
        "fields": [
            {"name": "model_version", "type": "text", "label": "YOLO Version (8/11)", "default": "11"},
            {"name": "model_size", "type": "text", "label": "Model Size (nano/small/medium/large)", "default": "small"},
            {"name": "min_confidence", "type": "float", "label": "Min Confidence", "min": 0.05, "max": 1.0, "step": 0.05, "default": 0.25},
            {"name": "device", "type": "text", "label": "Device (cpu/cuda)", "default": "cpu"},
            {"name": "show_boxes", "type": "bool", "label": "Show Bounding Boxes", "default": True},
            {"name": "show_masks", "type": "bool", "label": "Show Segmentation Masks", "default": True},
            {"name": "show_labels", "type": "bool", "label": "Show Class Labels", "default": True},
            {"name": "show_confidence", "type": "bool", "label": "Show Confidence Scores", "default": True},
            {"name": "mask_alpha", "type": "float", "label": "Mask Transparency", "min": 0.0, "max": 1.0, "step": 0.1, "default": 0.4},
            {"name": "record_training", "type": "bool", "label": "Record for Training", "default": True},
        ],
    },
    "fastsam_segmentation": {
        "display_name": "FastSAM Segmentation ⚡",
        "description": "Better masks than YOLO, still real-time (~18 FPS). Multiple selection modes.",
        "default": {
            "enabled": True,
            "label": "FastSAM",
            "model_size": "small",
            "min_confidence": 0.4,
            "device": "cpu",
            "selection_mode": "largest",
            "center_region_percent": 50.0,
            "min_object_size": 50,
            "max_object_size": 50000,
            "show_boxes": True,
            "show_masks": True,
            "show_confidence": True,
            "mask_alpha": 0.5,
            "record_training": True,
            "frequency_hz": 3.0,
        },
        "fields": [
            {"name": "selection_mode", "type": "text", "label": "Selection Mode (all/largest/center_region/point_click)", "default": "largest"},
            {"name": "model_size", "type": "text", "label": "Model Size (small/large)", "default": "small"},
            {"name": "min_confidence", "type": "float", "label": "Min Confidence", "min": 0.05, "max": 1.0, "step": 0.05, "default": 0.4},
            {"name": "device", "type": "text", "label": "Device (cpu/cuda)", "default": "cpu"},
            {"name": "center_region_percent", "type": "float", "label": "Center Region % (for center_region mode)", "min": 10, "max": 90, "step": 5, "default": 50},
            {"name": "min_object_size", "type": "float", "label": "Min Object Size (px)", "min": 10, "max": 1000, "step": 10, "default": 50},
            {"name": "max_object_size", "type": "float", "label": "Max Object Size (px)", "min": 1000, "max": 100000, "step": 1000, "default": 50000},
            {"name": "show_boxes", "type": "bool", "label": "Show Bounding Boxes", "default": True},
            {"name": "show_masks", "type": "bool", "label": "Show Segmentation Masks", "default": True},
            {"name": "show_confidence", "type": "bool", "label": "Show Confidence Scores", "default": True},
            {"name": "mask_alpha", "type": "float", "label": "Mask Transparency", "min": 0.0, "max": 1.0, "step": 0.1, "default": 0.5},
            {"name": "record_training", "type": "bool", "label": "Record for Training", "default": True},
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
