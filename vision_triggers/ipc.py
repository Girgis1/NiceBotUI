"""IPC helpers for sharing state between the sequencer and vision daemon."""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Optional

from utils.logging_utils import log_exception
from .time_utils import get_timezone, now_iso

if os.name == "posix":  # pragma: no cover - platform dependent
    import fcntl  # type: ignore
else:  # pragma: no cover - platform dependent
    fcntl = None


class IPCManager:
    """Manage IPC state files for vision daemon communication"""

    def __init__(self, runtime_dir: Path, timezone_name: Optional[str] = None):
        self.runtime_dir = runtime_dir
        self.robot_state_file = runtime_dir / "robot_state.json"
        self.vision_events_file = runtime_dir / "vision_events.json"
        self.daemon_pid_file = runtime_dir / "vision_daemon.pid"
        self.timezone = get_timezone(timezone_name)
        
        # Ensure runtime directory exists
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self._use_fcntl = os.name == "posix"
    
    # ------------------------------------------------------------------
    # Internal helpers

    @contextmanager
    def _lock(self, name: str, exclusive: bool):
        if not self._use_fcntl or fcntl is None:
            yield None
            return
        lock_path = self.runtime_dir / f"{name}.lock"
        lock_file = open(lock_path, "w")
        flag = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        fcntl.flock(lock_file.fileno(), flag)
        try:
            yield lock_file
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()

    def _temp_path(self, target: Path) -> Path:
        return target.with_name(f".{target.name}.tmp")

    def _write_json_atomic(self, target: Path, data: Dict, lock_name: str) -> bool:
        temp_path = self._temp_path(target)
        try:
            with self._lock(lock_name, exclusive=True):
                with open(temp_path, "w") as handle:
                    json.dump(data, handle, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, target)
            return True
        except Exception as exc:
            log_exception(f"IPC: failed to write {target.name}", exc)
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass
            return False

    def _read_json(self, source: Path, lock_name: str) -> Optional[Dict]:
        try:
            with self._lock(lock_name, exclusive=False):
                if not source.exists():
                    return None
                with open(source, "r") as handle:
                    return json.load(handle)
        except Exception as exc:
            log_exception(f"IPC: failed to read {source.name}", exc)
            return None

    def _write_text_atomic(self, target: Path, text: str, lock_name: str) -> bool:
        temp_path = self._temp_path(target)
        try:
            with self._lock(lock_name, exclusive=True):
                with open(temp_path, "w") as handle:
                    handle.write(text)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, target)
            return True
        except Exception as exc:
            log_exception(f"IPC: failed to write text {target.name}", exc)
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass
            return False

    def _read_text(self, source: Path, lock_name: str) -> Optional[str]:
        try:
            with self._lock(lock_name, exclusive=False):
                if not source.exists():
                    return None
                with open(source, "r") as handle:
                    return handle.read().strip()
        except Exception as exc:
            log_exception(f"IPC: failed to read text {source.name}", exc)
            return None

    def _clear_file(self, path: Path, lock_name: str) -> bool:
        try:
            with self._lock(lock_name, exclusive=True):
                if path.exists():
                    path.unlink()
            return True
        except Exception as exc:
            log_exception(f"IPC: failed to clear {path.name}", exc)
            return False
    
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
        data = {
            "state": state,
            "moving": moving,
            "current_sequence": current_sequence,
            "accepting_triggers": accepting_triggers,
            "timestamp": time.time(),
            "timestamp_iso": now_iso(self.timezone),
        }
        return self._write_json_atomic(self.robot_state_file, data, "robot_state")
    
    def read_robot_state(self) -> Optional[Dict]:
        """
        Read robot state (daemon reads this)
        
        Returns:
            Dict with robot state, or None if error/not found
        """
        data = self._read_json(self.robot_state_file, "robot_state")
        if data is None and not self.robot_state_file.exists():
            return {
                "state": "unknown",
                "moving": False,
                "current_sequence": None,
                "accepting_triggers": False,
                "timestamp": time.time(),
                "timestamp_iso": now_iso(self.timezone),
            }
        return data
    
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
        data = {
            "last_check": time.time(),
            "last_check_iso": now_iso(self.timezone),
            "status": status,
            "trigger_id": trigger_id,
            "event": event,
        }
        return self._write_json_atomic(self.vision_events_file, data, "vision_events")
    
    def read_vision_event(self) -> Optional[Dict]:
        """
        Read vision event (sequencer reads this)
        
        Returns:
            Dict with vision event data, or None if error/not found
        """
        return self._read_json(self.vision_events_file, "vision_events")
    
    def clear_vision_event(self) -> bool:
        """Clear vision event (after sequencer has processed it)"""
        return self._clear_file(self.vision_events_file, "vision_events")
    
    # Daemon PID Management
    
    def write_daemon_pid(self, pid: int) -> bool:
        """Write daemon process ID"""
        return self._write_text_atomic(self.daemon_pid_file, str(pid), "daemon_pid")
    
    def read_daemon_pid(self) -> Optional[int]:
        """Read daemon process ID"""
        text = self._read_text(self.daemon_pid_file, "daemon_pid")
        if not text:
            return None
        try:
            return int(text)
        except ValueError as exc:
            log_exception("IPC: daemon PID file corrupt", exc)
            return None
    
    def clear_daemon_pid(self) -> bool:
        """Clear daemon PID file"""
        return self._clear_file(self.daemon_pid_file, "daemon_pid")
    
    def is_daemon_running(self) -> bool:
        """Check if daemon is running (checks PID file and process)"""
        pid = self.read_daemon_pid()
        if not pid:
            return False
        
        try:
            import psutil
            return psutil.pid_exists(pid)
        except ImportError:
            return self.daemon_pid_file.exists()
        except Exception as exc:
            log_exception("IPC: daemon running check failed", exc, level="warning")
            return False
    
    # Utility Methods
    
    def initialize(self) -> bool:
        """Initialize IPC system (create initial state files)"""
        try:
            self.write_robot_state(
                state="home",
                moving=False,
                accepting_triggers=False,
            )
            self.clear_vision_event()
            self.clear_daemon_pid()
            print("[IPC] ✓ Initialized IPC system")
            return True
        except Exception as exc:
            log_exception("IPC: initialization failed", exc)
            return False
    
    def cleanup(self) -> bool:
        """Cleanup IPC files"""
        try:
            self.clear_vision_event()
            self.clear_daemon_pid()
            print("[IPC] ✓ Cleaned up IPC files")
            return True
        except Exception as exc:
            log_exception("IPC: cleanup failed", exc)
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
