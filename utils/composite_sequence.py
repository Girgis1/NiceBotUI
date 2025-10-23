"""
Composite Sequence Manager - Orchestrate multiple steps into one sequence

DESIGN:
- Folder-based storage: Each sequence is a folder
- manifest.json: Defines step order, loop mode, configuration
- Step files: Individual JSON files for each step
- Clean separation: Orchestration (manifest) vs Steps (individual files)

EXAMPLE:
    data/sequences/assembly_workflow/
    ├── manifest.json
    ├── 01_grab_part_action.json
    ├── 02_position_part_action.json
    ├── 03_wait_delay.json
    ├── 04_inspect_model.json
    └── 05_return_home.json
"""

import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
import pytz

try:
    from .sequence_step import SequenceStep, ActionStep, ModelStep, DelayStep, HomeStep, VisionStep
except ImportError:
    # Allow running as standalone script for testing
    from sequence_step import SequenceStep, ActionStep, ModelStep, DelayStep, HomeStep, VisionStep


TIMEZONE = pytz.timezone('Australia/Sydney')


class CompositeSequence:
    """Manage a composite sequence with multiple steps"""
    
    def __init__(self, name: str, sequences_dir: Path, description: str = "", loop: bool = False):
        self.name = name
        self.sequences_dir = sequences_dir
        self.description = description
        self.loop = loop
        self.steps = []
        self._next_step_number = 1
        self.created_at = datetime.now(TIMEZONE).isoformat()
        self.modified_at = datetime.now(TIMEZONE).isoformat()
        
        # Ensure sequences directory exists
        self.sequences_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def sequence_dir(self) -> Path:
        """Get the directory for this specific sequence"""
        # Sanitize name for folder
        safe_name = self.name.lower().replace(' ', '_')
        safe_name = ''.join(c for c in safe_name if c.isalnum() or c in '_-')
        return self.sequences_dir / safe_name
    
    @property
    def manifest_path(self) -> Path:
        """Get path to manifest.json"""
        return self.sequence_dir / "manifest.json"
    
    @property
    def step_count(self) -> int:
        """Get total number of steps"""
        return len(self.steps)
    
    @property
    def estimated_duration(self) -> float:
        """Estimate total duration (rough approximation)"""
        total = 0.0
        for step in self.steps:
            # Add delay_after from each step
            total += step.get('delay_after', 0.0)
            
            # Estimate step duration based on type
            step_type = step.get('step_type', '')
            if step_type == 'delay':
                total += step.get('duration', 1.0)
            elif step_type == 'model':
                total += step.get('duration', 25.0)
            elif step_type == 'action':
                # Rough estimate for action execution
                total += 5.0
            elif step_type == 'home':
                # Rough estimate for homing
                total += 3.0
            elif step_type == 'vision':
                total += 2.0
        
        return total
    
    def create_new(self) -> bool:
        """Create new composite sequence structure"""
        try:
            # Create sequence directory
            self.sequence_dir.mkdir(parents=True, exist_ok=True)
            
            # Initialize empty steps list
            self.steps = []
            self._next_step_number = 1
            
            # Save initial manifest
            return self.save_manifest()
            
        except Exception as e:
            print(f"[ERROR] Failed to create composite sequence {self.name}: {e}")
            return False
    
    def save_manifest(self) -> bool:
        """Save manifest to disk"""
        try:
            self.modified_at = datetime.now(TIMEZONE).isoformat()
            
            manifest = {
                "format_version": "2.0",
                "name": self.name,
                "type": "composite_sequence",
                "description": self.description,
                "loop": self.loop,
                "steps": self.steps,
                "metadata": {
                    "created": self.created_at,
                    "modified": self.modified_at,
                    "total_steps": self.step_count,
                    "estimated_duration": self.estimated_duration
                }
            }
            
            with open(self.manifest_path, 'w') as f:
                json.dump(manifest, f, indent=2)
            
            print(f"[SEQUENCE] ✓ Saved manifest: {self.name} ({self.step_count} steps)")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to save manifest for {self.name}: {e}")
            return False
    
    @staticmethod
    def load(name: str, sequences_dir: Path) -> Optional['CompositeSequence']:
        """Load existing composite sequence from disk"""
        try:
            # Create temporary instance to get paths
            temp = CompositeSequence(name, sequences_dir)
            manifest_path = temp.manifest_path
            
            if not manifest_path.exists():
                print(f"[ERROR] Manifest not found for sequence: {name}")
                return None
            
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            
            # Create composite sequence instance
            composite = CompositeSequence(
                name=manifest.get("name", name),
                sequences_dir=sequences_dir,
                description=manifest.get("description", ""),
                loop=manifest.get("loop", False)
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
            
            print(f"[SEQUENCE] ✓ Loaded: {composite.name} ({composite.step_count} steps, loop={composite.loop})")
            return composite
            
        except Exception as e:
            print(f"[ERROR] Failed to load composite sequence {name}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def add_step(self, step_type: str, name: str, step_file: str, 
                 enabled: bool = True, delay_after: float = 0.0,
                 **kwargs) -> str:
        """Add a step to the composite sequence
        
        Args:
            step_type: "action", "model", "delay", "home", or "vision"
            name: Display name for this step
            step_file: Filename of the step JSON (e.g., "01_grab_action.json")
            enabled: Whether step is active
            delay_after: Seconds to wait after step completes
            **kwargs: Additional step-specific parameters
        
        Returns:
            step_id: Unique identifier for this step
        """
        step_id = f"step_{self._next_step_number:03d}"
        step_number = self._next_step_number
        self._next_step_number += 1
        
        step = {
            "step_id": step_id,
            "step_number": step_number,
            "step_type": step_type,
            "name": name,
            "file": step_file,
            "enabled": enabled,
            "delay_after": delay_after
        }
        
        # Add type-specific fields
        if step_type == "action":
            step["action_name"] = kwargs.get("action_name", "")
        elif step_type == "model":
            step["task"] = kwargs.get("task", "")
            step["checkpoint"] = kwargs.get("checkpoint", "last")
            step["duration"] = kwargs.get("duration", 25.0)
        elif step_type == "delay":
            step["duration"] = kwargs.get("duration", 1.0)
        elif step_type == "vision":
            step["camera"] = kwargs.get("camera", {})
            step["trigger"] = kwargs.get("trigger", {})
        # home type has no extra fields
        
        self.steps.append(step)
        print(f"[SEQUENCE] Added step {step_number}: {name} ({step_type})")
        return step_id
    
    def remove_step(self, step_id: str) -> bool:
        """Remove a step by ID"""
        for i, step in enumerate(self.steps):
            if step.get("step_id") == step_id:
                removed = self.steps.pop(i)
                print(f"[SEQUENCE] Removed step: {removed['name']}")
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
            updates: Dict of properties to update
        """
        for step in self.steps:
            if step.get("step_id") == step_id:
                step.update(updates)
                print(f"[SEQUENCE] Updated step: {step['name']}")
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
        
        print(f"[SEQUENCE] Reordered step: {step['name']} to position {new_position + 1}")
        return True
    
    def get_all_steps(self) -> List[Dict]:
        """Get all steps in order"""
        return self.steps.copy()
    
    def add_action_step(self, name: str, action_name: str, enabled: bool = True, 
                       delay_after: float = 0.0) -> str:
        """Create and save an action step
        
        Returns:
            step_id: ID of created step
        """
        try:
            # Create step object
            step_obj = ActionStep(name, action_name, enabled, delay_after)
            
            # Generate filename
            filename = f"{self._next_step_number:02d}_{name.lower().replace(' ', '_')}_action.json"
            filepath = self.sequence_dir / filename
            
            # Save step file
            if step_obj.save(filepath):
                # Add to manifest
                step_id = self.add_step("action", name, filename, enabled, delay_after, 
                                       action_name=action_name)
                return step_id
            else:
                return ""
                
        except Exception as e:
            print(f"[ERROR] Failed to add action step: {e}")
            return ""
    
    def add_model_step(self, name: str, task: str, checkpoint: str = "last", 
                      duration: float = 25.0, enabled: bool = True, 
                      delay_after: float = 0.0) -> str:
        """Create and save a model step
        
        Returns:
            step_id: ID of created step
        """
        try:
            # Create step object
            step_obj = ModelStep(name, task, checkpoint, duration, enabled, delay_after)
            
            # Generate filename
            filename = f"{self._next_step_number:02d}_{name.lower().replace(' ', '_')}_model.json"
            filepath = self.sequence_dir / filename
            
            # Save step file
            if step_obj.save(filepath):
                # Add to manifest
                step_id = self.add_step("model", name, filename, enabled, delay_after,
                                       task=task, checkpoint=checkpoint, duration=duration)
                return step_id
            else:
                return ""
                
        except Exception as e:
            print(f"[ERROR] Failed to add model step: {e}")
            return ""

    def add_vision_step(self, name: str, camera: Dict, trigger: Dict,
                        enabled: bool = True, delay_after: float = 0.0) -> str:
        """Create and save a vision step"""
        try:
            camera_data = json.loads(json.dumps(camera))
            trigger_data = json.loads(json.dumps(trigger))
            step_obj = VisionStep(name, camera_data, trigger_data, enabled, delay_after)

            filename = f"{self._next_step_number:02d}_{name.lower().replace(' ', '_')}_vision.json"
            filepath = self.sequence_dir / filename

            if step_obj.save(filepath):
                step_id = self.add_step(
                    "vision",
                    name,
                    filename,
                    enabled,
                    delay_after,
                    camera=camera_data,
                    trigger=trigger_data,
                )
                return step_id
            return ""
        except Exception as e:
            print(f"[ERROR] Failed to add vision step: {e}")
            return ""
    
    def add_delay_step(self, name: str, duration: float, enabled: bool = True, 
                      delay_after: float = 0.0) -> str:
        """Create and save a delay step
        
        Returns:
            step_id: ID of created step
        """
        try:
            # Create step object
            step_obj = DelayStep(name, duration, enabled, delay_after)
            
            # Generate filename
            filename = f"{self._next_step_number:02d}_{name.lower().replace(' ', '_')}_delay.json"
            filepath = self.sequence_dir / filename
            
            # Save step file
            if step_obj.save(filepath):
                # Add to manifest
                step_id = self.add_step("delay", name, filename, enabled, delay_after,
                                       duration=duration)
                return step_id
            else:
                return ""
                
        except Exception as e:
            print(f"[ERROR] Failed to add delay step: {e}")
            return ""
    
    def add_home_step(self, name: str = "Home", enabled: bool = True, 
                     delay_after: float = 0.0) -> str:
        """Create and save a home step
        
        Returns:
            step_id: ID of created step
        """
        try:
            # Create step object
            step_obj = HomeStep(name, enabled, delay_after)
            
            # Generate filename
            filename = f"{self._next_step_number:02d}_{name.lower().replace(' ', '_')}_home.json"
            filepath = self.sequence_dir / filename
            
            # Save step file
            if step_obj.save(filepath):
                # Add to manifest
                step_id = self.add_step("home", name, filename, enabled, delay_after)
                return step_id
            else:
                return ""
                
        except Exception as e:
            print(f"[ERROR] Failed to add home step: {e}")
            return ""
    
    def get_step_data(self, filename: str) -> Optional[Dict]:
        """Load a step file and return its data as dict"""
        try:
            filepath = self.sequence_dir / filename
            
            if not filepath.exists():
                print(f"[ERROR] Step file not found: {filename}")
                return None
            
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            return data
            
        except Exception as e:
            print(f"[ERROR] Failed to load step {filename}: {e}")
            return None
    
    def delete_step_file(self, filename: str) -> bool:
        """Delete a step file"""
        try:
            filepath = self.sequence_dir / filename
            
            if filepath.exists():
                filepath.unlink()
                print(f"[SEQUENCE] ✓ Deleted step file: {filename}")
                return True
            return False
            
        except Exception as e:
            print(f"[ERROR] Failed to delete step {filename}: {e}")
            return False
    
    def get_full_sequence_data(self) -> Dict:
        """Get complete sequence data for execution
        
        Returns a dict with all steps and their full data loaded.
        Used by ExecutionManager to run the sequence.
        """
        full_data = {
            "name": self.name,
            "type": "composite_sequence",
            "description": self.description,
            "loop": self.loop,
            "steps": []
        }
        
        for step in self.steps:
            step_data = self.get_step_data(step['file'])
            if step_data:
                # Merge manifest step info with loaded step data
                full_step = step.copy()
                full_step['step_data'] = step_data
                full_data['steps'].append(full_step)
            else:
                print(f"[WARNING] Could not load step file for: {step['name']}")
        
        return full_data
    
    def get_info(self) -> Dict:
        """Get summary information about this sequence"""
        return {
            "name": self.name,
            "type": "composite_sequence",
            "description": self.description,
            "loop": self.loop,
            "step_count": self.step_count,
            "created": self.created_at,
            "modified": self.modified_at,
            "estimated_duration": self.estimated_duration,
            "sequence_dir": str(self.sequence_dir)
        }
    
    def delete_sequence(self) -> bool:
        """Delete entire composite sequence (folder and all files)"""
        try:
            if self.sequence_dir.exists():
                shutil.rmtree(self.sequence_dir)
                print(f"[SEQUENCE] ✓ Deleted sequence: {self.name}")
                return True
            return False
            
        except Exception as e:
            print(f"[ERROR] Failed to delete sequence {self.name}: {e}")
            return False


# Example usage and testing
if __name__ == "__main__":
    print("=== Composite Sequence Manager ===\n")
    
    # Create test directory
    test_dir = Path(__file__).parent.parent / "data" / "test_sequences"
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a new composite sequence
    print("1. Creating new composite sequence...")
    sequence = CompositeSequence("Test Assembly", test_dir, "Test assembly workflow", loop=False)
    sequence.create_new()
    print(f"   Sequence dir: {sequence.sequence_dir}\n")
    
    # Add an action step
    print("2. Adding action step...")
    step1_id = sequence.add_action_step("Grab Part", "GrabPart", delay_after=0.5)
    print()
    
    # Add a model step
    print("3. Adding model step...")
    step2_id = sequence.add_model_step("Inspect Part", "InspectQuality", "last", 15.0, delay_after=1.0)
    print()
    
    # Add a delay step
    print("4. Adding delay step...")
    step3_id = sequence.add_delay_step("Wait for Adhesive", 3.0)
    print()
    
    # Add a home step
    print("5. Adding home step...")
    step4_id = sequence.add_home_step("Return Home", delay_after=0.5)
    print()
    
    # Save manifest
    print("6. Saving manifest...")
    sequence.save_manifest()
    print()
    
    # Load sequence back
    print("7. Loading sequence...")
    loaded = CompositeSequence.load("Test Assembly", test_dir)
    if loaded:
        print(f"   Name: {loaded.name}")
        print(f"   Steps: {loaded.step_count}")
        print(f"   Loop: {loaded.loop}")
        print(f"   Description: {loaded.description}\n")
        
        # Get full data
        print("8. Getting full sequence data...")
        full_data = loaded.get_full_sequence_data()
        print(f"   Steps loaded: {len(full_data['steps'])}")
        for step in full_data['steps']:
            print(f"   - {step['name']}: {step['step_type']} (enabled={step['enabled']})")
        print()
        
        # Get info
        print("9. Getting sequence info...")
        info = loaded.get_info()
        for key, value in info.items():
            print(f"   {key}: {value}")
        print()
    
    # Clean up test
    print("10. Cleaning up test...")
    if loaded:
        loaded.delete_sequence()
    print()
    
    print("✓ Composite sequence manager working!")
