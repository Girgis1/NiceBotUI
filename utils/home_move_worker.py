"""Qt worker utilities for running home moves without freezing the UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from PySide6.QtCore import QObject, Signal, Slot

from .motor_controller import MotorController


@dataclass(slots=True)
class HomeMoveRequest:
    """Parameters describing a home move operation."""

    config: Mapping[str, Any]
    velocity_override: Optional[int] = None


class HomeMoveWorker(QObject):
    """Execute the home move sequence on a background thread."""

    progress = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, request: HomeMoveRequest, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._request = request

    @Slot()
    def run(self) -> None:
        """Perform the home move while emitting progress updates."""

        config = dict(self._request.config or {})
        rest_config = dict(config.get("rest_position") or {})
        positions = rest_config.get("positions")

        if not positions:
            self.finished.emit(False, "No home position configured. Set home first.")
            return

        robot_cfg = config.get("robot") or {}
        if not robot_cfg.get("port"):
            self.finished.emit(False, "Robot port not configured. Check settings.")
            return

        base_velocity = rest_config.get("velocity", 600)
        velocity = self._request.velocity_override or base_velocity

        try:
            velocity = int(max(50, min(1200, velocity)))
        except Exception:
            velocity = int(max(50, min(1200, base_velocity)))

        self.progress.emit("Connecting to motors...")

        try:
            controller = MotorController(config)
        except Exception as exc:  # pragma: no cover - controller init touches hardware libs
            self.finished.emit(False, f"Motor controller initialisation failed: {exc}")
            return

        try:
            if not controller.connect():
                self.finished.emit(False, "Failed to connect to motors.")
                return

            self.progress.emit(f"Moving to home @ velocity {velocity}")
            controller.set_positions(
                positions,
                velocity=velocity,
                wait=True,
                keep_connection=False,
            )
        except Exception as exc:  # pragma: no cover - hardware specific
            self.finished.emit(False, f"Home move failed: {exc}")
        else:
            self.finished.emit(True, f"✓ Home position reached @ {velocity}")
        finally:
            try:
                controller.disconnect()
            except Exception:
                pass
