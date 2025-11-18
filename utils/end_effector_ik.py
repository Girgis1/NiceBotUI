"""End-effector keyboard style inverse kinematics helpers.

This module adapts the "ee keyboard" control method from the XLeRobot
simulation tooling so that the NiceBotUI teleop keypad can command
planar end-effector motions using inverse kinematics.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional, Tuple

from utils.logging_utils import log_exception


UNITS_PER_RAD = 4095.0 / (2 * math.pi)


@dataclass
class ArmGeometry:
    """Kinematic constants that mirror the ee keyboard reference."""

    upper_arm: float = 0.1159
    forearm: float = 0.1350
    theta1_offset: float = math.atan2(0.028, 0.11257)
    theta2_offset: float = math.atan2(0.0052, 0.1349) + theta1_offset
    min_joint2: float = -0.1
    max_joint2: float = 3.45
    min_joint3: float = -0.2
    max_joint3: float = math.pi
    default_x: float = 0.162
    default_y: float = 0.118


def clamp_workspace(x: float, y: float, geometry: ArmGeometry) -> Tuple[float, float]:
    """Clamp an XY target to the reachable workspace of the planar arm."""

    r = math.hypot(x, y)
    max_reach = geometry.upper_arm + geometry.forearm
    min_reach = abs(geometry.upper_arm - geometry.forearm)

    if r > max_reach:
        scale = max_reach / r
        x *= scale
        y *= scale
    elif 0 < r < min_reach:
        scale = min_reach / r
        x *= scale
        y *= scale
    return x, y


def solve_planar_ik(x: float, y: float, geometry: ArmGeometry) -> Tuple[float, float, float, float]:
    """Solve planar IK returning joint2, joint3 and the clamped XY target."""

    x, y = clamp_workspace(x, y, geometry)
    r = math.hypot(x, y)

    # Law of cosines for the elbow angle (theta2)
    cos_theta2 = -(r ** 2 - geometry.upper_arm ** 2 - geometry.forearm ** 2)
    cos_theta2 /= (2 * geometry.upper_arm * geometry.forearm)
    cos_theta2 = max(-1.0, min(1.0, cos_theta2))
    theta2 = math.pi - math.acos(cos_theta2)

    # Shoulder angle
    beta = math.atan2(y, x)
    gamma = math.atan2(
        geometry.forearm * math.sin(theta2),
        geometry.upper_arm + geometry.forearm * math.cos(theta2),
    )
    theta1 = beta + gamma

    joint2 = theta1 + geometry.theta1_offset
    joint3 = theta2 + geometry.theta2_offset

    joint2 = max(geometry.min_joint2, min(geometry.max_joint2, joint2))
    joint3 = max(geometry.min_joint3, min(geometry.max_joint3, joint3))

    return joint2, joint3, x, y


class EndEffectorIKController:
    """Utility that mirrors the ee keyboard logic for hardware control."""

    def __init__(
        self,
        motor_controller,
        *,
        geometry: ArmGeometry | None = None,
        ee_step: float = 0.005,
        default_velocity: int = 600,
    ) -> None:
        self.motor_controller = motor_controller
        self.geometry = geometry or ArmGeometry()
        self.ee_step = ee_step
        self.default_velocity = default_velocity
        self.last_target: Tuple[float, float] | None = (
            self.geometry.default_x,
            self.geometry.default_y,
        )
        self.last_error: str | None = None

    # ------------------------------------------------------------------
    # Utility helpers

    def set_motor_controller(self, motor_controller) -> None:
        self.motor_controller = motor_controller
        self.last_target = None

    def format_target(self) -> str:
        if not self.last_target:
            return "EE X: -- m\nEE Y: -- m"
        x, y = self.last_target
        return f"EE X: {x:.3f} m\nEE Y: {y:.3f} m"

    def _units_to_rad(self, value: int) -> float:
        return (value / 4095.0) * 2 * math.pi

    def _rad_to_units(self, angle: float) -> int:
        units = angle * UNITS_PER_RAD
        return int(max(0, min(4095, units)))

    # ------------------------------------------------------------------
    # Synchronization helpers

    def sync_with_robot(self) -> bool:
        """Read the current arm pose and derive the matching EE target."""

        if not self.motor_controller:
            self.last_error = "Motor controller unavailable"
            return False

        positions = []
        try:
            if self.motor_controller.bus:
                positions = self.motor_controller.read_positions_from_bus()
            if not positions:
                positions = self.motor_controller.read_positions()
        except Exception as exc:  # pragma: no cover - hardware interaction
            log_exception("IK: failed to read robot pose", exc, level="warning")
            self.last_error = str(exc)
            return False

        if not positions or len(positions) < 3:
            self.last_error = "Unable to read joint positions"
            return False

        shoulder = self._units_to_rad(int(positions[1]))
        elbow = self._units_to_rad(int(positions[2]))

        theta1 = shoulder - self.geometry.theta1_offset
        theta2 = elbow - self.geometry.theta2_offset

        x = self.geometry.upper_arm * math.cos(theta1) + self.geometry.forearm * math.cos(theta2)
        y = self.geometry.upper_arm * math.sin(theta1) + self.geometry.forearm * math.sin(theta2)

        self.last_target = (x, y)
        self.last_error = None
        return True

    # ------------------------------------------------------------------
    # Command helpers

    def reset_target(self) -> Tuple[bool, Optional[Tuple[float, float]]]:
        """Return to the default IK target."""

        return self._write_target(self.geometry.default_x, self.geometry.default_y)

    def nudge(self, axis: str, direction: int) -> Tuple[bool, Optional[Tuple[float, float]]]:
        """Incrementally move the EE target along the requested axis."""

        if axis not in ("x", "y"):
            raise ValueError(f"Unsupported axis: {axis}")

        if not self.last_target:
            if not self.sync_with_robot():
                return False, None

        x, y = self.last_target
        delta = self.ee_step * direction
        if axis == "x":
            x += delta
        else:
            y += delta

        return self._write_target(x, y)

    def _write_target(self, x: float, y: float) -> Tuple[bool, Optional[Tuple[float, float]]]:
        """Solve IK for the new target and send it to the motors."""

        if not self.motor_controller:
            self.last_error = "Motor controller unavailable"
            return False, None

        try:
            joint2, joint3, clamped_x, clamped_y = solve_planar_ik(x, y, self.geometry)
        except Exception as exc:  # pragma: no cover - math edge cases
            log_exception("IK: failed to solve inverse kinematics", exc, level="error")
            self.last_error = str(exc)
            return False, None

        target2 = self._rad_to_units(joint2)
        target3 = self._rad_to_units(joint3)

        bus = getattr(self.motor_controller, "bus", None)
        names = getattr(self.motor_controller, "motor_names", [])
        if not bus or len(names) < 3:
            self.last_error = "Motor bus unavailable"
            return False, None

        velocity = int(max(120, min(1200, self.default_velocity)))
        try:
            bus.write("Goal_Velocity", names[1], velocity, normalize=False)
            bus.write("Goal_Velocity", names[2], velocity, normalize=False)
            bus.write("Goal_Position", names[1], target2, normalize=False)
            bus.write("Goal_Position", names[2], target3, normalize=False)
        except Exception as exc:  # pragma: no cover - hardware interaction
            log_exception("IK: failed to write IK target", exc, level="error")
            self.last_error = str(exc)
            return False, None

        self.last_target = (clamped_x, clamped_y)
        self.last_error = None
        return True, self.last_target

