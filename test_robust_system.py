#!/usr/bin/env python3
"""
Test Script for Robust Architecture

Tests the new individual-file system for recordings and sequences.
Run this to verify everything works before using in production.
"""

import sys
import json
from pathlib import Path

# Add parent directory
sys.path.insert(0, str(Path(__file__).parent))

from utils.actions_manager import ActionsManager
from utils.sequences_manager import SequencesManager


def test_actions_manager():
    """Test ActionsManager with individual files"""
    print("=" * 60)
    print("TEST: ActionsManager")
    print("=" * 60)
    
    mgr = ActionsManager()
    
    # Test 1: Save a simple position recording
    print("\n[TEST 1] Save simple position recording")
    recording1 = {
        "type": "position",
        "speed": 100,
        "positions": [
            {
                "name": "Position 1",
                "motor_positions": [2048, 2048, 2048, 2048, 2048, 2048],
                "velocity": 600
            },
            {
                "name": "Position 2",
                "motor_positions": [2100, 2050, 2048, 2048, 2048, 2048],
                "velocity": 600
            }
        ],
        "delays": {}
    }
    
    success = mgr.save_action("Test Grab Cup v1", recording1)
    if success:
        print("  ✓ Saved: Test Grab Cup v1")
    else:
        print("  ✗ Failed to save")
        return False
    
    # Test 2: Save a live recording
    print("\n[TEST 2] Save live recording")
    recording2 = {
        "type": "live_recording",
        "speed": 100,
        "recorded_data": [
            {"positions": [2048, 2048, 2048, 2048, 2048, 2048], "timestamp": 0.000, "velocity": 600},
            {"positions": [2051, 2049, 2047, 2048, 2048, 2048], "timestamp": 0.053, "velocity": 600},
            {"positions": [2055, 2050, 2045, 2048, 2048, 2048], "timestamp": 0.106, "velocity": 600}
        ]
    }
    
    success = mgr.save_action("Test Complex Motion", recording2)
    if success:
        print("  ✓ Saved: Test Complex Motion")
    else:
        print("  ✗ Failed to save")
        return False
    
    # Test 3: List recordings
    print("\n[TEST 3] List all recordings")
    recordings = mgr.list_actions()
    print(f"  Found {len(recordings)} recordings:")
    for name in recordings:
        print(f"    - {name}")
    
    if len(recordings) < 2:
        print("  ✗ Expected at least 2 recordings")
        return False
    
    # Test 4: Load recording
    print("\n[TEST 4] Load recording")
    loaded = mgr.load_action("Test Grab Cup v1")
    if loaded:
        print(f"  ✓ Loaded: {loaded['name']}")
        print(f"    Type: {loaded['type']}")
        print(f"    Positions: {len(loaded['positions'])}")
    else:
        print("  ✗ Failed to load")
        return False
    
    # Test 5: Get recording info
    print("\n[TEST 5] Get recording info")
    info = mgr.get_recording_info("Test Complex Motion")
    if info:
        print(f"  ✓ Info retrieved:")
        print(f"    Name: {info['name']}")
        print(f"    Type: {info['type']}")
        print(f"    Points: {info['point_count']}")
        print(f"    Created: {info['created']}")
        print(f"    File size: {info['file_size_kb']:.2f} KB")
    else:
        print("  ✗ Failed to get info")
        return False
    
    # Test 6: Update recording (should create backup)
    print("\n[TEST 6] Update recording (creates backup)")
    recording1["speed"] = 150  # Change speed
    success = mgr.save_action("Test Grab Cup v1", recording1)
    if success:
        print("  ✓ Updated: Test Grab Cup v1")
        # Check if backup was created
        backups_dir = mgr.backups_dir
        backups = list(backups_dir.glob("test_grab_cup_v1_*.json"))
        print(f"  ✓ Found {len(backups)} backup(s)")
    else:
        print("  ✗ Failed to update")
        return False
    
    # Test 7: Filename sanitization
    print("\n[TEST 7] Filename sanitization")
    test_names = [
        "Pick & Place!",
        "Test/Run #2",
        "Complex   Name    v1.5"
    ]
    for name in test_names:
        success = mgr.save_action(name, recording1)
        if success:
            filepath = mgr._get_filepath(name)
            print(f"  ✓ '{name}' → {filepath.name}")
        else:
            print(f"  ✗ Failed to save: {name}")
    
    # Test 8: Delete recording (should create backup)
    print("\n[TEST 8] Delete recording (creates backup)")
    success = mgr.delete_action("Test Complex Motion")
    if success:
        print("  ✓ Deleted: Test Complex Motion")
    else:
        print("  ✗ Failed to delete")
        return False
    
    print("\n✓ All ActionsManager tests passed!")
    return True


