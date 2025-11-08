"""State persistence helpers for the dashboard tab."""

from PySide6.QtCore import Qt


class DashboardStateMixin:
    """Mixin providing configuration persistence helpers."""

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

    def _restore_run_selection(self) -> bool:
        """Attempt to re-select the last run item; return True if successful."""
        target = self._initial_run_selection or ""
        self._restoring_run_selection = True
        try:
            if target:
                index = self.run_combo.findText(target, Qt.MatchExactly)
                if index != -1:
                    self.run_combo.setCurrentIndex(index)
                    return True
            self.run_combo.setCurrentIndex(0)
            self._initial_run_selection = ""
            return False
        finally:
            self._restoring_run_selection = False

    def _persist_dashboard_state(self) -> None:
        """Persist loop, speed, and run preferences to config.json."""
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

        window = self.window()
        if hasattr(window, "save_config"):
            try:
                window.save_config()
            except Exception as exc:
                self._append_log_entry(
                    "warning",
                    "Dashboard preferences were not saved.",
                    action=f"Details: {exc}",
                    code="persist_dashboard_failed",
                )


__all__ = ["DashboardStateMixin"]
