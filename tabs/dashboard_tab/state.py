"""State persistence and selection helpers for the dashboard tab."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.config_compat import get_active_arm_index, set_active_arm_index


class DashboardStateMixin:
    """Mixin providing state management utilities for :class:`DashboardTab`."""

    def _apply_saved_dashboard_state(self) -> None:
        """Load persisted dashboard preferences or apply safe defaults."""
        state = self.config.setdefault("dashboard_state", {})

        speed_percent = state.get("speed_percent")
        if isinstance(speed_percent, int) and 10 <= speed_percent <= 120:
            self.master_speed = speed_percent / 100.0
        else:
            speed_percent = 100
            self.master_speed = speed_percent / 100.0
            state["speed_percent"] = speed_percent

        loop_value = state.get("loop_enabled")
        if isinstance(loop_value, bool):
            self.loop_enabled = loop_value
        else:
            self.loop_enabled = True
            state["loop_enabled"] = True

        saved_run = state.get("run_selection")
        if isinstance(saved_run, str) and saved_run:
            self._initial_run_selection = saved_run
        else:
            self._initial_run_selection = ""
            state.pop("run_selection", None)

        control_cfg = self.config.setdefault("control", {})
        control_cfg["speed_multiplier"] = self.master_speed
        control_cfg["loop_enabled"] = self.loop_enabled

        saved_arm = state.get("active_robot_arm_index")
        self.active_robot_arm_index = get_active_arm_index(self.config, preferred=saved_arm, arm_type="robot")
        state["active_robot_arm_index"] = self.active_robot_arm_index

    def _restore_run_selection(self) -> bool:
        """Attempt to re-select the last run item; return ``True`` if successful."""

        target = self._initial_run_selection or ""
        self._restoring_run_selection = True
        try:
            if target:
                index = self.run_combo.findText(target, Qt.MatchExactly)
                if index != -1:
                    self.run_combo.setCurrentIndex(index)
                    return True
            # Default to placeholder entry
            self.run_combo.setCurrentIndex(0)
            self._initial_run_selection = ""
            return False
        finally:
            self._restoring_run_selection = False

    def _persist_dashboard_state(self) -> None:
        """Persist loop, speed, and run preferences to ``config.json``."""

        state = self.config.setdefault("dashboard_state", {})
        state["speed_percent"] = int(round(self.master_speed * 100))
        state["loop_enabled"] = bool(self.loop_enabled)

        current_run = self.run_combo.currentText() if self.run_combo.count() else ""
        if current_run and not current_run.startswith("--"):
            state["run_selection"] = current_run
        else:
            state.pop("run_selection", None)

        control_cfg = self.config.setdefault("control", {})
        control_cfg["speed_multiplier"] = self.master_speed
        control_cfg["loop_enabled"] = self.loop_enabled

        active_arm = getattr(self, "active_robot_arm_index", None)
        if isinstance(active_arm, int):
            set_active_arm_index(self.config, active_arm, arm_type="robot")

        window = self.window()
        if hasattr(window, "save_config"):
            try:
                window.save_config()
            except Exception as exc:  # pragma: no cover - defensive logging
                self._append_log_entry(
                    "warning",
                    "Dashboard preferences were not saved.",
                    action=f"Details: {exc}",
                    code="persist_dashboard_failed",
                )

    def _append_log_entry(
        self,
        level: str,
        message: str,
        action: Optional[str] = None,
        code: Optional[str] = None,
    ) -> None:
        """Render a friendly log entry with simple dedupe logic."""

        clean_message = (message or "").strip()
        if not clean_message:
            return

        if code and self._last_log_code == code and self._last_log_message == clean_message:
            return
        if not code and self._last_log_message == clean_message:
            return

        icon_map = {
            "welcome": "👋",
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "success": "✅",
            "vision": "👀",
            "system": "🛠️",
            "action": "▶️",
            "speed": "🚀",
            "stop": "⏹️",
        }

        icon = icon_map.get(level, icon_map["info"])
        entry_lines = [f"{icon} {clean_message}"]

        if action:
            entry_lines.append(f"   Fix: {action.strip()}")

        entry = "\n".join(entry_lines)
        self.log_text.append(entry)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

        self._last_log_code = code
        self._last_log_message = clean_message

    def refresh_run_selector(self):
        """Populate RUN dropdown with models, sequences, and actions."""

        if not hasattr(self, "run_combo"):
            return

        self.run_combo.blockSignals(True)
        self.run_combo.clear()

        placeholder = "-- Select a model, sequence, or action --"
        self.run_combo.addItem(placeholder)

        sys.path.insert(0, str(Path(__file__).parent.parent))
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
        except Exception as exc:  # pragma: no cover - defensive logging
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
        if hasattr(self, "_rebuild_robot_arm_order"):
            self._rebuild_robot_arm_order()
        else:
            self._robot_total = 1 if self.config.get("robot") else 0

        for name in list(self._camera_status.keys()):
            if name not in self.camera_order:
                self._camera_status.pop(name)
        for name in self.camera_order:
            self._camera_status.setdefault(name, "empty")

        if hasattr(self, "_rebuild_camera_indicator_map"):
            self._rebuild_camera_indicator_map()

        self.camera_toggle_btn.setEnabled(bool(self.camera_order))
        self._refresh_active_camera_label()
        if self.camera_view_active:
            self.update_camera_previews(force=True)
        elif not self.camera_order:
            self.single_camera_preview.update_preview(None, "No camera configured.")

        if hasattr(self, "_refresh_arm_selector"):
            self._refresh_arm_selector()

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

        self.master_speed = aligned / 100.0
        self.speed_value_label.setText(f"{aligned}%")

        control_cfg = self.config.setdefault("control", {})
        control_cfg["speed_multiplier"] = self.master_speed

        if self.execution_worker and self.execution_worker.isRunning():
            try:
                self.execution_worker.set_speed_multiplier(self.master_speed)
            except Exception:  # pragma: no cover - worker may not expose setter
                pass
        if self.worker and hasattr(self.worker, "set_speed_multiplier"):
            try:
                self.worker.set_speed_multiplier(self.master_speed)
            except Exception:  # pragma: no cover - worker may be unavailable
                pass
        if not self._speed_initialized:
            self._speed_initialized = True
        self._persist_dashboard_state()
