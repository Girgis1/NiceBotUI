"""
Sequences Manager - Save and load sequences (composite folder-based format)

ROBUST DESIGN:
- Each sequence stored as a folder with manifest.json
- Individual step files for modular editing
- Automatic backups on save
- Folder-based listing (no central index to corrupt)
- Safe filename sanitization
- Metadata in manifest

NEW ARCHITECTURE:
- Uses CompositeSequence class for folder management
- Each sequence: data/sequences/{sequence_name}/
  - manifest.json (orchestration)
  - 01_step_action.json
  - 02_step_delay.json
  - etc.
"""

import json
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
import pytz

try:
    from .composite_sequence import CompositeSequence
except ImportError:
    from composite_sequence import CompositeSequence


TIMEZONE = pytz.timezone('Australia/Sydney')
SEQUENCES_DIR = Path(__file__).parent.parent / "data" / "sequences"
BACKUPS_DIR = Path(__file__).parent.parent / "data" / "backups" / "sequences"


class SequencesManager:
    """Manage saved sequences with composite folder-based storage"""
    
    def __init__(self):
        self.sequences_dir = SEQUENCES_DIR
        self.backups_dir = BACKUPS_DIR
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Ensure data directories exist"""
        self.sequences_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_sequence_dir(self, name: str) -> Path:
        """Get directory path for a sequence folder"""
        # Use CompositeSequence's naming logic for consistency
        safe_name = name.lower().replace(' ', '_')
        safe_name = ''.join(c for c in safe_name if c.isalnum() or c in '_-')
        return self.sequences_dir / safe_name
    
    def _create_backup(self, sequence_dir: Path):
        """Create timestamped backup of a sequence folder"""
        if not sequence_dir.exists() or not sequence_dir.is_dir():
            return
        
        timestamp = datetime.now(TIMEZONE).strftime("%Y%m%d_%H%M%S")
        backup_name = f"{sequence_dir.name}_{timestamp}"
        backup_path = self.backups_dir / backup_name
        
        try:
            shutil.copytree(sequence_dir, backup_path)
            # Keep only last 10 backups per sequence
            self._cleanup_old_backups(sequence_dir.name)
        except Exception as e:
            print(f"[WARNING] Backup failed: {e}")
    
    def _cleanup_old_backups(self, sequence_name: str, keep_count: int = 10):
        """Keep only the most recent N backups for a sequence"""
        pattern = f"{sequence_name}_*"
        backups = sorted(
            [p for p in self.backups_dir.glob(pattern) if p.is_dir()],
            key=lambda p: p.stat().st_mtime, 
            reverse=True
        )
        
        # Delete old backups
        for old_backup in backups[keep_count:]:
            try:
                shutil.rmtree(old_backup)
            except Exception as e:
                print(f"[WARNING] Failed to delete old backup {old_backup}: {e}")
    
    def save_sequence(self, name: str, steps: List[Dict], loop: bool = False, description: str = "") -> bool:
        """Save a sequence using composite folder format
        
        Args:
            name: Sequence name (e.g., "Production Run v2")
            steps: List of step dicts from SequenceTab:
                   {"type": "action", "name": "GrabCup"}
                   {"type": "delay", "duration": 2.0}
                   {"type": "model", "task": "GrabBlock", "checkpoint": "last", "duration": 25.0}
                   {"type": "home"}
            loop: Whether to loop the sequence
            description: Optional description
        
        Creates folder structure:
            data/sequences/{safe_name}/
            ├── manifest.json
            ├── 01_step_action.json
            ├── 02_step_delay.json
            └── etc.
        """
        try:
            sequence_dir = self._get_sequence_dir(name)
            
            # Create backup if sequence already exists
            if sequence_dir.exists():
                self._create_backup(sequence_dir)
            
            # Create or load existing composite sequence
            composite = CompositeSequence(name, self.sequences_dir, description, loop)
            
            # Check if loading existing (to preserve created_at)
            existing = CompositeSequence.load(name, self.sequences_dir)
            if existing:
                composite.created_at = existing.created_at
            
            # Create the folder structure
            composite.create_new()
            
            # Add steps from the provided list
            for step_dict in steps:
                step_type = step_dict.get("type", "")
                step_name = step_dict.get("name", "Unnamed Step")
                if step_type == "vision" and (not step_name or step_name == "Unnamed Step"):
                    step_name = step_dict.get("trigger", {}).get("display_name", "Vision Trigger")
                
                if step_type == "action":
                    action_name = step_dict.get("name", "")
                    composite.add_action_step(step_name, action_name)
                
                elif step_type == "model":
                    task = step_dict.get("task", "")
                    checkpoint = step_dict.get("checkpoint", "last")
                    duration = step_dict.get("duration", 25.0)
                    composite.add_model_step(step_name, task, checkpoint, duration)
                
                elif step_type == "delay":
                    duration = step_dict.get("duration", 1.0)
                    composite.add_delay_step(step_name, duration)
                
                elif step_type == "home":
                    composite.add_home_step(step_name)
                
                elif step_type == "vision":
                    camera = step_dict.get("camera", {})
                    trigger = step_dict.get("trigger", {})
                    trigger.setdefault("idle_mode", {"enabled": False, "interval_seconds": 2.0})
                    enabled = step_dict.get("enabled", True)
                    delay_after = step_dict.get("delay_after", 0.0)
                    composite.add_vision_step(step_name, camera, trigger, enabled, delay_after)
            
            # Save manifest
            success = composite.save_manifest()
            
            if success:
                print(f"[SEQUENCES] ✓ Saved composite sequence: {name} ({len(steps)} steps)")
            
            return success
            
        except Exception as e:
            print(f"[ERROR] Failed to save sequence {name}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def load_sequence(self, name: str) -> Optional[Dict]:
        """Load a specific sequence (returns simplified format for UI compatibility)
        
        Returns a dict compatible with the old format:
            {
                "name": "Sequence Name",
                "steps": [{"type": "action", "name": "GrabCup"}, ...],
                "loop": false,
                "metadata": {...}
            }
        """
        try:
            # Try loading as composite sequence
            composite = CompositeSequence.load(name, self.sequences_dir)
            if not composite:
                return None
            
            # Convert composite steps to simple format for UI
            simple_steps = []
            for step in composite.steps:
                step_type = step.get("step_type", "")
                simple_step = {"type": step_type}
                
                if step_type == "action":
                    simple_step["name"] = step.get("action_name", "")
                elif step_type == "model":
                    simple_step["task"] = step.get("task", "")
                    simple_step["checkpoint"] = step.get("checkpoint", "last")
                    simple_step["duration"] = step.get("duration", 25.0)
                elif step_type == "delay":
                    simple_step["duration"] = step.get("duration", 1.0)
                elif step_type == "home":
                    pass  # No extra fields for home
                elif step_type == "vision":
                    simple_step["name"] = step.get("name", step.get("trigger", {}).get("display_name", "Vision Trigger"))
                    simple_step["camera"] = step.get("camera", {})
                    simple_step["trigger"] = step.get("trigger", {})
                    simple_step["trigger"].setdefault("idle_mode", {"enabled": False, "interval_seconds": 2.0})
                
                simple_steps.append(simple_step)
            
            # Return in old format for compatibility
            return {
                "name": composite.name,
                "steps": simple_steps,
                "loop": composite.loop,
                "metadata": {
                    "created": composite.created_at,
                    "modified": composite.modified_at,
                    "version": "2.0",
                    "file_format": "lerobot_composite_sequence",
                    "step_count": composite.step_count
                }
            }
            
        except Exception as e:
            print(f"[ERROR] Failed to load sequence {name}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def delete_sequence(self, name: str) -> bool:
        """Delete a sequence folder (with backup)"""
        try:
            composite = CompositeSequence.load(name, self.sequences_dir)
            if not composite:
                return False
            
            # Create final backup before deletion
            self._create_backup(composite.sequence_dir)
            
            # Delete the entire folder
            success = composite.delete_sequence()
            
            if success:
                print(f"[SEQUENCES] ✓ Deleted composite sequence: {name}")
            
            return success
            
        except Exception as e:
            print(f"[ERROR] Failed to delete sequence {name}: {e}")
            return False
    
    def list_sequences(self) -> List[str]:
        """List all sequence names (from folders)"""
        try:
            names = []
            
            # Look for folders with manifest.json
            for item in self.sequences_dir.iterdir():
                if item.is_dir():
                    manifest_path = item / "manifest.json"
                    if manifest_path.exists():
                        try:
                            with open(manifest_path, 'r') as f:
                                data = json.load(f)
                                names.append(data.get("name", item.name))
                        except:
                            # Fallback to folder name if manifest is corrupted
                            names.append(item.name.replace('_', ' ').title())
            
            return sorted(names)
            
        except Exception as e:
            print(f"[ERROR] Failed to list sequences: {e}")
            return []
    
    def sequence_exists(self, name: str) -> bool:
        """Check if sequence exists"""
        sequence_dir = self._get_sequence_dir(name)
        manifest_path = sequence_dir / "manifest.json"
        return manifest_path.exists()
    
    def get_sequence_info(self, name: str) -> Optional[Dict]:
        """Get metadata about a sequence without loading full data"""
        try:
            composite = CompositeSequence.load(name, self.sequences_dir)
            if not composite:
                return None
            
            return composite.get_info()
            
        except Exception as e:
            print(f"[ERROR] Failed to get sequence info for {name}: {e}")
            return None
