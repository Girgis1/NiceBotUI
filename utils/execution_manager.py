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
        self._stop_requested = False
        
        # Managers
        self.actions_mgr = ActionsManager()
        self.sequences_mgr = SequencesManager()
        self.motor_controller = MotorController(config)
    
    def run(self):
        """Main execution thread
        
        NOTE: Models are NOT executed here to avoid nested threads.
        Models use RobotWorker directly from the Dashboard.
        """
        self._stop_requested = False
        
        try:
            if self.execution_type == "recording":
                self._execute_recording()
            elif self.execution_type == "sequence":
                self._execute_sequence()
            else:
                raise ValueError(f"Unsupported execution type: {self.execution_type}. Models should use RobotWorker directly.")
                
        except Exception as e:
            self.log_message.emit('error', f"Execution error: {e}")
            self.execution_completed.emit(False, f"Failed: {e}")
    
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
            
            if recording_type == "live_recording":
                self._playback_live_recording(recording)
            else:
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
        """Execute a sequence of steps"""
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
        
        # Execute steps
        iteration = 0
        while True:
            iteration += 1
            
            for idx, step in enumerate(steps):
                if self._stop_requested:
                    break
                
                step_type = step.get("type")
                
                self.progress_update.emit(idx + 1, total_steps)
                self.status_update.emit(f"Step {idx+1}/{total_steps}: {step_type}")
                
                if step_type == "recording":
                    # Execute recording
                    recording_name = step.get("name")
                    self.log_message.emit('info', f"→ Executing recording: {recording_name}")
                    self._execute_recording_inline(recording_name)
                    
                elif step_type == "delay":
                    # Wait
                    duration = step.get("duration", 1.0)
                    self.log_message.emit('info', f"→ Delay: {duration}s")
                    time.sleep(duration)
                    
                elif step_type == "model":
                    # Execute model
                    self.log_message.emit('warning', "Model execution not yet implemented in sequences")
                    # TODO: Implement model execution
                
                else:
                    self.log_message.emit('warning', f"Unknown step type: {step_type}")
            
            if self._stop_requested or not loop:
                break
            
            self.log_message.emit('info', f"Loop iteration {iteration} completed, repeating...")
        
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
        
        if recording_type == "live_recording":
            self._playback_live_recording(recording)
        else:
            self._playback_position_recording(recording)
    
    
    def stop(self):
        """Request execution to stop"""
        self._stop_requested = True
        
        # Emergency stop motors
        if self.motor_controller.bus:
            self.motor_controller.emergency_stop()

