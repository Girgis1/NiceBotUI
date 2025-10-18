"""
Composite Recording Manager - Orchestrate multiple components into one recording

DESIGN:
- Folder-based storage: Each recording is a folder
- manifest.json: Defines step order, speeds, delays
- Component files: Individual JSON files for each step
- Clean separation: Orchestration (manifest) vs Data (components)

EXAMPLE:
    data/recordings/grab_cup/
    ├── manifest.json
    ├── 01_approach_live.json
    ├── 02_grasp_positions.json
    └── 03_retreat_live.json
"""

import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
import pytz

try:
    from .recording_component import RecordingComponent, LiveRecordingComponent, PositionSetComponent
except ImportError:
    # Allow running as standalone script for testing
    from recording_component import RecordingComponent, LiveRecordingComponent, PositionSetComponent


TIMEZONE = pytz.timezone('Australia/Sydney')


class CompositeRecording:
    """Manage a composite recording with multiple components"""
    
    def __init__(self, name: str, recordings_dir: Path, description: str = ""):
        self.name = name
        self.recordings_dir = recordings_dir
        self.description = description
        self.steps = []
        self._next_step_number = 1
        self.created_at = datetime.now(TIMEZONE).isoformat()
        self.modified_at = datetime.now(TIMEZONE).isoformat()
        
        # Ensure recordings directory exists
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def recording_dir(self) -> Path:
        """Get the directory for this specific recording"""
        # Sanitize name for folder
        safe_name = self.name.lower().replace(' ', '_')
        safe_name = ''.join(c for c in safe_name if c.isalnum() or c in '_-')
        return self.recordings_dir / safe_name
    
    @property
    def manifest_path(self) -> Path:
        """Get path to manifest.json"""
        return self.recording_dir / "manifest.json"
    
    @property
    def step_count(self) -> int:
        """Get total number of steps"""
        return len(self.steps)
    
    @property
    def total_duration_estimate(self) -> float:
        """Estimate total duration (for display purposes)"""
        total = 0.0
        for step in self.steps:
            # Add delays
            total += step.get('delay_before', 0.0)
            total += step.get('delay_after', 0.0)
            
            # Estimate component duration (would need to load to be accurate)
            # For now, just placeholder
            total += 1.0
        return total
    
    def create_new(self) -> bool:
        """Create new composite recording structure"""
        try:
            # Create recording directory
            self.recording_dir.mkdir(parents=True, exist_ok=True)
            
            # Initialize empty steps list
            self.steps = []
            self._next_step_number = 1
            
            # Save initial manifest
            return self.save()
            
        except Exception as e:
            print(f"[ERROR] Failed to create composite recording {self.name}: {e}")
            return False
    
    def save(self) -> bool:
        """Save manifest to disk"""
        try:
            self.modified_at = datetime.now(TIMEZONE).isoformat()
            
            manifest = {
                "format_version": "2.0",
                "name": self.name,
                "type": "composite_recording",
                "description": self.description,
                "steps": self.steps,
                "metadata": {
                    "created": self.created_at,
                    "modified": self.modified_at,
                    "total_steps": self.step_count
                }
            }
            
            with open(self.manifest_path, 'w') as f:
                json.dump(manifest, f, indent=2)
            
            print(f"[COMPOSITE] ✓ Saved manifest: {self.name} ({self.step_count} steps)")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to save manifest for {self.name}: {e}")
            return False
    
    @staticmethod
    def load(name: str, recordings_dir: Path) -> Optional['CompositeRecording']:
        """Load existing composite recording from disk"""
        try:
            # Create temporary instance to get paths
            temp = CompositeRecording(name, recordings_dir)
            manifest_path = temp.manifest_path
            
            if not manifest_path.exists():
                print(f"[ERROR] Manifest not found for recording: {name}")
                return None
            
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            
            # Create composite recording instance
            composite = CompositeRecording(
                name=manifest.get("name", name),
                recordings_dir=recordings_dir,
                description=manifest.get("description", "")
            )
            
            # Load steps and metadata
            composite.steps = manifest.get("steps", [])
            metadata = manifest.get("metadata", {})
            composite.created_at = metadata.get("created", composite.created_at)
            composite.modified_at = metadata.get("modified", composite.modified_at)
            
            # Update next step number
            if composite.steps:
                max_num = max(step.get('step_number', 0) for step in composite.steps)
                composite._next_step_number = max_num + 1
            
            print(f"[COMPOSITE] ✓ Loaded: {composite.name} ({composite.step_count} steps)")
            return composite
            
        except Exception as e:
            print(f"[ERROR] Failed to load composite recording {name}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def add_step(self, step_type: str, name: str, component_file: str, 
                 speed: int = 100, enabled: bool = True, 
                 delay_before: float = 0.0, delay_after: float = 0.0,
                 notes: str = "") -> str:
        """Add a step to the composite recording
        
        Args:
            step_type: "live_recording" or "position_set"
            name: Display name for this step
            component_file: Filename of the component (e.g., "01_approach_live.json")
            speed: Speed percentage (0-100)
            enabled: Whether step is active
            delay_before: Seconds to wait before step
            delay_after: Seconds to wait after step
            notes: Optional notes about this step
        
        Returns:
            step_id: Unique identifier for this step
        """
        step_id = f"step_{self._next_step_number:03d}"
        step_number = self._next_step_number
        self._next_step_number += 1
        
        step = {
            "step_id": step_id,
            "step_number": step_number,
            "type": step_type,
            "name": name,
            "file": component_file,
            "speed": speed,
            "enabled": enabled,
            "delay_before": delay_before,
            "delay_after": delay_after,
            "notes": notes
        }
        
        self.steps.append(step)
        print(f"[COMPOSITE] Added step {step_number}: {name} ({step_type})")
        return step_id
    
    def remove_step(self, step_id: str) -> bool:
        """Remove a step by ID"""
        for i, step in enumerate(self.steps):
            if step.get("step_id") == step_id:
                removed = self.steps.pop(i)
                print(f"[COMPOSITE] Removed step: {removed['name']}")
                return True
        return False
    
    def get_step(self, step_id: str) -> Optional[Dict]:
        """Get step by ID"""
        for step in self.steps:
            if step.get("step_id") == step_id:
                return step
        return None
    
    def update_step(self, step_id: str, updates: Dict) -> bool:
        """Update step properties
        
        Args:
            step_id: ID of step to update
            updates: Dict of properties to update (speed, enabled, delays, notes, etc.)
        """
        for step in self.steps:
            if step.get("step_id") == step_id:
                step.update(updates)
                print(f"[COMPOSITE] Updated step: {step['name']}")
                return True
        return False
    
    def reorder_step(self, step_id: str, new_position: int) -> bool:
        """Move a step to a new position (0-indexed)
        
        Args:
            step_id: ID of step to move
            new_position: New index position (0 = first)
        """
        # Find current step
        current_idx = None
        for i, step in enumerate(self.steps):
            if step.get("step_id") == step_id:
                current_idx = i
                break
        
        if current_idx is None:
            return False
        
        # Validate new position
        if new_position < 0 or new_position >= len(self.steps):
            return False
        
        # Move step
        step = self.steps.pop(current_idx)
        self.steps.insert(new_position, step)
        
        # Update step numbers
        for i, s in enumerate(self.steps):
            s['step_number'] = i + 1
        
        print(f"[COMPOSITE] Reordered step: {step['name']} to position {new_position + 1}")
        return True
    
    def get_all_steps(self) -> List[Dict]:
        """Get all steps in order"""
        return self.steps.copy()
    
    def add_live_recording_component(self, name: str, recorded_data: List[Dict],
                                    description: str = "") -> str:
        """Create and save a live recording component
        
        Returns:
            component_filename: Filename of saved component
        """
        try:
            # Create component
            component = LiveRecordingComponent(name, description, recorded_data)
            
            # Generate filename
            filename = f"{self._next_step_number:02d}_{name.lower().replace(' ', '_')}_live.json"
            filepath = self.recording_dir / filename
            
            # Save component
            if component.save(filepath):
                print(f"[COMPOSITE] ✓ Saved live recording component: {filename}")
                return filename
            else:
                return ""
                
        except Exception as e:
            print(f"[ERROR] Failed to save live recording component: {e}")
            return ""
    
    def add_position_set_component(self, name: str, positions: List[Dict],
                                  description: str = "") -> str:
        """Create and save a position set component
        
        Returns:
            component_filename: Filename of saved component
        """
        try:
            # Create component
            component = PositionSetComponent(name, description, positions)
            
            # Generate filename
            filename = f"{self._next_step_number:02d}_{name.lower().replace(' ', '_')}_positions.json"
            filepath = self.recording_dir / filename
            
            # Save component
            if component.save(filepath):
                print(f"[COMPOSITE] ✓ Saved position set component: {filename}")
                return filename
            else:
                return ""
                
        except Exception as e:
            print(f"[ERROR] Failed to save position set component: {e}")
            return ""
    
    def get_component(self, filename: str) -> Optional[Dict]:
        """Load a component file and return its data as dict"""
        try:
            filepath = self.recording_dir / filename
            
            if not filepath.exists():
                print(f"[ERROR] Component file not found: {filename}")
                return None
            
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            return data
            
        except Exception as e:
            print(f"[ERROR] Failed to load component {filename}: {e}")
            return None
    
    def delete_component(self, filename: str) -> bool:
        """Delete a component file"""
        try:
            filepath = self.recording_dir / filename
            
            if filepath.exists():
                filepath.unlink()
                print(f"[COMPOSITE] ✓ Deleted component: {filename}")
                return True
            return False
            
        except Exception as e:
            print(f"[ERROR] Failed to delete component {filename}: {e}")
            return False
    
    def get_full_recording_data(self) -> Dict:
        """Get complete recording data for execution
        
        Returns a dict with all steps and their component data loaded.
        Used by ExecutionManager to run the recording.
        """
        full_data = {
            "name": self.name,
            "type": "composite_recording",
            "description": self.description,
            "steps": []
        }
        
        for step in self.steps:
            component_data = self.get_component(step['file'])
            if component_data:
                step_data = step.copy()
                step_data['component_data'] = component_data
                full_data['steps'].append(step_data)
            else:
                print(f"[WARNING] Could not load component for step: {step['name']}")
        
        return full_data
    
    def get_info(self) -> Dict:
        """Get summary information about this recording"""
        return {
            "name": self.name,
            "type": "composite_recording",
            "description": self.description,
            "step_count": self.step_count,
            "created": self.created_at,
            "modified": self.modified_at,
            "total_duration_estimate": self.total_duration_estimate,
            "recording_dir": str(self.recording_dir)
        }
    
    def delete_recording(self) -> bool:
        """Delete entire composite recording (folder and all files)"""
        try:
            if self.recording_dir.exists():
                shutil.rmtree(self.recording_dir)
                print(f"[COMPOSITE] ✓ Deleted recording: {self.name}")
                return True
            return False
            
        except Exception as e:
            print(f"[ERROR] Failed to delete recording {self.name}: {e}")
            return False


