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
    speed_multiplier: Optional[float] = None


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

        base_config = dict(self._request.config or {})
        rest_config = dict(base_config.get("rest_position") or {})
        positions = rest_config.get("positions")

        if not positions:
            self.finished.emit(False, "No home position configured. Set home first.")
            return

        robot_cfg = base_config.get("robot") or {}
        if not robot_cfg.get("port"):
            self.finished.emit(False, "Robot port not configured. Check settings.")
            return

        try:
            velocity = self._resolve_velocity(rest_config)
        except ValueError as exc:
            self.finished.emit(False, str(exc))
            return

        control_cfg = dict(base_config.get("control") or {})
        multiplier = self._resolve_multiplier(control_cfg.get("speed_multiplier"))
        if self._request.speed_multiplier is not None:
            multiplier = self._resolve_multiplier(self._request.speed_multiplier)
        control_cfg["speed_multiplier"] = multiplier

        # Prepare an isolated config for the motor controller so we avoid mutating caller state.
        run_config = dict(base_config)
        run_config["control"] = control_cfg
        run_config["rest_position"] = rest_config

        self.progress.emit("Connecting to motors...")

        try:
            controller = MotorController(run_config)
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

    def _resolve_velocity(self, rest_config: Mapping[str, Any]) -> int:
        """Return the target velocity for the move."""

        candidate = self._request.velocity_override
        if candidate is None:
            candidate = rest_config.get("velocity", 600)

        try:
            velocity = int(candidate)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid home velocity: {candidate}") from exc

        return max(50, min(2000, velocity))

    def _resolve_multiplier(self, default: Optional[float]) -> float:
        """Clamp the supplied speed multiplier to a safe range."""

        candidate = self._request.speed_multiplier
        if candidate is None:
            candidate = default if default is not None else 1.0

        try:
            multiplier = float(candidate)
        except (TypeError, ValueError):
            multiplier = 1.0

        return max(0.2, min(1.5, multiplier))
