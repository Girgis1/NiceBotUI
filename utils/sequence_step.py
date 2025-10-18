"""
Sequence Step Classes - Modular building blocks for composite sequences

DESIGN:
- SequenceStep: Base class for all step types
- ActionStep: Execute a saved recording/action
- ModelStep: Run a trained policy model
- DelayStep: Wait for specified duration
- HomeStep: Return arm to rest position

Each step is self-contained and represents a unit of work in a sequence.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict
import pytz


TIMEZONE = pytz.timezone('Australia/Sydney')


class SequenceStep:
    """Base class for sequence steps"""
    
    def __init__(self, step_type: str, name: str, enabled: bool = True, delay_after: float = 0.0):
        self.step_type = step_type
        self.name = name
        self.enabled = enabled
        self.delay_after = delay_after
        self.created_at = datetime.now(TIMEZONE).isoformat()
        self.modified_at = datetime.now(TIMEZONE).isoformat()
    
    def to_dict(self) -> dict:
        """Convert step to dictionary for JSON serialization"""
        return {
            "step_type": self.step_type,
            "name": self.name,
            "enabled": self.enabled,
            "delay_after": self.delay_after,
            "metadata": {
                "created_at": self.created_at,
                "modified_at": self.modified_at
            }
        }
    
    def save(self, filepath: Path) -> bool:
        """Save step to JSON file"""
        try:
            self.modified_at = datetime.now(TIMEZONE).isoformat()
            data = self.to_dict()
            
            # Ensure parent directory exists
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f"[STEP] ✓ Saved {self.step_type}: {self.name} -> {filepath.name}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to save step {self.name}: {e}")
            return False
    
    @staticmethod
    def load(filepath: Path) -> Optional['SequenceStep']:
        """Load step from JSON file"""
        try:
            if not filepath.exists():
                print(f"[ERROR] Step file not found: {filepath}")
                return None
            
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            step_type = data.get("step_type", "unknown")
            
            if step_type == "action":
                return ActionStep.from_dict(data)
            elif step_type == "model":
                return ModelStep.from_dict(data)
            elif step_type == "delay":
                return DelayStep.from_dict(data)
            elif step_type == "home":
                return HomeStep.from_dict(data)
            else:
                print(f"[ERROR] Unknown step type: {step_type}")
                return None
                
        except Exception as e:
            print(f"[ERROR] Failed to load step from {filepath}: {e}")
            return None


class ActionStep(SequenceStep):
    """Action/Recording execution step
    
    Executes a saved recording (composite or legacy) by name.
    """
    
    def __init__(self, name: str, action_name: str, enabled: bool = True, delay_after: float = 0.0):
        super().__init__("action", name, enabled, delay_after)
        self.action_name = action_name
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        data = super().to_dict()
        data["action_name"] = self.action_name
        return data
    
    @staticmethod
    def from_dict(data: dict) -> 'ActionStep':
        """Create ActionStep from dictionary"""
        step = ActionStep(
            name=data.get("name", "Untitled Action"),
            action_name=data.get("action_name", ""),
            enabled=data.get("enabled", True),
            delay_after=data.get("delay_after", 0.0)
        )
        
        # Restore metadata if available
        metadata = data.get("metadata", {})
        step.created_at = metadata.get("created_at", step.created_at)
        step.modified_at = metadata.get("modified_at", step.modified_at)
        
        return step


class ModelStep(SequenceStep):
    """Trained policy model execution step
    
    Runs a trained LeRobot policy for specified duration.
    """
    
    def __init__(self, name: str, task: str, checkpoint: str = "last", 
                 duration: float = 25.0, enabled: bool = True, delay_after: float = 0.0):
        super().__init__("model", name, enabled, delay_after)
        self.task = task
        self.checkpoint = checkpoint
        self.duration = duration
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        data = super().to_dict()
        data["task"] = self.task
        data["checkpoint"] = self.checkpoint
        data["duration"] = self.duration
        return data
    
    @staticmethod
    def from_dict(data: dict) -> 'ModelStep':
        """Create ModelStep from dictionary"""
        step = ModelStep(
            name=data.get("name", "Untitled Model"),
            task=data.get("task", ""),
            checkpoint=data.get("checkpoint", "last"),
            duration=data.get("duration", 25.0),
            enabled=data.get("enabled", True),
            delay_after=data.get("delay_after", 0.0)
        )
        
        # Restore metadata if available
        metadata = data.get("metadata", {})
        step.created_at = metadata.get("created_at", step.created_at)
        step.modified_at = metadata.get("modified_at", step.modified_at)
        
        return step


class DelayStep(SequenceStep):
    """Delay/Wait step
    
    Pauses sequence execution for specified duration.
    """
    
    def __init__(self, name: str, duration: float, enabled: bool = True, delay_after: float = 0.0):
        super().__init__("delay", name, enabled, delay_after)
        self.duration = duration
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        data = super().to_dict()
        data["duration"] = self.duration
        return data
    
    @staticmethod
    def from_dict(data: dict) -> 'DelayStep':
        """Create DelayStep from dictionary"""
        step = DelayStep(
            name=data.get("name", "Delay"),
            duration=data.get("duration", 1.0),
            enabled=data.get("enabled", True),
            delay_after=data.get("delay_after", 0.0)
        )
        
        # Restore metadata if available
        metadata = data.get("metadata", {})
        step.created_at = metadata.get("created_at", step.created_at)
        step.modified_at = metadata.get("modified_at", step.modified_at)
        
        return step


class HomeStep(SequenceStep):
    """Home position step
    
    Returns robot arm to configured rest/home position.
    """
    
    def __init__(self, name: str = "Home", enabled: bool = True, delay_after: float = 0.0):
        super().__init__("home", name, enabled, delay_after)
    
    @staticmethod
    def from_dict(data: dict) -> 'HomeStep':
        """Create HomeStep from dictionary"""
        step = HomeStep(
            name=data.get("name", "Home"),
            enabled=data.get("enabled", True),
            delay_after=data.get("delay_after", 0.0)
        )
        
        # Restore metadata if available
        metadata = data.get("metadata", {})
        step.created_at = metadata.get("created_at", step.created_at)
        step.modified_at = metadata.get("modified_at", step.modified_at)
        
        return step


# Example usage (for testing/documentation):
if __name__ == "__main__":
    print("=== Sequence Step Classes ===\n")
    
    # Create different step types
    print("1. Creating ActionStep...")
    action_step = ActionStep("Execute Grab", "GrabCup", delay_after=0.5)
    print(f"   Name: {action_step.name}")
    print(f"   Action: {action_step.action_name}")
    print(f"   Delay after: {action_step.delay_after}s\n")
    
    print("2. Creating ModelStep...")
    model_step = ModelStep("Run Policy", "GrabBlock1", "last", 25.0, delay_after=1.0)
    print(f"   Name: {model_step.name}")
    print(f"   Task: {model_step.task}")
    print(f"   Duration: {model_step.duration}s\n")
    
    print("3. Creating DelayStep...")
    delay_step = DelayStep("Wait", 2.0)
    print(f"   Name: {delay_step.name}")
    print(f"   Duration: {delay_step.duration}s\n")
    
    print("4. Creating HomeStep...")
    home_step = HomeStep("Return Home", delay_after=0.5)
    print(f"   Name: {home_step.name}")
    print(f"   Type: {home_step.step_type}\n")
    
    # Test serialization
    print("5. Testing serialization...")
    action_dict = action_step.to_dict()
    model_dict = model_step.to_dict()
    delay_dict = delay_step.to_dict()
    home_dict = home_step.to_dict()
    print(f"   Action dict keys: {list(action_dict.keys())}")
    print(f"   Model dict keys: {list(model_dict.keys())}")
    print(f"   Delay dict keys: {list(delay_dict.keys())}")
    print(f"   Home dict keys: {list(home_dict.keys())}\n")
    
    # Test deserialization
    print("6. Testing deserialization...")
    action_step2 = ActionStep.from_dict(action_dict)
    model_step2 = ModelStep.from_dict(model_dict)
    delay_step2 = DelayStep.from_dict(delay_dict)
    home_step2 = HomeStep.from_dict(home_dict)
    print(f"   Restored action: {action_step2.name} -> {action_step2.action_name}")
    print(f"   Restored model: {model_step2.name} -> {model_step2.task}")
    print(f"   Restored delay: {delay_step2.name} ({delay_step2.duration}s)")
    print(f"   Restored home: {home_step2.name}\n")
    
    print("✓ All step classes working!")

