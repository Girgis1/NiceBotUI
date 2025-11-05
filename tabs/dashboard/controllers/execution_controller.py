"""
Execution Controller - Handles robot execution logic

Coordinates robot control operations including model execution, sequences,
recordings, and home movements.
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple, Any
from PySide6.QtCore import QObject, Signal, QThread

try:
    from robot_worker import RobotWorker
    from utils.execution_manager import ExecutionWorker
    from utils.home_move_worker import HomeMoveWorker, HomeMoveRequest
except ImportError:
    # Handle missing imports gracefully for testing
    RobotWorker = None
    ExecutionWorker = None
    HomeMoveWorker = None
    HomeMoveRequest = None


class ExecutionController(QObject):
    """Handles robot execution logic and coordination"""

    # Signals for UI updates
    execution_started = Signal(str, str)  # (execution_type, execution_name)
    execution_stopped = Signal()
    execution_completed = Signal(bool, str)  # (success, message)
    home_started = Signal()
    home_completed = Signal(bool, str)  # (success, message)
    home_progress = Signal(str)  # progress message
    ui_reset_needed = Signal()  # signal to reset UI state
    log_entry_needed = Signal(str, str, dict)  # (level, message, metadata)

    def __init__(self, config: Dict[str, Any], device_manager=None):
        super().__init__()
        self.config = config
        self.device_manager = device_manager

        # Execution state
        self.is_running = False
        self._stopping_run = False
        self._fatal_error_active = False
        self._last_log_code = None
        self._last_log_message = None
        self.loop_enabled = False
        self.master_speed = 1.0

        # Workers
        self.worker = None  # RobotWorker for models
        self.execution_worker = None  # ExecutionWorker for sequences/recordings
        self._home_thread = None
        self._home_worker = None

        # Vision state (needed for execution coordination)
        self._vision_state_active = False
        self._last_vision_signature = None
        self.active_vision_zones = set()
        self._last_preview_timestamp = 0.0
        self.camera_view_active = False

    def toggle_start_stop(self) -> bool:
        """Toggle between start and stop states

        Returns:
            bool: True if starting, False if stopping
        """
        if self.is_running:
            self.stop_run()
            return False
        else:
            self.start_run()
            return True

    def start_run(self) -> bool:
        """Start robot run - unified execution for models, recordings, and sequences

        Returns:
            bool: True if run started successfully, False otherwise
        """
        if self.is_running:
            self._log("warning", "A run is already active. Press Stop before starting another.")
            return False

        # Reset vision state
        self._vision_state_active = False
        self._last_vision_signature = None
        self.active_vision_zones.clear()
        self._last_preview_timestamp = 0.0

        # Get execution parameters from UI state (will be passed in)
        # For now, return False - this will be implemented when integrated
        self._log("warning", "Execution parameters not yet configured - integration needed")
        return False

    def start_run_with_params(self, execution_type: str, execution_name: str,
                            checkpoint_name: str = "last", loop: bool = False) -> bool:
        """Start run with explicit parameters (called from UI integration)

        Args:
            execution_type: "model", "sequence", or "recording"
            execution_name: Name of the item to execute
            checkpoint_name: Checkpoint to use for models
            loop: Whether to loop the execution

        Returns:
            bool: True if started successfully
        """
        if self.is_running:
            self._log("warning", "A run is already active. Press Stop before starting another.")
            return False

        self._fatal_error_active = False
        self._last_log_code = None
        self._last_log_message = None
        self.is_running = True

        type_label = {
            "model": "Model",
            "sequence": "Sequence",
            "recording": "Action",
        }.get(execution_type, "Run")

        self._log("action", f"Starting {type_label} "{execution_name}".", code="run_start")
        self._log("speed", f"Robot speed set to {int(self.master_speed * 100)}%.", code="run_speed")

        # Handle models
        if execution_type == "model":
            local_mode = self.config.get("policy", {}).get("local_mode", True)

            if local_mode:
                self._log("system", "Running directly on this computer.", code="run_local_mode")

                if loop:
                    num_episodes = -1  # Infinite loop
                    self._log("info", "Loop mode is ON — the run will repeat until you stop it.", code="loop_enabled")
                else:
                    num_episodes = 1

                self._start_execution_worker(execution_type, execution_name, {
                    "checkpoint": checkpoint_name,
                    "duration": self.config.get("control", {}).get("episode_time_s", 30),
                    "num_episodes": num_episodes
                })
            else:
                self._log("system", "Connecting to the NiceBot server for this run.", code="run_server_mode")
                self._start_model_execution(execution_name, checkpoint_name)
        else:
            # For recordings and sequences, use ExecutionWorker
            options = {"loop": loop} if execution_type in {"sequence", "recording"} else {}
            self._start_execution_worker(execution_type, execution_name, options)

        self.execution_started.emit(execution_type, execution_name)
        return True

    def stop_run(self, quiet: bool = False) -> None:
        """Stop robot run"""
        if not self.is_running:
            return

        if self._stopping_run:
            return
        self._stopping_run = True

        if not quiet:
            self._log("stop", "Stopping the current run…", code="run_stopping")

        # Stop execution worker (for recordings/sequences)
        if self.execution_worker and hasattr(self.execution_worker, 'isRunning') and self.execution_worker.isRunning():
            self.execution_worker.stop()
            if hasattr(self.execution_worker, 'wait'):
                self.execution_worker.wait(5000)  # Wait up to 5 seconds

        # Stop robot worker (for models)
        if self.worker and hasattr(self.worker, 'isRunning') and self.worker.isRunning():
            self.worker.stop()
            if hasattr(self.worker, 'wait'):
                self.worker.wait(5000)  # Wait up to 5 seconds

        # Reset state
        self._reset_execution_state()
        self._stopping_run = False
        self.execution_stopped.emit()

    def go_home(self) -> bool:
        """Move to the configured home position

        Returns:
            bool: True if home movement started successfully
        """
        if self._home_thread and hasattr(self._home_thread, 'isRunning') and self._home_thread.isRunning():
            self._log("warning", "Home command already running.", code="home_already_running")
            return False

        rest_config = self.config.get("rest_position", {}) if self.config else {}
        if not rest_config.get("positions"):
            self._log("error", "No home position configured. Set home first in Settings.", code="home_not_configured")
            return False

        home_velocity = rest_config.get("velocity")

        self._log("info", "Moving to the home position…", code="home_start")
        if home_velocity is not None:
            self._log("speed", f"Home velocity set to {home_velocity}.", code="home_speed")

        request = HomeMoveRequest(
            config=self.config,
            velocity_override=home_velocity,
        )

        worker = HomeMoveWorker(request)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_home_progress)
        worker.finished.connect(self._on_home_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_home_thread_finished)

        self._home_thread = thread
        self._home_worker = worker

        thread.start()
        self.home_started.emit()
        return True

    def run_from_dashboard(self) -> bool:
        """Execute the selected RUN item (same as pressing START)"""
        if not self.is_running:
            return self.start_run()
        return False

    def set_speed_multiplier(self, speed: float) -> None:
        """Set the master speed multiplier"""
        self.master_speed = speed

    def set_loop_enabled(self, enabled: bool) -> None:
        """Enable or disable loop mode"""
        self.loop_enabled = enabled

    def _start_model_execution(self, model_name: str, checkpoint_name: str = "last") -> None:
        """Start model execution using RobotWorker directly"""
        try:
            train_dir = Path(self.config["policy"].get("base_path", ""))
            checkpoint_path = train_dir / model_name / "checkpoints" / checkpoint_name / "pretrained_model"

            # Update config for this run
            model_config = self.config.copy()
            model_config.setdefault("control", {})["speed_multiplier"] = self.master_speed
            model_config["policy"]["path"] = str(checkpoint_path)

            checkpoint_display = checkpoint_name if isinstance(checkpoint_name, str) else str(checkpoint_name)
            self._log("action", f"Loading model "{model_name}" ({checkpoint_display}). This may take a moment.", code="model_loading")

            # Stop any existing worker first
            if self.worker and hasattr(self.worker, 'isRunning') and self.worker.isRunning():
                self._log("warning", "Stopping the previous run before starting a new one…", code="stopping_previous_worker")
                self.worker.stop()
                if hasattr(self.worker, 'wait'):
                    self.worker.wait(2000)

            # Create RobotWorker directly (not nested in another thread)
            if RobotWorker:
                self.worker = RobotWorker(model_config)

                # Connect signals with error handling
                self.worker.status_update.connect(self._on_status_update)
                self.worker.log_message.connect(self._on_log_message)
                self.worker.progress_update.connect(self._on_progress_update)
                self.worker.run_completed.connect(self._on_model_completed)
                self.worker.finished.connect(self._on_worker_thread_finished)

                # Start worker
                self.worker.start()
            else:
                raise ImportError("RobotWorker not available")

        except Exception as e:
            self._log("error", "We couldn't start the model run.", action=f"Details: {e}", code="model_start_failed")
            self._reset_execution_state()

    def _start_execution_worker(self, execution_type: str, execution_name: str, options: Dict = None) -> None:
        """Start ExecutionWorker for recordings and sequences"""
        merged_options = dict(options or {})
        merged_options["speed_multiplier"] = self.master_speed

        # Create and start execution worker
        if ExecutionWorker:
            self.execution_worker = ExecutionWorker(
                self.config,
                execution_type,
                execution_name,
                merged_options
            )

            # Connect signals
            self.execution_worker.status_update.connect(self._on_status_update)
            self.execution_worker.log_message.connect(self._on_log_message)
            self.execution_worker.progress_update.connect(self._on_progress_update)
            self.execution_worker.execution_completed.connect(self._on_execution_completed)
            self.execution_worker.sequence_step_started.connect(self._on_sequence_step_started)
            self.execution_worker.sequence_step_completed.connect(self._on_sequence_step_completed)
            self.execution_worker.vision_state_update.connect(self._on_vision_state_update)

            # Start execution
            self.execution_worker.set_speed_multiplier(self.master_speed)
            self.execution_worker.start()
        else:
            raise ImportError("ExecutionWorker not available")

    def _reset_execution_state(self) -> None:
        """Reset execution state after run completes or stops"""
        try:
            self._stopping_run = False
            self._fatal_error_active = False
            self._last_log_code = None
            self._last_log_message = None
            self.is_running = False
            self._vision_state_active = False
            self._last_vision_signature = None
            self.active_vision_zones.clear()

            # Clean up execution worker (recordings/sequences)
            if self.execution_worker:
                try:
                    if hasattr(self.execution_worker, 'isRunning') and self.execution_worker.isRunning():
                        self.execution_worker.quit()
                        if hasattr(self.execution_worker, 'wait'):
                            self.execution_worker.wait(1000)
                except:
                    pass
                self.execution_worker = None

            # Clean up robot worker (models) - be very careful here
            if self.worker:
                try:
                    if hasattr(self.worker, 'isRunning') and self.worker.isRunning():
                        self.worker.quit()
                        if hasattr(self.worker, 'wait'):
                            self.worker.wait(2000)
                    # Mark for deletion but don't set to None yet
                    # Let Qt handle the cleanup
                    if hasattr(self.worker, 'deleteLater'):
                        self.worker.deleteLater()
                except Exception as e:
                    self._log("warning", f"Worker cleanup warning: {e}", code="worker_cleanup_warning")
                finally:
                    self.worker = None
        except Exception as e:
            self._log("error", "We ran into a problem while resetting the execution state.", action=f"Details: {e}", code="execution_reset_error")

        self.ui_reset_needed.emit()

    def _on_worker_thread_finished(self) -> None:
        """Handle worker thread finished (cleanup)"""
        try:
            if self.worker:
                if hasattr(self.worker, 'deleteLater'):
                    self.worker.deleteLater()
        except Exception as e:
            self._log("error", "There was a problem cleaning up the worker thread.", action=f"Details: {e}", code="worker_thread_cleanup_error")

    def _on_home_progress(self, message: str) -> None:
        """Handle home movement progress updates"""
        self.home_progress.emit(message)
        self._log("info", message, code="home_progress")

    def _on_home_finished(self, success: bool, message: str) -> None:
        """Handle home movement completion"""
        if not message:
            message = "✓ At home position" if success else "⚠️ Home failed"
        level = "info" if success else "error"
        code = "home_complete" if success else "home_failed"
        self._log(level, message, code=code)
        self.home_completed.emit(success, message)

    def _on_home_thread_finished(self) -> None:
        """Handle home thread cleanup"""
        if self._home_thread:
            if hasattr(self._home_thread, 'deleteLater'):
                self._home_thread.deleteLater()
        self._home_thread = None
        self._home_worker = None

    # Placeholder signal handlers - will be connected to actual handlers in integration
    def _on_status_update(self, status: str):
        pass

    def _on_log_message(self, level: str, message: str):
        pass

    def _on_progress_update(self, current: int, total: int):
        pass

    def _on_model_completed(self, success: bool, summary: str):
        self.execution_completed.emit(success, summary)

    def _on_execution_completed(self, success: bool, summary: str):
        self.execution_completed.emit(success, summary)

    def _on_sequence_step_started(self, index: int, total: int, step: dict):
        pass

    def _on_sequence_step_completed(self, index: int, total: int, step: dict):
        pass

    def _on_vision_state_update(self, state: str, payload: dict):
        pass

    def _log(self, level: str, message: str, action: str = "", code: str = "") -> None:
        """Emit log entry signal"""
        metadata = {}
        if action:
            metadata["action"] = action
        if code:
            metadata["code"] = code
        self.log_entry_needed.emit(level, message, metadata)

    @staticmethod
    def parse_run_selection(selected: str) -> Tuple[Optional[str], Optional[str]]:
        """Parse run selection into (type, name)

        Returns:
            ("model", "GrabBlock") or ("recording", "Grab Cup v1") or ("sequence", "Production Run")
        """
        if selected.startswith("🤖 Model:"):
            return ("model", selected.replace("🤖 Model: ", ""))
        elif selected.startswith("🔗 Sequence:"):
            return ("sequence", selected.replace("🔗 Sequence: ", ""))
        elif selected.startswith("🎬 Action:"):
            # Note: "Action" in UI = "recording" in code
            return ("recording", selected.replace("🎬 Action: ", ""))
        else:
            return (None, None)
