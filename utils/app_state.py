"""Centralized application state store with Qt signals."""

from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import QObject, Signal


class AppStateStore(QObject):
    """Singleton state store that propagates updates to interested listeners."""

    state_changed = Signal(str, object)

    _instance: "AppStateStore | None" = None

    def __init__(self) -> None:
        super().__init__()
        self._state: Dict[str, Any] = {}

    @classmethod
    def instance(cls) -> "AppStateStore":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def snapshot(self) -> Dict[str, Any]:
        """Return a shallow copy of the current state map."""
        return dict(self._state)

    def get(self, key: str, default: Any | None = None) -> Any:
        return self._state.get(key, default)

    def set_state(self, key: str, value: Any) -> None:
        """Set ``key`` to ``value`` and emit if it changed."""
        current = self._state.get(key)
        if current == value:
            return
        self._state[key] = value
        self.state_changed.emit(key, value)

    def update_namespace(self, namespace: str, values: Dict[str, Any]) -> None:
        """Bulk update of ``namespace.*`` entries."""
        for name, value in values.items():
            dotted = f"{namespace}.{name}"
            self.set_state(dotted, value)
