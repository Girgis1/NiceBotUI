"""
Dashboard Layout - UI layout construction for the dashboard

This module contains layout construction logic extracted from the monolithic
dashboard_tab.py init_ui method for better organization.
"""

from typing import List, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
)
from PySide6.QtCore import Qt

from ..widgets.status_indicators import StatusIndicator, CircularProgress
from ..widgets.control_panel import RunSelector, ControlButtons, SpeedControl, LogDisplay


class StatusBar(QWidget):
    """Compact status bar with indicators and time display"""

    def __init__(self, camera_order: Optional[List[str]] = None, parent=None):
        super().__init__(parent)
        self.camera_order = camera_order or []
        self.init_ui()

    def init_ui(self):
        """Initialize the status bar layout"""
        layout = QHBoxLayout(self)
        layout.setSpacing(18)

        # Normal status container
        self.normal_status_container = QWidget()
        normal_status_layout = QHBoxLayout(self.normal_status_container)
        normal_status_layout.setSpacing(18)
        normal_status_layout.setContentsMargins(0, 0, 0, 0)

        # Throbber
        self.throbber = CircularProgress()
        normal_status_layout.addWidget(self.throbber)

        # Robot status group
        robot_group = QHBoxLayout()
        robot_group.setSpacing(6)
        self.robot_lbl = QLabel("Robot")
        self.robot_lbl.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        robot_group.addWidget(self.robot_lbl)
        self.robot_indicator1 = StatusIndicator()
        self.robot_indicator1.set_null()
        robot_group.addWidget(self.robot_indicator1)
        self.robot_indicator2 = StatusIndicator()
        self.robot_indicator2.set_null()
        robot_group.addWidget(self.robot_indicator2)
        normal_status_layout.addLayout(robot_group)

        self.robot_status_circle = self.robot_indicator1

        # Camera status group
        camera_group = QHBoxLayout()
        camera_group.setSpacing(6)
        self.camera_lbl = QLabel("Cameras")
        self.camera_lbl.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        camera_group.addWidget(self.camera_lbl)
        self.camera_indicator1 = StatusIndicator()
        self.camera_indicator1.set_null()
        camera_group.addWidget(self.camera_indicator1)
        self.camera_indicator2 = StatusIndicator()
        self.camera_indicator2.set_null()
        camera_group.addWidget(self.camera_indicator2)
        self.camera_indicator3 = StatusIndicator()
        self.camera_indicator3.set_null()
        camera_group.addWidget(self.camera_indicator3)
        normal_status_layout.addLayout(camera_group)

        self.camera_front_circle = self.camera_indicator1
        self.camera_wrist_circle = self.camera_indicator2

        layout.addWidget(self.normal_status_container, stretch=0)

        # Compact status summary (hidden by default)
        self.status_summary_container = QWidget()
        summary_layout = QVBoxLayout(self.status_summary_container)
        summary_layout.setSpacing(2)
        summary_layout.setContentsMargins(0, 0, 0, 0)

        self.compact_throbber = CircularProgress()
        summary_layout.addWidget(self.compact_throbber, alignment=Qt.AlignHCenter)

        self.robot_summary_label = QLabel("R:0/1")
        self.robot_summary_label.setAlignment(Qt.AlignCenter)
        self.robot_summary_label.setStyleSheet("color: #a0a0a0; font-size: 11px; font-weight: bold;")
        summary_layout.addWidget(self.robot_summary_label)

        self.camera_summary_label = QLabel("C:0/0")
        self.camera_summary_label.setAlignment(Qt.AlignCenter)
        self.camera_summary_label.setStyleSheet("color: #a0a0a0; font-size: 11px; font-weight: bold;")
        summary_layout.addWidget(self.camera_summary_label)

        self.status_summary_container.hide()
        layout.addWidget(self.status_summary_container, stretch=0)

        # Time label
        self.time_label = QLabel("00:00")
        self.time_label.setStyleSheet("color: #4CAF50; font-size: 12px; font-weight: bold; font-family: monospace;")
        layout.addWidget(self.time_label)

        # Action label (right-aligned, stretches to fill space)
        self.action_label = QLabel("At home position")
        self._action_label_style_template = (
            "color: #ffffff; font-size: 14px; font-weight: bold; "
            "background-color: {bg}; border-radius: 4px; padding: 8px 20px;"
        )
        self._set_action_label_style("#383838")
        self.action_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.action_label, stretch=1)

    def _set_action_label_style(self, background: str):
        """Set the action label background color"""
        self.action_label.setStyleSheet(
            self._action_label_style_template.format(bg=background)
        )

    def set_action_status(self, text: str, background: str = "#383838"):
        """Update the action status display"""
        self.action_label.setText(text)
        self._set_action_label_style(background)

    def toggle_compact_mode(self, compact: bool):
        """Toggle between normal and compact status display"""
        if compact:
            self.normal_status_container.hide()
            self.status_summary_container.show()
        else:
            self.normal_status_container.show()
            self.status_summary_container.hide()


