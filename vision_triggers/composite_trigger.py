"""
Composite Trigger - Orchestrate zones and conditions into a trigger

DESIGN (Following CompositeRecording pattern):
- Folder-based storage: Each trigger is a folder
- manifest.json: Defines trigger metadata, timing, actions
- zones.json: Zone definitions
- conditions.json: Trigger logic and rules
- Clean separation: Orchestration (manifest) vs Data (zones/conditions)

EXAMPLE:
    data/vision_triggers/idle_standby/
    ├── manifest.json
    ├── zones.json
    └── conditions.json
"""

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional

try:
    from .zone import Zone
except ImportError:
    from zone import Zone

from .time_utils import now_iso
from utils.logging_utils import log_exception


class CompositeTrigger:
    """Manage a composite trigger with zones and conditions"""
    
    # Trigger types
    TYPE_PRESENCE = "presence"      # Object present/absent
    TYPE_COUNT = "count"            # Count objects
    TYPE_MULTI_ZONE = "multi_zone"  # Multiple zone logic (AND/OR)
    
    # Action types
    ACTION_ADVANCE = "advance_sequence"     # Move to next step
    ACTION_START = "start_sequence"         # Start specific sequence
    ACTION_STOP = "stop"                    # Stop current sequence
    ACTION_ALERT = "alert"                  # Show alert only
    
    def __init__(self, name: str, triggers_dir: Path, description: str = ""):
        self.name = name
        self.triggers_dir = triggers_dir
        self.description = description
        self.trigger_type = self.TYPE_PRESENCE
        self.enabled = True
        self.check_interval_seconds = 5.0
        self.zones = []
        self.conditions = {}
        self.action = {"type": self.ACTION_ADVANCE}
        self.active_when = {"robot_state": "home"}
        self.created_at = now_iso()
        self.modified_at = now_iso()
        
        # Ensure triggers directory exists
        self.triggers_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def trigger_dir(self) -> Path:
        """Get the directory for this specific trigger"""
        # Sanitize name for folder
        safe_name = self.name.lower().replace(' ', '_')
        safe_name = ''.join(c for c in safe_name if c.isalnum() or c in '_-')
        return self.triggers_dir / safe_name
    
    @property
    def manifest_path(self) -> Path:
        """Get path to manifest.json"""
        return self.trigger_dir / "manifest.json"
    
    @property
    def zones_path(self) -> Path:
        """Get path to zones.json"""
        return self.trigger_dir / "zones.json"
    
    @property
    def conditions_path(self) -> Path:
        """Get path to conditions.json"""
        return self.trigger_dir / "conditions.json"
    
    @property
    def trigger_id(self) -> str:
        """Get trigger ID from folder name"""
        safe_name = self.name.lower().replace(' ', '_')
        return ''.join(c for c in safe_name if c.isalnum() or c in '_-')
    
    def create_new(self) -> bool:
        """Create new composite trigger structure"""
        try:
            # Create trigger directory
            self.trigger_dir.mkdir(parents=True, exist_ok=True)
            
            # Save initial manifest
            return self.save()
            
        except Exception as exc:
            log_exception(f"CompositeTrigger: failed to create {self.name}", exc)
            return False
    
    def save(self) -> bool:
        """Save all trigger components to disk"""
        try:
            self.trigger_dir.mkdir(parents=True, exist_ok=True)
            self.modified_at = now_iso()
            
            # Save manifest
            manifest_data = {
                "name": self.name,
                "trigger_id": self.trigger_id,
                "type": self.trigger_type,
                "created_at": self.created_at,
                "modified_at": self.modified_at,
                "description": self.description,
                "enabled": self.enabled,
                "check_interval_seconds": self.check_interval_seconds,
                "active_when": self.active_when,
                "action": self.action,
                "components": {
                    "zones": "zones.json",
                    "conditions": "conditions.json"
                }
            }
            
            with open(self.manifest_path, 'w') as f:
                json.dump(manifest_data, f, indent=2)
            
            # Save zones
            zones_data = {
                "zones": [zone.to_dict() for zone in self.zones]
            }
            
            with open(self.zones_path, 'w') as f:
                json.dump(zones_data, f, indent=2)
            
            # Save conditions
            with open(self.conditions_path, 'w') as f:
                json.dump(self.conditions, f, indent=2)
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to save trigger {self.name}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    @classmethod
    def load(cls, name: str, triggers_dir: Path) -> Optional['CompositeTrigger']:
        """Load a trigger from disk"""
        try:
            # Create temporary instance to get directory path
            temp = cls(name, triggers_dir)
            
            if not temp.manifest_path.exists():
                return None
            
            # Load manifest
            with open(temp.manifest_path, 'r') as f:
                manifest_data = json.load(f)
            
            # Create trigger instance
            trigger = cls(
                name=manifest_data.get("name", name),
                triggers_dir=triggers_dir,
                description=manifest_data.get("description", "")
            )
            
            # Load metadata
            trigger.trigger_type = manifest_data.get("type", cls.TYPE_PRESENCE)
            trigger.enabled = manifest_data.get("enabled", True)
            trigger.check_interval_seconds = manifest_data.get("check_interval_seconds", 5.0)
            trigger.active_when = manifest_data.get("active_when", {"robot_state": "home"})
            trigger.action = manifest_data.get("action", {"type": cls.ACTION_ADVANCE})
            trigger.created_at = manifest_data.get("created_at", trigger.created_at)
            trigger.modified_at = manifest_data.get("modified_at", trigger.modified_at)
            
            # Load zones
            if trigger.zones_path.exists():
                with open(trigger.zones_path, 'r') as f:
                    zones_data = json.load(f)
                
                trigger.zones = [Zone.from_dict(z) for z in zones_data.get("zones", [])]
            
            # Load conditions
            if trigger.conditions_path.exists():
                with open(trigger.conditions_path, 'r') as f:
                    trigger.conditions = json.load(f)
            
            return trigger
            
        except Exception as exc:
            log_exception(f"CompositeTrigger: failed to load {name}", exc, stack=True)
            return None
    
    def add_zone(self, zone: Zone):
        """Add a zone to this trigger"""
        self.zones.append(zone)
    
    def remove_zone(self, zone_id: str) -> bool:
        """Remove a zone by ID"""
        original_len = len(self.zones)
        self.zones = [z for z in self.zones if z.zone_id != zone_id]
        return len(self.zones) < original_len
    
    def get_zone(self, zone_id: str) -> Optional[Zone]:
        """Get zone by ID"""
        for zone in self.zones:
            if zone.zone_id == zone_id:
                return zone
        return None
    
    def set_presence_condition(self, zone_id: str, min_objects: int = 1, stability_frames: int = 2):
        """Set presence-based trigger condition"""
        self.trigger_type = self.TYPE_PRESENCE
        self.conditions = {
            "condition_type": "presence",
            "rules": {
                "zone": zone_id,
                "min_objects": min_objects,
                "stability_frames": stability_frames
            }
        }
    
    def set_count_condition(self, zone_id: str, count: int, operator: str = ">=", cumulative: bool = False):
        """Set count-based trigger condition"""
        self.trigger_type = self.TYPE_COUNT
        self.conditions = {
            "condition_type": "count",
            "rules": {
                "zone": zone_id,
                "count": count,
                "operator": operator,  # ">=", "<=", "==", ">", "<"
                "cumulative": cumulative
            }
        }
    
    def set_multi_zone_condition(self, zone_rules: List[Dict], logic: str = "AND"):
        """
        Set multi-zone trigger condition
        
        Args:
            zone_rules: List of {"zone": zone_id, "min_objects": n} dicts
            logic: "AND" or "OR"
        """
        self.trigger_type = self.TYPE_MULTI_ZONE
        self.conditions = {
            "condition_type": "multi_zone",
            "rules": {
                "logic": logic,
                "zones": zone_rules
            }
        }
    
    def delete_trigger(self) -> bool:
        """Delete the entire trigger folder"""
        try:
            if self.trigger_dir.exists():
                shutil.rmtree(self.trigger_dir)
                print(f"[TRIGGER] ✓ Deleted trigger folder: {self.trigger_dir}")
                return True
            return False
        except Exception as exc:
            log_exception(f"CompositeTrigger: failed to delete {self.name}", exc)
            return False
    
    def get_info(self) -> Dict:
        """Get metadata about trigger without full data"""
        return {
            "name": self.name,
            "trigger_id": self.trigger_id,
            "type": self.trigger_type,
            "enabled": self.enabled,
            "zone_count": len(self.zones),
            "check_interval": self.check_interval_seconds,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "description": self.description
        }
    
    def get_full_trigger_data(self) -> Dict:
        """Get complete trigger data for execution"""
        return {
            "name": self.name,
            "trigger_id": self.trigger_id,
            "type": self.trigger_type,
            "enabled": self.enabled,
            "check_interval_seconds": self.check_interval_seconds,
            "active_when": self.active_when,
            "action": self.action,
            "zones": [z.to_dict() for z in self.zones],
            "conditions": self.conditions,
            "metadata": {
                "created_at": self.created_at,
                "modified_at": self.modified_at,
                "description": self.description
            }
        }
    
    def __repr__(self) -> str:
        return f"CompositeTrigger(name='{self.name}', type={self.trigger_type}, zones={len(self.zones)})"


