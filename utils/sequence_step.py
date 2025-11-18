"""
Sequence Step Classes - Modular building blocks for composite sequences

DESIGN:
- SequenceStep: Base class for all step types
- ActionStep: Execute a saved recording/action
- ModelStep: Run a trained policy model
- DelayStep: Wait for specified duration
- HomeStep: Return arm Home

Each step is self-contained and represents a unit of work in a sequence.
"""

import json
import uuid
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
            elif step_type == "vision":
                return VisionStep.from_dict(data)
            elif step_type == "palletize":
                return PalletizeStep.from_dict(data)
            else:
                print(f"[ERROR] Unknown step type: {step_type}")
                return None
                
        except Exception as e:
            print(f"[ERROR] Failed to load step from {filepath}: {e}")
            return None


class ActionStep(SequenceStep):
    """Action/Recording execution step
    
    Executes a saved recording (composite or legacy) by name.
    Includes mode (solo/bimanual) to indicate how it was recorded.
    """
    
    def __init__(self, name: str, action_name: str, enabled: bool = True, delay_after: float = 0.0, mode: str = "solo"):
        super().__init__("action", name, enabled, delay_after)
        self.action_name = action_name
        self.mode = mode  # "solo" or "bimanual"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        data = super().to_dict()
        data["action_name"] = self.action_name
        data["mode"] = self.mode
        return data
    
    @staticmethod
    def from_dict(data: dict) -> 'ActionStep':
        """Create ActionStep from dictionary"""
        step = ActionStep(
            name=data.get("name", "Untitled Action"),
            action_name=data.get("action_name", ""),
            enabled=data.get("enabled", True),
            delay_after=data.get("delay_after", 0.0),
            mode=data.get("mode", "solo")  # Default to solo for backward compatibility
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


class VisionStep(SequenceStep):
    """Vision trigger configuration step."""

    def __init__(
        self,
        name: str,
        camera: Dict,
        trigger: Dict,
        enabled: bool = True,
        delay_after: float = 0.0,
    ):
        super().__init__("vision", name, enabled, delay_after)
        self.camera = camera or {}
        self.trigger = trigger or {}
        self.trigger.setdefault("idle_mode", {"enabled": False, "interval_seconds": 2.0})

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["camera"] = self.camera
        data["trigger"] = self.trigger
        return data

    @staticmethod
    def from_dict(data: dict) -> 'VisionStep':
        step = VisionStep(
            name=data.get("name", data.get("trigger", {}).get("display_name", "Vision Trigger")),
            camera=data.get("camera", {}),
            trigger=data.get("trigger", {}),
            enabled=data.get("enabled", True),
            delay_after=data.get("delay_after", 0.0),
        )
        metadata = data.get("metadata", {})
        step.created_at = metadata.get("created_at", step.created_at)
        step.modified_at = metadata.get("modified_at", step.modified_at)
        return step


class PalletizeStep(SequenceStep):
    """Palletize grid placement step."""

    def __init__(
        self,
        name: str,
        arm_index: int,
        grid: Dict,
        motion: Dict,
        palletizer_uid: str,
        enabled: bool = True,
        delay_after: float = 0.0,
    ):
        super().__init__("palletize", name, enabled, delay_after)
        self.arm_index = arm_index
        self.grid = grid or {}
        self.motion = motion or {}
        self.palletizer_uid = palletizer_uid

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["arm_index"] = self.arm_index
        data["grid"] = self.grid
        data["motion"] = self.motion
        data["palletizer_uid"] = self.palletizer_uid
        return data

    @staticmethod
    def from_dict(data: dict) -> "PalletizeStep":
        step = PalletizeStep(
            name=data.get("name", "Palletize"),
            arm_index=data.get("arm_index", 0),
            grid=data.get("grid", {}),
            motion=data.get("motion", {}),
            palletizer_uid=data.get("palletizer_uid") or f"pal_{uuid.uuid4().hex[:8]}",
            enabled=data.get("enabled", True),
            delay_after=data.get("delay_after", 0.0),
        )
        metadata = data.get("metadata", {})
        step.created_at = metadata.get("created_at", step.created_at)
        step.modified_at = metadata.get("modified_at", step.modified_at)
        return step


class HomeStep(SequenceStep):
    """Home position step
    
    Returns robot arm(s) to configured rest/home position.
    Supports multi-arm selection via home_arm_1 and home_arm_2 flags.
    """
    
    def __init__(self, name: str = "Home", enabled: bool = True, delay_after: float = 0.0,
                 home_arm_1: bool = True, home_arm_2: bool = True):
        super().__init__("home", name, enabled, delay_after)
        self.home_arm_1 = home_arm_1
        self.home_arm_2 = home_arm_2
    
    def to_dict(self) -> dict:
        """Convert to dictionary with arm selection"""
        data = super().to_dict()
        data["home_arm_1"] = self.home_arm_1
        data["home_arm_2"] = self.home_arm_2
        return data
    
    @staticmethod
    def from_dict(data: dict) -> 'HomeStep':
        """Create HomeStep from dictionary"""
        step = HomeStep(
            name=data.get("name", "Home"),
            enabled=data.get("enabled", True),
            delay_after=data.get("delay_after", 0.0),
            home_arm_1=data.get("home_arm_1", True),  # Default both arms enabled
            home_arm_2=data.get("home_arm_2", True)
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
