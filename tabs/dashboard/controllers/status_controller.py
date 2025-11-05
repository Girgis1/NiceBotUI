"""
Status Controller - Manages device status monitoring and UI updates

Handles device status changes, connection monitoring, and execution feedback
events for coordinated status display across the dashboard.
"""

from typing import Dict, Optional, Any, TYPE_CHECKING
from PySide6.QtCore import QObject, Signal, QTimer

if TYPE_CHECKING:
    from utils.log_messages import LogEntry

try:
    from utils.log_messages import translate_worker_message, LogEntry
except ImportError:
    translate_worker_message = None
    LogEntry = None


class StatusController(QObject):
    """Manages device status monitoring and UI state coordination"""

    # Signals for UI updates
    status_indicators_updated = Signal()  # Trigger UI indicator updates
    action_label_updated = Signal(str, str)  # (text, background_color)
    log_entry_needed = Signal(str, str, dict)  # (level, message, metadata)
    progress_updated = Signal(int, int)  # (current, total)
    sequence_step_started = Signal(int, int, dict)  # (index, total, step)
    sequence_step_completed = Signal(int, int, dict)  # (index, total, step)
    vision_state_updated = Signal(str, dict)  # (state, payload)
    execution_completed = Signal(bool, str)  # (success, summary)
    model_completed = Signal(bool, str)  # (success, summary)
    fatal_error_occurred = Signal()  # Signal fatal error handling needed

    def __init__(self, device_manager=None):
        super().__init__()
        self.device_manager = device_manager

        # Status tracking
        self._robot_status = "empty"
        self._robot_total = 1  # Expected number of robots
        self._camera_status: Dict[str, str] = {}
        self._fatal_error_active = False
        self._last_log_code = None
        self._last_log_message = None
        self._vision_state_active = False

        # Throbber state
        self.throbber_progress = 0

        # Timer for throbber animation
        self.throbber_timer = QTimer(self)
        self.throbber_timer.timeout.connect(self._update_throbber_progress)
        self.throbber_timer.setInterval(100)  # Update every 100ms

        # Timer for connection checking
        self.connection_timer = QTimer(self)
        self.connection_timer.timeout.connect(self._check_connections_background)
        self.connection_timer.setInterval(5000)  # Check every 5 seconds

    def start_monitoring(self):
        """Start status monitoring timers"""
        self.throbber_timer.start()
        self.connection_timer.start()

    def stop_monitoring(self):
        """Stop status monitoring timers"""
        self.throbber_timer.stop()
        self.connection_timer.stop()

    def _update_throbber_progress(self):
        """Update throbber animation progress"""
        self.throbber_progress += 1
        if self.throbber_progress > 100:
            self.throbber_progress = 0
        # Emit signal to update UI throbbers
        self.status_indicators_updated.emit()

    def _check_connections_background(self):
        """Check device connections in background"""
        if not self.device_manager:
            return
        try:
            status_changed = self.device_manager.refresh_status()
            if status_changed:
                self.status_indicators_updated.emit()
        except Exception as exc:  # pragma: no cover - defensive
            self._log("warning", "Device status check failed.", action=f"Details: {exc}", code="device_refresh_failed")

    def on_robot_status_changed(self, status: str):
        """Handle robot status change from device manager

        Args:
            status: "empty", "online", or "offline"
        """
        self._robot_status = status
        self.status_indicators_updated.emit()

    def on_camera_status_changed(self, camera_name: str, status: str):
        """Handle camera status change from device manager

        Args:
            camera_name: "front" or "wrist"
            status: "empty", "online", or "offline"
        """
        self._camera_status[camera_name] = status
        self.status_indicators_updated.emit()

    def on_discovery_log(self, message: str):
        """Handle discovery log messages from device manager

        Args:
            message: Log message to display
        """
        self._log("info", message, code="discovery_log")

    def get_status_summary(self) -> Dict[str, Any]:
        """Get current status summary for UI display"""
        robot_online = 1 if self._robot_status == "online" else 0
        camera_total = len(self._camera_status)
        camera_online = sum(1 for state in self._camera_status.values() if state == "online")

        return {
            "robot_online": robot_online,
            "robot_total": self._robot_total,
            "camera_online": camera_online,
            "camera_total": camera_total,
            "robot_status": self._robot_status,
            "camera_status": self._camera_status.copy(),
            "throbber_progress": self.throbber_progress
        }

    # Event handlers for execution feedback

    def _on_status_update(self, status: str):
        """Handle status update from worker"""
        if self._vision_state_active:
            return
        self.action_label_updated.emit(status, "#383838")

    def _on_log_message(self, level: str, message: str):
        """Handle log message from worker"""
        if not translate_worker_message:
            self._log(level, message)
            return

        entry = translate_worker_message(level, message)
        if not entry:
            return

        # Suppress success messages once a fatal error has been shown.
        if self._fatal_error_active and entry.level == "success":
            return

        if entry.fatal and not self._fatal_error_active:
            self._fatal_error_active = True
            self._log(entry.level, entry.message, entry.action, entry.code)
            self._handle_fatal_error(entry)
            return

        if entry.fatal:
            return

        self._log(entry.level, entry.message, entry.action, entry.code)

    def _handle_fatal_error(self, entry: Optional['LogEntry']) -> None:
        """Stop the current run and provide guidance after a fatal error."""
        self.fatal_error_occurred.emit()
        self.action_label_updated.emit("Fix the issue, then press START.", "#b71c1c")

    def _on_progress_update(self, current: int, total: int):
        """Handle progress update from worker"""
        self.progress_updated.emit(current, total)

    def _on_sequence_step_started(self, index: int, total: int, step: dict):
        """Handle sequence step started"""
        self.sequence_step_started.emit(index, total, step)

    def _on_sequence_step_completed(self, index: int, total: int, step: dict):
        """Handle sequence step completed"""
        self.sequence_step_completed.emit(index, total, step)

    def _on_vision_state_update(self, state: str, payload: dict):
        """Handle vision state update"""
        self.vision_state_updated.emit(state, payload)

    def _on_execution_completed(self, success: bool, summary: str):
        """Handle execution completion"""
        self.execution_completed.emit(success, summary)

    def _on_model_completed(self, success: bool, summary: str):
        """Handle model execution completion"""
        self.model_completed.emit(success, summary)

    def set_vision_state_active(self, active: bool):
        """Set vision state active flag"""
        self._vision_state_active = active

    def reset_error_state(self):
        """Reset fatal error state"""
        self._fatal_error_active = False
        self._last_log_code = None
        self._last_log_message = None

    def _log(self, level: str, message: str, action: str = "", code: str = "") -> None:
        """Emit log entry signal"""
        metadata = {}
        if action:
            metadata["action"] = action
        if code:
            metadata["code"] = code
        self.log_entry_needed.emit(level, message, metadata)
