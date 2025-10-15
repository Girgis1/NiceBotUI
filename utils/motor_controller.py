"""
Motor Controller - Unified interface for motor operations
"""

import time
from pathlib import Path
import sys

# Add parent directory to path to import rest_pos
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from rest_pos import read_current_position, create_motor_bus, MOTOR_NAMES, read_config
    MOTOR_CONTROL_AVAILABLE = True
except ImportError:
    MOTOR_CONTROL_AVAILABLE = False
    print("Warning: Motor control not available")


class MotorController:
    """Unified motor control interface for action recording and playback"""
    
    def __init__(self, config: dict = None):
        """
        Args:
            config: Robot configuration dict (from config.json)
        """
        if config is None:
            config = read_config()
        
        self.config = config
        self.port = config["robot"]["port"]
        self.motor_names = MOTOR_NAMES
        self.bus = None
    
    def read_positions(self) -> list[int]:
        """Read current motor positions
        
        Returns:
            List of 6 motor positions [shoulder_pan, shoulder_lift, ...]
        """
        if not MOTOR_CONTROL_AVAILABLE:
            raise RuntimeError("Motor control not available")
        
        try:
            positions = read_current_position()
            return positions if positions else []
        except Exception as e:
            print(f"Error reading positions: {e}")
            return []
    
    def connect(self):
        """Connect to motor bus"""
        if not MOTOR_CONTROL_AVAILABLE:
            raise RuntimeError("Motor control not available")
        
        try:
            self.bus = create_motor_bus(self.port)
            return True
        except Exception as e:
            print(f"Error connecting to motors: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from motor bus"""
        if self.bus:
            try:
                self.bus.disconnect()
            except:
                pass
            self.bus = None
    
    def set_positions(self, positions: list[int], velocity: int = 600, wait: bool = True, keep_connection: bool = False):
        """Set motor positions with velocity
        
        Args:
            positions: List of 6 motor positions
            velocity: Movement velocity (0-4000)
            wait: If True, wait for movement to complete
            keep_connection: If True, keep bus connected (for smooth sequences)
        """
        if not MOTOR_CONTROL_AVAILABLE:
            raise RuntimeError("Motor control not available")
        
        if len(positions) != 6:
            raise ValueError(f"Expected 6 positions, got {len(positions)}")
        
        connected_locally = False
        if not self.bus:
            if not self.connect():
                raise RuntimeError("Failed to connect to motors")
            connected_locally = True
        
        try:
            # Enable torque (always keep on for smooth sequences)
            for name in self.motor_names:
                self.bus.write("Torque_Enable", name, 1, normalize=False)
            
            # Set velocity and acceleration
            acceleration = min(int(velocity / 4000 * 255), 255)
            for name in self.motor_names:
                self.bus.write("Goal_Velocity", name, velocity, normalize=False)
                self.bus.write("Acceleration", name, acceleration, normalize=False)
            
            # Set goal positions
            for idx, name in enumerate(self.motor_names):
                self.bus.write("Goal_Position", name, positions[idx], normalize=False)
            
            # Wait for movement if requested
            if wait:
                # Estimate time based on max movement and velocity
                max_move = 500  # Conservative estimate
                move_time = (max_move / velocity) * 2.0 if velocity > 0 else 2.0
                time.sleep(min(move_time, 5.0))  # Cap at 5 seconds
            
        finally:
            # Only disconnect if we connected locally AND not keeping connection
            if connected_locally and not keep_connection:
                self.disconnect()
    
    def move_to_position(self, positions: list[int], velocity: int = 600, wait: bool = True, keep_connection: bool = False):
        """Alias for set_positions (more descriptive name)"""
        self.set_positions(positions, velocity, wait, keep_connection)
    
    def emergency_stop(self):
        """Emergency stop - disable all motor torque"""
        if not self.bus:
            return
        
        try:
            for name in self.motor_names:
                self.bus.write("Torque_Enable", name, 0, normalize=False)
        except:
            pass