# Example usage and testing
if __name__ == "__main__":
    print("=== Composite Recording Manager ===\n")
    
    # Create test directory
    test_dir = Path(__file__).parent.parent / "data" / "test_recordings"
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a new composite recording
    print("1. Creating new composite recording...")
    recording = CompositeRecording("Test Grab Cup", test_dir, "Test composite recording")
    recording.create_new()
    print(f"   Recording dir: {recording.recording_dir}\n")
    
    # Add a live recording component
    print("2. Adding live recording component...")
    live_data = [
        {"timestamp": 0.0, "positions": [0, 0, 0, 0, 0, 0], "velocity": 600},
        {"timestamp": 0.1, "positions": [1, 2, 3, 4, 5, 6], "velocity": 600},
        {"timestamp": 0.2, "positions": [2, 4, 6, 8, 10, 12], "velocity": 600}
    ]
    component_file_1 = recording.add_live_recording_component("Approach", live_data, "Smooth approach")
    step1_id = recording.add_step("live_recording", "Approach", component_file_1, speed=80, delay_after=0.5)
    print()
    
    # Add a position set component
    print("3. Adding position set component...")
    positions_data = [
        {"name": "Pre-Grasp", "motor_positions": [10, 20, 30, 40, 50, 60], "velocity": 800},
        {"name": "Grasp", "motor_positions": [15, 25, 35, 45, 55, 65], "velocity": 400},
        {"name": "Lift", "motor_positions": [15, 25, 35, 45, 55, 85], "velocity": 600}
    ]
    component_file_2 = recording.add_position_set_component("Grasp", positions_data, "Grasp waypoints")
    step2_id = recording.add_step("position_set", "Grasp", component_file_2, speed=100, delay_after=1.0)
    print()
    
    # Save manifest
    print("4. Saving manifest...")
    recording.save()
    print()
    
    # Load recording back
    print("5. Loading recording...")
    loaded = CompositeRecording.load("Test Grab Cup", test_dir)
    if loaded:
        print(f"   Name: {loaded.name}")
        print(f"   Steps: {loaded.step_count}")
        print(f"   Description: {loaded.description}\n")
        
        # Get full data
        print("6. Getting full recording data...")
        full_data = loaded.get_full_recording_data()
        print(f"   Steps loaded: {len(full_data['steps'])}")
        for step in full_data['steps']:
            print(f"   - {step['name']}: {step['type']} ({step['speed']}%)")
        print()
        
        # Get info
        print("7. Getting recording info...")
        info = loaded.get_info()
        for key, value in info.items():
            print(f"   {key}: {value}")
        print()
    
    # Clean up test
    print("8. Cleaning up test...")
    if loaded:
        loaded.delete_recording()
    print()
    
    print("✓ Composite recording manager working!")

