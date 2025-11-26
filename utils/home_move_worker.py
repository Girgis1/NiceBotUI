"""Qt worker utilities for running home moves without freezing the UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional
import threading

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
                keep_connection=True,  # Keep connection for torque disable
            )

            # Disable torque after reaching home to let the arm rest
            try:
                if controller.bus:
                    for name in controller.motor_names:
                        controller.bus.write("Torque_Enable", name, 0, normalize=False)
            except Exception:
                pass
            finally:
                # Clean up connection
                try:
                    controller.disconnect()
                except Exception:
                    pass
        except Exception as exc:  # pragma: no cover - hardware specific
            self.finished.emit(False, f"Home move failed: {exc}")
        else:
            self.finished.emit(True, f"✓ Home position reached @ {velocity}")


def home_arm_blocking(config: Mapping[str, Any], arm_index: int, velocity_override: Optional[int] = None) -> tuple[bool, str]:
    """Blocking home for a single arm. Returns (success, message)."""
    cfg = dict(config or {})
    positions = get_home_positions(cfg, arm_index)
    if not positions:
        return False, f"No home position configured for arm {arm_index}. Set home first."

    port = get_arm_port(cfg, arm_index, "robot")
    if not port:
        return False, f"Robot port not configured for arm {arm_index}. Check settings."

    base_velocity = get_home_velocity(cfg, arm_index)
    try:
        velocity = int(max(50, min(1200, velocity_override or base_velocity)))
    except Exception:
        velocity = int(max(50, min(1200, base_velocity)))

    try:
        controller = get_motor_handle(arm_index, cfg)
    except Exception as exc:
        return False, f"Motor controller initialisation failed: {exc}"

    try:
        if not controller.connect():
            return False, "Failed to connect to motors."

        controller.set_positions(
            positions,
            velocity=velocity,
            wait=True,
            keep_connection=True,
        )

        # Disable torque after reaching home to let the arm rest
        try:
            if controller.bus:
                for name in controller.motor_names:
                    controller.bus.write("Torque_Enable", name, 0, normalize=False)
        except Exception:
            pass
        finally:
            try:
                controller.disconnect()
            except Exception:
                pass
    except Exception as exc:
        return False, f"Home move failed: {exc}"

    return True, f"✓ Home position reached @ {velocity}"


def home_multiple_arms(config: Mapping[str, Any], arm_indexes: list[int], velocity_override: Optional[int] = None) -> tuple[bool, list[tuple[int, bool, str]]]:
    """Home the selected arms in parallel. Returns aggregate success and per-arm results."""
    results: list[tuple[int, bool, str]] = []

    if not arm_indexes:
        return True, results

    threads = []
    result_map: dict[int, tuple[bool, str]] = {}

    def _run(idx: int):
        result_map[idx] = home_arm_blocking(config, idx, velocity_override)

    for idx in arm_indexes:
        t = threading.Thread(target=_run, args=(idx,), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    for idx in arm_indexes:
        success, msg = result_map.get(idx, (False, "Unknown error"))
        results.append((idx, success, msg))

    return all(r[1] for r in results), results
