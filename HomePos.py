#!/usr/bin/env python3
"""
Home control for SO-100/SO-101 robot.
Real Feetech motor control implementation.
"""

import argparse
import json
import os
import time
from pathlib import Path

try:
    from lerobot.motors.feetech import FeetechMotorsBus
    from lerobot.motors.motors_bus import Motor, MotorNormMode
    FEETECH_AVAILABLE = True
except ImportError:
    FEETECH_AVAILABLE = False
    print("Warning: Feetech library not available")


CONFIG_PATH = Path(__file__).parent / "config.json"

# SO-100/SO-101 motor configuration
MOTOR_NAMES = ['shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper']
MOTOR_MODEL = 'sts3215'  # Feetech STS3215 servos


def read_config():
    """Load configuration"""
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)


def write_config(cfg):
    """Save configuration"""
    with open(CONFIG_PATH, 'w') as f:
        json.dump(cfg, f, indent=2)


def create_motor_bus(port):
    """Create and connect to motor bus"""
    if not FEETECH_AVAILABLE:
        raise ImportError("Feetech library not installed. Run: pip install lerobot[feetech]")
    
    # Create motor configuration with proper Motor objects
    motors = {}
    for idx, name in enumerate(MOTOR_NAMES, start=1):
        motors[name] = Motor(
            id=idx,
            model=MOTOR_MODEL,
            norm_mode=MotorNormMode.DEGREES  # Use degree normalization
        )
    
    print(f"Connecting to motors on {port}...")
    bus = FeetechMotorsBus(
        port=port,
        motors=motors,
    )
    
    try:
        bus.connect()
        print(f"✓ Connected to {len(motors)} motors")
        return bus
    except Exception as e:
        print(f"✗ Failed to connect: {e}")
        raise


