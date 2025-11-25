"""Position-set playback helpers for ExecutionWorker."""

from __future__ import annotations

import time
from typing import Dict, List

from .context import ExecutionContext

RESCUE_RETRY_WINDOW = 2.0  # seconds to keep re-issuing the waypoint after a dropout
RESCUE_RETRY_INTERVAL = 0.15  # seconds between retry sends


def _within_tolerance(current: List[int], target: List[int], tolerance: int) -> bool:
    """Return True if all joints are within tolerance."""
    if not current or len(current) != len(target):
        return False
    return max(abs(current[i] - target[i]) for i in range(len(target))) <= tolerance


def _rescue_waypoint(context: ExecutionContext, target: List[int], velocity: int) -> bool:
    """Keep nudging the same waypoint for a short window when motors momentarily drop out."""
    controller = context.motor_controller
    tol = getattr(controller, "POSITION_TOLERANCE", 10)

    if not controller.bus:
        context.log_warning("Resilience: motor bus unavailable during retry window.")
        return False

    start = time.time()
    warned = False

    while (time.time() - start) < RESCUE_RETRY_WINDOW:
        positions = controller.read_positions_from_bus()
        if _within_tolerance(positions, target, tol):
            if warned:
                context.log_info("Resilience: motor bus recovered, target reached.")
            return True

        # Re-send the goal to keep the bus nudging toward target
        try:
            for idx, motor_name in enumerate(controller.motor_names):
                controller.bus.write("Goal_Position", motor_name, target[idx], normalize=False)
        except Exception as exc:  # Keep going; transient errors are expected here
            if not warned:
                context.log_warning(f"Resilience: retrying waypoint after bus error ({exc})")
            warned = True
            time.sleep(RESCUE_RETRY_INTERVAL)
            continue

        if not warned:
            context.log_warning(
                f"Resilience: motor dropout detected, retrying waypoint for up to {RESCUE_RETRY_WINDOW:.1f}s"
            )
            warned = True

        time.sleep(RESCUE_RETRY_INTERVAL)

    context.log_warning("Resilience: waypoint not confirmed after retries; continuing.")
    return False


def execute_position_component(context: ExecutionContext, component: Dict, speed_override: int) -> None:
    """Execute a position-set component inside a composite recording."""
    positions_list: List[Dict] = component.get("positions", [])

    if not positions_list:
        context.log_warning("No positions in component")
        return

    total_positions = len(positions_list)
    context.log_info(f"Moving through {total_positions} waypoints at {speed_override}% speed")

    for idx, pos_data in enumerate(positions_list):
        if context.should_stop():
            break

        pos_name = pos_data.get("name", f"Position {idx + 1}")
        motor_positions = pos_data.get("motor_positions", [])
        velocity = pos_data.get("velocity", 600)
        wait_for_completion = pos_data.get("wait_for_completion", True)

        velocity = int(velocity * (speed_override / 100.0))

        context.log_info(
            f"  → {pos_name}: {motor_positions[:3]}... @ {velocity} vel"
        )
        context.motor_controller.set_positions(
            motor_positions,
            velocity=velocity,
            wait=wait_for_completion,
            keep_connection=True,
        )
        tol = getattr(context.motor_controller, "POSITION_TOLERANCE", 10)
        reached = _within_tolerance(
            context.motor_controller.read_positions_from_bus(), motor_positions, tol
        ) or _rescue_waypoint(context, motor_positions, velocity)

        progress = int(((idx + 1) / total_positions) * 100)
        if reached:
            context.log_info(f"  ✓ Reached {pos_name} ({progress}%)")
        else:
            context.log_warning(f"  ⚠️ Continuing without confirmed reach for {pos_name} ({progress}%)")


def playback_position_recording(context: ExecutionContext, recording: Dict) -> None:
    """Play back a simple position recording."""
    positions_list = recording.get("positions", [])
    speed = recording.get("speed", 100)
    delays = recording.get("delays", {})

    total_steps = len(positions_list)
    context.log_info(f"Playing {total_steps} positions at {speed}% speed")

    for idx, pos_data in enumerate(positions_list):
        if context.should_stop():
            break

        if isinstance(pos_data, dict):
            positions = pos_data.get("motor_positions", pos_data.get("positions", []))
            velocity = pos_data.get("velocity", 600)
        else:
            positions = pos_data
            velocity = 600

        velocity = int(velocity * (speed / 100.0))

        context.update_progress(idx + 1, total_steps)
        context.set_status(f"Position {idx + 1}/{total_steps}")

        context.log_info(f"→ Position {idx + 1}: {positions[:3]}... @ {velocity} vel")
        context.motor_controller.set_positions(
            positions,
            velocity=velocity,
            wait=True,
            keep_connection=True,
        )
        tol = getattr(context.motor_controller, "POSITION_TOLERANCE", 10)
        reached = _within_tolerance(
            context.motor_controller.read_positions_from_bus(), positions, tol
        ) or _rescue_waypoint(context, positions, velocity)
        if not reached:
            context.log_warning("Resilience: waypoint not confirmed; moving on.")

        delay = delays.get(str(idx), 0)
        if delay > 0:
            context.log_info(f"Delay: {delay}s")
            time.sleep(delay)