# Test the CompositeTrigger class
if __name__ == "__main__":
    print("=== CompositeTrigger Tests ===\n")
    
    # Setup test directory
    test_dir = Path("data/vision_triggers_test")
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # Test 1: Create a simple presence trigger
    print("1. Creating idle standby trigger...")
    trigger = CompositeTrigger(
        name="Idle Standby",
        triggers_dir=test_dir,
        description="Wait for any object in work area"
    )
    
    # Add zone
    work_area = Zone(
        name="Work Area",
        polygon=[(200, 120), (1080, 120), (1080, 560), (200, 560)],
        zone_type=Zone.TYPE_TRIGGER
    )
    trigger.add_zone(work_area)
    
    # Set condition
    trigger.set_presence_condition(work_area.zone_id, min_objects=1, stability_frames=2)
    
    # Set check interval
    trigger.check_interval_seconds = 5.0
    
    # Create and save
    success = trigger.create_new()
    print(f"   Created: {'✓' if success else '✗'}")
    print(f"   {trigger}")
    print(f"   Folder: {trigger.trigger_dir}\n")
    
    # Test 2: Load the trigger
    print("2. Loading trigger from disk...")
    loaded = CompositeTrigger.load("Idle Standby", test_dir)
    if loaded:
        print(f"   ✓ Loaded: {loaded}")
        print(f"   Zones: {len(loaded.zones)}")
        print(f"   Type: {loaded.trigger_type}")
        print(f"   Interval: {loaded.check_interval_seconds}s\n")
    
    # Test 3: Create multi-zone trigger
    print("3. Creating dual-box check trigger...")
    dual_trigger = CompositeTrigger(
        name="Dual Box Check",
        triggers_dir=test_dir,
        description="Start when both boxes filled"
    )
    
    box1 = Zone("Box 1", [(100, 200), (400, 200), (400, 500), (100, 500)])
    box2 = Zone("Box 2", [(600, 200), (900, 200), (900, 500), (600, 500)])
    
    dual_trigger.add_zone(box1)
    dual_trigger.add_zone(box2)
    
    dual_trigger.set_multi_zone_condition([
        {"zone": box1.zone_id, "min_objects": 1},
        {"zone": box2.zone_id, "min_objects": 1}
    ], logic="AND")
    
    dual_trigger.action = {"type": "start_sequence", "sequence_id": "production_run"}
    dual_trigger.create_new()
    print(f"   ✓ Created: {dual_trigger}\n")
    
    # Test 4: Get trigger info
    print("4. Getting trigger info...")
    info = loaded.get_info()
    for key, value in info.items():
        print(f"   {key}: {value}")
    print()
    
    # Test 5: Get full trigger data
    print("5. Getting full trigger data...")
    full_data = loaded.get_full_trigger_data()
    print(f"   Keys: {list(full_data.keys())}")
    print(f"   Zones count: {len(full_data['zones'])}")
    print(f"   Conditions: {full_data['conditions']['condition_type']}\n")
    
    # Cleanup
    print("6. Cleaning up test data...")
    trigger.delete_trigger()
    dual_trigger.delete_trigger()
    test_dir.rmdir()
    print("   ✓ Cleanup complete\n")
    
    print("✓ CompositeTrigger tests complete!")
