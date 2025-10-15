"""
Actions Manager - Save and load action sequences
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional


DATA_PATH = Path(__file__).parent.parent / "data" / "actions.json"


class ActionsManager:
    """Manage saved action sequences"""
    
    def __init__(self):
        self.data_path = DATA_PATH
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        """Ensure data file exists"""
        if not self.data_path.exists():
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            self.save_all({})
    
    def load_all(self) -> dict:
        """Load all actions"""
        try:
            with open(self.data_path, 'r') as f:
                data = json.load(f)
                return data.get("actions", {})
        except Exception as e:
            print(f"Error loading actions: {e}")
            return {}
    
    def save_all(self, actions: dict):
        """Save all actions"""
        try:
            with open(self.data_path, 'w') as f:
                json.dump({"actions": actions}, f, indent=2)
        except Exception as e:
            print(f"Error saving actions: {e}")
    
    def save_action(self, name: str, positions: list, delays: dict = None) -> bool:
        """Save an action sequence
        
        Args:
            name: Action name (e.g., "GrabCup_v1")
            positions: List of position dicts [{"name": "Pos 1", "motor_positions": [...], "velocity": 600}, ...]
            delays: Dict of delays {position_index: delay_seconds}
        """
        try:
            actions = self.load_all()
            
            actions[name] = {
                "positions": positions,
                "delays": delays or {},
                "created": actions.get(name, {}).get("created", datetime.now().isoformat()),
                "modified": datetime.now().isoformat()
            }
            
            self.save_all(actions)
            return True
        except Exception as e:
            print(f"Error saving action {name}: {e}")
            return False
    
    def load_action(self, name: str) -> Optional[dict]:
        """Load a specific action"""
        actions = self.load_all()
        return actions.get(name)
    
    def delete_action(self, name: str) -> bool:
        """Delete an action"""
        try:
            actions = self.load_all()
            if name in actions:
                del actions[name]
                self.save_all(actions)
                return True
            return False
        except Exception as e:
            print(f"Error deleting action {name}: {e}")
            return False
    
    def list_actions(self) -> list[str]:
        """List all action names"""
        actions = self.load_all()
        return sorted(actions.keys())
    
    def action_exists(self, name: str) -> bool:
        """Check if action exists"""
        return name in self.load_all()

