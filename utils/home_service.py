"""Utility helpers for reading and writing home positions on disk."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from app.config import CONFIG_PATH, load_config, save_config
from utils.config_compat import set_home_positions
from utils.config_store import ConfigStore


def save_home_positions(
    positions: Iterable[int],
    arm_index: int,
    home_velocity: int | None = None,
    config_path: Path | None = None,
) -> dict:
    """Persist home positions (and optional velocity) for the requested robot arm.

    Returns:
        Updated configuration dictionary (freshly loaded).
    """

    path = config_path or CONFIG_PATH
    if path != CONFIG_PATH:
        config = load_config(path)
        set_home_positions(config, list(positions), arm_index)
        if home_velocity is not None:
            arms = config.get("robot", {}).get("arms", [])
            if arm_index < len(arms):
                arms[arm_index]["home_velocity"] = home_velocity
        save_config(config, path)
        return config

    store = ConfigStore.instance()

    def mutator(cfg: dict) -> None:
        set_home_positions(cfg, list(positions), arm_index)
        if home_velocity is not None:
            arms = cfg.get("robot", {}).get("arms", [])
            if arm_index < len(arms):
                arms[arm_index]["home_velocity"] = home_velocity

    return store.update(mutator)
