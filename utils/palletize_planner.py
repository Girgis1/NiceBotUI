"""Palletize planning helpers for the sequencer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

MOTOR_COUNT = 6


def _lerp(a: int, b: int, t: float) -> float:
    return a + (b - a) * t


def _blend(a: Sequence[int], b: Sequence[int], t: float) -> List[float]:
    return [_lerp(av, bv, t) for av, bv in zip(a, b)]


@dataclass
class PalletizeValidation:
    valid: bool
    message: str = ""


class PalletizePlanner:
    """Utility class that expands palletize step data into trajectories."""

    def __init__(self, step_config: Dict):
        self.config = step_config or {}

    # ------------------------------------------------------------------
    # Configuration helpers

    def get_grid_shape(self) -> Tuple[int, int]:
        grid = self.config.get("grid", {})
        cols = max(1, int(grid.get("corner12_divisions", 1)))
        rows = max(1, int(grid.get("corner23_divisions", 1)))
        return cols, rows

    def get_corner_positions(self) -> List[List[int]]:
        corners = self.config.get("corners") or []
        normalized: List[List[int]] = []
        for corner in corners:
            positions = corner.get("positions") if isinstance(corner, dict) else None
            if positions and len(positions) == MOTOR_COUNT:
                normalized.append([int(value) for value in positions])
        # If caller stored corners as raw lists
        if not normalized and len(corners) == 4 and all(isinstance(c, (list, tuple)) for c in corners):
            normalized = [[int(value) for value in corner] for corner in corners]
        return normalized

    def validate(self) -> PalletizeValidation:
        corners = self.get_corner_positions()
        if len(corners) != 4:
            return PalletizeValidation(False, "Set all four corner poses before saving.")
        for idx, corner in enumerate(corners, start=1):
            if len(corner) != MOTOR_COUNT:
                return PalletizeValidation(False, f"Corner {idx} has {len(corner)} joints (expected {MOTOR_COUNT}).")
        cols, rows = self.get_grid_shape()
        if cols < 1 or rows < 1:
            return PalletizeValidation(False, "Grid must have at least one division per side.")
        return PalletizeValidation(True, "")

    # ------------------------------------------------------------------
    # Cell helpers

    def total_cells(self) -> int:
        cols, rows = self.get_grid_shape()
        return max(1, cols * rows)

    def cell_coordinates(self, cell_index: int) -> Tuple[int, int]:
        cols, rows = self.get_grid_shape()
        total = self.total_cells()
        idx = 0 if total == 0 else int(cell_index) % total
        row = idx // cols if cols else 0
        col = idx % cols if cols else 0
        return col, row

    def cell_position(self, cell_index: int) -> List[int]:
        corners = self.get_corner_positions()
        if len(corners) != 4:
            raise ValueError("All four corners must be configured before computing positions")
        cols, rows = self.get_grid_shape()
        col, row = self.cell_coordinates(cell_index)

        u = 0.0 if cols <= 1 else col / (cols - 1)
        v = 0.0 if rows <= 1 else row / (rows - 1)

        top = _blend(corners[0], corners[1], u)
        bottom = _blend(corners[3], corners[2], u)
        blended = _blend(top, bottom, v)
        return [int(round(value)) for value in blended]

    # ------------------------------------------------------------------
    # Motion helpers

    def down_adjustments(self) -> Dict[str, int]:
        defaults = {str(motor): 0 for motor in range(2, 6)}
        adjustments = defaults.copy()
        adjustments.update({
            str(key): int(value)
            for key, value in (self.config.get("down_adjustments") or {}).items()
            if str(key) in defaults
        })
        return adjustments

    def release_adjustment(self) -> int:
        return int(self.config.get("release_adjustment", 0))

    def velocities(self) -> Dict[str, int]:
        defaults = {
            "travel": 800,
            "down": 400,
            "release": 300,
            "retreat": 800,
        }
        data = self.config.get("velocities") or {}
        for key, default in defaults.items():
            value = data.get(key, default)
            try:
                defaults[key] = max(1, min(4000, int(value)))
            except (TypeError, ValueError):
                defaults[key] = default
        return defaults

    def apply_offsets(self, positions: Sequence[int], offsets: Dict[str, int]) -> List[int]:
        current = list(positions)
        for key, delta in offsets.items():
            try:
                motor_index = int(key) - 1
            except (TypeError, ValueError):
                continue
            if 0 <= motor_index < MOTOR_COUNT:
                current[motor_index] = int(current[motor_index] + int(delta))
        return current

    def apply_release(self, positions: Sequence[int], release_delta: int) -> List[int]:
        current = list(positions)
        gripper_index = MOTOR_COUNT - 1
        current[gripper_index] = int(current[gripper_index] + release_delta)
        return current

    def build_motion_plan(self, cell_index: int) -> List[Tuple[str, List[int], int]]:
        base = self.cell_position(cell_index)
        velocities = self.velocities()
        down_position = self.apply_offsets(base, self.down_adjustments())
        release_position = self.apply_release(down_position, self.release_adjustment())
        retreat_position = list(base)
        return [
            ("travel", base, velocities["travel"]),
            ("down", down_position, velocities["down"]),
            ("release", release_position, velocities["release"]),
            ("retreat", retreat_position, velocities["retreat"]),
        ]

    def describe_cell(self, cell_index: int) -> str:
        cols, rows = self.get_grid_shape()
        col, row = self.cell_coordinates(cell_index)
        total = self.total_cells()
        return f"cell {row * cols + col + 1}/{total} (row {row + 1}, col {col + 1})"


__all__ = ["PalletizePlanner", "PalletizeValidation", "MOTOR_COUNT"]