def emergency_catch_and_hold():
    """EMERGENCY: Catch arm at current position immediately after stop
    
    This opens connection, reads current position, enables torque, and sets
    goal position to current position to hold the arm exactly where it is.
    Must be called IMMEDIATELY after robot_client disconnects.
    """
    try:
        cfg = read_config()
        port = cfg["robot"]["port"]
        
        # Quick connection - no delays
        bus = create_motor_bus(port)
        
        # Read current positions FIRST
        current_positions = []
        for name in MOTOR_NAMES:
            pos = bus.read("Present_Position", name, normalize=False)
            current_positions.append(int(pos))
        
        # Enable torque on ALL motors
        for name in MOTOR_NAMES:
            bus.write("Torque_Enable", name, 1, normalize=False)
        
        # Set goal position to CURRENT position (holds arm exactly where it is)
        for idx, name in enumerate(MOTOR_NAMES):
            bus.write("Goal_Position", name, current_positions[idx], normalize=False)
        
        bus.disconnect()
        print(f"✓ Emergency catch complete - arm held at {current_positions}")
        return True, current_positions
    except Exception as e:
        print(f"✗ Failed to catch arm: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def go_to_rest(disable_torque=None):
    """Return robot Home
    
    Args:
        disable_torque: Override config setting - if None, uses config value.
                       Set to False to keep torque enabled (safety for emergency stops)
    """
    cfg = read_config()
    port = cfg["robot"]["port"]
    rest_config = cfg["rest_position"]
    positions = rest_config["positions"]
    velocity = rest_config.get("velocity", 1200)
    control_cfg = cfg.get("control", {})
    speed_multiplier = control_cfg.get("speed_multiplier", 1.0)
    env_multiplier = os.environ.get("LEROBOT_SPEED_MULTIPLIER")
    if env_multiplier:
        try:
            speed_multiplier = float(env_multiplier)
        except ValueError:
            pass
    if not 0.1 <= speed_multiplier <= 1.2:
        speed_multiplier = 1.0
    velocity = int(max(1, min(4000, velocity * speed_multiplier)))
    
    # Allow override of disable_torque setting (important for emergency stops)
    if disable_torque is None:
        disable_torque = rest_config.get("disable_torque_on_arrival", True)
    
    print(f"[HomePos] Returning Home:")
    print(f"  Port: {port}")
    print(f"  Positions: {positions}")
    print(f"  Velocity: {velocity} (scale {speed_multiplier:.2f}×)")
    
    try:
        # Connect to motors
        bus = create_motor_bus(port)
        
        # Enable torque on all motors first
        print("Enabling torque...")
        for name in MOTOR_NAMES:
            bus.write("Torque_Enable", name, 1, normalize=False)
        
        # Set speed for all motors (Goal_Velocity controls movement speed)
        # Goal_Velocity range: 0-4000, where higher = faster
        # Acceleration range: 0-255 (1 byte)
        acceleration = min(int(velocity / 4000 * 255), 255)  # Scale acceleration proportionally
        print(f"Setting velocity to {velocity}, acceleration to {acceleration}...")
        for name in MOTOR_NAMES:
            bus.write("Goal_Velocity", name, velocity, normalize=False)
            bus.write("Acceleration", name, acceleration, normalize=False)
        
        # Move to each position
        print("Returning Home...")
        for idx, name in enumerate(MOTOR_NAMES):
            bus.write("Goal_Position", name, positions[idx], normalize=False)
        
        # Wait for movement to complete
        # Estimate time based on max movement and velocity
        max_move = max(abs(positions[i] - 2048) for i in range(len(positions)))
        move_time = (max_move / velocity) * 2.0 if velocity > 0 else 5.0  # Rough estimate
        time.sleep(min(move_time, 10.0))  # Cap at 10 seconds
        
        print("✓ Home reached")
        
        # Disable torque if requested
        if disable_torque:
            print("Disabling motor torque...")
            for name in MOTOR_NAMES:
                bus.write("Torque_Enable", name, 0, normalize=False)
            print("✓ Torque disabled - motors are relaxed")
        
        # Disconnect
        bus.disconnect()
        print("✓ Move complete")
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def read_current_position():
    """Read current joint positions from robot"""
    cfg = read_config()
    port = cfg["robot"]["port"]
    
    print(f"[HomePos] Reading current position from {port}")
    
    try:
        # Connect to motors
        bus = create_motor_bus(port)
        
        # Read positions from each motor
        print("Reading positions...")
        position_list = []
        for name in MOTOR_NAMES:
            pos = bus.read("Present_Position", name, normalize=False)
            pos = int(pos)
            position_list.append(pos)
            print(f"  {name}: {pos}")
        
        # Disconnect
        bus.disconnect()
        
        return position_list
        
    except Exception as e:
        print(f"✗ Error reading positions: {e}")
        import traceback
        traceback.print_exc()
        return None


def save_current_as_home():
    """Read current position and save as home"""
    positions = read_current_position()
    if positions:
        cfg = read_config()
        cfg["rest_position"]["positions"] = positions
        write_config(cfg)
        print(f"\n✓ Saved current position as home: {positions}")
        return True
    return False


def check_robot_connection(port):
    """Check if robot is actually connected and responding
    
    Returns:
        "connected" - Motors responding
        "no_power" - Serial connected but motors not powered (check power!)
        "disconnected" - Serial port doesn't exist or can't open
    """
    import os
    from serial import SerialException
    
    # First check if port exists
    if not os.path.exists(port):
        return "disconnected"
    
    try:
        # Try to create motor bus and read from first motor
        bus = create_motor_bus(port)
        
        # Try to read position from first motor with timeout
        try:
            position = bus.read("Present_Position", MOTOR_NAMES[0], normalize=False)
            bus.disconnect()
            return "connected"  # Motors responding!
            
        except TimeoutError:
            # Serial connected but motor not responding (likely no power)
            try:
                bus.disconnect()
            except:
                pass
            return "no_power"
        except Exception as e:
            # Motor read failed for other reasons
            try:
                bus.disconnect()
            except:
                pass
            error_str = str(e).lower()
            
            # Check for "Missing motor IDs" error - means all 6 motors not found = no power
            if "missing motor" in error_str or "full found motor list" in error_str:
                return "no_power"
            if "torque" in error_str or "timeout" in error_str:
                return "no_power"
            return "disconnected"
            
    except SerialException:
        # Can't open serial port
        return "disconnected"
    except Exception as e:
        # Other connection errors - check if it's the "all motors missing" error
        error_str = str(e).lower()
        if "missing motor" in error_str or "{}" in str(e):  # Empty motor list
            print(f"Connection check error: {e}")
            return "no_power"  # Serial OK, but all motors missing = check power
        print(f"Connection check error: {e}")
        return "disconnected"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SO-100/SO-101 Home Control")
    parser.add_argument('--go', action='store_true', help='Return Home')
    parser.add_argument('--read', action='store_true', help='Read current position')
    parser.add_argument('--save', action='store_true', help='Save current position as home')
    parser.add_argument('--test', action='store_true', help='Test connection')
    parser.add_argument('--keep-torque', action='store_true', help='Keep torque enabled after reaching home (safety feature)')
    parser.add_argument('--emergency-catch', action='store_true', help='EMERGENCY: Catch and hold arm at current position')
    
    args = parser.parse_args()
    
    if args.emergency_catch:
        # CRITICAL SAFETY: Catch arm at current position, hold it there
        success, positions = emergency_catch_and_hold()
        exit(0 if success else 1)
    elif args.go:
        # If --keep-torque is set, disable_torque=False (keep it on)
        success = go_to_rest(disable_torque=(not args.keep_torque))
        exit(0 if success else 1)
    elif args.read:
        positions = read_current_position()
        if positions:
            print(f"\nCurrent positions: {positions}")
            exit(0)
        exit(1)
    elif args.save:
        success = save_current_as_home()
        exit(0 if success else 1)
    elif args.test:
        cfg = read_config()
        try:
            bus = create_motor_bus(cfg["robot"]["port"])
            print("✓ Connection test successful")
            bus.disconnect()
            exit(0)
        except Exception as e:
            print(f"✗ Connection test failed: {e}")
            exit(1)
    else:
        parser.print_help()
