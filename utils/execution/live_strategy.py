"""Live recording playback helpers."""

from __future__ import annotations

import time
from typing import Dict

from .context import ExecutionContext


def execute_live_component(context: ExecutionContext, component: Dict, speed_override: int) -> None:
    """Execute a live-recording component inside a composite recording."""
    recorded_data = component.get("recorded_data", [])

    if not recorded_data:
        context.log_warning("No recorded data in component")
        return

    total_points = len(recorded_data)
    context.log_info(f"Playing {total_points} recorded points at {speed_override}% speed")

    start_time = time.time()

    for idx, point in enumerate(recorded_data):
        if context.should_stop():
            break

        positions = point["positions"]
        target_timestamp = point["timestamp"] * (100.0 / speed_override)
        velocity = int(point.get("velocity", 600) * (speed_override / 100.0))

        current_time = time.time() - start_time
        wait_time = target_timestamp - current_time
        if wait_time > 0:
            time.sleep(wait_time)

        if idx % 10 == 0:
            progress = int((idx / total_points) * 100)
            context.log_info(f"  → Point {idx}/{total_points} ({progress}%)")

        context.motor_controller.set_positions(
            positions,
            velocity=velocity,
            wait=False,
            keep_connection=True,
        )


def playback_live_recording(context: ExecutionContext, recording: Dict) -> None:
    """Play back a recorded live trajectory with time-based interpolation."""
    recorded_data = recording.get("recorded_data", [])
    speed = recording.get("speed", 100)

    if not recorded_data:
        context.log_warning("No recorded data found")
        return

    total_points = len(recorded_data)
    context.log_info(f"Playing {total_points} recorded points at {speed}% speed")

    start_time = time.time()

    for idx, point in enumerate(recorded_data):
        if context.should_stop():
            break

        positions = point["positions"]
        target_timestamp = point["timestamp"] * (100.0 / speed)
        velocity = int(point.get("velocity", 600) * (speed / 100.0))

        current_time = time.time() - start_time
        wait_time = target_timestamp - current_time
        if wait_time > 0:
            time.sleep(wait_time)

        if idx % 10 == 0:
            progress = int((idx / total_points) * 100)
            context.update_progress(idx, total_points)
            context.set_status(f"Playing: {progress}%")
            context.log_info(f"→ Point {idx}/{total_points} ({progress}%)")

        context.motor_controller.set_positions(
            positions,
            velocity=velocity,
            wait=False,
            keep_connection=True,
        )
