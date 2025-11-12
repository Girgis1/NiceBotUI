"""Centralized configuration store to keep a single source of truth."""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Callable

from app.config import CONFIG_PATH, load_config, save_config
from utils.config_compat import ensure_multi_arm_config


class ConfigStore:
    """Singleton wrapper that keeps config mutations consistent across the app."""

    _instance: ConfigStore | None = None

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or CONFIG_PATH
        self._lock = Lock()
        initial = ensure_multi_arm_config(load_config(self._path))
        self._config: dict = initial  # Shared dict reference

    @classmethod
    def instance(cls) -> ConfigStore:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_config(self) -> dict:
        """Return the shared config dictionary."""
        return self._config

    def reload(self) -> dict:
        """Reload config from disk while preserving the shared dict reference."""
        with self._lock:
            fresh = ensure_multi_arm_config(load_config(self._path))
            self._replace_config(fresh)
            return self._config

    def save(self) -> None:
        """Persist the current in-memory config to disk."""
        with self._lock:
            save_config(self._config, self._path)

    def update(self, mutator: Callable[[dict], None]) -> dict:
        """Apply a mutation function and immediately save to disk."""
        with self._lock:
            mutator(self._config)
            save_config(self._config, self._path)
            return self._config

    def set_config(self, new_config: dict, persist: bool = True) -> dict:
        """Replace the entire config (used when saving Settings)."""
        with self._lock:
            normalized = ensure_multi_arm_config(new_config)
            if persist:
                save_config(normalized, self._path)
            self._replace_config(normalized)
            return self._config

    # ------------------------------------------------------------------ helpers
    def _replace_config(self, new_config: dict) -> None:
        """Mutate the shared dict in-place to keep references alive."""
        if self._config is new_config:
            return
        self._config.clear()
        self._config.update(new_config)
