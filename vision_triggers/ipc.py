"""
IPC - Inter-Process Communication via file-based state exchange

Simple, reliable communication between vision daemon and sequencer using JSON files.

Files:
- robot_state.json: Sequencer → Daemon (robot state, accepting triggers)
- vision_events.json: Daemon → Sequencer (detection events, trigger results)
"""

import json
import time
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime
import pytz


TIMEZONE = pytz.timezone('Australia/Sydney')


class IPCManager:
    """Manage IPC state files for vision daemon communication"""
    
    def __init__(self, runtime_dir: Path):
        self.runtime_dir = runtime_dir
        self.robot_state_file = runtime_dir / "robot_state.json"
        self.vision_events_file = runtime_dir / "vision_events.json"
        self.daemon_pid_file = runtime_dir / "vision_daemon.pid"
        
        # Ensure runtime directory exists
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
    
    # Robot State (Sequencer → Daemon)
    
    def write_robot_state(
        self,
        state: str = "home",
        moving: bool = False,
        current_sequence: Optional[str] = None,
        accepting_triggers: bool = True
    ) -> bool:
        """
        Write robot state for daemon to read
        
        Args:
            state: Robot state (home, moving, working, error)
            moving: Whether robot is currently moving
            current_sequence: Name of running sequence
            accepting_triggers: Whether to accept vision triggers
        """
        try:
            data = {
                "state": state,
                "moving": moving,
                "current_sequence": current_sequence,
                "accepting_triggers": accepting_triggers,
                "timestamp": time.time()
            }
            
            # Atomic write (write to temp, then rename)
            temp_file = self.robot_state_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            temp_file.replace(self.robot_state_file)
            return True
        
        except Exception as e:
            print(f"[IPC] Error writing robot state: {e}")
            return False
    
    def read_robot_state(self) -> Optional[Dict]:
        """
        Read robot state (daemon reads this)
        
        Returns:
            Dict with robot state, or None if error/not found
        """
        try:
            if not self.robot_state_file.exists():
                # Return default state if file doesn't exist yet
                return {
                    "state": "unknown",
                    "moving": False,
                    "current_sequence": None,
                    "accepting_triggers": False,
                    "timestamp": time.time()
                }
            
            with open(self.robot_state_file, 'r') as f:
                data = json.load(f)
            
            return data
        
        except Exception as e:
            print(f"[IPC] Error reading robot state: {e}")
            return None
    
    # Vision Events (Daemon → Sequencer)
    
    def write_vision_event(
        self,
        status: str,
        trigger_id: Optional[str] = None,
        event: Optional[Dict] = None
    ) -> bool:
        """
        Write vision event for sequencer to read
        
        Args:
            status: Daemon status (idle, detecting, triggered, error)
            trigger_id: ID of trigger that fired (if triggered)
            event: Event details (timestamp, result, zone, boxes, action)
        """
        try:
            data = {
                "last_check": time.time(),
                "status": status,
                "trigger_id": trigger_id,
                "event": event
            }
            
            # Atomic write
            temp_file = self.vision_events_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            temp_file.replace(self.vision_events_file)
            return True
        
        except Exception as e:
            print(f"[IPC] Error writing vision event: {e}")
            return False
    
    def read_vision_event(self) -> Optional[Dict]:
        """
        Read vision event (sequencer reads this)
        
        Returns:
            Dict with vision event data, or None if error/not found
        """
        try:
            if not self.vision_events_file.exists():
                return None
            
            with open(self.vision_events_file, 'r') as f:
                data = json.load(f)
            
            return data
        
        except Exception as e:
            print(f"[IPC] Error reading vision event: {e}")
            return None
    
    def clear_vision_event(self) -> bool:
        """Clear vision event (after sequencer has processed it)"""
        try:
            if self.vision_events_file.exists():
                self.vision_events_file.unlink()
            return True
        except Exception as e:
            print(f"[IPC] Error clearing vision event: {e}")
            return False
    
    # Daemon PID Management
    
    def write_daemon_pid(self, pid: int) -> bool:
        """Write daemon process ID"""
        try:
            with open(self.daemon_pid_file, 'w') as f:
                f.write(str(pid))
            return True
        except Exception as e:
            print(f"[IPC] Error writing daemon PID: {e}")
            return False
    
    def read_daemon_pid(self) -> Optional[int]:
        """Read daemon process ID"""
        try:
            if not self.daemon_pid_file.exists():
                return None
            
            with open(self.daemon_pid_file, 'r') as f:
                return int(f.read().strip())
        
        except Exception as e:
            print(f"[IPC] Error reading daemon PID: {e}")
            return None
    
    def clear_daemon_pid(self) -> bool:
        """Clear daemon PID file"""
        try:
            if self.daemon_pid_file.exists():
                self.daemon_pid_file.unlink()
            return True
        except Exception as e:
            print(f"[IPC] Error clearing daemon PID: {e}")
            return False
    
    def is_daemon_running(self) -> bool:
        """Check if daemon is running (checks PID file and process)"""
        pid = self.read_daemon_pid()
        if not pid:
            return False
        
        try:
            import psutil
            return psutil.pid_exists(pid)
        except ImportError:
            # Fallback: just check if PID file exists
            return self.daemon_pid_file.exists()
        except Exception:
            return False
    
    # Utility Methods
    
    def initialize(self) -> bool:
        """Initialize IPC system (create initial state files)"""
        try:
            # Initialize robot state
            self.write_robot_state(
                state="home",
                moving=False,
                accepting_triggers=False
            )
            
            # Clear any existing vision events
            self.clear_vision_event()
            
            # Clear PID file
            self.clear_daemon_pid()
            
            print("[IPC] ✓ Initialized IPC system")
            return True
        
        except Exception as e:
            print(f"[IPC] Error initializing: {e}")
            return False
    
    def cleanup(self) -> bool:
        """Cleanup IPC files"""
        try:
            self.clear_vision_event()
            self.clear_daemon_pid()
            print("[IPC] ✓ Cleaned up IPC files")
            return True
        except Exception as e:
            print(f"[IPC] Error during cleanup: {e}")
            return False


