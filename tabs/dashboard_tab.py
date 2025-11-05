"""
Dashboard Tab - Main robot control interface

Refactored to use modular components for better maintainability.
This is now a coordinator that orchestrates UI components and controllers.
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
import pytz

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTextEdit, QComboBox, QSizePolicy, QSpinBox, QSlider,
    QStackedWidget, QDialog
)
from PySide6.QtCore import Qt, QTimer as QTimerCore, Signal, QThread
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QImage, QPixmap

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import modular components
from tabs.dashboard.widgets import (
    StatusIndicator, CircularProgress, CameraPreviewWidget,
    RunSelector, ControlButtons, SpeedControl, LogDisplay
)
from tabs.dashboard.layouts import StatusBar, CameraPanel, ControlPanel, DashboardLayout
from tabs.dashboard.controllers import ExecutionController, StatusController, CameraController

# Legacy imports (will be removed when fully integrated)
try:
    from utils.camera_hub import CameraStreamHub
except ImportError:
    CameraStreamHub = None

# Timezone
TIMEZONE = pytz.timezone('Australia/Sydney')
ROOT = Path(__file__).parent.parent
HISTORY_PATH = ROOT / "run_history.json"


# All UI widget classes have been moved to tabs/dashboard/widgets/
# All layout classes have been moved to tabs/dashboard/layouts/


class DashboardTab(QWidget):
    """Main dashboard coordinator - orchestrates modular components"""

    def __init__(self, config: Dict[str, Any], parent=None, device_manager=None):
        super().__init__(parent)
        self.config = config
        self.device_manager = device_manager

        # Initialize camera hub
        self.camera_hub = CameraStreamHub(config) if CameraStreamHub else None

        # Initialize controllers
        self.execution_ctrl = ExecutionController(config, device_manager)
        self.status_ctrl = StatusController(device_manager)
        self.camera_ctrl = CameraController(config, self.camera_hub)

        # Initialize UI components
        self.status_bar = StatusBar(self._get_camera_order())
        self.control_panel = ControlPanel(self._get_camera_order())

        # State management
        self.start_time: Optional[datetime] = None
        self.elapsed_seconds = 0
        self.timer = QTimerCore(self)
        self.timer.timeout.connect(self.update_elapsed_time)

        # Dashboard state persistence
        self._initial_run_selection = ""
        self._restoring_run_selection = False

        # Initialize the dashboard
        self.init_ui()
        self.setup_connections()
        self.load_initial_state()

    def _get_camera_order(self) -> List[str]:
        """Get the ordered list of camera names from config"""
        return list(self.config.get("cameras", {}).keys())

    def init_ui(self):
        """Initialize the user interface using modular components"""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(15, 15, 15, 15)

        # Add status bar
        layout.addWidget(self.status_bar)

        # Add control panel (takes remaining space)
        layout.addWidget(self.control_panel, stretch=1)

    def setup_connections(self):
        """Setup signal connections between components"""
        # Device manager connections
        if self.device_manager:
            self.device_manager.robot_status_changed.connect(self.status_ctrl.on_robot_status_changed)
            self.device_manager.camera_status_changed.connect(self.status_ctrl.on_camera_status_changed)
            self.device_manager.discovery_log.connect(self.status_ctrl.on_discovery_log)

        # Status controller connections
        self.status_ctrl.status_indicators_updated.connect(self._update_status_indicators)
        self.status_ctrl.action_label_updated.connect(self.status_bar.set_action_status)
        self.status_ctrl.log_entry_needed.connect(self._handle_log_entry)
        self.status_ctrl.execution_completed.connect(self._on_execution_completed)
        self.status_ctrl.fatal_error_occurred.connect(self._on_fatal_error)

        # Execution controller connections
        self.execution_ctrl.log_entry_needed.connect(self._handle_log_entry)
        self.execution_ctrl.execution_started.connect(self._on_execution_started)
        self.execution_ctrl.execution_stopped.connect(self._on_execution_stopped)
        self.execution_ctrl.home_started.connect(self._on_home_started)
        self.execution_ctrl.home_completed.connect(self._on_home_completed)
        self.execution_ctrl.ui_reset_needed.connect(self._reset_ui_state)

        # Camera controller connections
        self.camera_ctrl.camera_mode_changed.connect(self._on_camera_mode_changed)
        self.camera_ctrl.active_camera_changed.connect(self._on_active_camera_changed)
        self.camera_ctrl.camera_preview_updated.connect(self._on_camera_preview_updated)
        self.camera_ctrl.log_entry_needed.connect(self._handle_log_entry)

        # UI component connections
        self.control_panel.run_selector.run_selection_changed.connect(self.on_run_selection_changed)
        self.control_panel.run_selector.checkpoint_changed.connect(self.on_checkpoint_changed)
        self.control_panel.run_selector.camera_toggled.connect(self.on_camera_toggle)
        self.control_panel.control_buttons.start_stop_clicked.connect(self.execution_ctrl.toggle_start_stop)
        self.control_panel.control_buttons.home_clicked.connect(self.execution_ctrl.go_home)
        self.control_panel.control_buttons.loop_toggled.connect(self.execution_ctrl.set_loop_enabled)
        self.control_panel.speed_control.speed_changed.connect(self.execution_ctrl.set_speed_multiplier)

    def load_initial_state(self):
        """Load initial dashboard state"""
        # Start status monitoring
        self.status_ctrl.start_monitoring()

        # Initialize camera controller
        self.camera_ctrl.initialize_cameras(self._get_camera_order())

        # Load saved state
        self._apply_saved_dashboard_state()

    def _update_status_indicators(self):
        """Update all status indicators from controller"""
        status_summary = self.status_ctrl.get_status_summary()

        # Update status bar indicators
        self.status_bar.time_label.setText(self._format_elapsed_time())

        # Update summary labels
        self.status_bar.robot_summary_label.setText(
            f"R:{status_summary['robot_online']}/{status_summary['robot_total']}"
        )
        self.status_bar.camera_summary_label.setText(
            f"C:{status_summary['camera_online']}/{status_summary['camera_total']}"
        )

        # Update throbber
        self.status_bar.throbber.set_progress(status_summary['throbber_progress'])
        if hasattr(self.status_bar, 'compact_throbber') and self.status_bar.compact_throbber:
            self.status_bar.compact_throbber.set_progress(status_summary['throbber_progress'])

    def _handle_log_entry(self, level: str, message: str, metadata: Dict[str, Any]):
        """Handle log entry from any controller"""
        # Add to log display
        entry_text = f"[{level.upper()}] {message}"
        if metadata.get('action'):
            entry_text += f" - {metadata['action']}"
        self.control_panel.log_display.append_log_entry(entry_text)

    def _format_elapsed_time(self) -> str:
        """Format elapsed time for display"""
        if self.start_time is None:
            return "00:00"

        elapsed = datetime.now() - self.start_time
        total_seconds = int(elapsed.total_seconds())
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    # Event handlers

    def _on_execution_started(self, execution_type: str, execution_name: str):
        """Handle execution start"""
        self.start_time = datetime.now()
        self.elapsed_seconds = 0
        self.timer.start(1000)  # Update every second
        self.status_bar.set_action_status(f"Running {execution_type}: {execution_name}", "#4CAF50")

    def _on_execution_stopped(self):
        """Handle execution stop"""
        self.timer.stop()
        self.start_time = None
        self.status_bar.set_action_status("Stopped", "#FF9800")

    def _on_execution_completed(self, success: bool, summary: str):
        """Handle execution completion"""
        self.timer.stop()
        self.start_time = None
        color = "#4CAF50" if success else "#f44336"
        self.status_bar.set_action_status(summary, color)

    def _on_home_started(self):
        """Handle home movement start"""
        self.status_bar.set_action_status("Moving to home...", "#2196F3")

    def _on_home_completed(self, success: bool, message: str):
        """Handle home movement completion"""
        color = "#4CAF50" if success else "#f44336"
        self.status_bar.set_action_status(message, color)

    def _on_fatal_error(self):
        """Handle fatal error occurrence"""
        self.control_panel.control_buttons.set_loop_enabled(False)
        self.status_bar.set_action_status("Fix the issue, then press START.", "#b71c1c")

    def _on_camera_mode_changed(self, active: bool):
        """Handle camera mode changes"""
        if active:
            # Hide status bar text when cameras open
            self.status_bar.normal_status_container.hide()
            self.status_bar.status_summary_container.show()
            self.status_bar.time_label.hide()
            self.control_panel.run_selector.run_label.hide()
        else:
            # Show status bar text when cameras close
            self.status_bar.normal_status_container.show()
            self.status_bar.status_summary_container.hide()
            self.status_bar.time_label.show()
            self.control_panel.run_selector.run_label.show()

    def _on_active_camera_changed(self, camera_name: str):
        """Handle active camera changes"""
        # Update camera preview label
        if hasattr(self.control_panel, 'single_camera_preview'):
            display_name = self.camera_ctrl._camera_display_name(camera_name)
            self.control_panel.single_camera_preview.set_camera_name(display_name)

    def _on_camera_preview_updated(self, camera_name: str, pixmap: QPixmap, status: str):
        """Handle camera preview updates"""
        if hasattr(self.control_panel, 'single_camera_preview'):
            self.control_panel.single_camera_preview.update_preview(pixmap, status=status)

    def _reset_ui_state(self):
        """Reset UI state after execution"""
        self.start_time = None
        self.elapsed_seconds = 0
        self.timer.stop()
        self.status_bar.set_action_status("At home position", "#383838")

    # UI event handlers

    def on_run_selection_changed(self, text: str):
        """Handle RUN selector change - show/hide checkpoint dropdown"""
        if text.startswith("🤖 Model:"):
            # Show checkpoint dropdown for models
            self.control_panel.run_selector.show_checkpoint_selector(True)
            # Extract model name and load checkpoints
            model_name = text.replace("🤖 Model: ", "")
            self.load_checkpoints_for_model(model_name)
        else:
            # Hide checkpoint dropdown for sequences and actions
            self.control_panel.run_selector.show_checkpoint_selector(False)
            self.control_panel.run_selector.set_checkpoint_options([])

        if text and not text.startswith("--"):
            self._initial_run_selection = text
        else:
            self._initial_run_selection = ""

        if not self._restoring_run_selection:
            self._persist_dashboard_state()

    def on_checkpoint_changed(self, text: str):
        """Handle checkpoint selection change"""
        if not self._restoring_run_selection:
            self._persist_dashboard_state()

    def on_camera_toggle(self, checked: bool):
        """Handle camera toggle button"""
        # Update button text (red with X when open)
        button_text = "✕" if checked else "Cameras"
        # Note: This would need to be updated in the UI component

        if checked:
            self.camera_ctrl.enter_camera_mode()
        else:
            self.camera_ctrl.exit_camera_mode()

    # State persistence methods

    def _apply_saved_dashboard_state(self) -> None:
        """Load persisted dashboard preferences or apply safe defaults."""
        state = self.config.setdefault("dashboard_state", {})

        speed_percent = state.get("speed_percent")
        if isinstance(speed_percent, int) and 10 <= speed_percent <= 120:
            self.execution_ctrl.set_speed_multiplier(speed_percent / 100.0)
            self.control_panel.speed_control.set_speed(speed_percent)

        loop_enabled = state.get("loop_enabled", True)
        self.execution_ctrl.set_loop_enabled(loop_enabled)
        self.control_panel.control_buttons.set_loop_enabled(loop_enabled)

        self._restore_run_selection()

    def _restore_run_selection(self) -> bool:
        """Restore the last selected run option."""
        if not hasattr(self, '_initial_run_selection'):
            return False

        state = self.config.get("dashboard_state", {})
        run_selection = state.get("run_selection")

        if run_selection and run_selection in [self.control_panel.run_selector.run_combo.itemText(i)
                                              for i in range(self.control_panel.run_selector.run_combo.count())]:
            self._restoring_run_selection = True
            self.control_panel.run_selector.run_combo.setCurrentText(run_selection)
            self.on_run_selection_changed(run_selection)
            self._restoring_run_selection = False
            return True

        return False

    def _persist_dashboard_state(self) -> None:
        """Save current dashboard state to config."""
        state = self.config.setdefault("dashboard_state", {})

        current_speed = self.control_panel.speed_control.get_speed()
        state["speed_percent"] = current_speed

        state["loop_enabled"] = self.execution_ctrl.loop_enabled

        current_run = self.control_panel.run_selector.get_current_run_selection()
        if current_run:
            state["run_selection"] = current_run

        # Save config (this would normally be handled by the main app)
        # self.save_config()

    # Model and sequence management

    def load_checkpoints_for_model(self, model_name: str):
        """Load checkpoints for the selected model"""
        checkpoints = self._get_model_checkpoints(model_name)
        self.control_panel.run_selector.set_checkpoint_options(checkpoints)

    def _get_model_checkpoints(self, model_name: str) -> List[str]:
        """Get available checkpoints for a model"""
        try:
            train_dir = Path(self.config["policy"].get("base_path", ""))
            checkpoints_dir = train_dir / model_name / "checkpoints"

            if checkpoints_dir.exists():
                checkpoints = []
                for item in checkpoints_dir.iterdir():
                    if item.is_dir() and (item / "pretrained_model").exists():
                        checkpoints.append(item.name)
                return sorted(checkpoints, reverse=True)  # Most recent first
        except Exception:
            pass
        return []

    # Time tracking

    def update_elapsed_time(self):
        """Update elapsed time display"""
        if self.start_time:
            self.elapsed_seconds = int((datetime.now() - self.start_time).total_seconds())
        self._update_status_indicators()

    # Cleanup

    def closeEvent(self, event):
        """Handle window close event"""
        try:
            # Stop all controllers
            self.status_ctrl.stop_monitoring()
            self.camera_ctrl.exit_camera_mode()
            self.execution_ctrl.stop_run()

            # Shutdown camera hub
            if self.camera_hub and hasattr(self.camera_hub, 'shutdown'):
                self.camera_hub.shutdown()

        except Exception as e:
            print(f"[WARNING] Error during cleanup: {e}")
        finally:
            event.accept()
