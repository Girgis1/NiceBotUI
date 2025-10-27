"""Background workers for home/return operations.

These helpers offload long-running home movement logic from the Qt GUI
thread so the interface stays responsive even if the robot takes a long
time to settle.  The design intentionally keeps error handling defensive
to avoid leaving the UI in an uncertain state when hardware faults occur.
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
        timeout: int = 30,
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
        except Exception as exc:  # pragma: no cover - subprocess errors are environment-specific
            self.completed.emit(False, "", str(exc))


class MotorHomeWorker(QThread):
    """Move the robot to its configured home position in the background."""

    completed = Signal(bool, str)

    def __init__(self, config: Mapping, velocity: int, parent=None) -> None:
        super().__init__(parent)
        self._config = dict(config)
        self._velocity = velocity

    def run(self) -> None:  # type: ignore[override]
        try:
            from utils.motor_controller import MotorController  # Local import to avoid circular deps

            rest_config = self._config.get("rest_position", {})
            positions = rest_config.get("positions")
            if not positions:
                self.completed.emit(False, "No home position saved")
                return

            motor_config = self._config.get("robot", {})
            controller = MotorController(motor_config)
            if not controller.connect():
                self.completed.emit(False, "Failed to connect to motors")
                return

            try:
                controller.set_positions(
                    positions,
                    velocity=self._velocity,
                    wait=True,
                    keep_connection=False,
                )
            finally:
                try:
                    controller.disconnect()
                except Exception:
                    pass

            self.completed.emit(True, "")
        except Exception as exc:  # pragma: no cover - hardware interactions
            self.completed.emit(False, str(exc))
