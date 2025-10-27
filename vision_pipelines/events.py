"""Centralized Qt event bus for the vision pipeline runtime."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class VisionEventBus(QObject):
    """Singleton Qt signal hub for cross-component communication."""

    _instance: "VisionEventBus" | None = None

    handDetectionChanged = Signal(str, bool, float)
    pipelineResult = Signal(str, str, dict)
    profileUpdated = Signal(dict)

    def __init__(self) -> None:
        super().__init__()

    @classmethod
    def instance(cls) -> "VisionEventBus":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


__all__ = ["VisionEventBus"]
