"""Capability detection helpers for graceful degradation."""

from __future__ import annotations

from typing import Any, Dict


def _arm_list_has_ports(arms: list[Dict[str, Any]]) -> bool:
    """Return True if any enabled arm entry has a configured port."""

    for arm in arms or []:
        if not arm.get("enabled", True):
            continue
        port = (arm.get("port") or "").strip()
        if port:
            return True
    return False


def detect_capabilities(config: Dict[str, Any]) -> Dict[str, Any]:
    robot_cfg = config.get("robot", {}) or {}
    arms = robot_cfg.get("arms", []) or []
    followers_available = _arm_list_has_ports(arms)

    teleop_cfg = config.get("teleop", {}) or {}
    teleop_arms = teleop_cfg.get("arms", []) or []
    leaders_available = _arm_list_has_ports(teleop_arms)

    cameras_cfg = config.get("cameras", {}) or {}
    camera_flags = {
        name: bool(cfg.get("index_or_path")) for name, cfg in cameras_cfg.items()
    }

    teleop_available = followers_available and leaders_available

    return {
        "robot": {
            "followers": followers_available,
            "leaders": leaders_available,
        },
        "teleop": {
            "available": teleop_available,
            "followers": followers_available,
            "leaders": leaders_available,
        },
        "cameras": camera_flags,
    }


__all__ = ["detect_capabilities"]
