"""Home movement helpers for the dashboard tab."""

from __future__ import annotations

from PySide6.QtCore import QThread

from utils.config_compat import get_enabled_arms
from utils.home_move_worker import HomeMoveRequest, HomeMoveWorker


class DashboardHomeMixin:
    """Mixin that encapsulates homing logic for :class:`DashboardTab`."""

    def go_home(self) -> None:
        """Move all enabled robot arms to their configured home positions."""
        if self._home_thread and self._home_thread.isRunning():
            self._append_log_entry(
                "warning",
                "Home command already running.",
                code="home_already_running",
            )
            return

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

        self._home_arms_queue = []
        for i, arm in enumerate(enabled_arms):
            arm_id = arm.get("arm_id", i + 1)
            arm_name = arm.get("name", f"Arm {arm_id}")
            home_velocity = arm.get("home_velocity")

            robot_arms = self.config.get("robot", {}).get("arms", [])
            arm_index = next((idx for idx, a in enumerate(robot_arms) if a.get("arm_id") == arm_id), i)

            self._home_arms_queue.append(
                {
                    "arm_index": arm_index,
                    "arm_id": arm_id,
                    "arm_name": arm_name,
                    "velocity": home_velocity,
                }
            )

        self._home_thread = None
        self._home_worker = None
        self._home_next_arm()

    def _home_next_arm(self) -> None:
        """Home the next arm in the queue."""
        if not self._home_arms_queue:
            self.action_label.setText("✅ All arms homed")
            self._append_log_entry(
                "success",
                "All enabled arms have been homed.",
                code="home_complete",
            )
            self.home_btn.setEnabled(True)
            return

        arm_info = self._home_arms_queue.pop(0)
        arm_index = arm_info["arm_index"]
        arm_name = arm_info["arm_name"]
        velocity = arm_info["velocity"]

        self.action_label.setText(f"Homing {arm_name}...")
        self._append_log_entry(
            "info",
            f"Homing {arm_name} (Arm {arm_info['arm_id']})…",
            code="home_arm_start",
        )
        if velocity is not None:
            self._append_log_entry(
                "speed",
                f"Velocity: {velocity}",
                code="home_speed",
            )

        request = HomeMoveRequest(
            config=self.config,
            velocity_override=velocity,
            arm_index=arm_index,
        )

        worker = HomeMoveWorker(request)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_home_progress)
        worker.finished.connect(self._on_home_finished_multi)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_home_thread_finished)

        self._home_thread = thread
        self._home_worker = worker

        thread.start()

    def _on_home_finished_multi(self, success: bool, message: str) -> None:
        if success:
            self._append_log_entry("success", message, code="home_arm_success")
        else:
            self._append_log_entry("error", message, code="home_arm_error")

    def _on_home_progress(self, message: str) -> None:
        self.action_label.setText(message)
        self._append_log_entry("info", message, code="home_progress")

    def _on_home_finished(self, success: bool, message: str) -> None:
        self.home_btn.setEnabled(True)
        if not message:
            message = "✓ At home position" if success else "⚠️ Home failed"
        self.action_label.setText(message)
        level = "info" if success else "error"
        self._append_log_entry(level, message, code="home_complete" if success else "home_failed")

    def _on_home_thread_finished(self) -> None:
        if self._home_thread:
            self._home_thread.deleteLater()
        self._home_thread = None
        self._home_worker = None
