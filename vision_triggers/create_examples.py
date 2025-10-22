"""
Create Example Triggers

Creates pre-configured example triggers for common use cases:
1. Idle Standby - Wait for any object in work area
2. Dual Box Check - Start when both boxes filled
3. Count Exit - Exit after 10 items counted
"""

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

from vision_triggers.triggers_manager import TriggersManager


def create_idle_standby():
    """Create idle standby trigger"""
    print("Creating 'Idle Standby' trigger...")
    
    manager = TriggersManager()
    
    zones = [{
        "zone_id": "work_area",
        "name": "Work Area",
        "type": "trigger",
        "polygon": [[200, 120], [1080, 120], [1080, 560], [200, 560]],
        "enabled": True,
        "notes": "Main work area for object detection"
    }]
    
    conditions = {
        "condition_type": "presence",
        "rules": {
            "zone": "work_area",
            "min_objects": 1,
            "stability_frames": 2
        }
    }
    
    success = manager.save_trigger(
        name="Idle Standby",
        trigger_type="presence",
        zones=zones,
        conditions=conditions,
        check_interval=5.0,
        enabled=True,
        action={"type": "advance_sequence"},
        active_when={"robot_state": "home"},
        description="Wait for any object to appear in work area. Checks every 5 seconds."
    )
    
    if success:
        print("  ✓ Created 'Idle Standby'")
    else:
        print("  ✗ Failed to create 'Idle Standby'")
    
    return success


def create_dual_box_check():
    """Create dual box check trigger"""
    print("Creating 'Dual Box Check' trigger...")
    
    manager = TriggersManager()
    
    zones = [
        {
            "zone_id": "box_1",
            "name": "Box 1",
            "type": "trigger",
            "polygon": [[100, 200], [400, 200], [400, 500], [100, 500]],
            "enabled": True,
            "notes": "Left input box"
        },
        {
            "zone_id": "box_2",
            "name": "Box 2",
            "type": "trigger",
            "polygon": [[600, 200], [900, 200], [900, 500], [600, 500]],
            "enabled": True,
            "notes": "Right input box"
        }
    ]
    
    conditions = {
        "condition_type": "multi_zone",
        "rules": {
            "logic": "AND",
            "zones": [
                {"zone": "box_1", "min_objects": 1},
                {"zone": "box_2", "min_objects": 1}
            ]
        }
    }
    
    success = manager.save_trigger(
        name="Dual Box Check",
        trigger_type="multi_zone",
        zones=zones,
        conditions=conditions,
        check_interval=2.0,
        enabled=False,  # Disabled by default, user can enable
        action={"type": "start_sequence", "sequence_id": "production_run"},
        active_when={"robot_state": "home"},
        description="Start when objects present in BOTH boxes. Useful for dual-part assembly."
    )
    
    if success:
        print("  ✓ Created 'Dual Box Check'")
    else:
        print("  ✗ Failed to create 'Dual Box Check'")
    
    return success


def create_count_exit():
    """Create count-based exit trigger"""
    print("Creating 'Count Exit' trigger...")
    
    manager = TriggersManager()
    
    zones = [{
        "zone_id": "output_bin",
        "name": "Output Bin",
        "type": "count",
        "polygon": [[50, 50], [500, 50], [500, 500], [50, 500]],
        "enabled": True,
        "notes": "Output bin for counting completed items"
    }]
    
    conditions = {
        "condition_type": "count",
        "rules": {
            "zone": "output_bin",
            "count": 10,
            "operator": ">=",
            "cumulative": True
        }
    }
    
    success = manager.save_trigger(
        name="Count Exit",
        trigger_type="count",
        zones=zones,
        conditions=conditions,
        check_interval=1.0,
        enabled=False,  # Disabled by default
        action={"type": "advance_sequence"},
        active_when={"robot_state": "home"},
        description="Exit after 10 items counted in output bin. Cumulative counting across frames."
    )
    
    if success:
        print("  ✓ Created 'Count Exit'")
    else:
        print("  ✗ Failed to create 'Count Exit'")
    
    return success


def main():
    """Create all example triggers"""
    print("=" * 60)
    print("Creating Example Vision Triggers")
    print("=" * 60)
    print()
    
    results = []
    
    results.append(("Idle Standby", create_idle_standby()))
    print()
    
    results.append(("Dual Box Check", create_dual_box_check()))
    print()
    
    results.append(("Count Exit", create_count_exit()))
    print()
    
    # Summary
    print("=" * 60)
    print("Summary:")
    print("=" * 60)
    
    for name, success in results:
        status = "✓" if success else "✗"
        print(f"  {status} {name}")
    
    successful = sum(1 for _, success in results if success)
    print()
    print(f"Created {successful} of {len(results)} example triggers")
    print()
    
    if successful == len(results):
        print("✓ All examples created successfully!")
        print()
        print("To enable triggers, edit them in the Vision tab or manually enable in:")
        print("  data/vision_triggers/{trigger_name}/manifest.json")
        return 0
    else:
        print("⚠ Some examples failed to create")
        return 1


if __name__ == "__main__":
    sys.exit(main())

