"""
Motor Controller - Unified interface for motor operations with position verification
"""

import time
from pathlib import Path
import sys
import logging

# Add parent directory to path to import rest_pos
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from rest_pos import read_current_position, create_motor_bus, MOTOR_NAMES, read_config
    MOTOR_CONTROL_AVAILABLE = True
except ImportError:
    MOTOR_CONTROL_AVAILABLE = False
    print("Warning: Motor control not available")

# Try to import LeRobot IK components
try:
    from lerobot.model.kinematics import RobotKinematics
    from lerobot.robots.so100_follower.robot_kinematic_processor import InverseKinematicsEEToJoints
    from lerobot.processor import RobotAction, RobotObservation
    LEROBOT_IK_AVAILABLE = True
except ImportError:
    LEROBOT_IK_AVAILABLE = False
    logging.warning("LeRobot IK not available - using direct joint control")


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
        
        # Initialize IK solver if available
        self.ik_solver = None
        self.ik_processor = None
        self.ee_reference = None  # Current end-effector reference position
        
        if LEROBOT_IK_AVAILABLE:
            self._init_ik_solver()
    
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
    
    def _init_ik_solver(self):
        """Initialize IK solver using LeRobot's kinematics"""
        try:
            # Check for URDF file path in config
            urdf_path = self.config.get("urdf_path")
            
            if not urdf_path:
                # Default URDF path (user needs to download it)
                urdf_path = Path(__file__).parent.parent / "SO101" / "so101_new_calib.urdf"
                
            if not Path(urdf_path).exists():
                logging.warning(
                    f"URDF file not found at {urdf_path}. "
                    "Download from: https://github.com/TheRobotStudio/SO-ARM100/blob/main/Simulation/SO101/so101_new_calib.urdf"
                )
                return
            
            # Initialize kinematics solver
            self.ik_solver = RobotKinematics(
                urdf_path=str(urdf_path),
                target_frame_name="gripper_frame_link",
                joint_names=self.motor_names
            )
            
            # Initialize IK processor
            self.ik_processor = InverseKinematicsEEToJoints(
                kinematics=self.ik_solver,
                motor_names=self.motor_names,
                initial_guess_current_joints=True  # Use current joint state as IK starting point
            )
            
            logging.info("✓ IK solver initialized successfully")
            print("[MOTOR] ✓ IK solver initialized - using proper end-effector control")
            
        except Exception as e:
            logging.error(f"Failed to initialize IK solver: {e}")
            self.ik_solver = None
            self.ik_processor = None
    
    def set_torque_enable(self, enable: bool):
        """
        Enable or disable torque for all motors.
        Used by touch teleop panel for manual positioning mode.
        
        Args:
            enable: True to turn torque ON (hold position)
                   False to turn torque OFF (limp/free movement)
        """
        if not MOTOR_CONTROL_AVAILABLE:
            raise RuntimeError("Motor control not available")
        
        connected_locally = False
        if not self.bus:
            if not self.connect():
                raise RuntimeError("Failed to connect to motors")
            connected_locally = True
        
        try:
            for name in self.motor_names:
                self.bus.write("Torque_Enable", name, int(enable), normalize=False)
            
        except Exception as e:
            print(f"[MOTOR] Error setting torque: {e}")
            raise
        finally:
            if connected_locally:
                self.disconnect()
    
    def get_torque_status(self) -> dict:
        """Get torque enable status for all motors"""
        if not self.bus:
            return {}
        
        status = {}
        try:
            for name in self.motor_names:
                status[name] = bool(self.bus.read("Torque_Enable", name, normalize=False))
        except Exception as e:
            print(f"[MOTOR] Error reading torque status: {e}")
        return status
    
    def get_current_position(self) -> dict:
        """
        Get current end-effector position in Cartesian coordinates.
        
        Returns:
            dict with keys 'x', 'y', 'z' (in meters) or empty dict on error
        """
        try:
            # Read joint positions
            joint_positions = self.read_positions()
            if not joint_positions or len(joint_positions) != 6:
                return {}
            
            # TODO: Implement forward kinematics to convert joint angles to X/Y/Z
            # For now, return joint positions as placeholder
            # This should be replaced with proper FK using robot URDF/DH parameters
            
            # Placeholder: Use first 3 joint positions scaled to mm
            # In production, this needs proper FK calculation
            x = joint_positions[0] / 4095.0 * 100.0  # Scale to ~100mm range
            y = joint_positions[1] / 4095.0 * 100.0
            z = joint_positions[2] / 4095.0 * 100.0
            
            return {
                'x': x,
                'y': y,
                'z': z,
                '_raw_joints': joint_positions  # Include raw data for debugging
            }
            
        except Exception as e:
            print(f"[MOTOR] Error getting position: {e}")
            return {}
    
    def move_joint_delta(self, joint_index: int, delta_steps: int, velocity: int = 400):
        """
        Move a specific joint by delta motor steps (direct joint control).
        This is the simplest, most reliable control method matching HIL-SERL keyboard teleop.
        
        Args:
            joint_index: Joint number (0-5)
            delta_steps: Motor steps to move (positive or negative, typically 5-100)
            velocity: Movement velocity (0-4000)
        """
        if not MOTOR_CONTROL_AVAILABLE:
            raise RuntimeError("Motor control not available")
        
        if not 0 <= joint_index < 6:
            raise ValueError(f"Invalid joint index {joint_index}, must be 0-5")
        
        try:
            # Read current joint positions
            current_joints = self.read_positions()
            if not current_joints or len(current_joints) != 6:
                raise RuntimeError("Failed to read current position")
            
            # Calculate target position for this joint
            target_joints = current_joints.copy()
            target_joints[joint_index] += delta_steps
            
            # Clamp to valid range [0, 4095]
            target_joints[joint_index] = max(0, min(4095, target_joints[joint_index]))
            
            # Silently move joint (no terminal spam)
            pass
            
            # Move to target position
            self.set_positions(target_joints, velocity=velocity, wait=False, keep_connection=True)
            
        except Exception as e:
            logging.error(f"[MOTOR] Error moving joint {joint_index}: {e}")
            raise
    
    def move_wrist_roll(self, delta_steps: int, velocity: int = 400):
        """
        Move wrist roll joint (Joint 5) by delta steps.
        Convenience method for teleop panel.
        """
        self.move_joint_delta(4, delta_steps, velocity)  # Joint 4 = wrist roll
    
    def set_gripper(self, action: int, velocity: int = 400):
        """
        Control gripper state.
        
        Args:
            action: 0 = close, 1 = hold, 2 = open
            velocity: Movement velocity (0-4000)
        """
        # Use move_joint_delta for gripper control
        # Gripper is joint 5 (last motor)
        
        # Map action to position
        # Adjust these values based on your gripper's actual range
        gripper_positions = {
            0: 1024,   # Closed
            1: 2048,   # Hold/neutral
            2: 3072    # Open
        }
        
        target_position = gripper_positions.get(action, 2048)
        
        try:
            # Read current positions
            current_joints = self.read_positions()
            if not current_joints or len(current_joints) != 6:
                raise RuntimeError("Failed to read current position")
            
            # Set gripper to target position
            target_joints = current_joints.copy()
            target_joints[5] = target_position  # Joint 5 = gripper
            
            self.set_positions(target_joints, velocity=velocity, wait=False, keep_connection=True)
            
        except Exception as e:
            logging.error(f"[MOTOR] Error controlling gripper: {e}")
            raise
    
    def go_to_home(self):
        """Move to configured home/rest position"""
        if not MOTOR_CONTROL_AVAILABLE:
            raise RuntimeError("Motor control not available")
        
        # Get home position from config
        home_position = self.config.get("rest_position")
        if not home_position:
            raise RuntimeError("No home position configured")
        
        print(f"[MOTOR] Moving to home position")
        self.set_positions(home_position, velocity=600, wait=True)

