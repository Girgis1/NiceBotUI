"""Background workers for home/return operations.

Provides helpers that keep long-running home moves off the UI thread so the
interface stays responsive even when the robot is travelling.
"""

from __future__ import annotations

import subprocess
from typing import Iterable, Mapping, Optional

from PySide6.QtCore import QThread, Signal


class HomeProcessWorker(QThread):
    """Run the HomePos script in a background thread."""

    completed = Signal(bool, str, str)

    def __init__(
        self,
        command: Iterable[str],
        *,
        env: Optional[Mapping[str, str]] = None,
        timeout: int = 45,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._command = list(command)
        self._env = dict(env) if env is not None else None
        self._timeout = timeout

    def run(self) -> None:  # type: ignore[override]
        try:
            result = subprocess.run(
                self._command,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                env=self._env,
            )
            self.completed.emit(result.returncode == 0, result.stdout, result.stderr)
        except Exception as exc:  # pragma: no cover - defensive subprocess handling
            self.completed.emit(False, "", str(exc))


class MotorHomeWorker(QThread):
    """Move the robot to its configured home position in the background."""

    progress = Signal(str)
    completed = Signal(bool, str)

    def __init__(self, config: Mapping, velocity: int, *, parent=None) -> None:
        super().__init__(parent)
        self._config = dict(config)
        self._velocity = int(velocity)

    def run(self) -> None:  # type: ignore[override]
        rest_config = self._config.get("rest_position", {})
        positions = rest_config.get("positions")
        if not positions:
            self.completed.emit(False, "No home position saved")
            return

        base_velocity = rest_config.get("velocity", 600)
        try:
            target_velocity = int(self._velocity)
        except Exception:
            target_velocity = base_velocity

        target_velocity = max(50, min(1200, target_velocity))
        self.progress.emit(f"Connecting to motors...")

        try:
            from utils.motor_controller import MotorController  # Local import to avoid cycles
        except Exception as exc:  # pragma: no cover - import safety
            self.completed.emit(False, f"Motor controller import failed: {exc}")
            return

        try:
            controller = MotorController(self._config.get("robot", {}))
        except Exception as exc:
            self.completed.emit(False, f"Motor controller init failed: {exc}")
            return

        try:
            if not controller.connect():
                self.completed.emit(False, "Failed to connect to motors")
                return

            self.progress.emit(f"Moving to home @ velocity {target_velocity}")
            controller.set_positions(
                positions,
                velocity=target_velocity,
                wait=True,
                keep_connection=False,
            )
        except Exception as exc:  # pragma: no cover - hardware dependent failure
            self.completed.emit(False, f"Home move failed: {exc}")
        else:
            self.completed.emit(True, f"✓ Home position reached @ {target_velocity}")
        finally:
            try:
                controller.disconnect()
            except Exception:
                pass
