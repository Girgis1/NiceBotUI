"""Tests for palletizer helpers."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.palletizer import (
    PalletizerStateStore,
    build_cell_positions,
    reorder_cells_for_snake,
)


def test_build_cell_positions_bilinear():
    corners = [
        [0, 0, 0, 0, 0, 0],
        [10, 0, 0, 0, 0, 0],
        [10, 20, 0, 0, 0, 0],
        [0, 20, 0, 0, 0, 0],
    ]
    cells = build_cell_positions(corners, columns=2, rows=2)
    assert cells[0][0] == 0  # top-left
    assert cells[1][0] == 10  # top-right interpolation
    assert cells[2][1] == 20  # bottom-right second joint
    assert cells[3][1] == 20  # bottom-left second joint


def test_reorder_cells_for_snake():
    cells = [[i] for i in range(6)]
    ordered = reorder_cells_for_snake(cells, columns=3, snake=True)
    assert [cell[0] for cell in ordered] == [0, 1, 2, 5, 4, 3]


def test_palletizer_state_store(tmp_path):
    store = PalletizerStateStore(runtime_dir=tmp_path)
    uid = "pal_test"
    assert store.peek_next(uid, 4) == 0
    assert store.advance(uid, 4) == 0
    assert store.advance(uid, 4) == 1
    store.reset(uid)
    assert store.peek_next(uid, 4) == 0
