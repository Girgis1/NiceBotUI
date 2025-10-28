"""Configuration helpers for the multi-model vision system."""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Dict, List

DEFAULT_CAMERAS = ["front", "wrist"]

VISION_PROFILE_PATH = Path(__file__).resolve().parent.parent / "runtime" / "vision_profiles.json"

DEFAULT_VISION_PROFILE: Dict[str, Dict] = {
    "version": 1,
    "max_pipelines_per_camera": 3,
    "cameras": {
        camera: {
            "display_name": camera.title(),
            "pipelines": [],
        }
        for camera in DEFAULT_CAMERAS
    },
}


def _ensure_camera_entries(profile: Dict, camera_names: List[str]) -> None:
    cameras = profile.setdefault("cameras", {})
    for camera in camera_names:
        if camera not in cameras:
            cameras[camera] = {"display_name": camera.title(), "pipelines": []}
    # Drop removed cameras gracefully by keeping their settings but marking inactive.


def _ensure_pipeline_ids(profile: Dict) -> None:
    for camera_cfg in profile.get("cameras", {}).values():
        for pipeline in camera_cfg.get("pipelines", []):
            pipeline.setdefault("id", f"pipeline_{uuid.uuid4().hex[:8]}")
            pipeline.setdefault("enabled", True)
            pipeline.setdefault("options", {})


def load_vision_profile(path: Path = VISION_PROFILE_PATH, camera_names: List[str] | None = None) -> Dict:
    """Load the persisted vision profile and normalize defaults."""

    profile = deepcopy(DEFAULT_VISION_PROFILE)
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                profile.update({k: v for k, v in loaded.items() if k != "cameras"})
                if "cameras" in loaded and isinstance(loaded["cameras"], dict):
                    profile["cameras"] = loaded["cameras"]
        except Exception as exc:
            print(f"[VISION][WARN] Failed to load vision profile {path}: {exc}")

    camera_list = camera_names or list(profile.get("cameras", {}).keys())
    if not camera_list:
        camera_list = list(DEFAULT_CAMERAS)

    _ensure_camera_entries(profile, camera_list)
    _ensure_pipeline_ids(profile)
    return profile


def save_vision_profile(profile: Dict, path: Path = VISION_PROFILE_PATH) -> None:
    """Persist the provided profile to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(profile, handle, indent=2)


__all__ = [
    "DEFAULT_VISION_PROFILE",
    "VISION_PROFILE_PATH",
    "load_vision_profile",
    "save_vision_profile",
]
