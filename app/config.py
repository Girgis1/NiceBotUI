"""Configuration helpers for the NiceBot UI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

from utils.config_compat import ensure_multi_arm_config

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"


def create_default_config() -> Dict[str, Any]:
    """Return the default configuration used on fresh installs."""
    return {
        "robot": {
            "mode": "solo",
            "arms": [
                {
                    "enabled": True,
                    "name": "Follower 1",
                    "type": "so100_follower",
                    "port": "/dev/ttyACM0",
                    "id": "follower_arm",
                    "arm_id": 1,
                    "home_positions": [2082, 1106, 2994, 2421, 1044, 2054],
                    "home_velocity": 600,
                },
                {
                    "enabled": False,
                    "name": "Follower 2",
                    "type": "so100_follower",
                    "port": "/dev/ttyACM1",
                    "id": "follower_arm_2",
                    "arm_id": 2,
                    "home_positions": [2082, 1106, 2994, 2421, 1044, 2054],
                    "home_velocity": 600,
                },
            ],
            "fps": 30,
            "min_time_to_move_multiplier": 3.0,
            "enable_motor_torque": True,
            "position_tolerance": 45,
            "position_verification_enabled": True,
        },
        "teleop": {
            "mode": "solo",
            "arms": [
                {
                    "enabled": False,
                    "name": "Leader 1",
                    "type": "so100_leader",
                    "port": "/dev/ttyACM2",
                    "id": "leader_arm",
                    "arm_id": 1,
                },
                {
                    "enabled": False,
                    "name": "Leader 2",
                    "type": "so100_leader",
                    "port": "/dev/ttyACM3",
                    "id": "leader_arm_2",
                    "arm_id": 2,
                },
            ],
        },
        "cameras": {
            "front": {
                "type": "opencv",
                "index_or_path": "/dev/video1",
                "width": 640,
                "height": 480,
                "fps": 30,
            },
            "wrist": {
                "type": "opencv",
                "index_or_path": "/dev/video3",
                "width": 640,
                "height": 480,
                "fps": 30,
            },
            "wrist_right": {
                "type": "opencv",
                "index_or_path": "/dev/video5",
                "width": 640,
                "height": 480,
                "fps": 30,
            },
        },
        "policy": {
            "path": "outputs/train/act_so100/checkpoints/last/pretrained_model",
            "device": "cpu",
            "base_path": "outputs/train",
            "local_mode": True,
        },
        "control": {
            "warmup_time_s": 3,
            "episode_time_s": 25,
            "reset_time_s": 8,
            "num_episodes": 3,
            "single_task": "PickPlace v1",
            "push_to_hub": False,
            "repo_id": None,
            "num_image_writer_processes": 0,
            "display_data": True,
            "speed_multiplier": 1.0,
            "loop_enabled": False,
        },
        "ui": {
            "object_gate": False,
            "roi": [220, 140, 200, 180],
            "presence_threshold": 0.12,
        },
        "safety": {
            "soft_limits_deg": [
                [-90, 90],
                [-60, 60],
                [-60, 60],
                [-90, 90],
                [-180, 180],
                [0, 100],
            ],
            "max_speed_scale": 1.0,
            "motor_temp_monitoring_enabled": False,
            "motor_temp_threshold_c": 75,
            "motor_temp_poll_interval_s": 2.0,
            "torque_monitoring_enabled": False,
            "torque_limit_percent": 120.0,
            "torque_auto_disable": False,
        },
        "async_inference": {
            "server_host": "127.0.0.1",
            "server_port": 8080,
            "policy_type": "act",
            "actions_per_chunk": 30,
            "chunk_size_threshold": 0.6,
        },
        "dashboard_state": {
            "speed_percent": 100,
            "loop_enabled": False,
            "run_selection": "",
            "active_robot_arm_index": 0,
        },
    }


def load_config(path: Path = CONFIG_PATH) -> Dict[str, Any]:
    """Load the JSON config, ensuring the latest schema without rewriting unnecessarily."""
    if path.exists():
        raw_text = path.read_text()
        original = json.loads(raw_text)
        # Work on a copy so we can detect schema updates
        config = ensure_multi_arm_config(json.loads(raw_text))
        state = config.setdefault("dashboard_state", {})
        state.setdefault("active_robot_arm_index", 0)
        changed = config != original
    else:
        config = create_default_config()
        changed = True

    if changed:
        _atomic_write_json(path, config)
    return config


def save_config(config: Dict[str, Any], path: Path = CONFIG_PATH) -> None:
    """Persist the configuration to disk."""
    _atomic_write_json(path, config)


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    """Write JSON to disk atomically to avoid partial writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2))
    os.replace(tmp_path, path)
