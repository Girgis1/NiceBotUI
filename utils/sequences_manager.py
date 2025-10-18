"""
Sequences Manager - Save and load sequences (individual files)

ROBUST DESIGN:
- Each sequence stored as individual JSON file
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
SEQUENCES_DIR = Path(__file__).parent.parent / "data" / "sequences"
BACKUPS_DIR = Path(__file__).parent.parent / "data" / "backups" / "sequences"


class SequencesManager:
    """Manage saved sequences with individual file storage"""
    
    def __init__(self):
        self.sequences_dir = SEQUENCES_DIR
        self.backups_dir = BACKUPS_DIR
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Ensure data directories exist"""
        self.sequences_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
    
    def _sanitize_filename(self, name: str) -> str:
        """Convert sequence name to safe filename
        
        Examples:
            "Production Run v2" -> "production_run_v2"
            "Test Sequence!" -> "test_sequence"
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
        """Get filepath for a sequence"""
        filename = self._sanitize_filename(name) + ".json"
        return self.sequences_dir / filename
    
    def _create_backup(self, filepath: Path):
        """Create timestamped backup of a file"""
        if not filepath.exists():
            return
        
        timestamp = datetime.now(TIMEZONE).strftime("%Y%m%d_%H%M%S")
        backup_name = f"{filepath.stem}_{timestamp}.json"
        backup_path = self.backups_dir / backup_name
        
        try:
            shutil.copy2(filepath, backup_path)
            # Keep only last 10 backups per sequence
            self._cleanup_old_backups(filepath.stem)
        except Exception as e:
            print(f"[WARNING] Backup failed: {e}")
    
    def _cleanup_old_backups(self, sequence_name: str, keep_count: int = 10):
        """Keep only the most recent N backups for a sequence"""
        pattern = f"{sequence_name}_*.json"
        backups = sorted(self.backups_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        
        # Delete old backups
        for old_backup in backups[keep_count:]:
            try:
                old_backup.unlink()
            except Exception as e:
                print(f"[WARNING] Failed to delete old backup {old_backup}: {e}")
    
    def save_sequence(self, name: str, steps: List[Dict], loop: bool = False) -> bool:
        """Save a sequence with full metadata
        
        Args:
            name: Sequence name (e.g., "Production Run v2")
            steps: List of step dicts
                   {"type": "recording", "name": "GrabCup_v1"}
                   {"type": "delay", "duration": 2.0}
                   {"type": "model", "task": "GrabBlock", "checkpoint": "last", "duration": 25.0}
            loop: Whether to loop the sequence
        
        Sequence data structure:
            {
                "name": "Production Run v2",
                "steps": [...],
                "loop": false,
                "metadata": {...}
            }
        """
        try:
            filepath = self._get_filepath(name)
            
            # Create backup if file exists
            if filepath.exists():
                self._create_backup(filepath)
            
            # Load existing metadata if updating
            existing_data = self.load_sequence(name)
            created_time = existing_data['metadata']['created'] if existing_data else datetime.now(TIMEZONE).isoformat()
            
            # Build complete sequence structure
            sequence = {
                "name": name,
                "steps": steps,
                "loop": loop,
                "metadata": {
                    "created": created_time,
                    "modified": datetime.now(TIMEZONE).isoformat(),
                    "version": "1.0",
                    "file_format": "lerobot_sequence",
                    "step_count": len(steps)
                }
            }
            
            # Save to file
            with open(filepath, 'w') as f:
                json.dump(sequence, f, indent=2)
            
            print(f"[SEQUENCES] ✓ Saved sequence: {name} -> {filepath.name}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to save sequence {name}: {e}")
            return False
    
    def load_sequence(self, name: str) -> Optional[Dict]:
        """Load a specific sequence"""
        try:
            filepath = self._get_filepath(name)
            
            if not filepath.exists():
                return None
            
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            return data
            
        except Exception as e:
            print(f"[ERROR] Failed to load sequence {name}: {e}")
            return None
    
    def delete_sequence(self, name: str) -> bool:
        """Delete a sequence (with backup)"""
        try:
            filepath = self._get_filepath(name)
            
            if not filepath.exists():
                return False
            
            # Create final backup before deletion
            self._create_backup(filepath)
            
            # Delete the file
            filepath.unlink()
            
            print(f"[SEQUENCES] ✓ Deleted sequence: {name}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to delete sequence {name}: {e}")
            return False
    
    def list_sequences(self) -> List[str]:
        """List all sequence names (from files)"""
        try:
            # Get all .json files
            json_files = self.sequences_dir.glob("*.json")
            
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
            print(f"[ERROR] Failed to list sequences: {e}")
            return []
    
    def sequence_exists(self, name: str) -> bool:
        """Check if sequence exists"""
        filepath = self._get_filepath(name)
        return filepath.exists()
    
    def get_sequence_info(self, name: str) -> Optional[Dict]:
        """Get metadata about a sequence without loading full data"""
        try:
            filepath = self._get_filepath(name)
            
            if not filepath.exists():
                return None
            
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            # Return summary info
            info = {
                "name": data.get("name", name),
                "step_count": len(data.get("steps", [])),
                "loop": data.get("loop", False),
                "created": data.get("metadata", {}).get("created", "unknown"),
                "modified": data.get("metadata", {}).get("modified", "unknown"),
                "file_size_kb": filepath.stat().st_size / 1024
            }
            
            return info
            
        except Exception as e:
            print(f"[ERROR] Failed to get sequence info for {name}: {e}")
            return None

