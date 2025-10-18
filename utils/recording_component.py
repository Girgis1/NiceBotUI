"""
Recording Component Classes - Modular building blocks for composite recordings

DESIGN:
- RecordingComponent: Base class for all component types
- LiveRecordingComponent: Time-series motion capture
- PositionSetComponent: Discrete waypoint positions

Each component is self-contained and can be saved/loaded independently.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
import pytz


TIMEZONE = pytz.timezone('Australia/Sydney')


class RecordingComponent:
    """Base class for recording components"""
    
    def __init__(self, component_type: str, name: str, description: str = ""):
        self.component_type = component_type
        self.name = name
        self.description = description
        self.created_at = datetime.now(TIMEZONE).isoformat()
        self.modified_at = datetime.now(TIMEZONE).isoformat()
    
    def to_dict(self) -> dict:
        """Convert component to dictionary for JSON serialization"""
        return {
            "component_type": self.component_type,
            "name": self.name,
            "description": self.description,
            "metadata": {
                "created_at": self.created_at,
                "modified_at": self.modified_at
            }
        }
    
    def save(self, filepath: Path) -> bool:
        """Save component to JSON file"""
        try:
            self.modified_at = datetime.now(TIMEZONE).isoformat()
            data = self.to_dict()
            
            # Ensure parent directory exists
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f"[COMPONENT] ✓ Saved {self.component_type}: {self.name} -> {filepath.name}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to save component {self.name}: {e}")
            return False
    
    @staticmethod
    def load(filepath: Path) -> Optional['RecordingComponent']:
        """Load component from JSON file"""
        try:
            if not filepath.exists():
                print(f"[ERROR] Component file not found: {filepath}")
                return None
            
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            component_type = data.get("component_type", "unknown")
            
            if component_type == "live_recording":
                return LiveRecordingComponent.from_dict(data)
            elif component_type == "position_set":
                return PositionSetComponent.from_dict(data)
            else:
                print(f"[ERROR] Unknown component type: {component_type}")
                return None
                
        except Exception as e:
            print(f"[ERROR] Failed to load component from {filepath}: {e}")
            return None


class LiveRecordingComponent(RecordingComponent):
    """Live recording component with time-series position data
    
    Stores continuous motion capture with timestamps and velocities.
    Used for smooth, demonstrated motions.
    """
    
    def __init__(self, name: str, description: str = "", recorded_data: List[Dict] = None):
        super().__init__("live_recording", name, description)
        self.recorded_data = recorded_data or []
    
    def add_point(self, timestamp: float, positions: List[int], velocity: int = 600):
        """Add a recorded point to the live recording"""
        point = {
            "timestamp": timestamp,
            "positions": positions,
            "velocity": velocity
        }
        self.recorded_data.append(point)
    
    def get_point_count(self) -> int:
        """Get total number of recorded points"""
        return len(self.recorded_data)
    
    def get_duration(self) -> float:
        """Get total duration of recording in seconds"""
        if not self.recorded_data:
            return 0.0
        return self.recorded_data[-1]['timestamp'] if self.recorded_data else 0.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        data = super().to_dict()
        data["recorded_data"] = self.recorded_data
        data["metadata"]["point_count"] = self.get_point_count()
        data["metadata"]["duration"] = self.get_duration()
        return data
    
    @staticmethod
    def from_dict(data: dict) -> 'LiveRecordingComponent':
        """Create LiveRecordingComponent from dictionary"""
        component = LiveRecordingComponent(
            name=data.get("name", "Untitled Live Recording"),
            description=data.get("description", ""),
            recorded_data=data.get("recorded_data", [])
        )
        
        # Restore metadata if available
        metadata = data.get("metadata", {})
        component.created_at = metadata.get("created_at", component.created_at)
        component.modified_at = metadata.get("modified_at", component.modified_at)
        
        return component


class PositionSetComponent(RecordingComponent):
    """Position set component with discrete waypoints
    
    Stores key positions that the robot should move through.
    Used for precise, waypoint-based motions.
    """
    
    def __init__(self, name: str, description: str = "", positions: List[Dict] = None):
        super().__init__("position_set", name, description)
        self.positions = positions or []
        self._next_position_id = 1
    
    def add_position(self, name: str, motor_positions: List[int], velocity: int = 600, 
                    wait_for_completion: bool = True, notes: str = "") -> str:
        """Add a waypoint position to the set
        
        Returns:
            position_id: Unique ID for this position
        """
        position_id = f"pos_{self._next_position_id:03d}"
        self._next_position_id += 1
        
        position = {
            "position_id": position_id,
            "name": name,
            "motor_positions": motor_positions,
            "velocity": velocity,
            "wait_for_completion": wait_for_completion,
            "notes": notes
        }
        
        self.positions.append(position)
        return position_id
    
    def remove_position(self, position_id: str) -> bool:
        """Remove a position by ID"""
        for i, pos in enumerate(self.positions):
            if pos.get("position_id") == position_id:
                self.positions.pop(i)
                return True
        return False
    
    def get_position(self, position_id: str) -> Optional[Dict]:
        """Get a position by ID"""
        for pos in self.positions:
            if pos.get("position_id") == position_id:
                return pos
        return None
    
    def get_position_count(self) -> int:
        """Get total number of positions"""
        return len(self.positions)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        data = super().to_dict()
        data["positions"] = self.positions
        data["metadata"]["position_count"] = self.get_position_count()
        return data
    
    @staticmethod
    def from_dict(data: dict) -> 'PositionSetComponent':
        """Create PositionSetComponent from dictionary"""
        component = PositionSetComponent(
            name=data.get("name", "Untitled Position Set"),
            description=data.get("description", ""),
            positions=data.get("positions", [])
        )
        
        # Restore metadata if available
        metadata = data.get("metadata", {})
        component.created_at = metadata.get("created_at", component.created_at)
        component.modified_at = metadata.get("modified_at", component.modified_at)
        
        # Update next position ID based on existing positions
        if component.positions:
            max_id = 0
            for pos in component.positions:
                pos_id = pos.get("position_id", "pos_000")
                try:
                    num = int(pos_id.split("_")[1])
                    max_id = max(max_id, num)
                except:
                    pass
            component._next_position_id = max_id + 1
        
        return component


# Example usage (for testing/documentation):
if __name__ == "__main__":
    print("=== Recording Component Classes ===\n")
    
    # Create a live recording component
    print("1. Creating LiveRecordingComponent...")
    live_rec = LiveRecordingComponent("Smooth Approach", "Smooth approach to cup")
    live_rec.add_point(0.0, [0, 0, 0, 0, 0, 0], 600)
    live_rec.add_point(0.1, [1, 2, 3, 4, 5, 6], 600)
    live_rec.add_point(0.2, [2, 4, 6, 8, 10, 12], 600)
    print(f"   Points: {live_rec.get_point_count()}")
    print(f"   Duration: {live_rec.get_duration():.1f}s\n")
    
    # Create a position set component
    print("2. Creating PositionSetComponent...")
    pos_set = PositionSetComponent("Grasp Waypoints", "Key positions for grasping")
    pos_set.add_position("Pre-Grasp", [10, 20, 30, 40, 50, 60], 800, notes="Hover above")
    pos_set.add_position("Grasp", [15, 25, 35, 45, 55, 65], 400, notes="Close gripper")
    pos_set.add_position("Lift", [15, 25, 35, 45, 55, 85], 600, notes="Lift up")
    print(f"   Positions: {pos_set.get_position_count()}\n")
    
    # Test serialization
    print("3. Testing serialization...")
    live_dict = live_rec.to_dict()
    pos_dict = pos_set.to_dict()
    print(f"   Live recording dict keys: {list(live_dict.keys())}")
    print(f"   Position set dict keys: {list(pos_dict.keys())}\n")
    
    # Test deserialization
    print("4. Testing deserialization...")
    live_rec2 = LiveRecordingComponent.from_dict(live_dict)
    pos_set2 = PositionSetComponent.from_dict(pos_dict)
    print(f"   Restored live recording: {live_rec2.name} ({live_rec2.get_point_count()} points)")
    print(f"   Restored position set: {pos_set2.name} ({pos_set2.get_position_count()} positions)\n")
    
    print("✓ All component classes working!")