def test_sequences_manager():
    """Test SequencesManager with individual files"""
    print("\n" + "=" * 60)
    print("TEST: SequencesManager")
    print("=" * 60)
    
    mgr = SequencesManager()
    
    # Test 1: Save a sequence
    print("\n[TEST 1] Save sequence")
    steps = [
        {"type": "recording", "name": "Test Grab Cup v1"},
        {"type": "delay", "duration": 2.0},
        {"type": "recording", "name": "Pick & Place!"},
        {"type": "model", "task": "GrabBlock", "checkpoint": "last", "duration": 25.0}
    ]
    
    success = mgr.save_sequence("Test Production Run v1", steps, loop=False)
    if success:
        print("  ✓ Saved: Test Production Run v1")
    else:
        print("  ✗ Failed to save")
        return False
    
    # Test 2: Save another sequence
    print("\n[TEST 2] Save another sequence")
    steps2 = [
        {"type": "recording", "name": "Test Grab Cup v1"},
        {"type": "delay", "duration": 1.0}
    ]
    
    success = mgr.save_sequence("Test Quality Check", steps2, loop=True)
    if success:
        print("  ✓ Saved: Test Quality Check")
    else:
        print("  ✗ Failed to save")
        return False
    
    # Test 3: List sequences
    print("\n[TEST 3] List all sequences")
    sequences = mgr.list_sequences()
    print(f"  Found {len(sequences)} sequences:")
    for name in sequences:
        print(f"    - {name}")
    
    if len(sequences) < 2:
        print("  ✗ Expected at least 2 sequences")
        return False
    
    # Test 4: Load sequence
    print("\n[TEST 4] Load sequence")
    loaded = mgr.load_sequence("Test Production Run v1")
    if loaded:
        print(f"  ✓ Loaded: {loaded['name']}")
        print(f"    Steps: {len(loaded['steps'])}")
        print(f"    Loop: {loaded['loop']}")
        for idx, step in enumerate(loaded['steps']):
            print(f"      {idx+1}. {step['type']}: {step.get('name', step.get('duration', 'N/A'))}")
    else:
        print("  ✗ Failed to load")
        return False
    
    # Test 5: Get sequence info
    print("\n[TEST 5] Get sequence info")
    info = mgr.get_sequence_info("Test Quality Check")
    if info:
        print(f"  ✓ Info retrieved:")
        print(f"    Name: {info['name']}")
        print(f"    Steps: {info['step_count']}")
        print(f"    Loop: {info['loop']}")
        print(f"    Created: {info['created']}")
    else:
        print("  ✗ Failed to get info")
        return False
    
    # Test 6: Update sequence (should create backup)
    print("\n[TEST 6] Update sequence (creates backup)")
    steps.append({"type": "delay", "duration": 5.0})
    success = mgr.save_sequence("Test Production Run v1", steps, loop=False)
    if success:
        print("  ✓ Updated: Test Production Run v1")
        # Check if backup was created
        backups_dir = mgr.backups_dir
        backups = list(backups_dir.glob("test_production_run_v1_*.json"))
        print(f"  ✓ Found {len(backups)} backup(s)")
    else:
        print("  ✗ Failed to update")
        return False
    
    # Test 7: Delete sequence (should create backup)
    print("\n[TEST 7] Delete sequence (creates backup)")
    success = mgr.delete_sequence("Test Quality Check")
    if success:
        print("  ✓ Deleted: Test Quality Check")
    else:
        print("  ✗ Failed to delete")
        return False
    
    print("\n✓ All SequencesManager tests passed!")
    return True


