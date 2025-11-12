"""Home movement helpers for the dashboard tab."""

from __future__ import annotations

from utils.config_compat import get_enabled_arms
from utils.home_sequence import HomeSequenceRunner


class DashboardHomeMixin:
    """Mixin that encapsulates homing logic for :class:`DashboardTab`."""

    def go_home(self) -> None:
        """Move all enabled robot arms to their configured home positions."""
        self._ensure_home_sequence_runner()

        if self._home_sequence_runner.is_running:
            self._append_log_entry(
                "warning",
                "Home command already running.",
                code="home_already_running",
            )
            return

        if not self._start_dashboard_homing():
            return

    # ------------------------------------------------------------------ runner helpers
    def _ensure_home_sequence_runner(self) -> None:
        if hasattr(self, "_home_sequence_runner") and self._home_sequence_runner:
            return

        self._home_sequence_runner = HomeSequenceRunner(self)
        self._home_sequence_runner.progress.connect(self._on_home_progress)
        self._home_sequence_runner.arm_started.connect(self._on_home_arm_started)
        self._home_sequence_runner.arm_finished.connect(self._on_home_arm_finished)
        self._home_sequence_runner.finished.connect(self._on_home_sequence_finished)
        self._home_sequence_runner.error.connect(self._on_home_sequence_error)

    def _start_dashboard_homing(self) -> bool:
        enabled_arms = get_enabled_arms(self.config, "robot")
        if not enabled_arms:
            self.action_label.setText("⚠️ No robot arms configured")
            self._append_log_entry(
                "error",
                "No enabled robot arms found. Configure arms in Settings.",
                code="home_no_arms",
            )
            return

        has_home = any(arm.get("home_positions") for arm in enabled_arms)
        if not has_home:
            self.action_label.setText("⚠️ No home positions configured")
            self._append_log_entry(
                "error",
                "No home positions configured. Set home in Settings.",
                code="home_not_configured",
            )
            return

        self.action_label.setText("Homing all enabled arms...")
        self._append_log_entry(
            "info",
            f"Homing {len(enabled_arms)} arm(s)…",
            code="home_start",
        )
        self.home_btn.setEnabled(False)
        started = self._home_sequence_runner.start(reload_from_disk=True, selection="all")
        if not started:
            self.home_btn.setEnabled(True)
        return started

    def _on_home_progress(self, message: str) -> None:
        self.action_label.setText(message)
        self._append_log_entry("info", message, code="home_progress")

    def _on_home_arm_started(self, arm_info: dict) -> None:
        arm_name = arm_info.get("arm_name") or f"Arm {arm_info.get('arm_id', '?')}"
        self.action_label.setText(f"Homing {arm_name}…")
        self._append_log_entry("info", f"Starting {arm_name}", code="home_arm_start")

    def _on_home_arm_finished(self, arm_info: dict, success: bool, message: str) -> None:
        entry = message or ("✓ Arm homed" if success else "⚠️ Home failed")
        level = "success" if success else "error"
        code = "home_arm_success" if success else "home_arm_error"
        self._append_log_entry(level, entry, code=code)

    def _on_home_sequence_finished(self, success: bool, message: str) -> None:
        level = "success" if success else "error"
        code = "home_complete" if success else "home_failed"
        self.action_label.setText(message)
        self._append_log_entry(level, message, code=code)
        self.home_btn.setEnabled(True)

    def _on_home_sequence_error(self, message: str) -> None:
        self.action_label.setText(f"⚠️ {message}")
        self._append_log_entry("error", message, code="home_error")
        self.home_btn.setEnabled(True)

    def _on_home_finished(self, success: bool, message: str) -> None:
        """Legacy helper retained for other components that home a single arm."""
        self.home_btn.setEnabled(True)
        if not message:
            message = "✓ At home position" if success else "⚠️ Home failed"
        self.action_label.setText(message)
        level = "info" if success else "error"
        self._append_log_entry(level, message, code="home_complete" if success else "home_failed")
