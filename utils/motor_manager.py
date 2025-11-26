"""
Motor Manager - Single-owner motor access per arm with shared telemetry.

Purpose:
- Ensure only one controller owns a given serial port at a time.
- Provide shared access to the same controller for multiple callers.
- Offer lightweight telemetry publishing for diagnostics without reopening the bus.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Dict, List, Optional

from utils.motor_controller import MotorController
from utils.logging_utils import log_exception


class MotorHandle:
    """Wrapper around MotorController that enforces single ownership and shares telemetry."""

    TELEMETRY_INTERVAL = 0.2  # seconds, ~5 Hz

    def __init__(self, config: dict, arm_index: int):
        self._config = config
        self._arm_index = arm_index
        self._controller = MotorController(config, arm_index=arm_index)
        self._lock = threading.RLock()
        self._telemetry_thread: Optional[threading.Thread] = None
        self._telemetry_running = threading.Event()
        self._telemetry_subs: List[Callable[[dict], None]] = []
        self._last_telemetry: Optional[List[Optional[dict]]] = None

    @property
    def speed_multiplier(self) -> float:
        return getattr(self._controller, "speed_multiplier", 1.0)

    @speed_multiplier.setter
    def speed_multiplier(self, value: float) -> None:
        self._controller.speed_multiplier = value

    @property
    def motor_names(self):
        return self._controller.motor_names

    @property
    def bus(self):
        return self._controller.bus

    def connect(self) -> bool:
        with self._lock:
            if self._controller.bus:
                return True
            if not self._controller.connect():
                return False
            self._start_telemetry()
            return True

    def disconnect(self) -> None:
        with self._lock:
            self._stop_telemetry()
            try:
                self._controller.disconnect()
            except Exception as exc:
                log_exception("MotorHandle: disconnect failed", exc, level="warning")

    def set_positions(self, *args, **kwargs):
        with self._lock:
            return self._controller.set_positions(*args, **kwargs)

    def read_positions_from_bus(self):
        with self._lock:
            return self._controller.read_positions_from_bus()

    def read_positions(self):
        with self._lock:
            return self._controller.read_positions()

    def emergency_stop(self):
        with self._lock:
            try:
                self._controller.emergency_stop()
            except Exception as exc:
                log_exception("MotorHandle: emergency_stop failed", exc, level="warning")

    def subscribe(self, callback: Callable[[dict], None]) -> None:
        """Subscribe to telemetry dicts (list per motor)."""
        self._telemetry_subs.append(callback)

    def unsubscribe(self, callback: Callable[[dict], None]) -> None:
        try:
            self._telemetry_subs.remove(callback)
        except ValueError:
            pass

    def last_telemetry(self) -> Optional[List[Optional[dict]]]:
        return self._last_telemetry

    # ------------------------------------------------------------------
    # Telemetry

    def _start_telemetry(self):
        if self._telemetry_thread and self._telemetry_thread.is_alive():
            return
        self._telemetry_running.set()
        self._telemetry_thread = threading.Thread(
            target=self._telemetry_loop, name=f"MotorTelemetry-{self._arm_index}", daemon=True
        )
        self._telemetry_thread.start()

    def _stop_telemetry(self):
        self._telemetry_running.clear()
        if self._telemetry_thread and self._telemetry_thread.is_alive():
            self._telemetry_thread.join(timeout=0.5)

    def _telemetry_loop(self):
        while self._telemetry_running.is_set():
            snapshot = []
            try:
                with self._lock:
                    bus = self._controller.bus
                    if not bus:
                        time.sleep(self.TELEMETRY_INTERVAL)
                        continue
                    for name in self._controller.motor_names:
                        try:
                            data = {
                                "position": int(bus.read("Present_Position", name, normalize=False)),
                                "goal": int(bus.read("Goal_Position", name, normalize=False)),
                                "velocity": int(bus.read("Present_Velocity", name, normalize=False)),
                                "load": int(bus.read("Present_Load", name, normalize=False)),
                                "temperature": int(bus.read("Present_Temperature", name, normalize=False)),
                                "current": int(bus.read("Present_Current", name, normalize=False)),
                                "voltage": int(bus.read("Present_Voltage", name, normalize=False)),
                                "moving": int(bus.read("Moving", name, normalize=False)),
                            }
                            snapshot.append(data)
                        except Exception as exc:
                            log_exception("MotorHandle: telemetry read failed", exc, level="warning")
                            snapshot.append(None)
                self._last_telemetry = snapshot
                if snapshot and self._telemetry_subs:
                    for cb in list(self._telemetry_subs):
                        try:
                            cb(snapshot)
                        except Exception as exc:
                            log_exception("MotorHandle: telemetry callback failed", exc, level="warning")
            finally:
                time.sleep(self.TELEMETRY_INTERVAL)


class MotorManager:
    """Singleton registry of MotorHandles keyed by arm index."""

    _instance: Optional["MotorManager"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._handles: Dict[int, MotorHandle] = {}

    @classmethod
    def instance(cls) -> "MotorManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = MotorManager()
            return cls._instance

    def get_handle(self, arm_index: int, config: dict) -> MotorHandle:
        with self._lock:
            if arm_index not in self._handles:
                self._handles[arm_index] = MotorHandle(config, arm_index)
            return self._handles[arm_index]

    def emergency_stop_all(self):
        with self._lock:
            for handle in self._handles.values():
                handle.emergency_stop()

    def disconnect_all(self):
        with self._lock:
            for handle in self._handles.values():
                handle.disconnect()


def get_motor_handle(arm_index: int, config: dict) -> MotorHandle:
    """Convenience accessor."""
    return MotorManager.instance().get_handle(arm_index, config)
