"""High-level tests for the composite recording and sequence managers."""

from __future__ import annotations

from typing import Iterable

import pytest

from utils import actions_manager as actions_manager_module
from utils import sequences_manager as sequences_manager_module


@pytest.fixture
def actions_manager(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """Provide an ActionsManager with isolated temporary storage."""

    recordings_dir = tmp_path / "recordings"
    backups_dir = tmp_path / "backups" / "recordings"

    monkeypatch.setattr(actions_manager_module, "RECORDINGS_DIR", recordings_dir)
    monkeypatch.setattr(actions_manager_module, "BACKUPS_DIR", backups_dir)

    return actions_manager_module.ActionsManager()


@pytest.fixture
def sequences_manager(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """Provide a SequencesManager with isolated temporary storage."""

    sequences_dir = tmp_path / "sequences"
    backups_dir = tmp_path / "backups" / "sequences"

    monkeypatch.setattr(sequences_manager_module, "SEQUENCES_DIR", sequences_dir)
    monkeypatch.setattr(sequences_manager_module, "BACKUPS_DIR", backups_dir)

    return sequences_manager_module.SequencesManager()


def _sample_position_recording() -> dict:
    return {
        "type": "position",
        "speed": 100,
        "positions": [
            {
                "name": "Position 1",
                "motor_positions": [2048, 2048, 2048, 2048, 2048, 2048],
                "velocity": 600,
            },
            {
                "name": "Position 2",
                "motor_positions": [2100, 2050, 2048, 2048, 2048, 2048],
                "velocity": 600,
            },
        ],
        "delays": {},
    }


def _sample_live_recording() -> dict:
    return {
        "type": "live_recording",
        "speed": 100,
        "recorded_data": [
            {
                "positions": [2048, 2048, 2048, 2048, 2048, 2048],
                "timestamp": 0.000,
                "velocity": 600,
            },
            {
                "positions": [2051, 2049, 2047, 2048, 2048, 2048],
                "timestamp": 0.053,
                "velocity": 600,
            },
            {
                "positions": [2055, 2050, 2045, 2048, 2048, 2048],
                "timestamp": 0.106,
                "velocity": 600,
            },
        ],
    }


def _sample_sequence_steps() -> Iterable[dict]:
    return (
        {"type": "action", "name": "Test Grab Cup v1"},
        {"type": "delay", "duration": 2.0},
        {"type": "model", "task": "GrabBlock", "checkpoint": "last", "duration": 25.0},
        {"type": "home"},
    )


def test_actions_manager_lifecycle(actions_manager):  # type: ignore[no-untyped-def]
    """Exercise the major ActionsManager operations end-to-end."""

    position_recording = _sample_position_recording()
    live_recording = _sample_live_recording()

    assert actions_manager.save_action("Test Grab Cup v1", position_recording)
    assert actions_manager.save_action("Test Complex Motion", live_recording)

    listed_actions = actions_manager.list_actions()
    assert set(listed_actions) >= {"Test Grab Cup v1", "Test Complex Motion"}

    loaded = actions_manager.load_action("Test Grab Cup v1")
    assert loaded is not None
    assert loaded["type"] == "composite_recording"
    assert len(loaded["steps"]) == 1

    step = loaded["steps"][0]
    assert step["type"] == "position_set"
    assert "component_data" in step and "positions" in step["component_data"]

    info = actions_manager.get_recording_info("Test Grab Cup v1")
    assert info is not None
    assert info["step_count"] == 1

    fancy_name = "Pick & Place!"
    assert actions_manager.save_action(fancy_name, position_recording)

    # Confirm filename sanitisation by checking the resulting directory exists
    sanitised_dir = actions_manager.recordings_dir / "pick__place"
    assert sanitised_dir.exists()

    assert actions_manager.delete_action("Test Complex Motion")
    assert "Test Complex Motion" not in actions_manager.list_actions()

    backups = list(actions_manager.backups_dir.glob("test_complex_motion_*"))
    assert backups, "Expected a backup to be created when deleting recordings"


def test_sequences_manager_lifecycle(sequences_manager):  # type: ignore[no-untyped-def]
    """Exercise the major SequencesManager operations end-to-end."""

    steps = list(_sample_sequence_steps())
    steps_second = [
        {"type": "action", "name": "Test Grab Cup v1"},
        {"type": "delay", "duration": 1.0},
    ]

    assert sequences_manager.save_sequence("Test Production Run v1", steps, loop=False)
    assert sequences_manager.save_sequence("Test Quality Check", steps_second, loop=True)

    listed_sequences = sequences_manager.list_sequences()
    assert set(listed_sequences) >= {"Test Production Run v1", "Test Quality Check"}

    loaded = sequences_manager.load_sequence("Test Production Run v1")
    assert loaded is not None
    assert loaded["loop"] is False
    assert [step["type"] for step in loaded["steps"]] == [step["type"] for step in steps]

    info = sequences_manager.get_sequence_info("Test Quality Check")
    assert info is not None
    assert info["step_count"] == len(steps_second)

    fancy_name = "Pick & Place!"
    assert sequences_manager.save_sequence(fancy_name, [])
    sanitised_dir = sequences_manager.sequences_dir / "pick__place"
    assert sanitised_dir.exists()

    assert sequences_manager.delete_sequence("Test Quality Check")
    assert "Test Quality Check" not in sequences_manager.list_sequences()

    backups = list(sequences_manager.backups_dir.glob("test_quality_check_*"))
    assert backups, "Expected a backup to be created when deleting sequences"
