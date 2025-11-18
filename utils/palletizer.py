"""Utility helpers for palletization steps.

This module keeps the data normalization, interpolation helpers, and
summaries for the palletize sequence step in one place so it can be shared
between the UI, sequence persistence, and the execution worker.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from utils.config_compat import (
    format_arm_label,
    get_active_arm_index,
    get_arm_config,
)

MOTOR_COUNT = 6
CORNER_COUNT = 4


@dataclass
class PalletCycle:
    """Pre-computed poses for one pallet cell."""

    approach: List[int]
    down: List[int]
    release: List[int]
    retreat: List[int]


def _empty_corners() -> List[dict]:
    return [
        {"name": f"Corner {idx + 1}", "motor_positions": None, "timestamp": None}
        for idx in range(CORNER_COUNT)
    ]


def _default_down_adjust() -> List[int]:
    # Only motors 2-5 (index 1-4) are used for the down offset, but keeping a
    # full list makes runtime addition simpler.
    values = [0] * MOTOR_COUNT
    for idx in range(1, 5):
        values[idx] = -40
    return values


def create_default_pallet_config(config: dict | None = None, *, arm_index: int | None = None) -> dict:
    """Return a fully populated default palletization config."""

    robot_config = config or {}
    if arm_index is None:
        arm_index = get_active_arm_index(robot_config, arm_type="robot")
    arm_cfg = get_arm_config(robot_config, arm_index or 0) or {}
    arm_label = format_arm_label(arm_index or 0, arm_cfg) if arm_cfg else f"Arm {(arm_index or 0) + 1}"

    return {
        "type": "palletize",
        "name": "Palletise",
        "arm_index": arm_index or 0,
        "arm_label": arm_label,
        "grid": {
            "columns": 3,
            "rows": 3,
            "pattern": "row-major",
            "snake": False,
        },
        "corners": _empty_corners(),
        "velocities": {
            "travel": 600,
            "down": 450,
            "release": 300,
        },
        "down_adjust": _default_down_adjust(),
        "release_adjust": 120,
        "release_hold": 0.3,
    }


def _lerp(a: Sequence[float], b: Sequence[float], t: float) -> List[float]:
    t = max(0.0, min(1.0, float(t)))
    return [a_val + (b_val - a_val) * t for a_val, b_val in zip(a, b)]


def _ensure_corner_vectors(corners: Iterable[dict]) -> List[List[int]]:
    vectors: List[List[int]] = []
    for corner in corners:
        positions = corner.get("motor_positions") if isinstance(corner, dict) else None
        if not positions or len(positions) != MOTOR_COUNT:
            return []
        vectors.append([int(pos) for pos in positions])
    return vectors


def have_all_corners(step: dict) -> bool:
    corners = step.get("corners") or []
    if len(corners) < CORNER_COUNT:
        return False
    return all(isinstance(c.get("motor_positions"), list) and len(c["motor_positions"]) == MOTOR_COUNT for c in corners[:CORNER_COUNT])


def normalize_down_adjust(values: Sequence[int] | None) -> List[int]:
    if not isinstance(values, Sequence):
        return [0] * MOTOR_COUNT
    data = list(values)[:MOTOR_COUNT]
    if len(data) < MOTOR_COUNT:
        data.extend([0] * (MOTOR_COUNT - len(data)))
    return [int(v) for v in data]


def normalize_velocities(step: dict) -> dict:
    velocities = step.get("velocities") or {}
    return {
        "travel": int(max(1, min(4000, velocities.get("travel", 600)))),
        "down": int(max(1, min(4000, velocities.get("down", velocities.get("travel", 600))))),
        "release": int(max(1, min(4000, velocities.get("release", velocities.get("down", 400))))),
    }


def compute_cell_positions(step: dict) -> List[List[int]]:
    """Return interpolated motor positions for every cell."""

    if not have_all_corners(step):
        return []

    corners = _ensure_corner_vectors(step.get("corners", []))
    if len(corners) < CORNER_COUNT:
        return []

    columns = int(max(1, step.get("grid", {}).get("columns", 1)))
    rows = int(max(1, step.get("grid", {}).get("rows", 1)))
    snake = bool(step.get("grid", {}).get("snake", False))

    denom_cols = max(columns - 1, 1)
    denom_rows = max(rows - 1, 1)

    c1, c2, c3, c4 = corners[:CORNER_COUNT]
    cells: List[List[int]] = []

    for row in range(rows):
        v = row / denom_rows if rows > 1 else 0.0
        row_points: List[List[int]] = []
        for col in range(columns):
            u = col / denom_cols if columns > 1 else 0.0
            top = _lerp(c1, c2, u)
            bottom = _lerp(c4, c3, u)
            point = _lerp(top, bottom, v)
            row_points.append([int(round(p)) for p in point])
        if snake and row % 2 == 1:
            row_points.reverse()
        cells.extend(row_points)

    return cells


def build_cycle(step: dict, cell_index: int) -> PalletCycle | None:
    cells = compute_cell_positions(step)
    if not cells:
        return None
    index = max(0, min(len(cells) - 1, cell_index))
    base = cells[index]
    down_adjust = normalize_down_adjust(step.get("down_adjust"))
    release_adjust = int(step.get("release_adjust", 0))

    down_pose = [base[i] + down_adjust[i] for i in range(MOTOR_COUNT)]
    release_pose = down_pose.copy()
    release_pose[-1] = down_pose[-1] + release_adjust

    return PalletCycle(
        approach=base,
        down=down_pose,
        release=release_pose,
        retreat=base,
    )


def describe_pallet_step(step: dict) -> str:
    grid = step.get("grid", {})
    cols = int(max(1, grid.get("columns", 1)))
    rows = int(max(1, grid.get("rows", 1)))
    arm_label = step.get("arm_label") or f"Arm {step.get('arm_index', 0) + 1}"
    corners = "set" if have_all_corners(step) else "missing"
    return f"🤲 Palletise: {arm_label} • {cols}x{rows} grid • corners {corners}"


def ensure_corner_structure(step: dict) -> None:
    """Mutate ``step`` so that it always has four corner entries."""

    existing = step.get("corners")
    if not isinstance(existing, list):
        step["corners"] = _empty_corners()
        return
    if len(existing) < CORNER_COUNT:
        existing.extend(_empty_corners()[len(existing):])


def update_arm_metadata(step: dict, config: dict, arm_index: int) -> None:
    arm_cfg = get_arm_config(config, arm_index) or {}
    step["arm_index"] = arm_index
    step["arm_label"] = format_arm_label(arm_index, arm_cfg) if arm_cfg else f"Arm {arm_index + 1}"


def clone_pallet_config(step: dict, *, defaults: dict | None = None) -> dict:
    template = deepcopy(defaults or create_default_pallet_config())
    merged = deepcopy(step or {})
    ensure_corner_structure(merged)
    template.update({k: v for k, v in merged.items() if k != "corners"})
    # Merge corners individually so we keep placeholder metadata.
    corners = merged.get("corners", [])
    for idx in range(min(len(corners), CORNER_COUNT)):
        if isinstance(corners[idx], dict):
            template["corners"][idx].update(corners[idx])
    return template
