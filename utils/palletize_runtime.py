"""Runtime helpers for palletization steps.

This module centralizes the math for pallet cell generation as well as the
shared motion routine that both the Sequence executor and the configuration
dialog use. Keeping this logic here avoids duplicated hardware handling in the
UI layer and the execution worker.
"""

from __future__ import annotations

"""Helper utilities for palletization step configuration and playback."""

import time
from typing import Callable, Dict, List, Optional, Sequence

from utils.config_compat import get_active_arm_index
from utils.motor_controller import MotorController


def create_default_palletize_config(config: Optional[dict] = None) -> dict:
    """Return a baseline configuration for a palletize step."""

    arm_index = 0
    if config:
        try:
            arm_index = get_active_arm_index(config)
        except Exception:
            arm_index = 0

    return {
        "type": "palletize",
        "name": "Palletize Grid",
        "arm_index": arm_index,
        "corners": [
            {"label": "Corner 1", "positions": []},
            {"label": "Corner 2", "positions": []},
            {"label": "Corner 3", "positions": []},
            {"label": "Corner 4", "positions": []},
        ],
        "divisions": {"c1_c2": 2, "c2_c3": 2},
        "approach_velocity": 700,
        "retract_velocity": 700,
        "down_velocity": 450,
        "release_velocity": 300,
        "settle_time": 0.15,
        "release_hold": 0.2,
        # Clearance offsets applied to joints 2–4 for the high approach pose.
        # Positive values follow the usual motor convention (e.g. positive = down
        # for joint 2); use negative values to lift above the cell.
        "down_offsets": {"2": -300, "3": 0, "4": 0},
        "release_offset": 140,
    }


def _coerce_positions(value: Sequence[float]) -> List[int]:
    numbers: List[int] = []
    for entry in value:
        if isinstance(entry, (int, float)):
            numbers.append(int(entry))
        else:
            break
        if len(numbers) == 6:
            break
    return numbers


def extract_corner_positions(step: Dict) -> List[List[int]]:
    """Return the four configured corner positions (lists of 6 ints)."""

    result: List[List[int]] = []
    corners = step.get("corners", [])

    for idx in range(4):
        corner_entry = corners[idx] if idx < len(corners) else {}
        positions: List[int] = []
        if isinstance(corner_entry, dict):
            raw = corner_entry.get("positions")
            if isinstance(raw, list):
                positions = _coerce_positions(raw)
        elif isinstance(corner_entry, list):
            positions = _coerce_positions(corner_entry)

        legacy_key = f"corner_{idx + 1}"
        if not positions and isinstance(step.get(legacy_key), list):
            positions = _coerce_positions(step[legacy_key])

        result.append(positions)

    return result


def _lerp_positions(a: Sequence[int], b: Sequence[int], t: float) -> List[int]:
    return [
        int(round(a[i] + (b[i] - a[i]) * t))
        for i in range(min(len(a), len(b)))
    ]


def compute_pallet_cells(step: Dict) -> List[List[int]]:
    """Compute every pallet cell pose using the configured corners."""

    corners = extract_corner_positions(step)
    if any(len(pos) != 6 for pos in corners):
        return []

    div_cfg = step.get("divisions", {}) or {}
    div_x = max(1, int(div_cfg.get("c1_c2", 1)))
    div_y = max(1, int(div_cfg.get("c2_c3", 1)))

    denom_x = max(div_x - 1, 1)
    denom_y = max(div_y - 1, 1)

    cells: List[List[int]] = []
    for row in range(div_y):
        v = row / denom_y if denom_y else 0.0
        left = _lerp_positions(corners[0], corners[3], v)
        right = _lerp_positions(corners[1], corners[2], v)
        for col in range(div_x):
            u = col / denom_x if denom_x else 0.0
            pose = _lerp_positions(left, right, u)
            cells.append(pose)

    return cells


def _normalize_offsets(offsets: Optional[Dict[str, float]]) -> Dict[int, int]:
    normalized: Dict[int, int] = {}
    if not isinstance(offsets, dict):
        return normalized

    for key, value in offsets.items():
        try:
            motor_id = int(key)
        except (TypeError, ValueError):
            continue
        if motor_id < 1 or motor_id > 6:
            continue
        try:
            normalized[motor_id] = int(value)
        except (TypeError, ValueError):
            continue
    return normalized


def _clamp_velocity(value: float) -> int:
    try:
        return max(1, min(4000, int(value)))
    except (TypeError, ValueError):
        return 400


def _clamp_position(value: int) -> int:
    return max(0, min(4095, int(value)))


def _apply_offsets(base: Sequence[int], offsets: Dict[int, int]) -> List[int]:
    updated = list(base)
    for motor_id, delta in offsets.items():
        idx = motor_id - 1
        if 0 <= idx < len(updated):
            updated[idx] = _clamp_position(updated[idx] + delta)
    return updated


