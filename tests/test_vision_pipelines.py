import sys
import types
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from vision_pipelines import load_vision_profile, save_vision_profile
from vision_pipelines.manager import VisionPipelineManager


def test_load_profile_assigns_ids(tmp_path):
    path = tmp_path / "vision_profiles.json"
    profile = load_vision_profile(path, ["front"])
    profile["cameras"]["front"]["pipelines"] = [
        {"type": "hand_detection", "enabled": True, "options": {"dashboard_indicator": True}}
    ]
    save_vision_profile(profile, path)

    reloaded = load_vision_profile(path, ["front"])
    pipelines = reloaded["cameras"]["front"]["pipelines"]
    assert pipelines and pipelines[0]["id"].startswith("pipeline_")


def test_manager_process_single_frame_returns_results():
    np = pytest.importorskip("numpy")

    profile = {
        "version": 1,
        "max_pipelines_per_camera": 3,
        "cameras": {
            "front": {
                "display_name": "Front",
                "pipelines": [
                    {
                        "id": "front_hand",
                        "type": "hand_detection",
                        "enabled": True,
                        "options": {"min_confidence": 0.01, "dashboard_indicator": True},
                    }
                ],
            }
        },
    }

    manager = VisionPipelineManager({"cameras": {"front": {}}}, profile, camera_hub=types.SimpleNamespace())
    frame = np.zeros((240, 320, 3), dtype="uint8")
    results = manager.process_single_frame("front", frame)
    assert results
    assert results[0].pipeline_id == "front_hand"
