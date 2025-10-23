#!/usr/bin/env python3
"""
Test Vision Triggers System

Simple script to test vision daemon communication.
Shows how to integrate with your sequencer.
"""

import time
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from vision_triggers.ipc import IPCManager


def main():
    print("=" * 60)
    print("Vision Triggers Test")
    print("=" * 60)
    print()
    
    # Initialize IPC
    runtime_dir = Path("runtime")
    ipc = IPCManager(runtime_dir)
    
    # Check if daemon is running
    print("1. Checking daemon status...")
    if ipc.is_daemon_running():
        pid = ipc.read_daemon_pid()
        print(f"   ✓ Daemon is running (PID: {pid})")
    else:
        print("   ✗ Daemon is not running")
        print("   Run: python vision_triggers/daemon.py")
        return 1
    print()
    
    # Tell daemon we're ready to accept triggers
    print("2. Setting robot state to HOME...")
    ipc.write_robot_state(
        state="home",
        moving=False,
        current_sequence="test_sequence",
        accepting_triggers=True
    )
    print("   ✓ Robot state set to HOME")
    print("   ✓ Accepting triggers: TRUE")
    print()
    
    print("3. Monitoring for vision events...")
    print("   (Place an object in front of the camera)")
    print("   Press Ctrl+C to stop")
    print()
    
    try:
        check_count = 0
        while True:
            # Read vision event
            event = ipc.read_vision_event()
            
            if event:
                status = event.get('status', 'unknown')
                trigger_id = event.get('trigger_id')
                
                if status == 'triggered' and trigger_id:
                    print(f"\n   🎯 TRIGGER FIRED: {trigger_id}")
                    print(f"   Time: {time.strftime('%H:%M:%S')}")
                    
                    if 'event' in event and event['event']:
                        evt = event['event']
                        print(f"   Result: {evt.get('result', 'N/A')}")
                        print(f"   Reason: {evt.get('reason', 'N/A')}")
                        print(f"   Action: {evt.get('action', 'N/A')}")
                    
                    print("\n   In your sequencer, you would now:")
                    print("   - Advance to next step")
                    print("   - Start a specific sequence")
                    print("   - Or trigger an action")
                    print()
                    
                    # Clear the event so daemon continues
                    ipc.clear_vision_event()
                    
                elif status == 'detecting':
                    if check_count % 10 == 0:  # Print every 10 checks
                        print(f"   [{time.strftime('%H:%M:%S')}] Detecting... (no trigger yet)")
                    check_count += 1
                
                elif status == 'idle':
                    if check_count % 10 == 0:
                        print(f"   [{time.strftime('%H:%M:%S')}] Idle (robot not at home)")
                    check_count += 1
            
            time.sleep(0.5)  # Check twice per second
    
    except KeyboardInterrupt:
        print("\n\n4. Stopping...")
        # Set state to not accepting triggers
        ipc.write_robot_state(
            state="idle",
            moving=False,
            accepting_triggers=False
        )
        print("   ✓ Robot state set to IDLE")
        print()
        print("To stop daemon: kill $(cat runtime/vision_daemon.pid)")
        return 0


if __name__ == "__main__":
    sys.exit(main())