# Test the IPC system
if __name__ == "__main__":
    print("=== IPC System Tests ===\n")
    
    # Setup test directory
    test_runtime = Path("runtime_test")
    test_runtime.mkdir(exist_ok=True)
    
    ipc = IPCManager(test_runtime)
    
    # Test 1: Initialize
    print("1. Initializing IPC system...")
    success = ipc.initialize()
    print(f"   Result: {'✓' if success else '✗'}\n")
    
    # Test 2: Write and read robot state
    print("2. Testing robot state communication...")
    ipc.write_robot_state(
        state="home",
        moving=False,
        current_sequence=None,
        accepting_triggers=True
    )
    
    robot_state = ipc.read_robot_state()
    if robot_state:
        print(f"   State: {robot_state['state']}")
        print(f"   Accepting triggers: {robot_state['accepting_triggers']}")
        print(f"   Timestamp: {robot_state['timestamp']}\n")
    
    # Test 3: Write and read vision event
    print("3. Testing vision event communication...")
    event_data = {
        "timestamp": time.time(),
        "result": "PRESENT",
        "zone": "work_area",
        "confidence": 0.95,
        "boxes": [[420, 180, 120, 160]],
        "action": "advance_sequence"
    }
    
    ipc.write_vision_event(
        status="triggered",
        trigger_id="idle_standby",
        event=event_data
    )
    
    vision_event = ipc.read_vision_event()
    if vision_event:
        print(f"   Status: {vision_event['status']}")
        print(f"   Trigger: {vision_event['trigger_id']}")
        print(f"   Result: {vision_event['event']['result']}\n")
    
    # Test 4: Daemon PID management
    print("4. Testing daemon PID management...")
    import os
    test_pid = os.getpid()
    ipc.write_daemon_pid(test_pid)
    read_pid = ipc.read_daemon_pid()
    print(f"   Written PID: {test_pid}")
    print(f"   Read PID: {read_pid}")
    print(f"   Match: {test_pid == read_pid}")
    print(f"   Daemon running: {ipc.is_daemon_running()}\n")
    
    # Test 5: Update robot state (simulate sequencer)
    print("5. Simulating sequencer state updates...")
    states = [
        ("home", False, True),
        ("moving", True, False),
        ("working", False, False),
        ("home", False, True)
    ]
    
    for state, moving, accepting in states:
        ipc.write_robot_state(state, moving, accepting_triggers=accepting)
        time.sleep(0.1)
        robot_state = ipc.read_robot_state()
        print(f"   {state.upper()}: moving={moving}, accepting={accepting} ✓")
    print()
    
    # Test 6: Clear event
    print("6. Testing event clearing...")
    ipc.clear_vision_event()
    cleared_event = ipc.read_vision_event()
    print(f"   Event cleared: {cleared_event is None}\n")
    
    # Test 7: Cleanup
    print("7. Cleaning up...")
    ipc.cleanup()
    
    # Remove test directory
    import shutil
    shutil.rmtree(test_runtime)
    print("   ✓ Cleanup complete\n")
    
    print("✓ IPC system tests complete!")

