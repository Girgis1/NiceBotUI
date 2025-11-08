"""Position-set playback helpers for ExecutionWorker."""

from __future__ import annotations

import time
from typing import Dict, List

from .context import ExecutionContext


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

        progress = int(((idx + 1) / total_positions) * 100)
        context.log_info(f"  ✓ Reached {pos_name} ({progress}%)")


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

        delay = delays.get(str(idx), 0)
        if delay > 0:
            context.log_info(f"Delay: {delay}s")
            time.sleep(delay)
