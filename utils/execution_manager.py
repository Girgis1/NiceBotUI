"""
Execution Manager - Unified execution system for recordings, sequences, and models

ROBUST DESIGN:
- Single entry point for all execution types
- Proper error handling and recovery
- Real-time progress feedback
- Emergency stop support
"""

import time
import sys
import threading
import subprocess
from pathlib import Path
from typing import Optional, Dict, List
from PySide6.QtCore import QThread, Signal

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.motor_controller import MotorController
from utils.actions_manager import ActionsManager
from utils.sequences_manager import SequencesManager


class ExecutionWorker(QThread):
    """Worker thread for executing recordings, sequences, or models"""
    
    # Signals for UI updates
    status_update = Signal(str)           # Current action/status text
    log_message = Signal(str, str)        # (level, message) - 'info', 'warning', 'error'
    progress_update = Signal(int, int)    # (current_step, total_steps)
    execution_completed = Signal(bool, str)  # (success, summary_message)
    
    def __init__(self, config: dict, execution_type: str, execution_name: str, execution_data: dict = None):
        """
        Args:
            config: Robot configuration
            execution_type: "recording", "sequence", or "model"
            execution_name: Name of the item to execute
            execution_data: Optional data (for models: checkpoint path, duration, etc.)
        """
        super().__init__()
        self.config = config
        self.execution_type = execution_type
        self.execution_name = execution_name
        self.execution_data = execution_data or {}
        self.options = execution_data or {}  # Alias for compatibility
        self._stop_requested = False
        
        # Managers
        self.actions_mgr = ActionsManager()
        self.sequences_mgr = SequencesManager()
        self.motor_controller = MotorController(config)
    
    def run(self):
        """Main execution thread
        
        Handles: recordings, sequences, and models (in local mode)
        """
        self._stop_requested = False
        
        try:
            if self.execution_type == "recording":
                self._execute_recording()
            elif self.execution_type == "sequence":
                self._execute_sequence()
            elif self.execution_type == "model":
                self._execute_model()
            else:
                raise ValueError(f"Unsupported execution type: {self.execution_type}")
                
        except Exception as e:
            self.log_message.emit('error', f"Execution error: {e}")
            self.execution_completed.emit(False, f"Failed: {e}")
    
    def _execute_model(self):
        """Execute a model directly (for Dashboard model runs)"""
        self.log_message.emit('info', f"Loading model: {self.execution_name}")
        self.status_update.emit("Starting model...")
        
        # Get options
        checkpoint = self.options.get("checkpoint", "last")
        duration = self.options.get("duration", 25.0)
        num_episodes = self.options.get("num_episodes", 3)  # Dashboard default
        
        # Execute model
        self._execute_model_inline(self.execution_name, checkpoint, duration, num_episodes)
        
        # Completion
        if not self._stop_requested:
            self.log_message.emit('info', f"✓ Model execution completed")
            self.execution_completed.emit(True, "Model completed")
        else:
            self.log_message.emit('warning', "Model execution stopped by user")
            self.execution_completed.emit(False, "Stopped by user")
    
    def _execute_recording(self):
        """Execute a single recording"""
        self.log_message.emit('info', f"Loading recording: {self.execution_name}")
        self.status_update.emit(f"Loading recording...")
        
        # Load recording
        recording = self.actions_mgr.load_action(self.execution_name)
        if not recording:
            self.log_message.emit('error', f"Recording not found: {self.execution_name}")
            self.execution_completed.emit(False, "Recording not found")
            return
        
        # Connect to motors
        self.log_message.emit('info', "Connecting to motors...")
        self.status_update.emit("Connecting to motors...")
        
        if not self.motor_controller.connect():
            self.log_message.emit('error', "Failed to connect to motors")
            self.execution_completed.emit(False, "Motor connection failed")
            return
        
        try:
            # Execute based on recording type
            recording_type = recording.get("type", "position")
            
            if recording_type == "composite_recording":
                # New composite format with multiple steps
                self._execute_composite_recording(recording)
            elif recording_type == "live_recording":
                # Legacy single live recording (shouldn't happen with new system)
                self._playback_live_recording(recording)
            else:
                # Legacy position recording (shouldn't happen with new system)
                self._playback_position_recording(recording)
            
            # Success
            if not self._stop_requested:
                self.log_message.emit('info', "✓ Recording completed successfully")
                self.execution_completed.emit(True, "Recording completed")
            else:
                self.log_message.emit('warning', "Recording stopped by user")
                self.execution_completed.emit(False, "Stopped by user")
                
        finally:
            self.motor_controller.disconnect()
    
    def _execute_composite_recording(self, recording: dict):
        """Execute a composite recording with multiple steps
        
        Each step can be a live_recording or position_set component.
        Steps are executed in order with per-step speed and delays.
        """
        steps = recording.get("steps", [])
        total_steps = len(steps)
        
        self.log_message.emit('info', f"Executing composite recording: {recording.get('name', 'Unknown')}")
        self.log_message.emit('info', f"Total steps: {total_steps}")
        
        for step_idx, step in enumerate(steps):
            if self._stop_requested:
                break
            
            # Check if step is enabled
            if not step.get('enabled', True):
                self.log_message.emit('info', f"[{step_idx+1}/{total_steps}] Skipping disabled step: {step['name']}")
                continue
            
            step_name = step.get('name', f'Step {step_idx + 1}')
            step_type = step.get('type', 'unknown')
            step_speed = step.get('speed', 100)
            delay_before = step.get('delay_before', 0.0)
            delay_after = step.get('delay_after', 0.0)
            
            self.log_message.emit('info', f"\n[{step_idx+1}/{total_steps}] === {step_name} ({step_type}) ===")
            self.status_update.emit(f"Step {step_idx+1}/{total_steps}: {step_name}")
            
            # Delay before step
            if delay_before > 0:
                self.log_message.emit('info', f"⏱ Waiting {delay_before}s before step...")
                time.sleep(delay_before)
            
            # Get component data
            component_data = step.get('component_data', {})
            if not component_data:
                self.log_message.emit('warning', f"No component data for step: {step_name}")
                continue
            
            # Execute step based on type
            try:
                if step_type == 'live_recording':
                    self._execute_live_component(component_data, step_speed)
                elif step_type == 'position_set':
                    self._execute_position_component(component_data, step_speed)
                else:
                    self.log_message.emit('error', f"Unknown step type: {step_type}")
            except Exception as e:
                self.log_message.emit('error', f"Failed to execute step {step_name}: {e}")
                if not self._stop_requested:
                    continue  # Try next step
            
            # Delay after step
            if delay_after > 0:
                self.log_message.emit('info', f"⏱ Waiting {delay_after}s after step...")
                time.sleep(delay_after)
            
            # Update overall progress
            progress_pct = int(((step_idx + 1) / total_steps) * 100)
            self.progress_update.emit(step_idx + 1, total_steps)
            self.log_message.emit('info', f"✓ Step complete ({progress_pct}% overall)")
    
    def _execute_live_component(self, component: dict, speed_override: int):
        """Execute a live recording component with speed override"""
        recorded_data = component.get("recorded_data", [])
        
        if not recorded_data:
            self.log_message.emit('warning', "No recorded data in component")
            return
        
        total_points = len(recorded_data)
        self.log_message.emit('info', f"Playing {total_points} recorded points at {speed_override}% speed")
        
        # Time-based playback
        start_time = time.time()
        
        for idx, point in enumerate(recorded_data):
            if self._stop_requested:
                break
            
            positions = point['positions']
            target_timestamp = point['timestamp'] * (100.0 / speed_override)  # Speed scaling
            velocity = int(point.get('velocity', 600) * (speed_override / 100.0))
            
            # Wait until target time
            current_time = time.time() - start_time
            wait_time = target_timestamp - current_time
            if wait_time > 0:
                time.sleep(wait_time)
            
            # Update progress (every 10 points to avoid spam)
            if idx % 10 == 0:
                progress = int((idx / total_points) * 100)
                self.log_message.emit('info', f"  → Point {idx}/{total_points} ({progress}%)")
            
            # Send position command
            self.motor_controller.set_positions(
                positions,
                velocity=velocity,
                wait=False,  # Don't wait for live recordings (time-based)
                keep_connection=True
            )
    
    def _execute_position_component(self, component: dict, speed_override: int):
        """Execute a position set component with speed override"""
        positions_list = component.get("positions", [])
        
        if not positions_list:
            self.log_message.emit('warning', "No positions in component")
            return
        
        total_positions = len(positions_list)
        self.log_message.emit('info', f"Moving through {total_positions} waypoints at {speed_override}% speed")
        
        for idx, pos_data in enumerate(positions_list):
            if self._stop_requested:
                break
            
            # Extract position data
            pos_name = pos_data.get("name", f"Position {idx + 1}")
            motor_positions = pos_data.get("motor_positions", [])
            velocity = pos_data.get("velocity", 600)
            wait_for_completion = pos_data.get("wait_for_completion", True)
            
            # Apply speed scaling
            velocity = int(velocity * (speed_override / 100.0))
            
            # Move to position
            self.log_message.emit('info', f"  → {pos_name}: {motor_positions[:3]}... @ {velocity} vel")
            self.motor_controller.set_positions(
                motor_positions,
                velocity=velocity,
                wait=wait_for_completion,
                keep_connection=True
            )
            
            progress = int(((idx + 1) / total_positions) * 100)
            self.log_message.emit('info', f"  ✓ Reached {pos_name} ({progress}%)")
    
    def _playback_position_recording(self, recording: dict):
        """Play back a simple position recording"""
        positions_list = recording.get("positions", [])
        speed = recording.get("speed", 100)
        delays = recording.get("delays", {})
        
        total_steps = len(positions_list)
        self.log_message.emit('info', f"Playing {total_steps} positions at {speed}% speed")
        
        for idx, pos_data in enumerate(positions_list):
            if self._stop_requested:
                break
            
            # Extract position
            if isinstance(pos_data, dict):
                positions = pos_data.get("motor_positions", pos_data.get("positions", []))
                velocity = pos_data.get("velocity", 600)
            else:
                positions = pos_data
                velocity = 600
            
            # Apply speed scaling
            velocity = int(velocity * (speed / 100.0))
            
            # Update progress
            self.progress_update.emit(idx + 1, total_steps)
            self.status_update.emit(f"Position {idx+1}/{total_steps}")
            
            # Move to position
            self.log_message.emit('info', f"→ Position {idx+1}: {positions[:3]}... @ {velocity} vel")
            self.motor_controller.set_positions(
                positions,
                velocity=velocity,
                wait=True,
                keep_connection=True
            )
            
            # Apply delay if specified
            delay = delays.get(str(idx), 0)
            if delay > 0:
                self.log_message.emit('info', f"Delay: {delay}s")
                time.sleep(delay)
    
    def _playback_live_recording(self, recording: dict):
        """Play back a live recording with time-based interpolation"""
        recorded_data = recording.get("recorded_data", [])
        speed = recording.get("speed", 100)
        
        if not recorded_data:
            self.log_message.emit('warning', "No recorded data found")
            return
        
        total_points = len(recorded_data)
        self.log_message.emit('info', f"Playing {total_points} recorded points at {speed}% speed")
        
        # Time-based playback
        start_time = time.time()
        
        for idx, point in enumerate(recorded_data):
            if self._stop_requested:
                break
            
            positions = point['positions']
            target_timestamp = point['timestamp'] * (100.0 / speed)  # Speed scaling
            velocity = int(point.get('velocity', 600) * (speed / 100.0))
            
            # Wait until target time
            current_time = time.time() - start_time
            wait_time = target_timestamp - current_time
            if wait_time > 0:
                time.sleep(wait_time)
            
            # Update progress (every 10 points to avoid spam)
            if idx % 10 == 0:
                progress = int((idx / total_points) * 100)
                self.progress_update.emit(idx, total_points)
                self.status_update.emit(f"Playing: {progress}%")
                self.log_message.emit('info', f"→ Point {idx}/{total_points} ({progress}%)")
            
            # Send position command
            self.motor_controller.set_positions(
                positions,
                velocity=velocity,
                wait=False,  # Don't wait for live recordings (time-based)
                keep_connection=True
            )
    
    def _execute_sequence(self):
        """Execute a sequence of steps with optimized policy server management"""
        self.log_message.emit('info', f"Loading sequence: {self.execution_name}")
        self.status_update.emit("Loading sequence...")
        
        # Load sequence
        sequence = self.sequences_mgr.load_sequence(self.execution_name)
        if not sequence:
            self.log_message.emit('error', f"Sequence not found: {self.execution_name}")
            self.execution_completed.emit(False, "Sequence not found")
            return
        
        steps = sequence.get("steps", [])
        loop = sequence.get("loop", False)
        
        total_steps = len(steps)
        self.log_message.emit('info', f"Executing {total_steps} steps (loop={loop})")
        
        # Debug: Log step types
        step_types = [s.get("type", "unknown") for s in steps]
        self.log_message.emit('info', f"Step types: {step_types}")
        
        # Pre-scan for model steps and start policy server if needed (SERVER MODE ONLY)
        model_steps = [s for s in steps if s.get("type") == "model"]
        policy_server_process = None
        local_mode = self.config.get("policy", {}).get("local_mode", True)
        
        self.log_message.emit('info', f"Found {len(model_steps)} model step(s)")
        
        if model_steps and not local_mode:
            # Only pre-start server in SERVER MODE
            # In local mode, each model step runs independently with lerobot-record
            first_model = model_steps[0]
            task = first_model.get("task", "")
            checkpoint = first_model.get("checkpoint", "last")
            
            self.log_message.emit('info', f"🚀 Pre-starting policy server for {task} (used by {len(model_steps)} step(s))")
            policy_server_process = self._start_policy_server(task, checkpoint)
            
            if not policy_server_process:
                self.log_message.emit('error', "Failed to start policy server - model steps will be skipped")
        elif model_steps and local_mode:
            self.log_message.emit('info', f"Using local mode - model steps will execute directly (no server)")
        
        # Execute steps
        iteration = 0
        try:
            while True:
                iteration += 1
                
                for idx, step in enumerate(steps):
                    if self._stop_requested:
                        break
                    
                    step_type = step.get("type")
                    
                    self.progress_update.emit(idx + 1, total_steps)
                    self.status_update.emit(f"Step {idx+1}/{total_steps}: {step_type}")
                    
                    if step_type == "action":
                        # Execute action/recording
                        action_name = step.get("name")
                        self.log_message.emit('info', f"→ Executing action: {action_name}")
                        self._execute_recording_inline(action_name)
                        
                    elif step_type == "delay":
                        # Wait while holding current position
                        duration = step.get("duration", 1.0)
                        self.log_message.emit('info', f"→ Delay: {duration}s (holding position)")
                        self._delay_with_hold(duration)
                    
                    elif step_type == "home":
                        # Return to home position
                        self.log_message.emit('info', "→ Returning to home position")
                        self._execute_home_inline()
                        
                    elif step_type == "model":
                        # Execute trained policy model
                        task = step.get("task", "")
                        checkpoint = step.get("checkpoint", "last")
                        duration = step.get("duration", 25.0)
                        
                        if local_mode:
                            # Local mode: Direct execution with lerobot-record
                            self.log_message.emit('info', f"→ Executing model: {task} for {duration}s (local mode)")
                            self._execute_model_inline(task, checkpoint, duration)
                        elif policy_server_process and policy_server_process.poll() is None:
                            # Server mode: Use pre-started server
                            self.log_message.emit('info', f"→ Executing model: {task} for {duration}s (server mode)")
                            self._execute_model_with_server(policy_server_process, task, checkpoint, duration)
                        else:
                            self.log_message.emit('warning', f"→ Skipping model {task} - policy server not running")
                    
                    else:
                        self.log_message.emit('warning', f"Unknown step type: {step_type}")
                
                if self._stop_requested or not loop:
                    break
                
                self.log_message.emit('info', f"Loop iteration {iteration} completed, repeating...")
        
        finally:
            # Clean up policy server
            if policy_server_process:
                self.log_message.emit('info', "Shutting down policy server...")
                policy_server_process.terminate()
                policy_server_process.wait(5)
                if policy_server_process.poll() is None:
                    policy_server_process.kill()
                self.log_message.emit('info', "✓ Policy server stopped")
        
        # Success
        if not self._stop_requested:
            self.log_message.emit('info', f"✓ Sequence completed ({iteration} iterations)")
            self.execution_completed.emit(True, f"Sequence completed ({iteration} iterations)")
        else:
            self.log_message.emit('warning', "Sequence stopped by user")
            self.execution_completed.emit(False, "Stopped by user")
    
    def _execute_recording_inline(self, recording_name: str):
        """Execute a recording as part of a sequence (inline)"""
        recording = self.actions_mgr.load_action(recording_name)
        if not recording:
            self.log_message.emit('error', f"Recording not found: {recording_name}")
            return
        
        # Connect if not already connected
        if not self.motor_controller.bus:
            if not self.motor_controller.connect():
                self.log_message.emit('error', "Failed to connect to motors")
                return
        
        # Execute based on type
        recording_type = recording.get("type", "position")
        
        if recording_type == "composite_recording":
            # New composite format - execute all steps
            self._execute_composite_recording(recording)
        elif recording_type == "live_recording":
            self._playback_live_recording(recording)
        else:
            self._playback_position_recording(recording)
    
    def _delay_with_hold(self, duration: float):
        """Delay while holding current motor position with torque enabled
        
        Args:
            duration: How long to delay (seconds)
        """
        # Connect if not already connected
        if not self.motor_controller.bus:
            if not self.motor_controller.connect():
                self.log_message.emit('error', "Failed to connect to motors - cannot hold position during delay")
                # Fall back to regular sleep
                time.sleep(duration)
                return
        
        try:
            # Read current positions
            current_positions = self.motor_controller.read_positions_from_bus()
            
            if not current_positions:
                self.log_message.emit('warning', "Could not read positions - delay without holding")
                time.sleep(duration)
                return
            
            self.log_message.emit('info', f"Holding position: {current_positions}")
            
            # Hold position by periodically re-sending position commands
            # This keeps torque enabled and arm locked in place
            start_time = time.time()
            hold_interval = 0.1  # Re-send position every 100ms
            
            while (time.time() - start_time) < duration:
                if self._stop_requested:
                    break
                
                # Re-send position command to maintain hold
                try:
                    for idx, motor_name in enumerate(self.motor_controller.motor_names):
                        self.motor_controller.bus.write(
                            "Goal_Position",
                            motor_name,
                            current_positions[idx],
                            normalize=False
                        )
                except Exception as e:
                    self.log_message.emit('warning', f"Hold position error: {e}")
                
                # Sleep for hold interval (or remaining time if less)
                remaining = duration - (time.time() - start_time)
                sleep_time = min(hold_interval, remaining)
                if sleep_time > 0:
                    time.sleep(sleep_time)
            
            self.log_message.emit('info', "✓ Delay complete (position held)")
            
        except Exception as e:
            self.log_message.emit('error', f"Error during delay hold: {e}")
            # Fall back to regular sleep for any remaining time
            elapsed = time.time() - start_time if 'start_time' in locals() else 0
            remaining = duration - elapsed
            if remaining > 0:
                time.sleep(remaining)
    
    def _execute_home_inline(self):
        """Return arm to home/rest position"""
        # Connect if not already connected
        if not self.motor_controller.bus:
            if not self.motor_controller.connect():
                self.log_message.emit('error', "Failed to connect to motors")
                return
        
        # Get home position from config (or use safe defaults)
        home_positions = self.config.get("robot", {}).get("home_position", [2048, 2048, 2048, 2048, 2048, 2048])
        
        self.log_message.emit('info', f"Moving to home position: {home_positions}")
        
        try:
            # Move to home position
            self.motor_controller.set_positions(
                home_positions,
                velocity=600,
                wait=True,
                keep_connection=True
            )
            
            self.log_message.emit('info', "✓ Reached home position")
            
        except Exception as e:
            self.log_message.emit('error', f"Failed to reach home: {e}")
    
    def _start_policy_server(self, task: str, checkpoint: str):
        """Start policy server and return process (for use in sequences)
        
        Args:
            task: Model task name
            checkpoint: Checkpoint name (e.g., "last", "best")
        
        Returns:
            subprocess.Popen object or None if failed
        """
        import subprocess
        from pathlib import Path
        
        try:
            # Get checkpoint path
            train_dir = Path(self.config["policy"].get("base_path", ""))
            checkpoint_path = train_dir / task / "checkpoints" / checkpoint / "pretrained_model"
            
            if not checkpoint_path.exists():
                self.log_message.emit('error', f"Model not found: {checkpoint_path}")
                return None
            
            # Build command
            policy_cmd = self._build_policy_server_cmd(checkpoint_path)
            
            # Start policy server
            policy_process = subprocess.Popen(
                policy_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # Wait for server to be ready
            import time
            time.sleep(2)
            
            # Check if server started successfully
            if policy_process.poll() is not None:
                self.log_message.emit('error', "Policy server failed to start")
                return None
            
            self.log_message.emit('info', "✓ Policy server ready")
            return policy_process
            
        except Exception as e:
            self.log_message.emit('error', f"Failed to start policy server: {e}")
            return None
    
    def _execute_model_with_server(self, policy_process, task: str, checkpoint: str, duration: float):
        """Execute model using an already-running policy server
        
        Args:
            policy_process: Running policy server subprocess
            task: Model task name
            checkpoint: Checkpoint name
            duration: How long to run (seconds)
        """
        import subprocess
        import time
        from pathlib import Path
        
        try:
            # Get checkpoint path
            train_dir = Path(self.config["policy"].get("base_path", ""))
            checkpoint_path = train_dir / task / "checkpoints" / checkpoint / "pretrained_model"
            
            # Build robot client command
            robot_cmd = self._build_robot_client_cmd(checkpoint_path)
            
            self.log_message.emit('info', "Starting robot client...")
            
            # Start robot client
            robot_process = subprocess.Popen(
                robot_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # Wait for client to connect
            time.sleep(2)
            
            # Check if client started successfully
            if robot_process.poll() is not None:
                self.log_message.emit('error', "Robot client failed to start")
                return
            
            self.log_message.emit('info', f"✓ Model running for {duration}s")
            
            # Run for specified duration (check for stop every second)
            start_time = time.time()
            while time.time() - start_time < duration:
                if self._stop_requested:
                    self.log_message.emit('info', "Model execution stopped by user")
                    break
                time.sleep(0.5)
            
            # Stop robot client (keep policy server running)
            self.log_message.emit('info', "Stopping robot client...")
            robot_process.terminate()
            robot_process.wait(5)
            
            # Force kill if still running
            if robot_process.poll() is None:
                robot_process.kill()
            
            self.log_message.emit('info', "✓ Model execution completed")
            
        except Exception as e:
            self.log_message.emit('error', f"Model execution failed: {e}")
            import traceback
            traceback.print_exc()
    
    def _cleanup_eval_folders(self, verbose: bool = True):
        """Clean up all eval folders to prevent naming conflicts
        
        Args:
            verbose: If True, log each folder being cleaned. If False, only log summary.
        """
        import shutil
        
        try:
            # Look for eval folders in lerobot data directory
            # Structure: ~/.cache/huggingface/lerobot/local/eval_*
            lerobot_data = Path.home() / ".cache" / "huggingface" / "lerobot" / "local"
            
            if not lerobot_data.exists():
                return
            
            # Find and delete all folders starting with "eval_"
            deleted_count = 0
            for item in lerobot_data.iterdir():
                if item.is_dir() and item.name.startswith("eval_"):
                    if verbose:
                        self.log_message.emit('info', f"Cleaning up: local/{item.name}")
                    shutil.rmtree(item)
                    deleted_count += 1
            
            if deleted_count > 0:
                self.log_message.emit('info', f"✓ Cleaned up {deleted_count} eval folder(s)")
        
        except Exception as e:
            self.log_message.emit('warning', f"Failed to cleanup eval folders: {e}")
    
    def _execute_model_local(self, task: str, checkpoint: str, duration: float, num_episodes: int):
        """Execute model using local mode (lerobot-record with policy)
        
        Args:
            task: Model task name
            checkpoint: Checkpoint name
            duration: How long to run (seconds)
            num_episodes: Number of episodes to run
        """
        try:
            # Clean up old eval folders
            self._cleanup_eval_folders()
            
            # Get checkpoint path
            train_dir = Path(self.config["policy"].get("base_path", ""))
            checkpoint_path = train_dir / task / "checkpoints" / checkpoint / "pretrained_model"
            
            if not checkpoint_path.exists():
                self.log_message.emit('error', f"Model not found: {checkpoint_path}")
                return
            
            # Build camera config string
            robot_config = self.config.get("robot", {})
            cameras = robot_config.get("cameras", {})
            camera_str = "{ "
            for cam_name, cam_config in cameras.items():
                camera_str += f"{cam_name}: {{type: opencv, index_or_path: {cam_config['path']}, width: {cam_config['width']}, height: {cam_config['height']}, fps: {cam_config['fps']}}}, "
            camera_str = camera_str.rstrip(", ") + " }"
            
            # Get lerobot working directory
            lerobot_dir = Path.home() / "lerobot"
            if not lerobot_dir.exists():
                lerobot_dir = Path("/home/daniel/lerobot")  # Fallback
            
            # Build command using lerobot-record CLI
            # This directly loads and runs the policy without needing a server
            cmd = [
                "lerobot-record",
                f"--robot.type={robot_config.get('type', 'so100_follower')}",
                f"--robot.port={robot_config.get('port', '/dev/ttyACM0')}",
                f"--robot.cameras={camera_str}",
                f"--robot.id={robot_config.get('id', 'follower_arm')}",
                "--display_data=false",
                f"--dataset.repo_id=local/eval_{task}_ckpt",
                f"--dataset.single_task=Eval {task}",
                f"--dataset.num_episodes={num_episodes}",
                f"--dataset.episode_time_s={duration}",
                "--dataset.push_to_hub=false",
                "--resume=false",
                f"--policy.path={checkpoint_path}"
            ]
            
            # Check if we have permissions to access the robot port
            robot_port = robot_config.get('port', '/dev/ttyACM0')
            if not Path(robot_port).exists():
                self.log_message.emit('error', f"Robot port not found: {robot_port}")
                self.log_message.emit('error', "Make sure the robot is connected")
                return
            
            try:
                # Test if we can access the port
                test_result = subprocess.run(['test', '-r', robot_port, '-a', '-w', robot_port], 
                                            capture_output=True, timeout=1)
                if test_result.returncode != 0:
                    self.log_message.emit('warning', f"No permission to access {robot_port}")
                    self.log_message.emit('warning', f"Run: sudo chmod 666 {robot_port}")
                    # Continue anyway - lerobot might handle this
            except:
                pass  # If test fails, continue anyway
            
            self.log_message.emit('info', f"Starting local mode: {task} for {duration}s ({num_episodes} episode(s))")
            self.log_message.emit('info', "Command: lerobot-record ...")
            
            # Start process with correct working directory
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(lerobot_dir)  # Run from lerobot directory
            )
            
            # Read and log output in real-time
            # This is CRITICAL - we must consume the pipe or it will block!
            output_lines = []
            def read_output():
                """Read subprocess output line by line"""
                try:
                    for line in iter(process.stdout.readline, ''):
                        if not line:
                            break
                        line = line.rstrip()
                        output_lines.append(line)
                        # Log important lines to GUI
                        if 'INFO' in line or 'ERROR' in line or 'Traceback' in line:
                            # Extract just the message part
                            if 'INFO' in line:
                                self.log_message.emit('info', f"[lerobot] {line.split('INFO')[-1].strip()}")
                            elif 'ERROR' in line:
                                self.log_message.emit('error', f"[lerobot] {line.split('ERROR')[-1].strip()}")
                            elif 'Traceback' in line:
                                self.log_message.emit('error', f"[lerobot] {line}")
                except Exception as e:
                    self.log_message.emit('warning', f"Output reading error: {e}")
                finally:
                    if process.stdout:
                        process.stdout.close()
            
            # Start output reader thread
            output_thread = threading.Thread(target=read_output, daemon=True)
            output_thread.start()
            
            # Wait a moment for process to start
            time.sleep(2)
            
            # Check if process started successfully
            if process.poll() is not None:
                exit_code = process.returncode
                self.log_message.emit('error', f"lerobot-record failed to start (exit code: {exit_code})")
                self.log_message.emit('error', "Check the logs above for details")
                # Print last few lines of output
                for line in output_lines[-10:]:
                    print(f"[lerobot] {line}")
                return
            
            self.log_message.emit('info', "✓ Process started, running...")
            
            # Calculate total runtime (num_episodes * episode_time + buffer)
            total_time = (num_episodes * duration) + 10  # 10s buffer for startup/shutdown
            
            # Wait for process to complete or timeout
            start_time = time.time()
            while time.time() - start_time < total_time:
                if self._stop_requested:
                    self.log_message.emit('warning', "Stopping by user request...")
                    break
                
                # Check if process finished
                if process.poll() is not None:
                    exit_code = process.returncode
                    if exit_code == 0:
                        self.log_message.emit('info', "✓ lerobot-record completed successfully")
                    else:
                        self.log_message.emit('error', f"lerobot-record failed with exit code {exit_code}")
                        # Print last few lines of output
                        for line in output_lines[-10:]:
                            print(f"[lerobot] {line}")
                    break
                
                time.sleep(0.5)
            
            # If still running, terminate it
            if process.poll() is None:
                self.log_message.emit('info', "Stopping lerobot-record...")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.log_message.emit('warning', "Force killing process...")
                    process.kill()
                    process.wait()
            
            # Wait for output thread to finish
            output_thread.join(timeout=2)
            
            self.log_message.emit('info', "✓ Local model execution completed")
            
        except Exception as e:
            self.log_message.emit('error', f"Local model execution failed: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            # Always cleanup eval folders at the end to keep things tidy
            self._cleanup_eval_folders(verbose=False)  # Less verbose at end
    
    def _execute_model_inline(self, task: str, checkpoint: str, duration: float, num_episodes: int = None):
        """Execute a trained policy model for specified duration
        
        Checks config to determine if local or server mode should be used.
        
        Args:
            task: Model task name (folder in training output)
            checkpoint: Checkpoint name (e.g., "last", "best")
            duration: How long to run the model (seconds)
            num_episodes: Number of episodes (default: 1 for sequences, or from options for dashboard)
        """
        # Check if local mode is enabled
        local_mode = self.config.get("policy", {}).get("local_mode", True)
        
        if local_mode:
            self.log_message.emit('info', "Using local mode (lerobot-record)")
            # Default to 1 episode for sequences, or use provided value
            if num_episodes is None:
                num_episodes = 1
            self._execute_model_local(task, checkpoint, duration, num_episodes)
            return
        
        # Otherwise use server mode
        try:
            # Get checkpoint path
            train_dir = Path(self.config["policy"].get("base_path", ""))
            checkpoint_path = train_dir / task / "checkpoints" / checkpoint / "pretrained_model"
            
            if not checkpoint_path.exists():
                self.log_message.emit('error', f"Model not found: {checkpoint_path}")
                return
            
            self.log_message.emit('info', f"Starting policy server: {checkpoint_path}")
            
            # Build commands (similar to RobotWorker)
            policy_cmd = self._build_policy_server_cmd(checkpoint_path)
            robot_cmd = self._build_robot_client_cmd(checkpoint_path)
            
            # Start policy server
            policy_process = subprocess.Popen(
                policy_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # Wait for server to be ready
            time.sleep(2)
            
            # Check if server started successfully
            if policy_process.poll() is not None:
                self.log_message.emit('error', "Policy server failed to start")
                return
            
            self.log_message.emit('info', "Starting robot client...")
            
            # Start robot client
            robot_process = subprocess.Popen(
                robot_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # Wait for client to connect
            time.sleep(2)
            
            # Check if client started successfully
            if robot_process.poll() is not None:
                self.log_message.emit('error', "Robot client failed to start")
                # Kill policy server
                policy_process.terminate()
                policy_process.wait(5)
                return
            
            self.log_message.emit('info', f"✓ Model running for {duration}s")
            
            # Run for specified duration (check for stop every second)
            start_time = time.time()
            while time.time() - start_time < duration:
                if self._stop_requested:
                    self.log_message.emit('info', "Model execution stopped by user")
                    break
                time.sleep(0.5)
            
            # Stop processes
            self.log_message.emit('info', "Stopping model...")
            robot_process.terminate()
            policy_process.terminate()
            
            # Wait for clean shutdown
            robot_process.wait(5)
            policy_process.wait(5)
            
            # Force kill if still running
            if robot_process.poll() is None:
                robot_process.kill()
            if policy_process.poll() is None:
                policy_process.kill()
            
            self.log_message.emit('info', "✓ Model execution completed")
            
        except Exception as e:
            self.log_message.emit('error', f"Model execution failed: {e}")
            import traceback
            traceback.print_exc()
    
    def _build_policy_server_cmd(self, checkpoint_path: Path) -> list:
        """Build command for policy server"""
        # Get python path from lerobot config, or fall back to system python
        lerobot_config = self.config.get("lerobot", {})
        lerobot_bin = lerobot_config.get("python_path", "python")
        
        return [
            lerobot_bin, "-m", "lerobot.async_inference.policy_server",
            f"--policy_device={self.config['policy'].get('device', 'cuda')}",
            f"--policy_type={self.config['policy'].get('type', 'act')}",
            f"--pretrained_name_or_path={checkpoint_path}",
            "--port=8080"
        ]
    
    def _build_robot_client_cmd(self, checkpoint_path: Path) -> list:
        """Build command for robot client"""
        # Get python path from lerobot config, or fall back to system python
        lerobot_config = self.config.get("lerobot", {})
        lerobot_bin = lerobot_config.get("python_path", "python")
        robot_config = self.config.get("robot", {})
        
        # Build camera config string
        cameras = robot_config.get("cameras", {})
        camera_str = "{"
        for cam_name, cam_config in cameras.items():
            camera_str += f"{cam_name}: {{type: opencv, index_or_path: '{cam_config['path']}', width: {cam_config['width']}, height: {cam_config['height']}, fps: {cam_config['fps']}}}, "
        camera_str = camera_str.rstrip(", ") + "}"
        
        return [
            lerobot_bin, "-m", "lerobot.async_inference.robot_client",
            "--server_address=127.0.0.1:8080",
            f"--robot.type={robot_config.get('type', 'so100_follower')}",
            f"--robot.port={robot_config.get('port', '/dev/ttyACM0')}",
            f"--robot.id={robot_config.get('id', 'follower_arm')}",
            f"--robot.cameras={camera_str}",
            f"--policy_type={self.config['policy'].get('type', 'act')}",
            f"--pretrained_name_or_path={checkpoint_path}",
            f"--policy_device={self.config['policy'].get('device', 'cuda')}",
            "--actions_per_chunk=30",
            "--chunk_size_threshold=0.6"
        ]
    
    
    def stop(self):
        """Request execution to stop"""
        self._stop_requested = True
        
        # Emergency stop motors
        if self.motor_controller.bus:
            self.motor_controller.emergency_stop()

