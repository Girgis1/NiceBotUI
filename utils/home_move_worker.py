"""Qt worker utilities for non-blocking home moves.

These helpers keep long-running motor operations off the UI thread so the
interface remains responsive while the robot returns to a safe position.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot

from .motor_controller import MotorController


@dataclass(slots=True)
class HomeMoveRequest:
    """Parameters describing a home-move operation."""

    config: dict
    velocity_override: Optional[int] = None
    speed_multiplier: float = 1.0


class HomeMoveWorker(QObject):
    """Execute the home move sequence in a background thread."""

    progress = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, request: HomeMoveRequest, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._request = request

    @Slot()
    def run(self) -> None:
        """Perform the home move while emitting progress updates."""

        config = dict(self._request.config or {})
        rest_config = config.get("rest_position", {}) or {}
        positions = rest_config.get("positions")

        if not positions:
            self.finished.emit(False, "No home position saved. Set home before moving.")
            return

        base_velocity = rest_config.get("velocity", 600)
        velocity = self._request.velocity_override or base_velocity

        try:
            multiplier = float(self._request.speed_multiplier or 1.0)
        except Exception:
            multiplier = 1.0

        # Clamp multiplier to safe range to avoid runaway speeds.
        multiplier = max(0.2, min(2.0, multiplier))

        try:
            velocity = int(velocity)
        except Exception:
            velocity = int(base_velocity)

        velocity = max(50, min(2000, int(velocity * multiplier)))

        self.progress.emit("Connecting to motors...")

        try:
            controller = MotorController(config)
        except Exception as exc:  # pragma: no cover - hardware/config failure
            self.finished.emit(False, f"Motor controller init failed: {exc}")
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
        except Exception as exc:  # pragma: no cover - dependent on hardware
            self.finished.emit(False, f"Failed to reach home: {exc}")
        else:
            self.finished.emit(True, f"✓ Home position reached @ {velocity}")
        finally:
            try:
                controller.disconnect()
            except Exception:
                pass
