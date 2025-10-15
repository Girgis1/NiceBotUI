#!/usr/bin/env python3
"""
LeRobot Operator Console - Main Application
Minimalist touch-friendly interface for SO-100/101 robot control.
"""

import sys
import json
import os
import subprocess
from pathlib import Path
from datetime import datetime
import pytz

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QSpinBox, QFrame,
    QSizePolicy, QComboBox, QTextEdit, QProgressBar
)
from PySide6.QtCore import Qt, QTimer, QSize, QRect
from PySide6.QtGui import QFont, QPalette, QColor, QKeySequence, QShortcut, QPainter, QPen

from robot_worker import RobotWorker
from settings_dialog import SettingsDialog


# Paths
ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.json"
HISTORY_PATH = ROOT / "run_history.json"

# Timezone for display (Sydney/Australia)
TIMEZONE = pytz.timezone('Australia/Sydney')


class CircularProgress(QWidget):
    """Circular progress indicator that fills clockwise"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.progress = 0  # 0-100
        self.setFixedSize(24, 24)
    
    def set_progress(self, value):
        """Set progress value (0-100)"""
        self.progress = value
        self.update()  # Trigger repaint
    
    def paintEvent(self, event):
        """Draw circular progress"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw background circle (gray outline)
        pen = QPen(QColor("#555555"), 2)
        painter.setPen(pen)
        painter.setBrush(QColor("#2d2d2d"))
        painter.drawEllipse(2, 2, 20, 20)
        
        # Draw progress arc (green, fills clockwise from top)
        if self.progress > 0:
            pen = QPen(QColor("#4CAF50"), 3)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            
            # Arc: start at -90° (top), sweep clockwise
            # Qt uses 16ths of a degree
            start_angle = -90 * 16
            span_angle = -(self.progress * 360 // 100) * 16  # Negative = clockwise
            
            painter.drawArc(3, 3, 18, 18, start_angle, span_angle)


class StatusIndicator(QLabel):
    """Colored dot indicator for connection status"""
    
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.connected = False
        self.warning = False
        self.update_style()
        
    def set_connected(self, connected):
        """Update connection state"""
        self.connected = connected
        self.warning = False
        self.update_style()
    
    def set_warning(self):
        """Set warning state (orange) - serial connected but no power"""
        self.connected = False
        self.warning = True
        self.update_style()
        
    def update_style(self):
        """Update visual style"""
        if self.warning:
            color = "#FF9800"  # Orange
        elif self.connected:
            color = "#4caf50"  # Green
        else:
            color = "#f44336"  # Red
            
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                border-radius: 8px;
                min-width: 16px;
                max-width: 16px;
                min-height: 16px;
                max-height: 16px;
            }}
        """)


class MainWindow(QMainWindow):
    """Main application window"""
    
    # Error message catalog
    ERROR_MESSAGES = {
        "serial_permission": {
            "title": "Cannot Access Motors",
            "problem": "Permission denied accessing robot controller.",
            "solution": "Run setup script:\n./setup.sh\n\nOr manually:\nsudo usermod -aG dialout $USER\nThen log out and back in."
        },
        "serial_not_found": {
            "title": "Motors Not Found",
            "problem": "Robot controller not detected at {port}",
            "solution": "1. Check USB cable is firmly plugged in\n2. Verify power supply is ON\n3. Check LED on controller board\n4. Try a different USB port\n5. Run 'ls /dev/tty*' to see available ports"
        },
        "serial_busy": {
            "title": "Port Already In Use",
            "problem": "Robot controller port is busy at {port}",
            "solution": "1. Close other programs using the robot\n2. Unplug and replug USB cable\n3. Restart the application"
        },
        "servo_timeout": {
            "title": "Joint {motor_id} Not Responding",
            "problem": "Motor at joint {motor_id} failed to respond",
            "solution": "1. Check cable connection AT JOINT {motor_id}\n2. Verify cable is fully seated in connector\n3. Check motor ID was set during setup\n4. Verify motor has power (LED should be on)"
        },
        "power_loss": {
            "title": "⚠️ POWER LOST",
            "problem": "Motors disconnected unexpectedly",
            "solution": "1. Check emergency stop button (if pressed, release it)\n2. Check power supply connection to controller\n3. Verify power outlet is working\n4. Press GO HOME when power is restored"
        },
        "camera_not_found": {
            "title": "Camera Not Found",
            "problem": "Cannot open camera at index {index}",
            "solution": "1. Check camera USB connection\n2. Verify camera index in Settings\n3. Run 'ls /dev/video*' to see available cameras\n4. Try a different USB port"
        },
        "policy_not_found": {
            "title": "Policy Checkpoint Missing",
            "problem": "Cannot find trained policy at:\n{path}",
            "solution": "1. Check path in Settings → Policy tab\n2. Verify the model checkpoint was trained\n3. Use the Browse button to locate the checkpoint folder"
        },
        "lerobot_not_found": {
            "title": "LeRobot Not Installed",
            "problem": "Cannot find LeRobot package",
            "solution": "Install LeRobot:\npip install -e .[feetech]\n\nOr run the setup script:\n./setup.sh"
        },
        "unknown": {
            "title": "Unexpected Error",
            "problem": "An unexpected error occurred",
            "solution": "1. Check the log output below\n2. Try restarting the application\n3. Check Settings for incorrect values\n4. Verify all connections"
        }
    }
    
    def __init__(self, fullscreen=True):
        super().__init__()
        self.config = self.load_config()
        self.worker = None
        self.start_time = None
        self.elapsed_seconds = 0
        self.fullscreen_mode = fullscreen
        
        self.setWindowTitle("LeRobot Operator Console")
        self.setMinimumSize(800, 600)  # Minimum size
        
        self.init_ui()
        self.validate_config()
        self.refresh_policy_list()  # Populate policy dropdown
        
        # Initialize time displays from config
        episode_time = self.config["control"].get("episode_time_s", 25.0)
        minutes = int(episode_time // 60)
        seconds = int(episode_time % 60)
        self.minutes_display.setText(str(minutes))
        self.seconds_display.setText(str(seconds))
        
        # Timer for elapsed time updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_elapsed_time)
        
        # Background connection check timer (every 10 seconds)
        self.connection_check_timer = QTimer()
        self.connection_check_timer.timeout.connect(self.check_connections_background)
        self.connection_check_timer.start(10000)  # 10 seconds
        
        # Throbber update timer (updates progress every 100ms for smooth animation)
        self.throbber_progress = 0
        self.throbber_update_timer = QTimer()
        self.throbber_update_timer.timeout.connect(self.update_throbber_progress)
        self.throbber_update_timer.start(100)  # Update 10 times per second
        
        # Set fullscreen if requested
        if self.fullscreen_mode:
            self.showFullScreen()
        else:
            # For windowed mode, size to screen
            self.resize(1024, 600)
        
        # Add keyboard shortcuts
        self.setup_shortcuts()
        
    def init_ui(self):
        """Initialize user interface"""
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        # Dark mode styling
        central.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                color: #ffffff;
            }
        """)
        
        layout = QVBoxLayout(central)
        layout.setSpacing(10)  # Tighter spacing for small screen
        layout.setContentsMargins(15, 15, 15, 15)  # Less margin for small screen
        
        # No header title - cleaner UI
        
        # Status panel
        status_frame = QFrame()
        status_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        status_frame.setStyleSheet("""
            QFrame { 
                background-color: #2d2d2d; 
                border: 1px solid #404040;
                border-radius: 8px; 
                padding: 10px; 
            }
        """)
        status_layout = QVBoxLayout(status_frame)
        
        # Single row: All status info on one line
        all_status_layout = QHBoxLayout()
        
        # Robot Arm indicators (2 boxes)
        arm_label = QLabel("Robot:")
        arm_label.setStyleSheet("color: #ffffff; font-size: 12px;")
        all_status_layout.addWidget(arm_label)
        
        self.robot_indicator1 = StatusIndicator()
        all_status_layout.addWidget(self.robot_indicator1)
        
        self.robot_indicator2 = StatusIndicator()
        all_status_layout.addWidget(self.robot_indicator2)
        
        all_status_layout.addSpacing(15)
        
        # Camera indicators (3 boxes that light up based on count)
        cam_label = QLabel("Cameras:")
        cam_label.setStyleSheet("color: #ffffff; font-size: 12px;")
        all_status_layout.addWidget(cam_label)
        
        self.camera_indicator1 = StatusIndicator()
        all_status_layout.addWidget(self.camera_indicator1)
        
        self.camera_indicator2 = StatusIndicator()
        all_status_layout.addWidget(self.camera_indicator2)
        
        self.camera_indicator3 = StatusIndicator()
        all_status_layout.addWidget(self.camera_indicator3)
        
        all_status_layout.addSpacing(15)
        
        # Time display
        self.time_label = QLabel("Time: 00:00")
        time_font = QFont()
        time_font.setPointSize(12)
        self.time_label.setFont(time_font)
        self.time_label.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        all_status_layout.addWidget(self.time_label)
        
        all_status_layout.addSpacing(15)
        
        # Action/Position status
        self.action_label = QLabel("At home position")
        action_font = QFont()
        action_font.setPointSize(12)
        self.action_label.setFont(action_font)
        self.action_label.setStyleSheet("color: #ffffff;")
        all_status_layout.addWidget(self.action_label)
        
        all_status_layout.addSpacing(10)
        
        # Circular throbber (connection check progress) - fills clockwise
        self.throbber = CircularProgress()
        all_status_layout.addWidget(self.throbber)
        
        all_status_layout.addStretch()
        
        # NICE LABS Robotics branding - right aligned
        branding_label = QLabel("NICE LABS Robotics")
        branding_label.setStyleSheet("color: #888888; font-size: 12px; font-weight: bold;")
        branding_label.setAlignment(Qt.AlignRight)
        all_status_layout.addWidget(branding_label)
        status_layout.addLayout(all_status_layout)
        
        layout.addWidget(status_frame)
        
        # Policy Selector - Task and Checkpoint
        policy_frame = QFrame()
        policy_frame.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border: 1px solid #404040;
                border-radius: 8px;
                padding: 8px;
            }
        """)
        policy_main_layout = QVBoxLayout(policy_frame)
        
        # Single row: MODEL label + Task dropdown (3/4) + Checkpoint dropdown (1/4)
        policy_selectors = QHBoxLayout()
        
        # MODEL: label
        model_label = QLabel("MODEL:")
        model_label.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        model_label.setAlignment(Qt.AlignVCenter)
        policy_selectors.addWidget(model_label)
        
        # Task selector (75% width) - Touch-friendly
        self.task_combo = QComboBox()
        self.task_combo.setMinimumHeight(55)
        self.task_combo.setStyleSheet("""
            QComboBox {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QComboBox:hover {
                border-color: #2196F3;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 8px solid #ffffff;
                margin-right: 8px;
            }
            QComboBox QAbstractItemView {
                background-color: #404040;
                color: #ffffff;
                selection-background-color: #2196F3;
                border: 1px solid #505050;
            }
        """)
        self.task_combo.currentTextChanged.connect(self.on_task_changed)
        policy_selectors.addWidget(self.task_combo, stretch=3)
        
        # Checkpoint selector (25% width) - Touch-friendly
        self.checkpoint_combo = QComboBox()
        self.checkpoint_combo.setMinimumHeight(55)
        self.checkpoint_combo.setStyleSheet("""
            QComboBox {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 13px;
            }
            QComboBox:hover {
                border-color: #2196F3;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 8px solid #ffffff;
                margin-right: 8px;
            }
            QComboBox QAbstractItemView {
                background-color: #404040;
                color: #ffffff;
                selection-background-color: #2196F3;
                border: 1px solid #505050;
            }
        """)
        self.checkpoint_combo.currentTextChanged.connect(self.on_checkpoint_changed)
        policy_selectors.addWidget(self.checkpoint_combo, stretch=1)
        
        policy_main_layout.addLayout(policy_selectors)
        layout.addWidget(policy_frame)
        
        # Main control area - Episodes/Time on left, buttons on right
        main_control_layout = QHBoxLayout()
        main_control_layout.setSpacing(15)
        main_control_layout.setAlignment(Qt.AlignTop)  # All controls aligned to top
        
        # LEFT SIDE - Episodes control (vertical)
        episodes_container = QVBoxLayout()
        episodes_container.setSpacing(5)
        episodes_container.setAlignment(Qt.AlignTop)
        
        episodes_label = QLabel("Episodes")
        episodes_label.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        episodes_label.setAlignment(Qt.AlignCenter)
        episodes_container.addWidget(episodes_label)
        
        # UP button - BIG with text fallback
        self.episodes_up_btn = QPushButton("▲")
        self.episodes_up_btn.setMinimumSize(80, 80)
        self.episodes_up_btn.setFont(QFont("Arial", 28))
        self.episodes_up_btn.setStyleSheet("""
            QPushButton {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 8px;
                font-size: 36px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QPushButton:pressed {
                background-color: #606060;
            }
        """)
        self.episodes_up_btn.clicked.connect(lambda: self.change_episodes(1))
        episodes_container.addWidget(self.episodes_up_btn)
        
        # Episode number display
        self.episodes_display = QLabel("3")
        self.episodes_display.setStyleSheet("""
            color: #ffffff;
            background-color: #2d2d2d;
            border: 2px solid #404040;
            border-radius: 8px;
            font-size: 32px;
            font-weight: bold;
            padding: 10px;
        """)
        self.episodes_display.setAlignment(Qt.AlignCenter)
        self.episodes_display.setMinimumSize(80, 60)
        episodes_container.addWidget(self.episodes_display)
        
        # DOWN button - BIG with text fallback
        self.episodes_down_btn = QPushButton("▼")
        self.episodes_down_btn.setMinimumSize(80, 80)
        self.episodes_down_btn.setFont(QFont("Arial", 28))
        self.episodes_down_btn.setStyleSheet("""
            QPushButton {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 8px;
                font-size: 36px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QPushButton:pressed {
                background-color: #606060;
            }
        """)
        self.episodes_down_btn.clicked.connect(lambda: self.change_episodes(-1))
        episodes_container.addWidget(self.episodes_down_btn)
        
        # No stretch - keep compact
        main_control_layout.addLayout(episodes_container)
        
        # MIDDLE - Time control (EXACT same style as Episodes)
        time_controls_layout = QHBoxLayout()
        time_controls_layout.setSpacing(0)  # No gap between Min and Sec columns
        time_controls_layout.setAlignment(Qt.AlignTop)
        
        # MINUTES control (matching Episodes layout exactly)
        minutes_container = QVBoxLayout()
        minutes_container.setSpacing(5)
        minutes_container.setAlignment(Qt.AlignTop)
        
        minutes_label = QLabel("Min")
        minutes_label.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        minutes_label.setAlignment(Qt.AlignCenter)
        minutes_container.addWidget(minutes_label)
        
        # UP button for minutes
        self.minutes_up_btn = QPushButton("▲")
        self.minutes_up_btn.setMinimumSize(80, 80)
        self.minutes_up_btn.setFont(QFont("Arial", 28))
        self.minutes_up_btn.setStyleSheet("""
            QPushButton {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 8px;
                font-size: 36px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QPushButton:pressed {
                background-color: #606060;
            }
        """)
        self.minutes_up_btn.clicked.connect(lambda: self.change_time('minutes', 1))
        minutes_container.addWidget(self.minutes_up_btn)
        
        # Minutes display
        self.minutes_display = QLabel("0")
        self.minutes_display.setStyleSheet("""
            color: #ffffff;
            background-color: #2d2d2d;
            border: 2px solid #404040;
            border-radius: 8px;
            font-size: 32px;
            font-weight: bold;
            padding: 10px;
        """)
        self.minutes_display.setAlignment(Qt.AlignCenter)
        self.minutes_display.setMinimumSize(80, 60)
        minutes_container.addWidget(self.minutes_display)
        
        # DOWN button for minutes
        self.minutes_down_btn = QPushButton("▼")
        self.minutes_down_btn.setMinimumSize(80, 80)
        self.minutes_down_btn.setFont(QFont("Arial", 28))
        self.minutes_down_btn.setStyleSheet("""
            QPushButton {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 8px;
                font-size: 36px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QPushButton:pressed {
                background-color: #606060;
            }
        """)
        self.minutes_down_btn.clicked.connect(lambda: self.change_time('minutes', -1))
        minutes_container.addWidget(self.minutes_down_btn)
        
        # No stretch - keep compact
        time_controls_layout.addLayout(minutes_container)
        
        # SECONDS control (matching Episodes layout exactly)
        seconds_container = QVBoxLayout()
        seconds_container.setSpacing(5)
        seconds_container.setAlignment(Qt.AlignTop)
        
        seconds_label = QLabel("Sec")
        seconds_label.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        seconds_label.setAlignment(Qt.AlignCenter)
        seconds_container.addWidget(seconds_label)
        
        # UP button for seconds
        self.seconds_up_btn = QPushButton("▲")
        self.seconds_up_btn.setMinimumSize(80, 80)
        self.seconds_up_btn.setFont(QFont("Arial", 28))
        self.seconds_up_btn.setStyleSheet("""
            QPushButton {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 8px;
                font-size: 36px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QPushButton:pressed {
                background-color: #606060;
            }
        """)
        self.seconds_up_btn.clicked.connect(lambda: self.change_time('seconds', 1))
        seconds_container.addWidget(self.seconds_up_btn)
        
        # Seconds display
        self.seconds_display = QLabel("25")
        self.seconds_display.setStyleSheet("""
            color: #ffffff;
            background-color: #2d2d2d;
            border: 2px solid #404040;
            border-radius: 8px;
            font-size: 32px;
            font-weight: bold;
            padding: 10px;
        """)
        self.seconds_display.setAlignment(Qt.AlignCenter)
        self.seconds_display.setMinimumSize(80, 60)
        seconds_container.addWidget(self.seconds_display)
        
        # DOWN button for seconds
        self.seconds_down_btn = QPushButton("▼")
        self.seconds_down_btn.setMinimumSize(80, 80)
        self.seconds_down_btn.setFont(QFont("Arial", 28))
        self.seconds_down_btn.setStyleSheet("""
            QPushButton {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 8px;
                font-size: 36px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QPushButton:pressed {
                background-color: #606060;
            }
        """)
        self.seconds_down_btn.clicked.connect(lambda: self.change_time('seconds', -1))
        seconds_container.addWidget(self.seconds_down_btn)
        
        # No stretch - keep compact
        time_controls_layout.addLayout(seconds_container)
        
        main_control_layout.addLayout(time_controls_layout)
        
        # RIGHT SIDE - START/STOP and HOME buttons side by side
        # Single row layout - no container needed
        top_buttons_layout = QHBoxLayout()
        top_buttons_layout.setSpacing(10)
        top_buttons_layout.setAlignment(Qt.AlignTop)
        
        # START/STOP toggle button
        self.start_stop_btn = QPushButton("START")
        self.start_stop_btn.setMinimumHeight(140)
        self.start_stop_btn.setMinimumWidth(200)
        self.start_stop_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.start_stop_btn.setCheckable(True)
        self.start_stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #2e7d32;
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 42px;
                font-weight: bold;
                padding: 15px;
            }
            QPushButton:hover {
                background-color: #1b5e20;
            }
            QPushButton:pressed {
                background-color: #0d3818;
            }
            QPushButton:checked {
                background-color: #c62828;
            }
            QPushButton:checked:hover {
                background-color: #b71c1c;
            }
            QPushButton:checked:pressed {
                background-color: #7f0000;
            }
        """)
        self.start_stop_btn.clicked.connect(self.toggle_start_stop)
        top_buttons_layout.addWidget(self.start_stop_btn, stretch=3)
        
        # HOME button - Blue minimalist icon (square, width=height dynamically)
        self.home_btn = QPushButton("⌂")  # Unicode house character
        self.home_btn.setMinimumHeight(140)
        self.home_btn.setMinimumWidth(140)
        # Will be resized to square after layout
        self.home_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        
        self.home_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: 2px solid #1976D2;
                border-radius: 12px;
                font-size: 64px;
                font-weight: normal;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #1E88E5;
                border-color: #1565C0;
            }
            QPushButton:pressed {
                background-color: #1976D2;
            }
            QPushButton:disabled {
                background-color: #252525;
                color: #3a3a3a;
                border-color: #2a2a2a;
            }
        """)
        self.home_btn.clicked.connect(self.go_home)
        top_buttons_layout.addWidget(self.home_btn, stretch=0)
        
        main_control_layout.addLayout(top_buttons_layout, stretch=1)
        
        layout.addLayout(main_control_layout)
        
        # Add padding after main controls
        layout.addSpacing(15)
        
        # Bottom section: Recent runs (fixed), Log (dynamic), and Settings in a row
        bottom_widgets = QHBoxLayout()
        bottom_widgets.setSpacing(10)
        
        # Recent runs list - Fixed width so text is always visible
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(200)
        self.history_list.setMinimumWidth(280)
        self.history_list.setMaximumWidth(280)
        self.history_list.setStyleSheet("""
            QListWidget {
                background-color: #2d2d2d;
                color: #ffffff;
                font-family: monospace;
                font-size: 10px;
                border: 1px solid #404040;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 3px;
            }
            QListWidget::item:hover {
                background-color: #404040;
            }
        """)
        bottom_widgets.addWidget(self.history_list, stretch=0)
        
        # Log text area - double height, dynamic width
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(200)
        self.log_text.setMinimumWidth(300)  # Minimum width for readability
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #2d2d2d;
                color: #ffffff;
                font-family: monospace;
                font-size: 10px;
                border: 1px solid #404040;
                border-radius: 4px;
            }
        """)
        bottom_widgets.addWidget(self.log_text, stretch=1)
        
        # Settings button - Fixed 200x200 to match log box height exactly
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setFixedHeight(200)
        self.settings_btn.setFixedWidth(200)
        self.settings_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.settings_btn.setFont(QFont("Arial", 72))
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #757575;
                color: white;
                border: 2px solid #616161;
                border-radius: 8px;
                font-size: 48px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #616161;
                border-color: #505050;
            }
            QPushButton:pressed {
                background-color: #424242;
            }
            QPushButton:disabled {
                background-color: #9e9e9e;
                color: #616161;
            }
        """)
        self.settings_btn.clicked.connect(self.open_settings)
        bottom_widgets.addWidget(self.settings_btn, stretch=0)
        
        layout.addLayout(bottom_widgets)
        
        # Load history
        self.load_history()
        
        # Add welcome message to log
        self.log_text.append("=== NICE LABS Robotics ===")
        self.log_text.append("System ready. Configure settings and press START to begin.")
        
    def setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        # F11 or Escape to toggle fullscreen
        self.fullscreen_shortcut = QShortcut(QKeySequence("F11"), self)
        self.fullscreen_shortcut.activated.connect(self.toggle_fullscreen)
        
        self.escape_shortcut = QShortcut(QKeySequence("Escape"), self)
        self.escape_shortcut.activated.connect(self.exit_fullscreen)
        
    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        if self.isFullScreen():
            self.showNormal()
            # Resize to fit current screen
            screen = QApplication.primaryScreen().geometry()
            self.resize(min(1024, screen.width()), min(600, screen.height()))
        else:
            self.showFullScreen()
            
    def exit_fullscreen(self):
        """Exit fullscreen mode"""
        if self.isFullScreen():
            self.showNormal()
            # Resize to fit current screen
            screen = QApplication.primaryScreen().geometry()
            self.resize(min(1024, screen.width()), min(600, screen.height()))
            
    def showEvent(self, event):
        """Handle show event - ensure proper sizing"""
        super().showEvent(event)
        if self.fullscreen_mode and not self.isFullScreen():
            self.showFullScreen()
            
    def resizeEvent(self, event):
        """Handle resize event"""
        super().resizeEvent(event)
        # Make home button square (width = height)
        if hasattr(self, 'home_btn'):
            height = self.home_btn.height()
            if height > 0:
                self.home_btn.setFixedWidth(height)
        
        # Settings button stays at fixed 200px height (doesn't become square)
            
    def closeEvent(self, event):
        """Handle window close event"""
        # If worker is running, stop it automatically
        if self.worker and self.worker.isRunning():
            self.log_text.append("[info] Stopping robot before exit...")
            self.worker.stop()
            self.worker.wait(5000)  # Wait up to 5 seconds
        event.accept()
        
    def load_config(self):
        """Load configuration from JSON"""
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, 'r') as f:
                return json.load(f)
        else:
            # Return default config
            return self.create_default_config()
            
    def save_config(self):
        """Save configuration to JSON"""
        with open(CONFIG_PATH, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def refresh_policy_list(self):
        """Scan for available tasks and populate dropdown"""
        self.task_combo.blockSignals(True)
        self.task_combo.clear()
        
        # Use base_path from config, or try to find it
        train_dir = None
        if "base_path" in self.config["policy"] and self.config["policy"]["base_path"]:
            train_dir = Path(self.config["policy"]["base_path"])
        else:
            # Fallback: try to find from policy path
            try:
                policy_path = Path(self.config["policy"]["path"])
                current = policy_path.parent
                while current != current.parent and current.name != '':
                    if current.name == 'train':
                        train_dir = current
                        # Save this for future use
                        self.config["policy"]["base_path"] = str(train_dir)
                        self.save_config()
                        break
                    current = current.parent
            except Exception as e:
                print(f"Could not auto-detect base_path: {e}")
                # Default fallback
                train_dir = Path("/home/daniel/lerobot/outputs/train")
        
        if train_dir and train_dir.exists():
            # Scan for task folders
            tasks = []
            for item in train_dir.iterdir():
                if item.is_dir():
                    checkpoints_dir = item / "checkpoints"
                    if checkpoints_dir.exists():
                        tasks.append(item.name)
            
            tasks.sort()
            
            for task in tasks:
                self.task_combo.addItem(task)
            
            # Select current task from config
            # Get task name from path
            try:
                policy_path = Path(self.config["policy"]["path"])
                current = policy_path.parent
                while current != current.parent and current.name != '':
                    if current.parent.name == 'train':
                        current_task = current.name
                        index = self.task_combo.findText(current_task)
                        if index >= 0:
                            self.task_combo.setCurrentIndex(index)
                        break
                    current = current.parent
            except Exception as e:
                print(f"Could not select current task: {e}")
            
            self.task_combo.setEnabled(True)
        else:
            self.task_combo.addItem("⚠️ No tasks found")
            self.task_combo.setEnabled(False)
        
        self.task_combo.blockSignals(False)
        
        # Refresh checkpoints for current task
        self.refresh_checkpoints()
    
    def refresh_checkpoints(self):
        """Scan for checkpoints in the selected task"""
        self.checkpoint_combo.blockSignals(True)
        self.checkpoint_combo.clear()
        
        task_name = self.task_combo.currentText()
        if not task_name or task_name.startswith("⚠️"):
            self.checkpoint_combo.addItem("—")
            self.checkpoint_combo.setEnabled(False)
            self.checkpoint_combo.blockSignals(False)
            return
        
        # Use base_path from config
        train_dir = None
        if "base_path" in self.config["policy"]:
            train_dir = Path(self.config["policy"]["base_path"])
        
        if not train_dir or not train_dir.exists():
            self.checkpoint_combo.addItem("—")
            self.checkpoint_combo.setEnabled(False)
            self.checkpoint_combo.blockSignals(False)
            return
        
        checkpoints_dir = train_dir / task_name / "checkpoints"
        
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
            
            # Select current checkpoint
            try:
                policy_path = Path(self.config["policy"]["path"])
                current = policy_path.parent
                if current.parent.name == 'checkpoints':
                    current_ckpt = current.name
                    for i in range(self.checkpoint_combo.count()):
                        if self.checkpoint_combo.itemData(i) == current_ckpt:
                            self.checkpoint_combo.setCurrentIndex(i)
                            break
                else:
                    # Default to "last"
                    for i in range(self.checkpoint_combo.count()):
                        if self.checkpoint_combo.itemData(i) == "last":
                            self.checkpoint_combo.setCurrentIndex(i)
                            break
            except Exception as e:
                # Default to "last"
                for i in range(self.checkpoint_combo.count()):
                    if self.checkpoint_combo.itemData(i) == "last":
                        self.checkpoint_combo.setCurrentIndex(i)
                        break
            
            self.checkpoint_combo.setEnabled(True)
        else:
            self.checkpoint_combo.addItem("⚠️ No checkpoints")
            self.checkpoint_combo.setEnabled(False)
        
        self.checkpoint_combo.blockSignals(False)
    
    def on_task_changed(self, text):
        """Handle task selection change"""
        if not self.task_combo.isEnabled() or text.startswith("⚠️"):
            return
        
        # Refresh checkpoints for new task
        self.refresh_checkpoints()
        
        # Update config to point to this task's "last" checkpoint
        self.update_policy_path()
    
    def on_checkpoint_changed(self, text):
        """Handle checkpoint selection change"""
        if not self.checkpoint_combo.isEnabled() or text.startswith("⚠️"):
            return
        
        self.update_policy_path()
    
    def update_policy_path(self):
        """Update config with selected task and checkpoint"""
        task_name = self.task_combo.currentText()
        checkpoint_index = self.checkpoint_combo.currentIndex()
        
        if checkpoint_index < 0:
            return
        
        checkpoint_name = self.checkpoint_combo.itemData(checkpoint_index)
        if not checkpoint_name:
            return
        
        # Use base_path from config
        train_dir = None
        if "base_path" in self.config["policy"]:
            train_dir = Path(self.config["policy"]["base_path"])
        
        if train_dir and train_dir.exists():
            new_path = train_dir / task_name / "checkpoints" / checkpoint_name / "pretrained_model"
            self.config["policy"]["path"] = str(new_path)
            self.save_config()
            print(f"Policy changed to: {new_path}")
            
    def create_default_config(self):
        """Create default configuration"""
        return {
            "robot": {
                "type": "so100_follower",
                "port": "/dev/ttyACM0",
                "id": "so100_shop_arm",
                "fps": 30,
                "min_time_to_move_multiplier": 3.0,
                "enable_motor_torque": True
            },
            "cameras": {
                "front": {
                    "type": "opencv",
                    "index_or_path": 0,
                    "width": 640,
                    "height": 480,
                    "fps": 30
                }
            },
            "policy": {
                "path": "outputs/train/act_so100/checkpoints/last/pretrained_model",
                "device": "cpu"
            },
            "control": {
                "warmup_time_s": 3,
                "episode_time_s": 25,
                "reset_time_s": 8,
                "num_episodes": 3,
                "single_task": "PickPlace v1",
                "push_to_hub": False,
                "repo_id": None,
                "num_image_writer_processes": 0
            },
            "rest_position": {
                "angles_deg": [0, -20, 35, -10, 0, 20],
                "speed_scale": 0.6
            },
            "ui": {
                "object_gate": False,
                "roi": [220, 140, 200, 180],
                "presence_threshold": 0.12
            },
            "safety": {
                "soft_limits_deg": [
                    [-90, 90], [-60, 60], [-60, 60],
                    [-90, 90], [-180, 180], [0, 100]
                ],
                "max_speed_scale": 1.0
            }
        }
        
    def validate_config(self):
        """Validate configuration and show warnings"""
        warnings = []
        
        # Check policy path
        policy_path = Path(self.config["policy"]["path"])
        if not policy_path.exists():
            warnings.append(f"⚠️  Policy not found: {policy_path}")
            print(f"Warning: Policy not found at {policy_path}")
            
        # Check robot arm serial port (USB) - Light up both indicators if connected
        port = self.config["robot"]["port"]
        if not os.path.exists(port):
            warnings.append(f"⚠️  Robot Arm USB not found: {port}")
            print(f"Warning: Robot Arm USB port not found: {port}")
            self.robot_indicator1.set_connected(False)
            self.robot_indicator2.set_connected(False)
        else:
            # Both indicators green when robot connected
            self.robot_indicator1.set_connected(True)
            self.robot_indicator2.set_connected(True)
            
        # Check and count cameras - Light up indicators based on count
        camera_count = 0
        try:
            import cv2
            cameras = self.config.get("cameras", {})
            
            for cam_name, cam_config in cameras.items():
                cam_idx = cam_config.get("index_or_path", 0)
                cap = cv2.VideoCapture(cam_idx)
                if cap.isOpened():
                    camera_count += 1
                    cap.release()
                else:
                    warnings.append(f"⚠️  Camera '{cam_name}' not available: {cam_idx}")
                    print(f"Warning: Camera '{cam_name}' not available at {cam_idx}")
                    cap.release()
            
            # Update camera indicators based on count (light up 1, 2, or 3)
            self.camera_indicator1.set_connected(camera_count >= 1)
            self.camera_indicator2.set_connected(camera_count >= 2)
            self.camera_indicator3.set_connected(camera_count >= 3)
            
        except Exception as e:
            print(f"Camera check error: {e}")
            self.camera_indicator1.set_connected(False)
            self.camera_indicator2.set_connected(False)
            self.camera_indicator3.set_connected(False)
            
        # Log warnings if any
        if warnings:
            self.log_text.append("\n[WARNING] Configuration issues:")
            for w in warnings:
                self.log_text.append(f"  {w}")
            self.log_text.append("  → Fix these in Settings before starting\n")
            self.action_label.setText("Configuration warnings - check log")
            
    def open_settings(self):
        """Open settings dialog"""
        dialog = SettingsDialog(self.config, self)
        if dialog.exec():
            # Settings were saved
            self.config = dialog.config
            self.save_config()
            self.episodes_display.setText(str(self.config["control"]["num_episodes"]))
            self.log_text.append("[info] Settings saved successfully")
            self.action_label.setText("Settings saved")
            
    def change_episodes(self, delta):
        """Change episode count by delta"""
        current = int(self.episodes_display.text())
        new_value = max(1, min(9999, current + delta))
        self.episodes_display.setText(str(new_value))
        self.config["control"]["num_episodes"] = new_value
        self.save_config()
    
    def change_time(self, unit, delta):
        """Change time value (minutes or seconds)"""
        if unit == 'minutes':
            current = int(self.minutes_display.text())
            new_value = max(0, min(99, current + delta))
            self.minutes_display.setText(str(new_value))
        else:  # seconds
            current = int(self.seconds_display.text())
            new_value = max(0, min(59, current + delta))
            self.seconds_display.setText(str(new_value))
        
        # Update config
        minutes = int(self.minutes_display.text())
        seconds = int(self.seconds_display.text())
        total_seconds = minutes * 60 + seconds
        
        self.config["control"]["episode_time_s"] = float(total_seconds)
        self.save_config()
        
        print(f"Episode time set to {minutes}m {seconds}s ({total_seconds}s)")
    
    def update_throbber_progress(self):
        """Update throbber progress (fills over 10 seconds)"""
        # Increment by 1% every 100ms = 100% in 10 seconds
        self.throbber_progress += 1
        if self.throbber_progress > 100:
            self.throbber_progress = 0
        self.throbber.set_progress(self.throbber_progress)
    
    def check_connections_background(self):
        """Background check for robot and camera connections"""
        if self.worker and self.worker.isRunning():
            # Don't check while robot is running
            return
        
        # Reset throbber progress (no need to change text, throbber shows we're checking)
        self.throbber_progress = 0
        self.throbber.set_progress(0)
        QApplication.processEvents()
        
        # Check robot connection
        from rest_pos import check_robot_connection
        robot_status = check_robot_connection(self.config["robot"]["port"])
        
        # Update robot indicators
        if robot_status == "connected":
            self.robot_indicator1.set_connected(True)
            self.robot_indicator2.set_connected(True)
        elif robot_status == "no_power":
            # Orange for serial connected but motors not powered
            self.robot_indicator1.set_warning()
            self.robot_indicator2.set_warning()
        else:
            self.robot_indicator1.set_connected(False)
            self.robot_indicator2.set_connected(False)
        
        # Check cameras
        camera_count = 0
        try:
            import cv2
            cameras = self.config.get("cameras", {})
            
            for cam_name, cam_config in cameras.items():
                cam_idx = cam_config.get("index_or_path", 0)
                cap = cv2.VideoCapture(cam_idx)
                if cap.isOpened():
                    camera_count += 1
                    cap.release()
                else:
                    cap.release()
        except Exception as e:
            print(f"Camera check error: {e}")
        
        # Update camera indicators
        self.camera_indicator1.set_connected(camera_count >= 1)
        self.camera_indicator2.set_connected(camera_count >= 2)
        self.camera_indicator3.set_connected(camera_count >= 3)
        
        # Status text stays as is (throbber shows checking progress)
    
    def on_time_changed(self):
        """Handle time spinbox changes"""
        minutes = self.minutes_spin.value()
        seconds = self.seconds_spin.value()
        total_seconds = (minutes * 60) + seconds
        
        # Update episode_time_s in config
        self.config["control"]["episode_time_s"] = float(total_seconds)
        self.save_config()
        
        print(f"Episode time set to: {minutes}:{seconds:02d} ({total_seconds}s)")
    
    def toggle_start_stop(self):
        """Toggle between start and stop"""
        if self.start_stop_btn.isChecked():
            # Button is now checked, start the run
            self.start_run()
        else:
            # Button is now unchecked, stop the run
            self.stop_run()
    
    def start_run(self):
        """Start robot control run"""
        if self.worker and self.worker.isRunning():
            self.log_text.append("[warning] Already running - stop current run first")
            self.start_stop_btn.setChecked(False)
            return
            
        # Update config with current episodes value
        self.config["control"]["num_episodes"] = int(self.episodes_display.text())
        self.save_config()
        
        # Check object gate if enabled
        if self.config["ui"].get("object_gate", False):
            if not self.check_object_presence():
                self.log_text.append("[warning] No object detected in ROI - place object before starting")
                self.action_label.setText("No object detected")
                self.start_stop_btn.setChecked(False)
                return
                
        # Update button text and UI
        self.start_stop_btn.setText("STOP")
        self.start_stop_btn.setChecked(True)
        self.home_btn.setEnabled(False)
        self.settings_btn.setEnabled(False)
        self.episodes_up_btn.setEnabled(False)
        self.episodes_down_btn.setEnabled(False)
        
        # Start timer
        self.start_time = datetime.now()
        self.elapsed_seconds = 0
        self.timer.start(1000)  # Update every second
        
        # Create and start worker
        self.worker = RobotWorker(self.config)
        self.worker.status_update.connect(self.on_status_update)
        self.worker.log_message.connect(self.on_log_message)
        self.worker.progress_update.connect(self.on_progress_update)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.run_completed.connect(self.on_run_completed)
        self.worker.connection_changed.connect(self.robot_indicator1.set_connected)
        self.worker.connection_changed.connect(self.robot_indicator2.set_connected)
        self.worker.start()
        
    def stop_run(self):
        """Stop current run - EMERGENCY STOP with arm catch"""
        if self.worker and self.worker.isRunning():
            self.log_text.append("[EMERGENCY] Stopping robot and catching arm...")
            self.action_label.setText("Emergency stop - securing arm...")
            
            # STEP 1: Stop the robot_client process IMMEDIATELY (closes serial connection)
            self.worker.stop()
            
            # STEP 2: Catch the arm ASAP (200ms gives process time to exit and release serial port)
            # Worker cleanup is now fast (<1.5s total, serial port released in ~200-500ms)
            QTimer.singleShot(200, self.emergency_catch_arm)  # 200ms = realistic for serial port release
                
    def emergency_catch_arm(self):
        """EMERGENCY: Catch arm immediately after stop (called 50ms after processes stop)"""
        script_path = ROOT / "rest_pos.py"
        try:
            result = subprocess.run(
                [sys.executable, str(script_path), "--emergency-catch"],
                timeout=3,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                self.log_text.append("[info] ✓ Arm caught and secured at current position")
                # Now move to home with torque kept on
                QTimer.singleShot(500, self.safe_return_home)
            else:
                self.log_text.append(f"[error] Failed to catch arm: {result.stderr}")
                self.action_label.setText("⚠️ Arm catch failed")
        except Exception as e:
            self.log_text.append(f"[error] Arm catch error: {e}")
            self.action_label.setText("⚠️ Emergency stop error")
    
    def safe_return_home(self):
        """Safely return to home with torque enabled (called after arm is caught)"""
        self.log_text.append("[info] Returning to home position...")
        self.go_home(keep_torque=True)
    
    def go_home(self, keep_torque=False):
        """Move robot to home/rest position
        
        Args:
            keep_torque: If True, keep torque enabled after reaching home (safety feature for emergency stops)
        """
        self.action_label.setText("Moving to home...")
        self.home_btn.setEnabled(False)
        
        # Change button color to orange while running
        self.home_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: 2px solid #F57C00;
                border-radius: 12px;
                font-size: 64px;
                font-weight: normal;
                padding: 10px;
            }
        """)
        
        try:
            # Run rest position script
            import subprocess
            result = subprocess.run(
                [sys.executable, str(ROOT / "rest_pos.py"), "--go"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                self.action_label.setText("✓ At home position")
            else:
                self.action_label.setText("⚠️  Home failed")
                self.log_text.append("[error] Failed to move to home position - check robot connection and power")
        except subprocess.TimeoutExpired:
            self.action_label.setText("⚠️  Home timeout")
            self.log_text.append("[error] Home operation timed out")
        except Exception as e:
            self.action_label.setText("⚠️  Home error")
            self.log_text.append(f"[error] Home operation failed: {e}")
        finally:
            # Restore button color to blue
            self.home_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    border: 2px solid #1976D2;
                    border-radius: 12px;
                    font-size: 64px;
                    font-weight: normal;
                    padding: 10px;
                }
                QPushButton:hover {
                    background-color: #1E88E5;
                    border-color: #1565C0;
                }
                QPushButton:pressed {
                    background-color: #1976D2;
                }
                QPushButton:disabled {
                    background-color: #9e9e9e;
                    color: #616161;
                    border-color: #757575;
                }
            """)
            self.home_btn.setEnabled(True)
            
    def check_object_presence(self):
        """Check if object is present in ROI using simple variance threshold"""
        try:
            import cv2
            import numpy as np
            
            cam_idx = self.config["cameras"]["front"]["index_or_path"]
            roi = self.config["ui"]["roi"]
            threshold = self.config["ui"]["presence_threshold"]
            
            x, y, w, h = roi
            
            cap = cv2.VideoCapture(cam_idx)
            if not cap.isOpened():
                return True  # Fail open - don't block operation
                
            ret, frame = cap.read()
            cap.release()
            
            if not ret or frame is None:
                return True
                
            # Extract ROI
            roi_img = frame[y:y+h, x:x+w]
            
            # Calculate normalized standard deviation
            variance = float(roi_img.std()) / 255.0
            
            print(f"Object gate: variance={variance:.3f}, threshold={threshold:.3f}")
            return variance > threshold
            
        except Exception as e:
            print(f"Object gate error: {e}")
            return True  # Fail open
            
    def on_status_update(self, status):
        """Handle status update from worker"""
        self.action_label.setText(status)
        
    def on_log_message(self, level, message):
        """Handle log message from worker"""
        print(f"[{level}] {message}")
        # Show in log widget
        if hasattr(self, 'log_text'):
            self.log_text.append(f"[{level}] {message}")
        
    def on_progress_update(self, current, total):
        """Handle progress update from worker"""
        self.action_label.setText(f"Recording Episode {current}/{total}")
        
    def on_error(self, error_key, context):
        """Handle error from worker - log instead of popup"""
        # Get error details
        from error_catalog import ERROR_CATALOG
        
        if error_key in ERROR_CATALOG:
            error_info = ERROR_CATALOG[error_key]
            problem = error_info["problem"]
            solution = error_info["solution"]
            
            # Format problem with context
            try:
                if "{port}" in problem and "port" in context:
                    problem = problem.replace("{port}", context["port"])
                if "{index}" in problem and "index" in context:
                    problem = problem.replace("{index}", str(context["index"]))
                if "{motor_id}" in problem and "motor_id" in context:
                    problem = problem.replace("{motor_id}", str(context["motor_id"]))
                if "{path}" in problem and "path" in context:
                    problem = problem.replace("{path}", context["path"])
            except:
                pass
            
            # Log to console
            self.log_text.append(f"\n[ERROR] {problem}")
            self.log_text.append(f"[SOLUTION] {solution}\n")
            self.action_label.setText("Error occurred - check log")
        else:
            # Unknown error
            self.log_text.append(f"\n[ERROR] Unknown error: {error_key}")
            if "stderr" in context:
                self.log_text.append(f"[DETAILS] {context['stderr'][:500]}\n")
            self.action_label.setText("Error occurred - check log")
        
    def on_run_completed(self, success, summary):
        """Handle run completion"""
        # Stop timer
        self.timer.stop()
        
        # Update UI - reset button to START state
        self.start_stop_btn.setChecked(False)
        self.start_stop_btn.setText("START")
        self.home_btn.setEnabled(True)
        self.settings_btn.setEnabled(True)
        self.episodes_up_btn.setEnabled(True)
        self.episodes_down_btn.setEnabled(True)
        
        if success:
            self.action_label.setText("✓ Run completed")
        else:
            self.action_label.setText("⚠️  Run failed")
            
        # Save to history
        self.save_run_to_history(success, summary)
        self.load_history()
        
        # Auto go home
        QTimer.singleShot(1000, self.go_home)
        
    def update_elapsed_time(self):
        """Update elapsed time display"""
        if self.start_time:
            self.elapsed_seconds = int((datetime.now() - self.start_time).total_seconds())
            minutes = self.elapsed_seconds // 60
            seconds = self.elapsed_seconds % 60
            self.time_label.setText(f"Time: {minutes:02d}:{seconds:02d}")
            
    def save_run_to_history(self, success, summary):
        """Save run result to history"""
        # Load existing history
        if HISTORY_PATH.exists():
            with open(HISTORY_PATH, 'r') as f:
                history = json.load(f)
        else:
            history = {"runs": []}
            
        # Create run entry
        now = datetime.now(TIMEZONE)
        run_entry = {
            "timestamp": now.isoformat(),
            "episodes_completed": self.config["control"]["num_episodes"] if success else 0,
            "episodes_total": self.config["control"]["num_episodes"],
            "status": "completed" if success else "failed",
            "duration_seconds": self.elapsed_seconds,
            "summary": summary
        }
        
        # Add to history (keep last 50)
        history["runs"].insert(0, run_entry)
        history["runs"] = history["runs"][:50]
        
        # Save
        with open(HISTORY_PATH, 'w') as f:
            json.dump(history, f, indent=2)
            
    def load_history(self):
        """Load and display run history"""
        self.history_list.clear()
        
        if not HISTORY_PATH.exists():
            return
            
        with open(HISTORY_PATH, 'r') as f:
            history = json.load(f)
            
        # Display last 10 runs
        for run in history["runs"][:10]:
            # Parse timestamp
            dt = datetime.fromisoformat(run["timestamp"])
            time_str = dt.strftime("%d %b %I:%M %p")
            
            # Format duration
            duration = run["duration_seconds"]
            dur_str = f"{duration//60}m {duration%60}s"
            
            # Status icon
            if run["status"] == "completed":
                icon = "✓"
            elif run["status"] == "failed":
                icon = "✗"
            else:
                icon = "⊗"
                
            # Format line
            episodes = f"{run['episodes_completed']}/{run['episodes_total']}"
            line = f"{icon} {time_str} - {episodes} episodes - {dur_str}"
            
            self.history_list.addItem(line)


def main():
    """Main entry point"""
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="LeRobot Operator Console")
    parser.add_argument('--windowed', action='store_true', 
                       help='Start in windowed mode instead of fullscreen')
    parser.add_argument('--no-fullscreen', action='store_true',
                       help='Disable fullscreen mode (same as --windowed)')
    args = parser.parse_args()
    
    # Determine fullscreen mode
    fullscreen = not (args.windowed or args.no_fullscreen)
    
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle("Fusion")
    
    # Set dark mode palette
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.WindowText, QColor(255, 255, 255))
    palette.setColor(QPalette.Base, QColor(45, 45, 45))
    palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
    palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
    palette.setColor(QPalette.Text, QColor(255, 255, 255))
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, QColor(255, 255, 255))
    palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
    app.setPalette(palette)
    
    # Create and show main window
    window = MainWindow(fullscreen=fullscreen)
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

