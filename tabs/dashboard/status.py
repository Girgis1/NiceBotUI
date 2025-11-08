"""Status and indicator helpers for the dashboard tab."""


class DashboardStatusMixin:
    """Mixin providing status indicator utilities."""

    def update_throbber_progress(self) -> None:
        self.throbber_progress += 1
        if self.throbber_progress > 100:
            self.throbber_progress = 0
        self.throbber.set_progress(self.throbber_progress)
        if self.compact_throbber:
            self.compact_throbber.set_progress(self.throbber_progress)

    def check_connections_background(self) -> None:
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

    def on_robot_status_changed(self, status: str) -> None:
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

    def _update_status_summaries(self) -> None:
        if not hasattr(self, "robot_summary_label") or not hasattr(self, "camera_summary_label"):
            return

        robot_online = 1 if self._robot_status == "online" else 0
        self.robot_summary_label.setText(f"R:{robot_online}/{self._robot_total}")

        camera_total = len(self._camera_status)
        camera_online = sum(1 for state in self._camera_status.values() if state == "online")
        self.camera_summary_label.setText(f"C:{camera_online}/{camera_total}")

    def on_discovery_log(self, message: str) -> None:
        self._append_log_entry("info", message, code="discovery_log")


__all__ = ["DashboardStatusMixin"]
