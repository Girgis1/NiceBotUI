"""Run execution helpers for the dashboard tab."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from robot_worker import RobotWorker
from utils.execution_manager import ExecutionWorker
from utils.log_messages import LogEntry, translate_worker_message


class DashboardExecutionMixin:
    def on_run_selection_changed(self, text):
        """Handle RUN selector change - show/hide checkpoint dropdown"""
        print(f"[DASHBOARD] Run selection changed: {text}")

        if text.startswith("🤖 Model:"):
            # Show checkpoint dropdown for models
            self.checkpoint_combo.show()

            # Extract model name and load checkpoints
            model_name = text.replace("🤖 Model: ", "")
            self.load_checkpoints_for_model(model_name)
        else:
            # Hide checkpoint dropdown for sequences and actions
            self.checkpoint_combo.hide()
            self.checkpoint_combo.clear()

        if text and not text.startswith("--"):
            self._initial_run_selection = text
        else:
            self._initial_run_selection = ""

        if not self._restoring_run_selection:
            self._persist_dashboard_state()

    def load_checkpoints_for_model(self, model_name: str):
        """Load checkpoints for the selected model"""
        self.checkpoint_combo.blockSignals(True)
        self.checkpoint_combo.clear()

        try:
            train_dir = Path(self.config["policy"].get("base_path", ""))
            checkpoints_dir = train_dir / model_name / "checkpoints"

            if checkpoints_dir.exists():
                checkpoints = []
                for item in checkpoints_dir.iterdir():
                    if item.is_dir() and (item / "pretrained_model").exists():
                        checkpoints.append(item.name)

                # Sort: "last" first, then numeric descending
                def sort_key(name):
                    if name == "last":
                        return (0, 0)
                    try:
                        return (1, -int(name))
                    except ValueError:
                        return (2, name)

                checkpoints.sort(key=sort_key)

                for ckpt in checkpoints:
                    display = f"✓ {ckpt}" if ckpt == "last" else ckpt
                    self.checkpoint_combo.addItem(display, ckpt)

                # Auto-select "last"
                for i in range(self.checkpoint_combo.count()):
                    if self.checkpoint_combo.itemData(i) == "last":
                        self.checkpoint_combo.setCurrentIndex(i)
                        break
            else:
                self.checkpoint_combo.addItem("No checkpoints")

        except Exception as e:
            print(f"[DASHBOARD] Error loading checkpoints: {e}")
            self.checkpoint_combo.addItem("Error loading")

        self.checkpoint_combo.blockSignals(False)

    def on_checkpoint_changed(self, text):
        """Handle checkpoint selection"""
        # Update config when checkpoint changes
        selected_run = self.run_combo.currentText()
        if selected_run.startswith("🤖 Model:"):
            model_name = selected_run.replace("🤖 Model: ", "")
            checkpoint_index = self.checkpoint_combo.currentIndex()

            if checkpoint_index >= 0:
                checkpoint_name = self.checkpoint_combo.itemData(checkpoint_index)
                if checkpoint_name:
                    try:
                        train_dir = Path(self.config["policy"].get("base_path", ""))
                        new_path = train_dir / model_name / "checkpoints" / checkpoint_name / "pretrained_model"
                        self.config["policy"]["path"] = str(new_path)
                        print(f"[DASHBOARD] Policy path updated to: {new_path}")
                    except Exception as e:
                        print(f"[DASHBOARD] Error updating policy path: {e}")

    def refresh_policy_list(self):
        """Legacy method - now uses refresh_run_selector"""
        self.refresh_run_selector()

    def validate_config(self):
        """Validate configuration

        NOTE: Status indicators are now managed by device_manager
        This method is kept for backwards compatibility but doesn't update indicators
        """
        # Status indicators are now updated by device_manager signals
        # We don't override them here to avoid conflicts
        pass

    def update_throbber_progress(self):
        """Update throbber"""
        self.throbber_progress += 1
        if self.throbber_progress > 100:
            self.throbber_progress = 0
        self.throbber.set_progress(self.throbber_progress)
        if self.compact_throbber:
            self.compact_throbber.set_progress(self.throbber_progress)

    def check_connections_background(self):
        """Check connections - now handled by device_manager"""
        if not self.device_manager:
            return
        try:
            self.device_manager.refresh_status()
        except Exception as exc:  # pragma: no cover - defensive
            self._append_log_entry(
                "warning",
                "Device status check failed.",
                action=f"Details: {exc}",
                code="device_refresh_failed",
            )


    def toggle_start_stop(self):
        """Toggle start/stop"""
        if self.start_stop_btn.isChecked():
            self.start_run()
        else:
            self.stop_run()

    def start_run(self):
        """Start robot run - unified execution for models, recordings, and sequences"""
        if self.is_running:
            self._append_log_entry(
                "warning",
                "A run is already active. Press Stop before starting another.",
            )
            return

        # Get selected item
        selected = self.run_combo.currentText()

        self._vision_state_active = False
        self._last_vision_signature = None
        self.active_vision_zones.clear()
        self._last_preview_timestamp = 0.0
        if self.camera_view_active:
            self.update_camera_previews(force=True)

        if selected.startswith("--"):
            self._append_log_entry(
                "warning",
                "Choose something to run from the list first.",
            )
            self.start_stop_btn.setChecked(False)
            return

        # Parse selection
        execution_type, execution_name = self._parse_run_selection(selected)

        if not execution_type or not execution_name:
            self._append_log_entry(
                "error",
                "We couldn't load that option. Pick a model, sequence, or action from the list.",
            )
            self.start_stop_btn.setChecked(False)
            return

        # Update UI
        self._fatal_error_active = False
        self._last_log_code = None
        self._last_log_message = None
        self.start_stop_btn.setText("STOP")
        self.is_running = True
        self.start_time = datetime.now()
        self.timer.start(1000)  # Update elapsed time every second

        type_label = {
            "model": "Model",
            "sequence": "Sequence",
            "recording": "Action",
        }.get(execution_type, "Run")
        self._append_log_entry(
            "action",
            f"Starting {type_label} “{execution_name}”.",
            code="run_start",
        )
        self._append_log_entry(
            "speed",
            f"Robot speed set to {int(self.master_speed * 100)}%.",
            code="run_speed",
        )
        self.action_label.setText(f"Starting {execution_type}...")

        # Handle models based on execution mode
        if execution_type == "model":
            local_mode = self.config.get("policy", {}).get("local_mode", True)

            if local_mode:
                # Local mode: Use ExecutionWorker (which uses lerobot-record)
                self._append_log_entry(
                    "system",
                    "Running directly on this computer.",
                    code="run_local_mode",
                )
                # Get checkpoint and episode settings from UI
                checkpoint_name = self.checkpoint_combo.currentData() if self.checkpoint_combo.isVisible() else "last"

                if self.loop_enabled:
                    num_episodes = -1  # Infinite loop
                    self._append_log_entry(
                        "info",
                        "Loop mode is ON — the run will repeat until you stop it.",
                        code="loop_enabled",
                    )
                else:
                    num_episodes = 1

                self._start_execution_worker(execution_type, execution_name, {
                    "checkpoint": checkpoint_name,
                    "duration": self.config.get("control", {}).get("episode_time_s", 30),
                    "num_episodes": num_episodes
                })
            else:
                # Server mode: Use RobotWorker (async inference)
                self._append_log_entry(
                    "system",
                    "Connecting to the NiceBot server for this run.",
                    code="run_server_mode",
                )
                self._start_model_execution(execution_name)
        else:
            # For recordings and sequences, use ExecutionWorker
            options = {}
            if execution_type in {"sequence", "recording"}:
                options["loop"] = self.loop_enabled
            self._start_execution_worker(execution_type, execution_name, options)

    def _start_model_execution(self, model_name: str):
        """Start model execution using RobotWorker directly"""
        # Get checkpoint path
        checkpoint_name = self.checkpoint_combo.currentData() if self.checkpoint_combo.isVisible() else "last"

        try:
            train_dir = Path(self.config["policy"].get("base_path", ""))
            checkpoint_path = train_dir / model_name / "checkpoints" / checkpoint_name / "pretrained_model"

            # Update config for this run
            model_config = self.config.copy()
            model_config.setdefault("control", {})["speed_multiplier"] = self.master_speed
            model_config["policy"]["path"] = str(checkpoint_path)

            checkpoint_display = checkpoint_name if isinstance(checkpoint_name, str) else str(checkpoint_name)
            self._append_log_entry(
                "action",
                f"Loading model “{model_name}” ({checkpoint_display}). This may take a moment.",
                code="model_loading",
            )

            # Stop any existing worker first
            if self.worker and self.worker.isRunning():
                self._append_log_entry(
                    "warning",
                    "Stopping the previous run before starting a new one…",
                    code="stopping_previous_worker",
                )
                self.worker.stop()
                self.worker.wait(2000)

            # Create RobotWorker directly (not nested in another thread)
            self.worker = RobotWorker(model_config)

            # Connect signals with error handling
            self.worker.status_update.connect(self._on_status_update)
            self.worker.log_message.connect(self._on_log_message)
            self.worker.progress_update.connect(self._on_progress_update)
            self.worker.run_completed.connect(self._on_model_completed)
            self.worker.finished.connect(self._on_worker_thread_finished)

            # Start worker
            self.worker.start()

        except Exception as e:
            import traceback
            self._append_log_entry(
                "error",
                "We couldn't start the model run.",
                action=f"Details: {e}",
                code="model_start_failed",
            )
            self._reset_ui_after_run()

    def _start_execution_worker(self, execution_type: str, execution_name: str, options: dict = None):
        """Start ExecutionWorker for recordings and sequences"""
        merged_options = dict(options or {})
        merged_options["speed_multiplier"] = self.master_speed

        # Create and start execution worker
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

    def run_sequence(self, sequence_name: str, loop: bool = False):
        """Run a sequence from the Sequence tab

        Args:
            sequence_name: Name of the sequence to run
            loop: Whether to loop the sequence
        """
        if self.is_running:
            self._append_log_entry(
                "warning",
                "A run is already active. Press Stop before starting another.",
            )
            return

        self._fatal_error_active = False
        self._last_log_code = None
        self._last_log_message = None
        self._append_log_entry(
            "action",
            f"Starting Sequence “{sequence_name}”.",
            code="sequence_start",
        )
        if loop:
            self._append_log_entry(
                "info",
                "Loop mode is ON — the run will repeat until you stop it.",
                code="loop_enabled",
            )

        # Update UI state
        self.is_running = True
        self.start_stop_btn.setChecked(True)
        self.start_stop_btn.setText("⏹ STOP")
        self.action_label.setText(f"Sequence: {sequence_name}")
        self._vision_state_active = False
        self._last_vision_signature = None

        # Start execution worker
        self._start_execution_worker("sequence", sequence_name, {"loop": loop})

    def stop_run(self, *, quiet: bool = False):
        """Stop robot run"""
        if not self.is_running:
            return

        if self._stopping_run:
            return
        self._stopping_run = True

        if not quiet:
            self._append_log_entry("stop", "Stopping the current run…", code="run_stopping")
            self.action_label.setText("Stopping…")

        # Stop execution worker (for recordings/sequences)
        if self.execution_worker and self.execution_worker.isRunning():
            self.execution_worker.stop()
            self.execution_worker.wait(5000)  # Wait up to 5 seconds

        # Stop robot worker (for models)
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(5000)  # Wait up to 5 seconds

        # Reset UI
        self._reset_ui_after_run()
        self._stopping_run = False

    def _parse_run_selection(self, selected: str) -> tuple:
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

    def _set_action_label_style(self, background: str):
        self.action_label.setStyleSheet(self._action_label_style_template.format(bg=background))

    def record_vision_status(self, state: str, detail: str, payload: Optional[dict] = None):
        payload = payload or {}
        countdown = payload.get("countdown")
        metric = payload.get("metric")
        zones_raw = payload.get("zones") or []
        zones = [z if isinstance(z, str) else str(z) for z in zones_raw]

        color_map = {
            "triggered": "#4CAF50",
            "idle": "#FFB300",
            "watching": "#383838",
            "complete": "#4CAF50",
            "error": "#b71c1c",
            "clear": "#383838",
        }

        bg = color_map.get(state, "#383838")
        self._set_action_label_style(bg)

        message = detail
        if countdown is not None:
            message = f"{detail} • {countdown}s"
        if metric is not None and state == "triggered":
            message = f"{detail} • metric={metric:.3f}"

        if state in {"idle", "watching", "triggered"}:
            self._vision_state_active = True
        elif state in {"complete", "clear", "error"}:
            self._vision_state_active = False

        if not self._vision_state_active and state in {"complete", "clear"}:
            self._set_action_label_style("#383838")

        self.action_label.setText(message)

        signature = (state, countdown, tuple(zones))
        if signature != self._last_vision_signature:
            log_message = message
            if zones:
                zone_list = ", ".join(zones)
                log_message = f"{message} [{zone_list}]"
            self._append_log_entry("vision", log_message, code=f"vision_{state}")
            self._last_vision_signature = signature

    def _on_status_update(self, status: str):
        """Handle status update from worker"""
        if self._vision_state_active:
            return
        self._set_action_label_style("#383838")
        self.action_label.setText(status)

    def _on_log_message(self, level: str, message: str):
        """Handle log message from worker"""
        entry = translate_worker_message(level, message)
        if not entry:
            return

        # Suppress success messages once a fatal error has been shown.
        if self._fatal_error_active and entry.level == "success":
            return

        if entry.fatal and not self._fatal_error_active:
            self._fatal_error_active = True
            self._append_log_entry(entry.level, entry.message, entry.action, entry.code)
            self._handle_fatal_error(entry)
            return

        if entry.fatal:
            return

        self._append_log_entry(entry.level, entry.message, entry.action, entry.code)

    def _handle_fatal_error(self, entry: LogEntry) -> None:
        """Stop the current run and provide guidance after a fatal error."""
        if self.loop_button.isChecked():
            self.loop_button.setChecked(False)
            self._append_log_entry(
                "info",
                "Loop mode turned off to avoid repeated errors.",
                code="loop_disabled_auto",
            )

        if self.is_running:
            self.stop_run(quiet=True)

        self._set_action_label_style("#b71c1c")
        self.action_label.setText("Fix the issue, then press START.")

    def _on_progress_update(self, current: int, total: int):
        """Handle progress update from worker"""
        if total > 0:
            progress = int((current / total) * 100)
            # Could update a progress bar here if we add one

    def _on_sequence_step_started(self, index: int, total: int, step: dict):
        seq_tab = self._get_sequence_tab()
        if seq_tab:
            seq_tab.highlight_running_step(index, step)

    def _on_sequence_step_completed(self, index: int, total: int, step: dict):
        # Placeholder for future use (e.g., marking completed)
        pass

    def _on_vision_state_update(self, state: str, payload: dict):
        message = payload.get("message", state.title())
        camera_name = payload.get("camera_name")
        zone_payload = payload.get("zone_polygons") or []

        if camera_name:
            if state in {"idle", "watching", "triggered"} and zone_payload:
                self.active_vision_zones[camera_name] = zone_payload
            elif state in {"complete", "clear", "error"}:
                self.active_vision_zones.pop(camera_name, None)

        self.record_vision_status(state, message, payload)
        if camera_name and self.camera_view_active and camera_name == self.active_camera_name:
            self.update_camera_previews(force=True)

    def _on_execution_completed(self, success: bool, summary: str):
        """Handle execution completion (for recordings/sequences)"""
        status_level = "success" if success else "error"
        self._append_log_entry(status_level, summary.strip(), code="execution_summary")

        if success:
            self.action_label.setText("✓ Completed")
        else:
            self.action_label.setText("✗ Failed")
        seq_tab = self._get_sequence_tab()
        if seq_tab:
            seq_tab.clear_running_highlight()

        # Reset UI
        self._reset_ui_after_run()

    def _on_model_completed(self, success: bool, summary: str):
        """Handle model execution completion"""
        try:
            status_level = "success" if success else "error"
            self._append_log_entry(status_level, summary.strip(), code="model_summary")

            if success:
                self.action_label.setText("✓ Model completed")
            else:
                self.action_label.setText("✗ Model failed")
                # Show user-friendly message
                self._append_log_entry(
                    "info",
                    "Check the robot connection and the model path, then try again.",
                    code="model_check_connection",
                )
        except Exception as e:
            self._append_log_entry(
                "error",
                "We ran into a problem while updating the dashboard after the run.",
                action=f"Details: {e}",
                code="model_completion_error",
            )
        finally:
            # Always reset UI, even if there's an error
            self._reset_ui_after_run()

    def _get_sequence_tab(self):
        parent = self.parent()
        while parent:
            if hasattr(parent, "sequence_tab"):
                return getattr(parent, "sequence_tab")
            parent = parent.parent()
        return None

    def _on_worker_thread_finished(self):
        """Handle worker thread finished (cleanup)"""
        try:
            if self.worker:
                self.worker.deleteLater()
        except Exception as e:
            self._append_log_entry(
                "error",
                "There was a problem cleaning up the worker thread.",
                action=f"Details: {e}",
                code="worker_thread_cleanup_error",
            )

    def _reset_ui_after_run(self):
        """Reset UI state after run completes or stops"""
        try:
            self._stopping_run = False
            self._fatal_error_active = False
            self._last_log_code = None
            self._last_log_message = None
            self.is_running = False
            self.start_stop_btn.setChecked(False)
            self.start_stop_btn.setText("START")
            self.timer.stop()
            self._vision_state_active = False
            self._last_vision_signature = None
            self.active_vision_zones.clear()
            self._set_action_label_style("#383838")
            seq_tab = self._get_sequence_tab()
            if seq_tab:
                seq_tab.clear_running_highlight()

            # Clean up execution worker (recordings/sequences)
            if self.execution_worker:
                try:
                    if self.execution_worker.isRunning():
                        self.execution_worker.quit()
                        self.execution_worker.wait(1000)
                except:
                    pass
                self.execution_worker = None

            # Clean up robot worker (models) - be very careful here
            if self.worker:
                try:
                    if self.worker.isRunning():
                        self.worker.quit()
                        self.worker.wait(2000)
                    # Mark for deletion but don't set to None yet
                    # Let Qt handle the cleanup
                    self.worker.deleteLater()
                except Exception as e:
                    self._append_log_entry(
                        "warning",
                        f"Worker cleanup warning: {e}",
                        code="worker_cleanup_warning",
                    )
                finally:
                    self.worker = None
        except Exception as e:
            self._append_log_entry(
                "error",
                "We ran into a problem while resetting the dashboard state.",
                action=f"Details: {e}",
                code="reset_ui_error",
            )

    def run_from_dashboard(self):
        """Execute the selected RUN item (same as pressing START)."""
        if not self.is_running:
            self.start_stop_btn.setChecked(True)
            self.start_run()

    def update_elapsed_time(self):
        """Update the elapsed run timer."""
        if self.start_time:
            self.elapsed_seconds = int((datetime.now() - self.start_time).total_seconds())
            minutes = self.elapsed_seconds // 60
            seconds = self.elapsed_seconds % 60
            self.time_label.setText(f"Time: {minutes:02d}:{seconds:02d}")

    def on_robot_status_changed(self, status: str):
        """Handle robot status change from the device manager."""
        if self.robot_indicator1:
            if status == "empty":
                self.robot_indicator1.set_null()
                if self.robot_indicator2:
                    self.robot_indicator2.set_null()
            elif status == "online":
                self.robot_indicator1.set_connected(True)
            else:
                self.robot_indicator1.set_connected(False)
        self._robot_status = status
        self._update_status_summaries()

    def on_camera_status_changed(self, camera_name: str, status: str):
        """Handle camera status change from the device manager."""
        indicator = None
        if hasattr(self, "_ensure_camera_indicator"):
            indicator = self._ensure_camera_indicator(camera_name)

        if indicator and hasattr(self, "_apply_indicator_status"):
            self._apply_indicator_status(indicator, status)

        self._camera_status[camera_name] = status
        self._update_status_summaries()

        if self.camera_view_active and camera_name == self.active_camera_name:
            self.update_camera_previews(force=True)

    def _update_status_summaries(self) -> None:
        """Update compact status summary labels."""
        if not hasattr(self, "robot_summary_label") or not hasattr(self, "camera_summary_label"):
            return

        robot_online = 1 if self._robot_status == "online" else 0
        self.robot_summary_label.setText(f"R:{robot_online}/{self._robot_total}")

        camera_total = len(self._camera_status)
        camera_online = sum(1 for state in self._camera_status.values() if state == "online")
        self.camera_summary_label.setText(f"C:{camera_online}/{camera_total}")

    def on_discovery_log(self, message: str):
        """Handle discovery log messages from the device manager."""
        self._append_log_entry("info", message, code="discovery_log")