class PalletizeRuntime:
    """Shared executor for palletization steps."""

    def __init__(self, config: dict, *, speed_multiplier: float = 1.0):
        self.config = config
        self.speed_multiplier = speed_multiplier

    def compute_cells(self, step: Dict) -> List[List[int]]:
        return compute_pallet_cells(step)

    def execute(
        self,
        step: Dict,
        *,
        cell_index: int = 0,
        logger: Optional[Callable[[str, str], None]] = None,
        stop_cb: Optional[Callable[[], bool]] = None,
        controller: Optional[MotorController] = None,
    ) -> int:
        """Execute the palletize routine for the requested cell."""

        cells = self.compute_cells(step)
        if not cells:
            raise ValueError("Palletize step is missing corner definitions")

        total_cells = len(cells)
        active_index = cell_index % total_cells
        approach_pose = cells[active_index]

        arm_index = int(step.get("arm_index", get_active_arm_index(self.config)))

        own_controller = controller is None
        if controller is None:
            controller = MotorController(self.config, arm_index=arm_index)
        controller.speed_multiplier = self.speed_multiplier

        def _log(level: str, message: str):
            if logger:
                logger(level, message)

        def _should_stop() -> bool:
            return bool(stop_cb and stop_cb())

        if _should_stop():
            raise RuntimeError("Palletize step aborted")

        if not controller.bus:
            if not controller.connect():
                raise RuntimeError("Failed to connect to motors for palletize step")

        approach_velocity = _clamp_velocity(step.get("approach_velocity", 600))
        retract_velocity = _clamp_velocity(step.get("retract_velocity", approach_velocity))
        down_velocity = _clamp_velocity(step.get("down_velocity", approach_velocity))
        release_velocity = _clamp_velocity(step.get("release_velocity", down_velocity))
        settle_time = max(0.0, float(step.get("settle_time", 0.0)))
        release_hold = max(0.0, float(step.get("release_hold", 0.0)))
        # Interpret down_offsets as clearance offsets for joints 2–4
        clearance_offsets = _normalize_offsets(step.get("down_offsets"))
        release_delta = int(step.get("release_offset", 0))

        def _move(target: List[int], velocity: int, stage: str):
            if _should_stop():
                raise RuntimeError("Palletize step aborted")
            _log("info", f"{stage}: velocity {velocity}")
            controller.set_positions(target, velocity=velocity, wait=True, keep_connection=True)

        _log(
            "info",
            f"Approaching pallet cell {active_index + 1}/{total_cells} on arm {arm_index + 1}",
        )

        # Stage 1: move joints 2–4 to their clearance heights above the cell,
        # keeping motor 1 (base) and motor 5 (wrist) at their current angles.
        # Motor 6 (gripper) is never driven to an absolute value from corners;
        # it stays at the value from the previous step until we apply the
        # release delta at the cell pose.
        current_positions = controller.read_positions()
        if len(current_positions) != 6:
            raise RuntimeError("Palletize step failed: could not read 6 joint positions for clearance path")

        gripper_current = current_positions[5]

        # Clearance pose derived from the final cell pose plus configurable offsets
        clearance_pose = _apply_offsets(approach_pose, clearance_offsets)
        # Ensure list has at least 6 entries and preserve current gripper value
        if len(clearance_pose) < 6:
            clearance_pose = list(clearance_pose) + [0] * (6 - len(clearance_pose))
        else:
            clearance_pose = list(clearance_pose)
        clearance_pose[5] = gripper_current

        stage1_pose = list(clearance_pose)
        stage1_pose[0] = current_positions[0]  # keep base heading
        stage1_pose[4] = current_positions[4]  # keep wrist rotation
        _move(stage1_pose, approach_velocity, "Approach (clearance height)")
        if settle_time:
            time.sleep(settle_time)

        # Stage 2: rotate base (motor 1) and wrist (motor 5) to their final
        # cell values while staying at the clearance height.
        stage2_pose = list(clearance_pose)
        _move(stage2_pose, down_velocity, "Approach (rotate base/wrist)")
        if settle_time:
            time.sleep(settle_time)

        # Stage 3: slow drop – move joints 2–4 down from clearance to the
        # exact corner/cell position, then perform the gripper release.
        approach_pose_no_grip = list(approach_pose)
        if len(approach_pose_no_grip) < 6:
            approach_pose_no_grip += [0] * (6 - len(approach_pose_no_grip))
        approach_pose_no_grip[5] = gripper_current
        _move(approach_pose_no_grip, down_velocity, "Drop to cell")
        if settle_time:
            time.sleep(settle_time)

        # Release is performed at the exact cell pose (approach_pose).
        release_pose = list(approach_pose_no_grip)
        if len(release_pose) >= 6:
            release_pose[5] = _clamp_position(release_pose[5] + release_delta)
        else:
            release_pose.append(_clamp_position(release_delta))

        _move(release_pose, release_velocity, "Release")
        if release_hold:
            time.sleep(release_hold)

        # Stage 4: retreat back to the clearance pose above the cell to exit
        # safely and prepare for the next cell. Keep motor 6 in its released
        # (open) state while moving up.
        clearance_exit_pose = list(clearance_pose)
        if len(release_pose) >= 6 and len(clearance_exit_pose) >= 6:
            clearance_exit_pose[5] = release_pose[5]
        _move(clearance_exit_pose, retract_velocity, "Retract to clearance")
        if settle_time:
            time.sleep(settle_time)

        if own_controller:
            try:
                controller.disconnect()
            except Exception:
                pass

        return active_index


__all__ = [
    "PalletizeRuntime",
    "compute_pallet_cells",
    "create_default_palletize_config",
    "extract_corner_positions",
]
