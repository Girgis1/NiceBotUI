"""Helpers to prepare motor buses before launching teleop."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from utils.logging_utils import log_exception
from utils.safe_print import safe_print
from utils.motor_manager import get_motor_handle

PROJECT_ROOT = Path(__file__).resolve().parents[1]

try:  # HomePos provides the Feetech bus helpers we already use elsewhere
    import sys

    sys.path.insert(0, str(PROJECT_ROOT))
    from HomePos import MOTOR_NAMES, create_motor_bus  # type: ignore
except Exception as exc:  # pragma: no cover - hardware-specific import
    MOTOR_NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]

    def _missing_bus(*args, **kwargs):
        raise RuntimeError(f"Feetech motor libraries unavailable: {exc}")

    create_motor_bus = _missing_bus  # type: ignore


class TeleopPreflight:
    """Reset Goal_Velocity/Acceleration for configured teleop arms."""

    def __init__(self, config: dict):
        self.config = config
        self.skip_prefight = bool(int(os.environ.get("TELEOP_SKIP_PREFLIGHT", "0") or 0))

    def prepare(self, arm_mode: str) -> bool:
        if self.skip_prefight:
            safe_print("[TeleopPreflight] Skipping preflight (TELEOP_SKIP_PREFLIGHT=1)")
            return True

        targets = self._select_ports(arm_mode)
        if not targets:
            safe_print("[TeleopPreflight] No ports selected for teleop preflight.")
            return False

        safe_print("[TeleopPreflight] Resetting Goal_Velocity for:")
        ok = True
        for label, port in targets:
            safe_print(f"  • {label}: {port}")
            result = self._reset_port(port)
            ok = ok and result

        if not ok:
            safe_print("[TeleopPreflight] ⚠️  One or more ports failed to reset.")
        else:
            safe_print("[TeleopPreflight] ✓ Motor velocities reset")
        return ok

    # ------------------------------------------------------------------
    # Internal helpers

    def _select_ports(self, arm_mode: str) -> List[Tuple[str, str]]:
        followers = (self.config.get("robot", {}) or {}).get("arms", []) or []
        leaders = (self.config.get("teleop", {}) or {}).get("arms", []) or []

        def port_for(arms: list, index: int) -> Tuple[str, str] | None:
            if index >= len(arms):
                return None
            arm = arms[index] or {}
            port = (arm.get("port") or "").strip()
            if not port:
                return None
            label = arm.get("name") or arm.get("id") or f"Arm {index + 1}"
            return label, port

        targets: List[Tuple[str, str]] = []
        indices = []
        if arm_mode == "left":
            indices = [0]
        elif arm_mode == "right":
            indices = [1]
        else:
            indices = list(range(len(followers)))

        for idx in indices:
            follower = port_for(followers, idx)
            if follower:
                targets.append((f"Follower {follower[0]}", follower[1]))
            leader = port_for(leaders, idx)
            if leader:
                targets.append((f"Leader {leader[0]}", leader[1]))
        return targets

    def _reset_port(self, port: str, velocity: int = 4000, acceleration: int = 255) -> bool:
        # Use the shared handle to avoid grabbing the port twice
        try:
            handle = get_motor_handle(0, {})  # arm index not used here; port matters
        except Exception:
            handle = None

        retries = 3
        for attempt in range(1, retries + 1):
            bus = None
            try:
                bus = create_motor_bus(port)
                # If supported, cap per-op timeouts to avoid hangs
                if hasattr(bus, "timeout"):
                    bus.timeout = 2.0
            except Exception as exc:
                log_exception(f"TeleopPreflight: connect failed ({port})", exc)
                time.sleep(0.2)
                continue

            try:
                success = True
                for name in MOTOR_NAMES:
                    try:
                        bus.write("Goal_Velocity", name, velocity, normalize=False)
                        bus.write("Acceleration", name, acceleration, normalize=False)
                        current = bus.read("Goal_Velocity", name, normalize=False)
                        if current < velocity - 50:  # Allow small tolerance
                            success = False
                            safe_print(f"     ⚠️ {port} {name}: still {current}")
                    except Exception as exc:
                        success = False
                        log_exception(f"TeleopPreflight: write failed ({port} {name})", exc, level="warning")
                return success
            finally:
                if bus:
                    try:
                        bus.disconnect()
                    except Exception:
                        pass
            time.sleep(0.2)
        return False


__all__ = ["TeleopPreflight"]
