"""
Actions Manager - Save and load action recordings (individual files)

ROBUST DESIGN:
- Each recording stored as individual JSON file
- Automatic backups on save
- File-based listing (no central index to corrupt)
- Safe filename sanitization
- Metadata in each file
"""

import json
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
import pytz


TIMEZONE = pytz.timezone('Australia/Sydney')
RECORDINGS_DIR = Path(__file__).parent.parent / "data" / "recordings"
BACKUPS_DIR = Path(__file__).parent.parent / "data" / "backups" / "recordings"


class ActionsManager:
    """Manage saved action recordings with individual file storage"""
    
    def __init__(self):
        self.recordings_dir = RECORDINGS_DIR
        self.backups_dir = BACKUPS_DIR
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Ensure data directories exist"""
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
    
    def _sanitize_filename(self, name: str) -> str:
        """Convert recording name to safe filename
        
        Examples:
            "Grab Cup v1" -> "grab_cup_v1"
            "Pick&Place!" -> "pick_place"
        """
        # Convert to lowercase
        safe_name = name.lower()
        # Replace spaces and special chars with underscore
        safe_name = re.sub(r'[^a-z0-9_-]+', '_', safe_name)
        # Remove duplicate underscores
        safe_name = re.sub(r'_+', '_', safe_name)
        # Remove leading/trailing underscores
        safe_name = safe_name.strip('_')
        # Limit length
        safe_name = safe_name[:50]
        return safe_name
    
    def _get_filepath(self, name: str) -> Path:
        """Get filepath for a recording"""
        filename = self._sanitize_filename(name) + ".json"
        return self.recordings_dir / filename
    
    def _create_backup(self, filepath: Path):
        """Create timestamped backup of a file"""
        if not filepath.exists():
            return
        
        timestamp = datetime.now(TIMEZONE).strftime("%Y%m%d_%H%M%S")
        backup_name = f"{filepath.stem}_{timestamp}.json"
        backup_path = self.backups_dir / backup_name
        
        try:
            shutil.copy2(filepath, backup_path)
            # Keep only last 10 backups per recording
            self._cleanup_old_backups(filepath.stem)
        except Exception as e:
            print(f"[WARNING] Backup failed: {e}")
    
    def _cleanup_old_backups(self, recording_name: str, keep_count: int = 10):
        """Keep only the most recent N backups for a recording"""
        pattern = f"{recording_name}_*.json"
        backups = sorted(self.backups_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        
        # Delete old backups
        for old_backup in backups[keep_count:]:
            try:
                old_backup.unlink()
            except Exception as e:
                print(f"[WARNING] Failed to delete old backup {old_backup}: {e}")
    
    def save_action(self, name: str, action_data: dict, action_type: str = "recording") -> bool:
        """Save a recording with full metadata
        
        Args:
            name: Recording name (e.g., "Grab Cup v1")
            action_data: Recording data dict with 'positions', 'recorded_data', etc.
            action_type: Type of action ("recording", "position", "live_recording")
        
        Recording data structure:
            {
                "name": "Grab Cup v1",
                "type": "live_recording",
                "positions": [...],  # For simple position recordings
                "recorded_data": [...],  # For live recordings
                "speed": 100,
                "delays": {},
                "metadata": {...}
            }
        """
        try:
            filepath = self._get_filepath(name)
            
            # Create backup if file exists
            if filepath.exists():
                self._create_backup(filepath)
            
            # Load existing metadata if updating
            existing_data = self.load_action(name)
            created_time = existing_data['metadata']['created'] if existing_data else datetime.now(TIMEZONE).isoformat()
            
            # Build complete recording structure
            recording = {
                "name": name,
                "type": action_data.get("type", action_type),
                "speed": action_data.get("speed", 100),
                "positions": action_data.get("positions", []),
                "recorded_data": action_data.get("recorded_data", []),
                "delays": action_data.get("delays", {}),
                "metadata": {
                    "created": created_time,
                    "modified": datetime.now(TIMEZONE).isoformat(),
                    "version": "1.0",
                    "file_format": "lerobot_recording"
                }
            }
            
            # Save to file
            with open(filepath, 'w') as f:
                json.dump(recording, f, indent=2)
            
            print(f"[ACTIONS] ✓ Saved recording: {name} -> {filepath.name}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to save recording {name}: {e}")
            return False
    
    def load_action(self, name: str) -> Optional[Dict]:
        """Load a specific recording"""
        try:
            filepath = self._get_filepath(name)
            
            if not filepath.exists():
                return None
            
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            return data
            
        except Exception as e:
            print(f"[ERROR] Failed to load recording {name}: {e}")
            return None
    
    def delete_action(self, name: str) -> bool:
        """Delete a recording (with backup)"""
        try:
            filepath = self._get_filepath(name)
            
            if not filepath.exists():
                return False
            
            # Create final backup before deletion
            self._create_backup(filepath)
            
            # Delete the file
            filepath.unlink()
            
            print(f"[ACTIONS] ✓ Deleted recording: {name}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to delete recording {name}: {e}")
            return False
    
    def list_actions(self) -> List[str]:
        """List all recording names (from files)"""
        try:
            # Get all .json files
            json_files = self.recordings_dir.glob("*.json")
            
            # Load names from files (use stored name, not filename)
            names = []
            for filepath in json_files:
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                        names.append(data.get("name", filepath.stem))
                except:
                    # Fallback to filename if file is corrupted
                    names.append(filepath.stem)
            
            return sorted(names)
            
        except Exception as e:
            print(f"[ERROR] Failed to list recordings: {e}")
            return []
    
    def action_exists(self, name: str) -> bool:
        """Check if recording exists"""
        filepath = self._get_filepath(name)
        return filepath.exists()
    
    def get_recording_info(self, name: str) -> Optional[Dict]:
        """Get metadata about a recording without loading full data"""
        try:
            filepath = self._get_filepath(name)
            
            if not filepath.exists():
                return None
            
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            # Return summary info
            info = {
                "name": data.get("name", name),
                "type": data.get("type", "unknown"),
                "speed": data.get("speed", 100),
                "point_count": len(data.get("positions", [])) or len(data.get("recorded_data", [])),
                "created": data.get("metadata", {}).get("created", "unknown"),
                "modified": data.get("metadata", {}).get("modified", "unknown"),
                "file_size_kb": filepath.stat().st_size / 1024
            }
            
            return info
            
        except Exception as e:
            print(f"[ERROR] Failed to get recording info for {name}: {e}")
            return None

