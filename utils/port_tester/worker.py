"""Utilities for jogging arms to identify which port maps to which hardware."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable, Sequence

from PySide6.QtCore import QThread, Signal

from HomePos import MOTOR_NAMES, create_motor_bus

# Position bounds for Feetech STS3215 motors
MIN_POSITION = 0
MAX_POSITION = 4095


def _clamp_position(value: int) -> int:
    return max(MIN_POSITION, min(MAX_POSITION, value))


def _motor_name_from_id(motor_id: int) -> str:
    index = max(1, min(len(MOTOR_NAMES), motor_id)) - 1
    return MOTOR_NAMES[index]


@dataclass
class PortTestSettings:
    """Adjustable motion parameters for port tests."""

    moves: Sequence[Sequence[tuple[int, int]]] = (
        (
            (4, -200),  # wrist flex up slightly
            (3, -200),  # elbow flex up
        ),
        (
            (2, 300),  # shoulder lift up
        ),
    )
    velocity: int = 550
    pause_s: float = 0.5


@dataclass
class PortTestRequest:
    """Single test invocation."""

    port: str
    label: str
    settings: PortTestSettings | None = None


class PortTestWorker(QThread):
    """Background worker that shakes arms on the requested ports."""

    progress = Signal(str)
    completed = Signal(bool, str)

    def __init__(
        self,
        requests: Iterable[PortTestRequest],
        default_settings: PortTestSettings | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.requests = list(requests)
        self.default_settings = default_settings or PortTestSettings()
        self._online_ports: list[str] = []

    def run(self) -> None:
        if not self.requests:
            self.completed.emit(False, "❌ No ports queued for testing")
            return

        overall_success = True
        for request in self.requests:
            label = request.label or request.port
            settings = request.settings or self.default_settings
            self.progress.emit(f"🔄 Testing {label} ({request.port})…")
            try:
                self._exercise_port(request.port, settings)
            except Exception as exc:  # pragma: no cover - hardware exceptions
                overall_success = False
                self.progress.emit(f"❌ {label}: {exc}")
            else:
                self._online_ports.append(request.port)
                self.progress.emit(f"✓ {label} responded")

        if self._online_ports:
            port_summary = ", ".join(sorted(set(self._online_ports)))
        else:
            port_summary = "None"
        summary = f"{'✓' if overall_success else '⚠️'} Ports online: {port_summary}"
        self.completed.emit(overall_success, summary)

    def _exercise_port(self, port: str, settings: PortTestSettings) -> None:
        """Connect to the given port, jog selected motors, and relax."""
        bus = create_motor_bus(port)
        all_motor_ids = [motor_id for step in settings.moves for motor_id, _ in step]
        unique_names = list(dict.fromkeys(_motor_name_from_id(motor_id) for motor_id in all_motor_ids))

        try:
            self._enable_and_configure(bus, unique_names, settings.velocity)
            baseline = self._read_positions(bus, unique_names)
            current_positions = baseline.copy()

            for step in settings.moves:
                for motor_id, delta in step:
                    name = _motor_name_from_id(motor_id)
                    start_value = current_positions.get(name, baseline.get(name))
                    if start_value is None:
                        continue
                    target = _clamp_position(start_value + delta)
                    bus.write("Goal_Position", name, target, normalize=False)
                    current_positions[name] = target
                time.sleep(settings.pause_s)
        finally:
            try:
                for name in unique_names:
                    bus.write("Torque_Enable", name, 0, normalize=False)
            finally:
                bus.disconnect()

    @staticmethod
    def _enable_and_configure(bus, motor_names: Sequence[str], velocity: int) -> None:
        for name in motor_names:
            bus.write("Torque_Enable", name, 1, normalize=False)
            bus.write("Goal_Velocity", name, velocity, normalize=False)

    @staticmethod
    def _read_positions(bus, motor_names: Sequence[str]) -> dict[str, int]:
        positions: dict[str, int] = {}
        for name in motor_names:
            positions[name] = int(bus.read("Present_Position", name, normalize=False))
        return positions
