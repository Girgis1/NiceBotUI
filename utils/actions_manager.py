"""
Actions Manager - Manage composite recordings

NEW FORMAT (v2.0):
- Each recording is a folder with manifest.json + component files
- Clean, modular, industrial-grade design
- No legacy support (clean start)

STRUCTURE:
    data/recordings/
    ├── grab_cup/
    │   ├── manifest.json
    │   ├── 01_approach_live.json
    │   └── 02_grasp_positions.json
    └── pick_place/
        ├── manifest.json
        └── 01_pickup_live.json
"""

import json
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
import pytz

try:
    from .composite_recording import CompositeRecording
except ImportError:
    from composite_recording import CompositeRecording


TIMEZONE = pytz.timezone('Australia/Sydney')
RECORDINGS_DIR = Path(__file__).parent.parent / "data" / "recordings"
BACKUPS_DIR = Path(__file__).parent.parent / "data" / "backups" / "recordings"


class ActionsManager:
    """Manage composite recordings with folder-based storage"""
    
    def __init__(self):
        self.recordings_dir = RECORDINGS_DIR
        self.backups_dir = BACKUPS_DIR
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Ensure data directories exist"""
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
    
    def list_actions(self) -> List[str]:
        """List all recording names

        Scans recordings directory for folders containing manifest.json
        """
        try:
            recordings = []

            # Find all subdirectories with manifest.json
            for item in self.recordings_dir.iterdir():
                if item.is_dir():
                    manifest_path = item / "manifest.json"
                    if manifest_path.exists():
                        try:
                            with open(manifest_path, 'r') as f:
                                manifest = json.load(f)
                                name = manifest.get("name", item.name)
                                recordings.append(name)
                        except:
                            # If manifest is corrupted, use folder name
                            recordings.append(item.name)

            return sorted(recordings)

        except Exception as e:
            print(f"[ERROR] Failed to list recordings: {e}")
            return []

    def load_all(self) -> Dict[str, Dict]:
        """Load all recordings that can be deserialised.

        Returns:
            Dict mapping recording name to the fully-expanded recording data.

        Notes:
            - Uses ``list_actions`` so only manifests that parse successfully
              are considered.  Any individual load failure is logged but does
              not abort the remaining loads so that one corrupt recording does
              not break the dashboard selector.
        """

        loaded: Dict[str, Dict] = {}

        for recording_name in self.list_actions():
            try:
                action = self.load_action(recording_name)
            except Exception as exc:  # Defensive: surface unexpected loader bugs
                print(f"[ERROR] Failed to load recording '{recording_name}': {exc}")
                continue

            if action:
                loaded[recording_name] = action

        return loaded
    
    def load_action(self, name: str) -> Optional[Dict]:
        """Load a recording and return execution-ready data
        
        Args:
            name: Recording name
        
        Returns:
            Dict with all recording data formatted for execution:
            {
                "name": str,
                "type": "composite_recording",
                "steps": [
                    {
                        "step_id": str,
                        "type": "live_recording" | "position_set",
                        "name": str,
                        "speed": int,
                        "enabled": bool,
                        "delay_after": float,
                        "component_data": {...}  # Actual recorded data
                    }
                ]
            }
        """
        try:
            # Load composite recording
            composite = CompositeRecording.load(name, self.recordings_dir)
            if not composite:
                return None
            
            # Get full data (loads all components)
            return composite.get_full_recording_data()
            
        except Exception as e:
            print(f"[ERROR] Failed to load recording {name}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def save_action(self, name: str, action_data: dict, action_type: str = "recording") -> bool:
        """Save a recording
        
        Args:
            name: Recording name
            action_data: Recording data dict
                For simple recordings: {"type": "live_recording", "recorded_data": [...]}
                                   or: {"type": "position", "positions": [...]}
                For composite: {"type": "composite_recording", "steps": [...]}
        
        Returns:
            bool: Success status
        """
        try:
            recording_type = action_data.get("type", action_type)
            
            # Check if this is already a composite or if we need to create one
            if recording_type == "composite_recording":
                # Full composite data provided
                return self._save_composite_recording(name, action_data)
            else:
                # Simple recording - create a composite with single component
                return self._save_simple_as_composite(name, action_data, recording_type)
                
        except Exception as e:
            print(f"[ERROR] Failed to save recording {name}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _save_simple_as_composite(self, name: str, data: dict, recording_type: str) -> bool:
        """Save a simple recording as a single-step composite
        
        This allows RecordTab to keep working with simple save calls
        while using the composite format underneath.
        """
        try:
            # Create or load composite recording
            composite = CompositeRecording.load(name, self.recordings_dir)
            if not composite:
                composite = CompositeRecording(name, self.recordings_dir, 
                                              description=data.get("description", ""))
                composite.create_new()
            
            # Clear existing steps (we're replacing)
            composite.steps = []
            composite._next_step_number = 1
            
            # Create component based on type
            if recording_type == "live_recording":
                # Save as live recording component
                recorded_data = data.get("recorded_data", [])
                if recorded_data:
                    component_file = composite.add_live_recording_component(
                        name=name,
                        recorded_data=recorded_data,
                        description=data.get("description", "")
                    )
                    
                    if component_file:
                        # Add step to manifest
                        composite.add_step(
                            step_type="live_recording",
                            name=name,
                            component_file=component_file,
                            speed=data.get("speed", 100),
                            enabled=True,
                            delay_after=0.0
                        )
            
            elif recording_type == "position":
                # Save as position set component
                positions = data.get("positions", [])
                if positions:
                    component_file = composite.add_position_set_component(
                        name=name,
                        positions=positions,
                        description=data.get("description", "")
                    )
                    
                    if component_file:
                        # Add step to manifest
                        composite.add_step(
                            step_type="position_set",
                            name=name,
                            component_file=component_file,
                            speed=data.get("speed", 100),
                            enabled=True,
                            delay_after=0.0
                        )
            
            # Save manifest
            return composite.save()
            
        except Exception as e:
            print(f"[ERROR] Failed to save simple recording as composite: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _save_composite_recording(self, name: str, data: dict) -> bool:
        """Save a full composite recording
        
        Used when RecordTab builds multi-step recordings
        """
        try:
            # Create composite recording
            composite = CompositeRecording(name, self.recordings_dir,
                                          description=data.get("description", ""))
            composite.create_new()
            
            # Process each step
            for step_data in data.get("steps", []):
                step_type = step_data.get("type")
                step_name = step_data.get("name")
                component_data = step_data.get("component_data", {})
                
                # Create component file
                component_file = ""
                if step_type == "live_recording":
                    recorded_data = component_data.get("recorded_data", [])
                    component_file = composite.add_live_recording_component(
                        name=step_name,
                        recorded_data=recorded_data,
                        description=component_data.get("description", "")
                    )
                elif step_type == "position_set":
                    positions = component_data.get("positions", [])
                    component_file = composite.add_position_set_component(
                        name=step_name,
                        positions=positions,
                        description=component_data.get("description", "")
                    )
                
                # Add step to manifest
                if component_file:
                    composite.add_step(
                        step_type=step_type,
                        name=step_name,
                        component_file=component_file,
                        speed=step_data.get("speed", 100),
                        enabled=step_data.get("enabled", True),
                        delay_before=step_data.get("delay_before", 0.0),
                        delay_after=step_data.get("delay_after", 0.0),
                        notes=step_data.get("notes", "")
                    )
            
            # Save manifest
            return composite.save()
            
        except Exception as e:
            print(f"[ERROR] Failed to save composite recording: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def delete_action(self, name: str) -> bool:
        """Delete a recording (with backup)"""
        try:
            # Load composite to get directory
            composite = CompositeRecording.load(name, self.recordings_dir)
            if not composite:
                return False
            
            # Create backup of entire folder
            timestamp = datetime.now(TIMEZONE).strftime("%Y%m%d_%H%M%S")
            backup_name = f"{composite.recording_dir.name}_{timestamp}"
            backup_path = self.backups_dir / backup_name
            
            # Copy folder to backup
            if composite.recording_dir.exists():
                shutil.copytree(composite.recording_dir, backup_path)
                print(f"[ACTIONS] Backed up to: {backup_path}")
            
            # Delete the recording
            result = composite.delete_recording()
            
            if result:
                print(f"[ACTIONS] ✓ Deleted recording: {name}")
            
            return result
            
        except Exception as e:
            print(f"[ERROR] Failed to delete recording {name}: {e}")
            return False
    
    def action_exists(self, name: str) -> bool:
        """Check if recording exists"""
        composite = CompositeRecording.load(name, self.recordings_dir)
        return composite is not None
    
    def get_recording_info(self, name: str) -> Optional[Dict]:
        """Get metadata about a recording without loading full data"""
        try:
            composite = CompositeRecording.load(name, self.recordings_dir)
            if not composite:
                return None
            
            return composite.get_info()
            
        except Exception as e:
            print(f"[ERROR] Failed to get recording info for {name}: {e}")
            return None
    
    def get_composite_recording(self, name: str) -> Optional[CompositeRecording]:
        """Get the CompositeRecording object for direct manipulation
        
        Useful for UI that wants to edit steps, reorder, etc.
        """
        return CompositeRecording.load(name, self.recordings_dir)


# Test the new ActionsManager
if __name__ == "__main__":
    print("=== New ActionsManager (Composite Format) ===\n")
    
    manager = ActionsManager()
    
    # Test 1: Save a simple live recording
    print("1. Saving simple live recording...")
    live_data = {
        "type": "live_recording",
        "speed": 80,
        "recorded_data": [
            {"timestamp": 0.0, "positions": [0, 0, 0, 0, 0, 0], "velocity": 600},
            {"timestamp": 0.1, "positions": [1, 2, 3, 4, 5, 6], "velocity": 600}
        ]
    }
    success = manager.save_action("Test Live", live_data)
    print(f"   Result: {'✓' if success else '✗'}\n")
    
    # Test 2: Save a simple position recording
    print("2. Saving simple position recording...")
    pos_data = {
        "type": "position",
        "speed": 100,
        "positions": [
            {"name": "Pos1", "motor_positions": [10, 20, 30, 40, 50, 60], "velocity": 800},
            {"name": "Pos2", "motor_positions": [15, 25, 35, 45, 55, 65], "velocity": 600}
        ]
    }
    success = manager.save_action("Test Positions", pos_data)
    print(f"   Result: {'✓' if success else '✗'}\n")
    
    # Test 3: List all recordings
    print("3. Listing all recordings...")
    recordings = manager.list_actions()
    print(f"   Found {len(recordings)} recordings:")
    for rec in recordings:
        print(f"   - {rec}")
    print()
    
    # Test 4: Load a recording
    print("4. Loading 'Test Live' recording...")
    loaded = manager.load_action("Test Live")
    if loaded:
        print(f"   Name: {loaded['name']}")
        print(f"   Type: {loaded['type']}")
        print(f"   Steps: {len(loaded.get('steps', []))}")
        if loaded.get('steps'):
            for step in loaded['steps']:
                print(f"   - Step: {step['name']} ({step['type']})")
    print()
    
    # Test 5: Get recording info
    print("5. Getting recording info...")
    info = manager.get_recording_info("Test Live")
    if info:
        for key, value in info.items():
            print(f"   {key}: {value}")
    print()
    
    # Test 6: Clean up
    print("6. Cleaning up test recordings...")
    manager.delete_action("Test Live")
    manager.delete_action("Test Positions")
    print()
    
    print("✓ ActionsManager working with composite format!")
