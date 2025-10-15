"""
Sequences Manager - Save and load sequences
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional


DATA_PATH = Path(__file__).parent.parent / "data" / "sequences.json"


class SequencesManager:
    """Manage saved sequences (combinations of actions, models, delays)"""
    
    def __init__(self):
        self.data_path = DATA_PATH
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        """Ensure data file exists"""
        if not self.data_path.exists():
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            self.save_all({})
    
    def load_all(self) -> dict:
        """Load all sequences"""
        try:
            with open(self.data_path, 'r') as f:
                data = json.load(f)
                return data.get("sequences", {})
        except Exception as e:
            print(f"Error loading sequences: {e}")
            return {}
    
    def save_all(self, sequences: dict):
        """Save all sequences"""
        try:
            with open(self.data_path, 'w') as f:
                json.dump({"sequences": sequences}, f, indent=2)
        except Exception as e:
            print(f"Error saving sequences: {e}")
    
    def save_sequence(self, name: str, steps: list) -> bool:
        """Save a sequence
        
        Args:
            name: Sequence name
            steps: List of step dicts
                   {"type": "action", "name": "GrabCup_v1"}
                   {"type": "delay", "duration": 2.0}
                   {"type": "model", "task": "GrabBlock", "checkpoint": "last", "duration": 25.0}
        """
        try:
            sequences = self.load_all()
            
            sequences[name] = {
                "steps": steps,
                "created": sequences.get(name, {}).get("created", datetime.now().isoformat()),
                "modified": datetime.now().isoformat()
            }
            
            self.save_all(sequences)
            return True
        except Exception as e:
            print(f"Error saving sequence {name}: {e}")
            return False
    
    def load_sequence(self, name: str) -> Optional[dict]:
        """Load a specific sequence"""
        sequences = self.load_all()
        return sequences.get(name)
    
    def delete_sequence(self, name: str) -> bool:
        """Delete a sequence"""
        try:
            sequences = self.load_all()
            if name in sequences:
                del sequences[name]
                self.save_all(sequences)
                return True
            return False
        except Exception as e:
            print(f"Error deleting sequence {name}: {e}")
            return False
    
    def list_sequences(self) -> list[str]:
        """List all sequence names"""
        sequences = self.load_all()
        return sorted(sequences.keys())
    
    def sequence_exists(self, name: str) -> bool:
        """Check if sequence exists"""
        return name in self.load_all()

