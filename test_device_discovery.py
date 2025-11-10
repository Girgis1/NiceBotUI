#!/usr/bin/env python3
"""
Test Device Discovery System
Quick test to verify device discovery works without GUI
"""

import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.device_manager import DeviceManager

def main():
    """Test device discovery"""
    print("\n" + "="*70)
    print("DEVICE DISCOVERY TEST")
    print("="*70)
    
    # Load config
    config_path = Path(__file__).parent / "config.json"
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    # Create device manager
    device_manager = DeviceManager(config)
    
    # Run discovery
    results = device_manager.discover_all_devices()
    
    # Print summary
    print("\n" + "="*70)
    print("DISCOVERY RESULTS SUMMARY")
    print("="*70)
    print(f"\nRobot Status: {device_manager.robot_status}")
    if device_manager.camera_statuses:
        for name, status in device_manager.camera_statuses.items():
            print(f"{name.title()} Camera Status: {status}")
    else:
        print("No cameras configured in the current profile.")
    
    if results["errors"]:
        print(f"\nErrors: {len(results['errors'])}")
        for err in results["errors"]:
            print(f"  - {err}")
    
    print("\n" + "="*70 + "\n")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

