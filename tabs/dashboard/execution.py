"""Execution and run management mixin for the dashboard tab."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from robot_worker import RobotWorker
from utils.execution_manager import ExecutionWorker
from utils.log_messages import LogEntry, translate_worker_message


class DashboardExecutionMixin:
    """Mixin that handles starting, stopping, and monitoring runs."""

    def refresh_run_selector(self) -> None:
        self.run_combo.blockSignals(True)
        self.run_combo.clear()

        self.run_combo.addItem("-- Select Item --")
        self.run_combo.model().item(0).setEnabled(False)

        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from utils.actions_manager import ActionsManager
        from utils.sequences_manager import SequencesManager
        from utils.mode_utils import get_mode_icon

        actions_mgr = ActionsManager()
        sequences_mgr = SequencesManager()

        try:
            train_dir = Path(self.config["policy"].get("base_path", ""))
            if train_dir.exists():
                for item in sorted(train_dir.iterdir()):
                    if item.is_dir() and (item / "checkpoints").exists():
                        self.run_combo.addItem(f"🤖 Model: {item.name}")
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[DASHBOARD] Error loading models: {exc}")

        sequences = sequences_mgr.list_sequences()
        if sequences:
            for seq in sequences:
                self.run_combo.addItem(f"🔗 Sequence: {seq}")

        actions = actions_mgr.list_actions()
        if actions:
            for action in actions:
                action_data = actions_mgr.load_action(action)
                mode = action_data.get("mode", "solo") if action_data else "solo"
                mode_icon = get_mode_icon(mode)
                self.run_combo.addItem(f"{mode_icon} 🎬 Action: {action}")

        self.run_combo.blockSignals(False)
        self.camera_order = list(self.config.get("cameras", {}).keys())
        self.vision_zones = self._load_vision_zones()
        self._robot_total = 1 if self.config.get("robot") else 0

        for name in list(self._camera_status.keys()):
            if name not in self.camera_order:
                self._camera_status.pop(name)
        for name in self.camera_order:
            self._camera_status.setdefault(name, "empty")

        self.camera_toggle_btn.setEnabled(bool(self.camera_order))
        self._refresh_active_camera_label()
        if self.camera_view_active:
            self.update_camera_previews(force=True)
        elif not self.camera_order:
            self.single_camera_preview.update_preview(None, "No camera configured.")

        self._update_status_summaries()
        restored = self._restore_run_selection()
        if not restored:
            self._persist_dashboard_state()

    def _refresh_loop_button(self) -> None:
        if self.loop_enabled:
            text = "Loop\nON"
            style = """
                QPushButton {
                    background-color: #4CAF50;
                    color: #ffffff;
                    border: 2px solid #43A047;
                    border-radius: 10px;
                    font-size: 26px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #43A047;
                }
            """
        else:
            text = "Loop\nOFF"
            style = """
                QPushButton {
                    background-color: #424242;
                    color: #ffffff;
                    border: 2px solid #515151;
                    border-radius: 10px;
                    font-size: 26px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                }
            """
        self.loop_button.setText(text)
        self.loop_button.setStyleSheet(style)

    def on_loop_button_toggled(self, checked: bool) -> None:
        self.loop_enabled = checked
        self._refresh_loop_button()
        control_cfg = self.config.setdefault("control", {})
        control_cfg["loop_enabled"] = checked
        if checked:
            self._append_log_entry(
                "info",
                "Loop mode is ON. The run will repeat until you press Stop.",
                code="loop_enabled",
            )
        else:
            self._append_log_entry(
                "info",
                "Loop mode is OFF. The run will finish after one pass.",
                code="loop_disabled",
            )
        self._persist_dashboard_state()

    def on_speed_slider_changed(self, value: int) -> None:
        aligned = max(10, min(120, 5 * round(value / 5)))
        if aligned != value:
            self.speed_slider.blockSignals(True)
            self.speed_slider.setValue(aligned)
            self.speed_slider.blockSignals(False)
            return

        self.master_speed = aligned / 100.0
        self.speed_value_label.setText(f"{aligned}%")
        control_cfg = self.config.setdefault("control", {})
        control_cfg["speed_multiplier"] = self.master_speed
        self._persist_dashboard_state()

    def on_run_selection_changed(self, text: str) -> None:
        print(f"[DASHBOARD] Run selection changed: {text}")

        if text.startswith("🤖 Model:"):
            self.checkpoint_combo.show()
            model_name = text.replace("🤖 Model: ", "")
            self.load_checkpoints_for_model(model_name)
        else:
            self.checkpoint_combo.hide()
            self.checkpoint_combo.clear()

        if text and not text.startswith("--"):
            self._initial_run_selection = text
        else:
            self._initial_run_selection = ""

        if not self._restoring_run_selection:
            self._persist_dashboard_state()

    def load_checkpoints_for_model(self, model_name: str) -> None:
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

                for i in range(self.checkpoint_combo.count()):
                    if self.checkpoint_combo.itemData(i) == "last":
                        self.checkpoint_combo.setCurrentIndex(i)
                        break
            else:
                self.checkpoint_combo.addItem("No checkpoints")

        except Exception as exc:  # pragma: no cover - defensive
            print(f"[DASHBOARD] Error loading checkpoints: {exc}")
            self.checkpoint_combo.addItem("Error loading")

        self.checkpoint_combo.blockSignals(False)

    def on_checkpoint_changed(self, text: str) -> None:
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
                    except Exception as exc:  # pragma: no cover - defensive
                        print(f"[DASHBOARD] Error updating policy path: {exc}")

    def refresh_policy_list(self) -> None:
        self.refresh_run_selector()

    def toggle_start_stop(self) -> None:
        if self.start_stop_btn.isChecked():
            self.start_run()
        else:
            self.stop_run()

    def start_run(self) -> None:
        if self.is_running:
            self._append_log_entry(
                "warning",
                "A run is already active. Press Stop before starting another.",
            )
            return

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

        execution_type, execution_name = self._parse_run_selection(selected)

        if not execution_type or not execution_name:
            self._append_log_entry(
                "error",
                "We couldn't load that option. Pick a model, sequence, or action from the list.",
            )
            self.start_stop_btn.setChecked(False)
            return

        self._fatal_error_active = False
        self._last_log_code = None
        self._last_log_message = None
        self.start_stop_btn.setText("STOP")
        self.is_running = True
        self.start_time = datetime.now()
        self.timer.start(1000)

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

        if execution_type == "model":
            local_mode = self.config.get("policy", {}).get("local_mode", True)

            if local_mode:
                self._append_log_entry(
                    "system",
                    "Running directly on this computer.",
                    code="run_local_mode",
                )
                checkpoint_name = self.checkpoint_combo.currentData() if self.checkpoint_combo.isVisible() else "last"

                if self.loop_enabled:
                    num_episodes = -1
                    self._append_log_entry(
                        "info",
                        "Loop mode is ON — the run will repeat until you stop it.",
                        code="loop_enabled",
                    )
                else:
                    num_episodes = 1

                self._start_execution_worker(
                    execution_type,
                    execution_name,
                    {
                        "checkpoint": checkpoint_name,
                        "duration": self.config.get("control", {}).get("episode_time_s", 30),
                        "num_episodes": num_episodes,
                    },
                )
            else:
                self._append_log_entry(
                    "system",
                    "Connecting to the NiceBot server for this run.",
                    code="run_server_mode",
                )
                self._start_model_execution(execution_name)
        else:
            options = {}
            if execution_type in {"sequence", "recording"}:
                options["loop"] = self.loop_enabled
            self._start_execution_worker(execution_type, execution_name, options)

    def _start_model_execution(self, model_name: str) -> None:
        checkpoint_name = self.checkpoint_combo.currentData() if self.checkpoint_combo.isVisible() else "last"

        try:
            train_dir = Path(self.config["policy"].get("base_path", ""))
            checkpoint_path = train_dir / model_name / "checkpoints" / checkpoint_name / "pretrained_model"

            model_config = self.config.copy()
            model_config.setdefault("control", {})["speed_multiplier"] = self.master_speed
            model_config["policy"]["path"] = str(checkpoint_path)

            checkpoint_display = checkpoint_name if isinstance(checkpoint_name, str) else str(checkpoint_name)
            self._append_log_entry(
                "action",
                f"Loading model “{model_name}” ({checkpoint_display}). This may take a moment.",
                code="model_loading",
            )

            if self.worker and self.worker.isRunning():
                self._append_log_entry(
                    "warning",
                    "Stopping the previous run before starting a new one…",
                    code="stopping_previous_worker",
                )
                self.worker.stop()
                self.worker.wait(2000)

            self.worker = RobotWorker(model_config)

            self.worker.status_update.connect(self._on_status_update)
            self.worker.log_message.connect(self._on_log_message)
            self.worker.progress_update.connect(self._on_progress_update)
            self.worker.run_completed.connect(self._on_model_completed)
            self.worker.finished.connect(self._on_worker_thread_finished)

            self.worker.start()

        except Exception as exc:  # pragma: no cover - defensive
            import traceback

            traceback.print_exc()
            self._append_log_entry(
                "error",
                "We couldn't start the model run.",
                action=f"Details: {exc}",
                code="model_start_failed",
            )
            self._reset_ui_after_run()

    def _start_execution_worker(
        self, execution_type: str, execution_name: str, options: Optional[dict] = None
    ) -> None:
        merged_options = dict(options or {})
        merged_options["speed_multiplier"] = self.master_speed

        self.execution_worker = ExecutionWorker(
            self.config,
            execution_type,
            execution_name,
            merged_options,
        )

        self.execution_worker.status_update.connect(self._on_status_update)
        self.execution_worker.log_message.connect(self._on_log_message)
        self.execution_worker.progress_update.connect(self._on_progress_update)
        self.execution_worker.execution_completed.connect(self._on_execution_completed)
        self.execution_worker.sequence_step_started.connect(self._on_sequence_step_started)
        self.execution_worker.sequence_step_completed.connect(self._on_sequence_step_completed)
        self.execution_worker.vision_state_update.connect(self._on_vision_state_update)

        self.execution_worker.set_speed_multiplier(self.master_speed)
        self.execution_worker.start()

    def run_sequence(self, sequence_name: str, loop: bool = False) -> None:
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

        self.is_running = True
        self.start_stop_btn.setChecked(True)
        self.start_stop_btn.setText("⏹ STOP")
        self.action_label.setText(f"Sequence: {sequence_name}")
        self._vision_state_active = False
        self._last_vision_signature = None

        self._start_execution_worker("sequence", sequence_name, {"loop": loop})

    def stop_run(self, *, quiet: bool = False) -> None:
        if not self.is_running:
            return

        if self._stopping_run:
            return
        self._stopping_run = True

        if not quiet:
            self._append_log_entry("stop", "Stopping the current run…", code="run_stopping")
            self.action_label.setText("Stopping…")

        if self.execution_worker and self.execution_worker.isRunning():
            self.execution_worker.stop()
            self.execution_worker.wait(5000)

        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(5000)

        self._reset_ui_after_run()
        self._stopping_run = False

    def _parse_run_selection(self, selected: str) -> Tuple[Optional[str], Optional[str]]:
        if selected.startswith("🤖 Model:"):
            return ("model", selected.replace("🤖 Model: ", ""))
        if selected.startswith("🔗 Sequence:"):
            return ("sequence", selected.replace("🔗 Sequence: ", ""))
        if selected.startswith("🎬 Action:"):
            return ("recording", selected.replace("🎬 Action: ", ""))
        return (None, None)

    def _set_action_label_style(self, background: str) -> None:
        self.action_label.setStyleSheet(self._action_label_style_template.format(bg=background))

    def record_vision_status(self, state: str, detail: str, payload: Optional[dict] = None) -> None:
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

    def _on_status_update(self, status: str) -> None:
        if self._vision_state_active:
            return
        self._set_action_label_style("#383838")
        self.action_label.setText(status)

    def _on_log_message(self, level: str, message: str) -> None:
        entry = translate_worker_message(level, message)
        if not entry:
            return

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

    def _on_progress_update(self, current: int, total: int) -> None:
        if total > 0:
            _ = int((current / total) * 100)

    def _on_sequence_step_started(self, index: int, total: int, step: dict) -> None:
        seq_tab = self._get_sequence_tab()
        if seq_tab:
            seq_tab.highlight_running_step(index, step)

    def _on_sequence_step_completed(self, index: int, total: int, step: dict) -> None:
        pass

    def _on_vision_state_update(self, state: str, payload: dict) -> None:
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

    def _on_execution_completed(self, success: bool, summary: str) -> None:
        status_level = "success" if success else "error"
        self._append_log_entry(status_level, summary.strip(), code="execution_summary")

        if success:
            self.action_label.setText("✓ Completed")
        else:
            self.action_label.setText("✗ Failed")
        seq_tab = self._get_sequence_tab()
        if seq_tab:
            seq_tab.clear_running_highlight()

        self._reset_ui_after_run()

    def _on_model_completed(self, success: bool, summary: str) -> None:
        try:
            status_level = "success" if success else "error"
            self._append_log_entry(status_level, summary.strip(), code="model_summary")

            if success:
                self.action_label.setText("✓ Model completed")
            else:
                self.action_label.setText("✗ Model failed")
                self._append_log_entry(
                    "info",
                    "Check the robot connection and the model path, then try again.",
                    code="model_check_connection",
                )
        except Exception as exc:  # pragma: no cover - defensive
            self._append_log_entry(
                "error",
                "We ran into a problem while updating the dashboard after the run.",
                action=f"Details: {exc}",
                code="model_completion_error",
            )
        finally:
            self._reset_ui_after_run()

    def _get_sequence_tab(self):
        parent = self.parent()
        while parent:
            if hasattr(parent, "sequence_tab"):
                return getattr(parent, "sequence_tab")
            parent = parent.parent()
        return None

    def _on_worker_thread_finished(self) -> None:
        try:
            if self.worker:
                self.worker.deleteLater()
        except Exception as exc:  # pragma: no cover - defensive
            self._append_log_entry(
                "error",
                "There was a problem cleaning up the worker thread.",
                action=f"Details: {exc}",
                code="worker_thread_cleanup_error",
            )

    def _reset_ui_after_run(self) -> None:
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

            if self.execution_worker:
                try:
                    if self.execution_worker.isRunning():
                        self.execution_worker.quit()
                        self.execution_worker.wait(1000)
                except Exception:
                    pass
                self.execution_worker = None

            if self.worker:
                try:
                    if self.worker.isRunning():
                        self.worker.quit()
                        self.worker.wait(2000)
                    self.worker.deleteLater()
                except Exception as exc:  # pragma: no cover - defensive
                    self._append_log_entry(
                        "warning",
                        f"Worker cleanup warning: {exc}",
                        code="worker_cleanup_warning",
                    )
                finally:
                    self.worker = None
        except Exception as exc:  # pragma: no cover - defensive
            self._append_log_entry(
                "error",
                "We ran into a problem while resetting the dashboard state.",
                action=f"Details: {exc}",
                code="reset_ui_error",
            )

    def run_from_dashboard(self) -> None:
        if not self.is_running:
            self.start_stop_btn.setChecked(True)
            self.start_run()

    def update_elapsed_time(self) -> None:
        if self.start_time:
            self.elapsed_seconds = int((datetime.now() - self.start_time).total_seconds())
            minutes = self.elapsed_seconds // 60
            seconds = self.elapsed_seconds % 60
            self.time_label.setText(f"Time: {minutes:02d}:{seconds:02d}")


__all__ = ["DashboardExecutionMixin"]
