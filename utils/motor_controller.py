"""
Motor Controller - Unified interface for motor operations with position verification
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
    """Unified motor control interface for action recording and playback with position feedback"""
    
    # Position verification settings
    POSITION_TOLERANCE = 10  # Units - motors must be within this range of target
    POLL_INTERVAL = 0.05  # Seconds - how often to check position during verification
    POSITION_STABLE_TIME = 0.1  # Seconds - position must be stable for this long
    
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
        
        # Load position tolerance from config if available
        if "position_tolerance" in config.get("robot", {}):
            self.POSITION_TOLERANCE = config["robot"]["position_tolerance"]
    
    def read_positions(self) -> list[int]:
        """Read current motor positions

        Returns:
            List of 6 motor positions [shoulder_pan, shoulder_lift, ...]
        """
        if not MOTOR_CONTROL_AVAILABLE:
            raise RuntimeError("Motor control not available")

        if self.bus:
            positions = self.read_positions_from_bus()
            return positions if positions else []

        try:
            positions = read_current_position(verbose=False)
            return positions if positions else []
        except Exception as e:
            print(f"Error reading positions: {e}")
            return []
    
    def read_positions_from_bus(self) -> list[int]:
        """Read positions from active bus connection (faster for verification loops)
        
        Returns:
            List of 6 motor positions, or empty list on error
        """
        if not self.bus:
            return []
        
        try:
            positions = []
            for name in self.motor_names:
                pos = self.bus.read("Present_Position", name, normalize=False)
                positions.append(int(pos))
            return positions
        except Exception as e:
            print(f"[MOTOR] Error reading positions from bus: {e}")
            return []
    
    def verify_position_reached(self, target_positions: list[int], timeout: float = 5.0) -> tuple[bool, list[int]]:
        """Verify motors reached target positions using position feedback
        
        Args:
            target_positions: List of 6 target positions
            timeout: Maximum time to wait for position (seconds)
        
        Returns:
            (success, final_positions) - True if all motors within tolerance
        """
        if not self.bus:
            print("[MOTOR] ⚠️ Cannot verify - no bus connection")
            return False, []
        
        start_time = time.time()
        stable_since = None
        last_positions = None
        
        print(f"[MOTOR] 🎯 Verifying position (tolerance: ±{self.POSITION_TOLERANCE} units)")
        
        while (time.time() - start_time) < timeout:
            current_positions = self.read_positions_from_bus()
            
            if not current_positions:
                time.sleep(self.POLL_INTERVAL)
                continue
            
            # Check if all motors within tolerance
            errors = [abs(current_positions[i] - target_positions[i]) for i in range(6)]
            max_error = max(errors)
            all_in_tolerance = max_error <= self.POSITION_TOLERANCE
            
            # Check if position has stabilized (not changing)
            if last_positions:
                position_changed = any(abs(current_positions[i] - last_positions[i]) > 2 for i in range(6))
                
                if all_in_tolerance:
                    if not position_changed:
                        # Position is good and stable
                        if stable_since is None:
                            stable_since = time.time()
                        elif (time.time() - stable_since) >= self.POSITION_STABLE_TIME:
                            elapsed = time.time() - start_time
                            print(f"[MOTOR] ✓ Position reached in {elapsed:.2f}s (max error: {max_error} units)")
                            return True, current_positions
                    else:
                        # Still moving
                        stable_since = None
                else:
                    # Not in tolerance yet
                    stable_since = None
            
            last_positions = current_positions
            time.sleep(self.POLL_INTERVAL)
        
        # Timeout reached
        final_positions = self.read_positions_from_bus()
        if final_positions:
            errors = [abs(final_positions[i] - target_positions[i]) for i in range(6)]
            max_error = max(errors)
            print(f"[MOTOR] ⚠️ Position verification timeout ({timeout}s)")
            print(f"[MOTOR]    Max error: {max_error} units (tolerance: {self.POSITION_TOLERANCE})")
            print(f"[MOTOR]    Target:  {target_positions}")
            print(f"[MOTOR]    Current: {final_positions}")
            print(f"[MOTOR]    Errors:  {errors}")
            return False, final_positions
        
        return False, []
    
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
        """Set motor positions with velocity and position verification (Option D - Hybrid Approach)
        
        Args:
            positions: List of 6 motor positions
            velocity: Movement velocity (0-4000)
            wait: If True, wait for movement to complete with verification
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
            # Read current positions to calculate actual move distance
            current_positions = self.read_positions_from_bus()
            
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
                # OPTION D - HYBRID APPROACH:
                # 1. Calculate actual distance needed
                if current_positions:
                    distances = [abs(positions[i] - current_positions[i]) for i in range(6)]
                    max_distance = max(distances) if distances else 500
                    print(f"[MOTOR] 📏 Move distance: {max_distance} units (max across all motors)")
                else:
                    max_distance = 500  # Fallback if can't read current position
                    print(f"[MOTOR] ⚠️ Couldn't read current position, using estimate")
                
                # 2. Calculate movement time with proper acceleration consideration
                # For STS3215: position units are 0-4095, velocity in units/sec
                # Time = distance / velocity, but add acceleration time
                if velocity > 0:
                    base_time = max_distance / velocity
                    # Add acceleration phase (rough estimate: 0.3-0.5s for acc + dec)
                    accel_time = 0.4 * (1.0 - acceleration / 255.0)  # Lower accel = more time
                    total_time = base_time + accel_time
                else:
                    total_time = 3.0  # Fallback
                
                # 3. Wait for 80% of estimated time (let most of move complete)
                wait_time = total_time * 0.8
                print(f"[MOTOR] ⏱️ Estimated move time: {total_time:.2f}s, waiting {wait_time:.2f}s before verification")
                time.sleep(wait_time)
                
                # 4. Poll position feedback until stable or timeout
                verification_timeout = max(2.0, total_time * 0.5)  # At least 2s for verification
                success, final_positions = self.verify_position_reached(positions, timeout=verification_timeout)
                
                if not success:
                    print(f"[MOTOR] ⚠️ Position verification failed - motors may not have reached target")
                    # Don't raise error, just warn - sometimes acceptable in loose control
            
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

