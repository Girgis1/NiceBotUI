"""Utility helpers for palletization steps."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

import json
import time
import uuid


ROOT = Path(__file__).resolve().parent.parent


def _load_default_arm_index(config: Dict | None) -> int:
    if not config:
        return 0
    from utils.config_compat import get_active_arm_index

    try:
        return get_active_arm_index(config, arm_type="robot")
    except Exception:
        return 0


def _generate_uid(prefix: str = "pal") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def create_default_palletizer_config(config: Dict | None = None) -> Dict:
    """Return the default step payload for a palletize entry."""

    default_corner = {"positions": [0, 0, 0, 0, 0, 0], "label": "Corner", "captured": False}
    return {
        "type": "palletize",
        "name": "Palletize Grid",
        "arm_index": _load_default_arm_index(config),
        "palletizer_uid": _generate_uid(),
        "grid": {
            "corners": [
                {**default_corner, "label": "Corner 1"},
                {**default_corner, "label": "Corner 2"},
                {**default_corner, "label": "Corner 3"},
                {**default_corner, "label": "Corner 4"},
            ],
            "columns": 2,
            "rows": 2,
            "start_corner": 0,
        },
        "motion": {
            "travel_velocity": 650,
            "down_velocity": 450,
            "release_velocity": 250,
            "retreat_velocity": 650,
            "down_offsets": [0, -25, -40, -40, -15, 0],
            "release_offset": 180,
        },
    }


def normalize_corner_positions(corners: Sequence) -> List[List[int]]:
    """Return four 6D joint arrays from a mixed structure."""

    normalized: List[List[int]] = []
    for corner in corners:
        if corner is None:
            positions = [0, 0, 0, 0, 0, 0]
        elif isinstance(corner, dict):
            positions = corner.get("positions") or corner.get("values") or []
        else:
            positions = corner

        if not isinstance(positions, (list, tuple)):
            positions = [0, 0, 0, 0, 0, 0]

        padded = list(positions)[:6]
        while len(padded) < 6:
            padded.append(0)
        normalized.append([int(round(value)) for value in padded])

    if len(normalized) < 4:
        for _ in range(4 - len(normalized)):
            normalized.append([0, 0, 0, 0, 0, 0])

    return normalized[:4]


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def bilerp_positions(corners: Sequence[Sequence[int]], u: float, v: float) -> List[int]:
    """Return bilinear interpolation of four joint sets."""

    tl, tr, br, bl = corners  # type: ignore[misc]
    values: List[int] = []
    for idx in range(6):
        c00 = tl[idx]
        c10 = tr[idx]
        c11 = br[idx]
        c01 = bl[idx]
        top = _lerp(c00, c10, u)
        bottom = _lerp(c01, c11, u)
        blended = _lerp(top, bottom, v)
        values.append(int(round(blended)))
    return values


def build_cell_positions(
    corners: Sequence[Sequence[int]], columns: int, rows: int
) -> List[List[int]]:
    columns = max(1, int(columns))
    rows = max(1, int(rows))
    normalized = normalize_corner_positions(corners)
    cells: List[List[int]] = []

    for row in range(rows):
        v = 0.0 if rows == 1 else row / (rows - 1)
        for column in range(columns):
            u = 0.0 if columns == 1 else column / (columns - 1)
            cells.append(bilerp_positions(normalized, u, v))
    return cells


def reorder_cells_for_snake(cells: List[List[int]], columns: int, snake: bool) -> List[List[int]]:
    if not snake:
        return cells
    ordered: List[List[int]] = []
    columns = max(1, columns)
    for row_index in range(0, len(cells), columns):
        row = list(cells[row_index : row_index + columns])
        if ((row_index // columns) % 2) == 1:
            row.reverse()
        ordered.extend(row)
    return ordered


def apply_down_offsets(base: Sequence[int], offsets: Sequence[int]) -> List[int]:
    if len(offsets) < 6:
        offsets = list(offsets) + [0] * (6 - len(offsets))
    return [int(round(base[i] + offsets[i])) for i in range(6)]


def apply_release_offset(base: Sequence[int], release_offset: int) -> List[int]:
    updated = list(base)
    if len(updated) < 6:
        updated.extend([0] * (6 - len(updated)))
    updated[5] = int(round(updated[5] + release_offset))
    return updated[:6]


def describe_cell(index: int, columns: int, snake: bool = False) -> Dict[str, int]:
    columns = max(1, columns)
    row = index // columns
    column = index % columns
    path_column = column
    if snake and (row % 2 == 1):
        column = columns - 1 - column
    return {"row": row, "column": column, "path_column": path_column}


class PalletizerStateStore:
    """Persist and advance palletizer progress per unique step."""

    def __init__(self, runtime_dir: Path | None = None):
        self.runtime_dir = runtime_dir or ROOT / "runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.runtime_dir / "palletizer_state.json"

    def _load(self) -> Dict:
        if not self.state_path.exists():
            return {"steps": {}}
        try:
            return json.loads(self.state_path.read_text())
        except Exception:
            return {"steps": {}}

    def _save(self, payload: Dict) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(self.state_path)

    def _ensure_entry(self, state: Dict, uid: str) -> Dict:
        steps = state.setdefault("steps", {})
        entry = steps.get(uid)
        if not entry:
            entry = {"next_cell": 0, "sequence": None, "updated": time.time()}
            steps[uid] = entry
        return entry

    def peek_next(self, uid: str, total_cells: int) -> int:
        state = self._load()
        entry = self._ensure_entry(state, uid)
        total_cells = max(1, total_cells)
        return int(entry.get("next_cell", 0)) % total_cells

    def advance(self, uid: str, total_cells: int, *, sequence: str | None = None) -> int:
        total_cells = max(1, total_cells)
        state = self._load()
        entry = self._ensure_entry(state, uid)
        index = int(entry.get("next_cell", 0)) % total_cells
        entry["next_cell"] = (index + 1) % total_cells
        entry["updated"] = time.time()
        if sequence is not None:
            entry["sequence"] = sequence
        self._save(state)
        return index

    def reset(self, uid: str) -> None:
        state = self._load()
        entry = self._ensure_entry(state, uid)
        entry["next_cell"] = 0
        entry["updated"] = time.time()
        self._save(state)


__all__ = [
    "apply_down_offsets",
    "apply_release_offset",
    "build_cell_positions",
    "create_default_palletizer_config",
    "describe_cell",
    "normalize_corner_positions",
    "PalletizerStateStore",
    "reorder_cells_for_snake",
]
