#!/usr/bin/env python3
"""
Quick Mode Switcher for Solo/Bimanual Configuration

Usage:
    python switch_mode.py solo       # Switch to solo mode
    python switch_mode.py bimanual   # Switch to bimanual mode
    python switch_mode.py status     # Show current mode
"""

import json
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config():
    """Load config.json"""
    if not CONFIG_PATH.exists():
        print(f"❌ Config file not found: {CONFIG_PATH}")
        sys.exit(1)
    
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)


def save_config(config):
    """Save config.json"""
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)


def show_status(config):
    """Display current mode configuration"""
    robot_mode = config.get("robot", {}).get("mode", "solo")
    teleop_mode = config.get("teleop", {}).get("mode", "solo")
    
    robot_arms = config.get("robot", {}).get("arms", [])
    teleop_arms = config.get("teleop", {}).get("arms", [])
    
    robot_enabled = sum(1 for arm in robot_arms if arm.get("enabled", False))
    teleop_enabled = sum(1 for arm in teleop_arms if arm.get("enabled", False))
    
    print("\n📊 Current Configuration:")
    print("=" * 50)
    print(f"🤖 Robot Mode:  {robot_mode.upper()}")
    print(f"   Enabled Arms: {robot_enabled}/{len(robot_arms)}")
    
    if robot_mode == "bimanual":
        if robot_enabled >= 2:
            print("   ✅ Bimanual ready (2+ arms enabled)")
        else:
            print("   ⚠️  Bimanual requires 2 enabled arms!")
    
    print(f"\n🎮 Teleop Mode: {teleop_mode.upper()}")
    print(f"   Enabled Arms: {teleop_enabled}/{len(teleop_arms)}")
    
    if teleop_mode == "bimanual":
        if teleop_enabled >= 2:
            print("   ✅ Bimanual ready (2+ arms enabled)")
        else:
            print("   ⚠️  Bimanual requires 2 enabled arms!")
    
    print("=" * 50)


def switch_to_solo(config):
    """Switch to solo mode"""
    print("\n🔄 Switching to SOLO mode...")
    
    # Set robot mode
    if "robot" in config:
        config["robot"]["mode"] = "solo"
        # Disable second arm if present
        arms = config["robot"].get("arms", [])
        if len(arms) >= 2:
            arms[1]["enabled"] = False
        print("   ✅ Robot set to solo (Arm 1 only)")
    
    # Set teleop mode
    if "teleop" in config:
        config["teleop"]["mode"] = "solo"
        # Disable second teleop arm if present
        arms = config["teleop"].get("arms", [])
        if len(arms) >= 2:
            arms[1]["enabled"] = False
        print("   ✅ Teleop set to solo (Leader 1 only)")
    
    save_config(config)
    print("\n✅ Switched to SOLO mode!")
    print("   👤 Actions will be recorded as solo")
    print("   Policy playback uses so100_follower\n")


def switch_to_bimanual(config):
    """Switch to bimanual mode with validation"""
    print("\n🔄 Switching to BIMANUAL mode...")
    
    # Validate robot arms exist
    robot_arms = config.get("robot", {}).get("arms", [])
    if len(robot_arms) < 2:
        print("   ❌ Error: Config needs 2 robot arms!")
        print("   Add a second arm in Settings first.")
        sys.exit(1)
    
    # Set robot mode
    config["robot"]["mode"] = "bimanual"
    
    # Enable both arms
    robot_arms[0]["enabled"] = True
    robot_arms[1]["enabled"] = True
    
    print(f"   ✅ Robot set to bimanual")
    print(f"      Left arm:  {robot_arms[0].get('port', 'N/A')}")
    print(f"      Right arm: {robot_arms[1].get('port', 'N/A')}")
    
    # Set teleop mode if arms exist
    if "teleop" in config:
        teleop_arms = config["teleop"].get("arms", [])
        config["teleop"]["mode"] = "bimanual"
        
        if len(teleop_arms) >= 2:
            teleop_arms[0]["enabled"] = True
            teleop_arms[1]["enabled"] = True
            print(f"   ✅ Teleop set to bimanual")
            print(f"      Left leader:  {teleop_arms[0].get('port', 'N/A')}")
            print(f"      Right leader: {teleop_arms[1].get('port', 'N/A')}")
        else:
            print("   ⚠️  Warning: Only 1 teleop arm configured")
            print("      Add second leader arm for bimanual teleop")
    
    save_config(config)
    print("\n✅ Switched to BIMANUAL mode!")
    print("   👥 Actions will be recorded as bimanual")
    print("   Policy playback uses bi_so100_follower")
    print("\n⚠️  Make sure both arms are physically connected!\n")


def main():
    """Main CLI entry point"""
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1].lower()
    config = load_config()
    
    if command == "status":
        show_status(config)
    
    elif command == "solo":
        switch_to_solo(config)
        show_status(config)
    
    elif command == "bimanual":
        switch_to_bimanual(config)
        show_status(config)
    
    else:
        print(f"❌ Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()