def test_file_structure():
    """Test that file structure is correct"""
    print("\n" + "=" * 60)
    print("TEST: File Structure")
    print("=" * 60)
    
    root = Path(__file__).parent
    
    # Check directories exist
    dirs_to_check = [
        "data/recordings",
        "data/sequences",
        "data/backups/recordings",
        "data/backups/sequences"
    ]
    
    print("\n[TEST] Check directories exist")
    for dir_path in dirs_to_check:
        full_path = root / dir_path
        if full_path.exists():
            print(f"  ✓ {dir_path}/")
        else:
            print(f"  ✗ Missing: {dir_path}/")
            return False
    
    # Check recording files
    print("\n[TEST] Check recording files")
    recordings_dir = root / "data" / "recordings"
    recording_files = list(recordings_dir.glob("*.json"))
    print(f"  Found {len(recording_files)} recording file(s):")
    for filepath in recording_files[:5]:  # Show first 5
        print(f"    - {filepath.name}")
    
    # Check sequence files
    print("\n[TEST] Check sequence files")
    sequences_dir = root / "data" / "sequences"
    sequence_files = list(sequences_dir.glob("*.json"))
    print(f"  Found {len(sequence_files)} sequence file(s):")
    for filepath in sequence_files[:5]:  # Show first 5
        print(f"    - {filepath.name}")
    
    # Check backup files
    print("\n[TEST] Check backup files")
    backups_recordings = root / "data" / "backups" / "recordings"
    backup_files = list(backups_recordings.glob("*.json"))
    print(f"  Found {len(backup_files)} backup file(s) (recordings)")
    
    backups_sequences = root / "data" / "backups" / "sequences"
    backup_files = list(backups_sequences.glob("*.json"))
    print(f"  Found {len(backup_files)} backup file(s) (sequences)")
    
    print("\n✓ File structure tests passed!")
    return True


def cleanup_test_data():
    """Clean up test data"""
    print("\n" + "=" * 60)
    print("CLEANUP: Test Data")
    print("=" * 60)
    
    mgr_actions = ActionsManager()
    mgr_sequences = SequencesManager()
    
    # Delete test recordings
    test_recordings = [
        "Test Grab Cup v1",
        "Test Complex Motion",
        "Pick & Place!",
        "Test/Run #2",
        "Complex   Name    v1.5"
    ]
    
    print("\n[CLEANUP] Removing test recordings...")
    for name in test_recordings:
        if mgr_actions.action_exists(name):
            mgr_actions.delete_action(name)
            print(f"  ✓ Deleted: {name}")
    
    # Delete test sequences
    test_sequences = [
        "Test Production Run v1",
        "Test Quality Check"
    ]
    
    print("\n[CLEANUP] Removing test sequences...")
    for name in test_sequences:
        if mgr_sequences.sequence_exists(name):
            mgr_sequences.delete_sequence(name)
            print(f"  ✓ Deleted: {name}")
    
    print("\n✓ Cleanup completed!")


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("LeRobotGUI Robust Architecture Test Suite")
    print("=" * 60)
    print()
    
    try:
        # Run tests
        test1 = test_actions_manager()
        test2 = test_sequences_manager()
        test3 = test_file_structure()
        
        # Summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        print(f"ActionsManager:   {'✓ PASS' if test1 else '✗ FAIL'}")
        print(f"SequencesManager: {'✓ PASS' if test2 else '✗ FAIL'}")
        print(f"File Structure:   {'✓ PASS' if test3 else '✗ FAIL'}")
        print()
        
        if test1 and test2 and test3:
            print("✓ ALL TESTS PASSED!")
            print()
            print("The robust architecture is working correctly.")
            print("You can now use the system with confidence.")
        else:
            print("✗ SOME TESTS FAILED")
            print()
            print("Please review the errors above.")
        
        # Offer cleanup
        print("\n" + "=" * 60)
        response = input("Clean up test data? (y/n): ")
        if response.lower() in ['y', 'yes']:
            cleanup_test_data()
        else:
            print("Test data preserved for inspection.")
        
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user.")
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

