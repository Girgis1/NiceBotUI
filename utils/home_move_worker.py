"""Qt worker utilities for running home moves without freezing the UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from PySide6.QtCore import QObject, Signal, Slot

from .motor_manager import get_motor_handle
from .config_compat import get_home_positions, get_home_velocity, get_arm_port


@dataclass(slots=True)
class HomeMoveRequest:
    """Parameters describing a home move operation."""

    config: Mapping[str, Any]
    velocity_override: Optional[int] = None
    arm_index: int = 0  # Which arm to home (0 for first arm)


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
        arm_index = self._request.arm_index
        
        # Get home positions using config helper
        positions = get_home_positions(config, arm_index)
        if not positions:
            self.finished.emit(False, f"No home position configured for arm {arm_index}. Set home first.")
            return

        # Check port is configured
        port = get_arm_port(config, arm_index, "robot")
        if not port:
            self.finished.emit(False, f"Robot port not configured for arm {arm_index}. Check settings.")
            return

        # Get velocity
        base_velocity = get_home_velocity(config, arm_index)
        velocity = self._request.velocity_override or base_velocity

        try:
            velocity = int(max(50, min(1200, velocity)))
        except Exception:
            velocity = int(max(50, min(1200, base_velocity)))

        self.progress.emit(f"Connecting to motors (arm {arm_index})...")

        try:
            controller = get_motor_handle(arm_index, config)
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

            # Disable torque after reaching home to let the arm rest
            try:
                if controller.bus:
                    for name in controller.motor_names:
                        controller.bus.write("Torque_Enable", name, 0, normalize=False)
            except Exception:
                pass
        except Exception as exc:  # pragma: no cover - hardware specific
            self.finished.emit(False, f"Home move failed: {exc}")
        else:
            self.finished.emit(True, f"✓ Home position reached @ {velocity}")
