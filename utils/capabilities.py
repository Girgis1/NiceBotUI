"""Capability detection helpers for graceful degradation."""

from __future__ import annotations

from typing import Any, Dict


def detect_capabilities(config: Dict[str, Any]) -> Dict[str, Any]:
    robot_cfg = config.get("robot", {}) or {}
    arms = robot_cfg.get("arms", []) or []
    followers_available = any(arm.get("enabled", True) for arm in arms)

    teleop_cfg = config.get("teleop", {}) or {}
    teleop_arms = teleop_cfg.get("arms", []) or []
    leaders_available = any(arm.get("enabled", True) for arm in teleop_arms)

    cameras_cfg = config.get("cameras", {}) or {}
    camera_flags = {
        name: bool(cfg.get("index_or_path")) for name, cfg in cameras_cfg.items()
    }

    return {
        "robot": {
            "followers": followers_available,
            "leaders": leaders_available,
        },
        "cameras": camera_flags,
    }


__all__ = ["detect_capabilities"]
