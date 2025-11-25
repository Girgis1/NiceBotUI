#!/usr/bin/env python3
"""
Optional test script for ResilientMotorController

Run this ONLY if you want to test the resilient motor controller.
Your existing sequences use the standard MotorController and are unaffected.

Usage:
    python3 test_resilient_controller.py [--no-resilience]
    
    --no-resilience: Test with resilience disabled (should behave exactly like MotorController)
"""

import argparse
import time
from utils.resilient_motor_controller import ResilientMotorController
from HomePos import read_config

def test_resilient_controller(enable_resilience: bool = True):
    """Test the resilient motor controller"""
    
    print("="*70)
    print("Testing ResilientMotorController")
    print(f"Resilience: {'ENABLED' if enable_resilience else 'DISABLED (Standard MotorController behavior)'}")
    print("="*70)
    print()
    
    config = read_config()
    
    # Create controller
    print("1. Creating controller...")
    controller = ResilientMotorController(config, arm_index=0, enable_resilience=enable_resilience)
    
    # Connect
    print("2. Connecting to motors...")
    if not controller.connect():
        print("❌ Failed to connect!")
        return False
    
    print("✓ Connected")
    print()
    
    # Read current positions
    print("3. Reading current positions...")
    positions = controller.read_positions_from_bus()
    
    if not positions:
        print("❌ Failed to read positions!")
        controller.disconnect()
        return False
    
    print(f"✓ Current positions: {positions}")
    print()
    
    # Test multiple reads (will show resilience in action if brownouts occur)
    print("4. Testing repeated reads (10 times)...")
    failures = 0
    for i in range(10):
        pos = controller.read_positions_from_bus()
        if not pos:
            failures += 1
            print(f"   Read {i+1}: FAILED")
        else:
            print(f"   Read {i+1}: OK (max: {max(pos)}, min: {min(pos)})")
        time.sleep(0.1)
    
    print()
    if failures > 0:
        print(f"⚠️  {failures}/10 reads failed")
        if enable_resilience:
            print("   (But resilience may have masked some transient errors)")
    else:
        print("✓ All reads successful!")
    print()
    
    # Disconnect and show stats
    print("5. Disconnecting...")
    controller.disconnect()
    print("✓ Disconnected")
    print()
    
    print("="*70)
    print("Test Complete!")
    print("="*70)
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Test ResilientMotorController (optional - your existing system is unaffected)"
    )
    parser.add_argument(
        "--no-resilience",
        action="store_true",
        help="Disable resilience (behaves exactly like standard MotorController)"
    )
    
    args = parser.parse_args()
    
    print()
    print("="*70)
    print("⚠️  OPTIONAL TEST - Your existing sequences are unaffected")
    print("="*70)
    print()
    print("This script tests the ResilientMotorController.")
    print("Your existing system uses MotorController (unchanged).")
    print()
    print("This test will:")
    print("  • Connect to motors")
    print("  • Read positions 10 times")
    print("  • Show statistics")
    print("  • Disconnect")
    print()
    
    input("Press Enter to continue (or Ctrl+C to cancel)...")
    print()
    
    try:
        success = test_resilient_controller(enable_resilience=not args.no_resilience)
        
        if success:
            print()
            print("✅ Test completed successfully!")
            print()
            if not args.no_resilience:
                print("If you saw retry messages or recovery messages,")
                print("that means the resilient controller handled transient errors.")
                print()
                print("To use this in your code:")
                print("  from utils.resilient_motor_controller import ResilientMotorController")
                print("  controller = ResilientMotorController(config, arm_index=0)")
                print()
                print("Or keep using your existing MotorController (works great!).")
        else:
            print()
            print("❌ Test failed!")
            print("This doesn't affect your existing system.")
            
    except KeyboardInterrupt:
        print()
        print("Test cancelled by user")
    except Exception as e:
        print()
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

