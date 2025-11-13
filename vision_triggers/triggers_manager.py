"""
Triggers Manager - Manage vision triggers (following ActionsManager/SequencesManager pattern)

DESIGN:
- Folder-based storage in data/vision_triggers/
- Automatic backups on save
- Folder-based listing (no central index to corrupt)
- Uses CompositeTrigger for folder management
- Clean API matching existing managers
"""

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional

try:
    from .composite_trigger import CompositeTrigger
except ImportError:
    from composite_trigger import CompositeTrigger

from .time_utils import format_timestamp
from utils.logging_utils import log_exception
TRIGGERS_DIR = Path(__file__).parent.parent / "data" / "vision_triggers"
BACKUPS_DIR = Path(__file__).parent.parent / "data" / "backups" / "vision_triggers"


class TriggersManager:
    """Manage saved vision triggers with composite folder-based storage"""
    
    def __init__(self):
        self.triggers_dir = TRIGGERS_DIR
        self.backups_dir = BACKUPS_DIR
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Ensure data directories exist"""
        self.triggers_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_trigger_dir(self, name: str) -> Path:
        """Get directory path for a trigger folder"""
        # Use CompositeTrigger's naming logic for consistency
        safe_name = name.lower().replace(' ', '_')
        safe_name = ''.join(c for c in safe_name if c.isalnum() or c in '_-')
        return self.triggers_dir / safe_name
    
    def _create_backup(self, trigger_dir: Path):
        """Create timestamped backup of a trigger folder"""
        if not trigger_dir.exists() or not trigger_dir.is_dir():
            return
        
        timestamp = format_timestamp("%Y%m%d_%H%M%S")
        backup_name = f"{trigger_dir.name}_{timestamp}"
        backup_path = self.backups_dir / backup_name
        
        try:
            shutil.copytree(trigger_dir, backup_path)
            # Keep only last 10 backups per trigger
            self._cleanup_old_backups(trigger_dir.name)
        except Exception as exc:
            log_exception(f"TriggersManager: backup failed for {trigger_dir.name}", exc, level="warning")

    def _cleanup_old_backups(self, trigger_name: str, keep_count: int = 10):
        """Keep only the most recent N backups for a trigger"""
        pattern = f"{trigger_name}_*"
        backups = sorted(
            [p for p in self.backups_dir.glob(pattern) if p.is_dir()],
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        # Delete old backups
        for old_backup in backups[keep_count:]:
            try:
                shutil.rmtree(old_backup)
            except Exception as exc:
                log_exception(f"TriggersManager: failed to delete backup {old_backup}", exc, level="warning")
    
    def list_triggers(self) -> List[str]:
        """List all trigger names
        
        Scans triggers directory for folders containing manifest.json
        """
        try:
            triggers = []
            
            # Find all subdirectories with manifest.json
            for item in self.triggers_dir.iterdir():
                if item.is_dir():
                    manifest_path = item / "manifest.json"
                    if manifest_path.exists():
                        try:
                            with open(manifest_path, 'r') as f:
                                manifest = json.load(f)
                                name = manifest.get("name", item.name)
                                triggers.append(name)
                        except:
                            # If manifest is corrupted, use folder name
                            triggers.append(item.name.replace('_', ' ').title())
            
            return sorted(triggers)
        
        except Exception as exc:
            log_exception("TriggersManager: failed to list triggers", exc)
            return []
    
    def load_all(self) -> Dict[str, Dict]:
        """Load all triggers that can be deserialised
        
        Returns:
            Dict mapping trigger name to full trigger data
        """
        loaded: Dict[str, Dict] = {}
        
        for trigger_name in self.list_triggers():
            try:
                trigger_data = self.load_trigger(trigger_name)
            except Exception as exc:
                log_exception(f"TriggersManager: failed to load trigger '{trigger_name}'", exc)
                continue
            
            if trigger_data:
                loaded[trigger_name] = trigger_data
        
        return loaded
    
    def load_trigger(self, name: str) -> Optional[Dict]:
        """Load a trigger and return execution-ready data
        
        Args:
            name: Trigger name
        
        Returns:
            Dict with all trigger data formatted for execution
        """
        try:
            # Load composite trigger
            composite = CompositeTrigger.load(name, self.triggers_dir)
            if not composite:
                return None
            
            # Get full data
            return composite.get_full_trigger_data()
        
        except Exception as exc:
            log_exception(f"TriggersManager: failed to load trigger {name}", exc, stack=True)
            return None
    
    def save_trigger(
        self, 
        name: str,
        trigger_type: str,
        zones: List[Dict],
        conditions: Dict,
        check_interval: float = 5.0,
        enabled: bool = True,
        action: Optional[Dict] = None,
        active_when: Optional[Dict] = None,
        description: str = ""
    ) -> bool:
        """Save a vision trigger
        
        Args:
            name: Trigger name
            trigger_type: Type (presence, count, multi_zone)
            zones: List of zone dicts
            conditions: Trigger condition rules
            check_interval: Check interval in seconds
            enabled: Whether trigger is active
            action: Action to take when triggered
            active_when: Conditions for when trigger is active
            description: Optional description
        
        Returns:
            bool: Success status
        """
        try:
            trigger_dir = self._get_trigger_dir(name)
            
            # Create backup if trigger already exists
            if trigger_dir.exists():
                self._create_backup(trigger_dir)
            
            # Create or load existing composite trigger
            composite = CompositeTrigger.load(name, self.triggers_dir)
            if not composite:
                composite = CompositeTrigger(name, self.triggers_dir, description)
            
            # Update properties
            composite.trigger_type = trigger_type
            composite.enabled = enabled
            composite.check_interval_seconds = check_interval
            composite.conditions = conditions
            
            if action:
                composite.action = action
            if active_when:
                composite.active_when = active_when
            
            # Clear and reload zones
            composite.zones = []
            try:
                from .zone import Zone
            except ImportError:
                from zone import Zone
            for zone_data in zones:
                zone = Zone.from_dict(zone_data)
                composite.add_zone(zone)
            
            # Create and save
            if not trigger_dir.exists():
                success = composite.create_new()
            else:
                success = composite.save()
            
            if success:
                print(f"[TRIGGERS] ✓ Saved trigger: {name}")
            
            return success
        
        except Exception as exc:
            log_exception(f"TriggersManager: failed to save trigger {name}", exc, stack=True)
            return False
    
    def delete_trigger(self, name: str) -> bool:
        """Delete a trigger (with backup)"""
        try:
            # Load composite to get directory
            composite = CompositeTrigger.load(name, self.triggers_dir)
            if not composite:
                return False
            
            # Create backup of entire folder
            self._create_backup(composite.trigger_dir)
            
            # Delete the trigger
            result = composite.delete_trigger()
            
            if result:
                print(f"[TRIGGERS] ✓ Deleted trigger: {name}")
            
            return result
        
        except Exception as exc:
            log_exception(f"TriggersManager: failed to delete trigger {name}", exc)
            return False
    
    def trigger_exists(self, name: str) -> bool:
        """Check if trigger exists"""
        composite = CompositeTrigger.load(name, self.triggers_dir)
        return composite is not None
    
    def get_trigger_info(self, name: str) -> Optional[Dict]:
        """Get metadata about a trigger without loading full data"""
        try:
            composite = CompositeTrigger.load(name, self.triggers_dir)
            if not composite:
                return None
            
            return composite.get_info()
        
        except Exception as exc:
            log_exception(f"TriggersManager: failed to get trigger info for {name}", exc)
            return None
    
    def get_composite_trigger(self, name: str) -> Optional[CompositeTrigger]:
        """Get the CompositeTrigger object for direct manipulation
        
        Useful for UI that wants to edit zones, conditions, etc.
        """
        return CompositeTrigger.load(name, self.triggers_dir)
    
    def get_enabled_triggers(self) -> List[str]:
        """Get list of enabled trigger names"""
        enabled = []
        for name in self.list_triggers():
            info = self.get_trigger_info(name)
            if info and info.get("enabled", False):
                enabled.append(name)
        return enabled


# Test the TriggersManager
if __name__ == "__main__":
    print("=== TriggersManager Tests ===\n")
    
    # Setup test directory
    test_triggers_dir = Path("data/vision_triggers_test")
    test_backups_dir = Path("data/backups/vision_triggers_test")
    
    manager = TriggersManager()
    # Override directories for testing
    manager.triggers_dir = test_triggers_dir
    manager.backups_dir = test_backups_dir
    manager._ensure_directories()
    
    # Test 1: Save a simple presence trigger
    print("1. Saving idle standby trigger...")
    zones = [{
        "zone_id": "work_area",
        "name": "Work Area",
        "type": "trigger",
        "polygon": [[200, 120], [1080, 120], [1080, 560], [200, 560]],
        "enabled": True,
        "notes": ""
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
        description="Wait for any object in work area"
    )
    print(f"   Result: {'✓' if success else '✗'}\n")
    
    # Test 2: Save a multi-zone trigger
    print("2. Saving dual box check trigger...")
    dual_zones = [
        {
            "zone_id": "box_1",
            "name": "Box 1",
            "type": "trigger",
            "polygon": [[100, 200], [400, 200], [400, 500], [100, 500]],
            "enabled": True,
            "notes": ""
        },
        {
            "zone_id": "box_2",
            "name": "Box 2",
            "type": "trigger",
            "polygon": [[600, 200], [900, 200], [900, 500], [600, 500]],
            "enabled": True,
            "notes": ""
        }
    ]
    
    dual_conditions = {
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
        zones=dual_zones,
        conditions=dual_conditions,
        check_interval=2.0,
        action={"type": "start_sequence", "sequence_id": "production_run"},
        description="Start when both boxes filled"
    )
    print(f"   Result: {'✓' if success else '✗'}\n")
    
    # Test 3: List all triggers
    print("3. Listing all triggers...")
    triggers = manager.list_triggers()
    print(f"   Found {len(triggers)} triggers:")
    for trigger_name in triggers:
        print(f"   - {trigger_name}")
    print()
    
    # Test 4: Load a trigger
    print("4. Loading 'Idle Standby' trigger...")
    loaded = manager.load_trigger("Idle Standby")
    if loaded:
        print(f"   Name: {loaded['name']}")
        print(f"   Type: {loaded['type']}")
        print(f"   Zones: {len(loaded['zones'])}")
        print(f"   Enabled: {loaded['enabled']}")
        print(f"   Interval: {loaded['check_interval_seconds']}s")
    print()
    
    # Test 5: Get trigger info
    print("5. Getting trigger info...")
    info = manager.get_trigger_info("Dual Box Check")
    if info:
        for key, value in info.items():
            print(f"   {key}: {value}")
    print()
    
    # Test 6: Check if trigger exists
    print("6. Checking trigger existence...")
    print(f"   'Idle Standby' exists: {manager.trigger_exists('Idle Standby')}")
    print(f"   'Nonexistent' exists: {manager.trigger_exists('Nonexistent')}")
    print()
    
    # Test 7: Get enabled triggers
    print("7. Getting enabled triggers...")
    enabled = manager.get_enabled_triggers()
    print(f"   Enabled triggers: {enabled}\n")
    
    # Test 8: Load all triggers
    print("8. Loading all triggers...")
    all_triggers = manager.load_all()
    print(f"   Loaded {len(all_triggers)} triggers")
    for name, data in all_triggers.items():
        print(f"   - {name}: {data['type']} ({len(data['zones'])} zones)")
    print()
    
    # Test 9: Clean up
    print("9. Cleaning up test triggers...")
    manager.delete_trigger("Idle Standby")
    manager.delete_trigger("Dual Box Check")
    
    # Clean up directories
    if test_triggers_dir.exists():
        shutil.rmtree(test_triggers_dir)
    if test_backups_dir.exists():
        shutil.rmtree(test_backups_dir)
    print()
    
    print("✓ TriggersManager working with composite format!")