class CameraPanel(QFrame):
    """Camera preview panel"""

    def __init__(self, camera_order: Optional[List[str]] = None, parent=None):
        super().__init__(parent)
        self.camera_order = camera_order or []
        self.setStyleSheet("""
            QFrame {
                background-color: #1f1f1f;
                border: 1px solid #333333;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Camera previews will be added dynamically
        self.camera_previews = {}

    def add_camera_preview(self, camera_name: str, preview_widget):
        """Add a camera preview widget to the panel"""
        self.camera_previews[camera_name] = preview_widget
        layout = self.layout()
        layout.addWidget(preview_widget)


class ControlPanel(QWidget):
    """Main control panel with run selector and buttons"""

    def __init__(self, camera_order: Optional[List[str]] = None, parent=None):
        super().__init__(parent)
        self.camera_order = camera_order or []
        self.init_ui()

    def init_ui(self):
        """Initialize the control panel layout"""
        layout = QHBoxLayout(self)
        layout.setSpacing(15)

        # Left column: Run selector
        left_column = QVBoxLayout()
        left_column.setSpacing(10)

        # Run selector frame
        self.run_selector = RunSelector(self.camera_order)
        left_column.addWidget(self.run_selector)

        # Camera panel (initially hidden)
        self.camera_panel = CameraPanel(self.camera_order)
        self.camera_panel.hide()
        left_column.addWidget(self.camera_panel)

        layout.addLayout(left_column)

        # Right column: Controls and log
        right_column = QVBoxLayout()
        right_column.setSpacing(10)

        # Control buttons row
        self.control_buttons = ControlButtons()
        right_column.addWidget(self.control_buttons)

        # Log display (expands to fill height)
        self.log_display = LogDisplay()
        right_column.addWidget(self.log_display, stretch=1)

        layout.addLayout(right_column, stretch=1)

        # Speed control column
        self.speed_control = SpeedControl()
        layout.addWidget(self.speed_control)


class DashboardLayout:
    """Main dashboard layout constructor"""

    def __init__(self, camera_order: Optional[List[str]] = None):
        self.camera_order = camera_order or []

    def create_main_layout(self, parent_widget) -> QVBoxLayout:
        """Create the main dashboard layout"""
        layout = QVBoxLayout(parent_widget)
        layout.setSpacing(12)
        layout.setContentsMargins(15, 15, 15, 15)

        return layout

    def create_status_bar(self) -> StatusBar:
        """Create and return a status bar widget"""
        return StatusBar(self.camera_order)

    def create_control_panel(self) -> ControlPanel:
        """Create and return a control panel widget"""
        return ControlPanel(self.camera_order)

    def assemble_layout(self, parent_widget, status_bar: StatusBar, control_panel: ControlPanel):
        """Assemble all components into the main layout"""
        layout = self.create_main_layout(parent_widget)

        # Add status bar at top
        layout.addWidget(status_bar)

        # Add control panel (takes remaining space)
        layout.addWidget(control_panel, stretch=1)
