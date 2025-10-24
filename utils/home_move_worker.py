"""Qt worker utilities to run home moves without blocking the UI thread."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot

from .motor_controller import MotorController


@dataclass(slots=True)
class HomeMoveRequest:
    """Request parameters for a home move operation."""

    config: dict
    velocity_override: Optional[int] = None
    speed_multiplier: float = 1.0


class HomeMoveWorker(QObject):
    """Background worker that moves the arm to the configured home position.

    The worker keeps all blocking motor operations off the UI thread so that
    the Qt event loop stays responsive while the arm travels home.
    """

    progress = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, request: HomeMoveRequest, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._request = request

    @Slot()
    def run(self) -> None:
        """Execute the home move sequence."""

        config = self._request.config or {}
        rest_config = config.get("rest_position", {})
        positions = rest_config.get("positions")

        if not positions:
            self.finished.emit(False, "No home position saved. Set home before moving.")
            return

        base_velocity = rest_config.get("velocity", 600)
        velocity = self._request.velocity_override or base_velocity

        try:
            velocity = int(max(50, min(1200, velocity * self._request.speed_multiplier)))
        except Exception:
            velocity = int(max(50, min(1200, base_velocity)))

        self.progress.emit("Connecting to motors...")

        try:
            controller = MotorController(config)
        except Exception as exc:
            self.finished.emit(False, f"Motor controller init failed: {exc}")
            return

        try:
            if not controller.connect():
                self.finished.emit(False, "Failed to connect to motors.")
                return

            self.progress.emit(f"Moving to home @ velocity {velocity}")
            controller.set_positions(positions, velocity=velocity, wait=True, keep_connection=False)
        except Exception as exc:  # pragma: no cover - hardware dependent
            self.finished.emit(False, f"Failed to reach home: {exc}")
        else:
            self.finished.emit(True, f"✓ Home position reached @ {velocity}")
        finally:
            try:
                controller.disconnect()
            except Exception:
                pass
