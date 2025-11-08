"""Composite recording strategy helpers."""

from __future__ import annotations

import time
from typing import Dict

from .context import ExecutionContext
from .live_strategy import execute_live_component
from .positions_strategy import execute_position_component


def execute_composite_recording(context: ExecutionContext, recording: Dict) -> None:
    """Execute a composite recording comprised of multiple components."""
    steps = recording.get("steps", [])
    total_steps = len(steps)

    context.log_info(
        f"Executing composite recording: {recording.get('name', 'Unknown')}"
    )
    context.log_info(f"Total steps: {total_steps}")

    for step_idx, step in enumerate(steps):
        if context.should_stop():
            break

        if not step.get("enabled", True):
            context.log_info(
                f"[{step_idx + 1}/{total_steps}] Skipping disabled step: {step.get('name', 'step')}"
            )
            continue

        step_name = step.get("name", f"Step {step_idx + 1}")
        step_type = step.get("type", "unknown")
        step_speed = step.get("speed", 100)
        delay_before = step.get("delay_before", 0.0)
        delay_after = step.get("delay_after", 0.0)

        context.log_info(
            f"\n[{step_idx + 1}/{total_steps}] === {step_name} ({step_type}) ==="
        )
        context.set_status(f"Step {step_idx + 1}/{total_steps}: {step_name}")

        if delay_before > 0:
            context.log_info(f"⏱ Waiting {delay_before}s before step...")
            time.sleep(delay_before)

        component_data = step.get("component_data", {})
        if not component_data:
            context.log_warning(f"No component data for step: {step_name}")
            continue

        try:
            if step_type == "live_recording":
                execute_live_component(context, component_data, step_speed)
            elif step_type == "position_set":
                execute_position_component(context, component_data, step_speed)
            else:
                context.log_error(f"Unknown step type: {step_type}")
        except Exception as exc:  # pragma: no cover - device timing
            context.log_error(f"Failed to execute step {step_name}: {exc}")
            if not context.should_stop():
                continue

        if delay_after > 0:
            context.log_info(f"⏱ Waiting {delay_after}s after step...")
            time.sleep(delay_after)

        context.update_progress(step_idx + 1, total_steps)
        progress_pct = int(((step_idx + 1) / total_steps) * 100)
        context.log_info(f"✓ Step complete ({progress_pct}% overall)")
