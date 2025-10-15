"""
Dashboard Tab - Main robot control interface
This is the existing UI refactored as a tab
"""

import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime
import pytz

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QFrame, QTextEdit, QComboBox
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QColor, QPainter, QPen

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from robot_worker import RobotWorker
from settings_dialog import SettingsDialog

# Timezone
TIMEZONE = pytz.timezone('Australia/Sydney')
ROOT = Path(__file__).parent.parent
HISTORY_PATH = ROOT / "run_history.json"


class CircularProgress(QWidget):
    """Circular progress indicator"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.progress = 0
        self.setFixedSize(24, 24)
    
    def set_progress(self, value):
        self.progress = value
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        pen = QPen(QColor("#555555"), 2)
        painter.setPen(pen)
        painter.setBrush(QColor("#2d2d2d"))
        painter.drawEllipse(2, 2, 20, 20)
        
        if self.progress > 0:
            pen = QPen(QColor("#4CAF50"), 3)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            
            start_angle = -90 * 16
            span_angle = -(self.progress * 360 // 100) * 16
            
            painter.drawArc(3, 3, 18, 18, start_angle, span_angle)


class StatusIndicator(QLabel):
    """Colored dot indicator"""
    
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.connected = False
        self.warning = False
        self.update_style()
    
    def set_connected(self, connected):
        self.connected = connected
        self.warning = False
        self.update_style()
    
    def set_warning(self):
        self.connected = False
        self.warning = True
        self.update_style()
    
    def update_style(self):
        if self.warning:
            color = "#FF9800"
        elif self.connected:
            color = "#4caf50"
        else:
            color = "#f44336"
        
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


class DashboardTab(QWidget):
    """Main dashboard for robot control (existing UI)"""
    
    # Signals for parent window
    settings_requested = Signal()
    
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.worker = None
        self.start_time = None
        self.elapsed_seconds = 0
        
        self.init_ui()
        self.validate_config()
        
        # Timers
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_elapsed_time)
        
        self.connection_check_timer = QTimer()
        self.connection_check_timer.timeout.connect(self.check_connections_background)
        self.connection_check_timer.start(10000)
        
        self.throbber_progress = 0
        self.throbber_update_timer = QTimer()
        self.throbber_update_timer.timeout.connect(self.update_throbber_progress)
        self.throbber_update_timer.start(100)
    
    def init_ui(self):
        """Initialize UI - same as original app.py"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
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
        
        all_status_layout = QHBoxLayout()
        
        # Robot indicators
        arm_label = QLabel("Robot:")
        arm_label.setStyleSheet("color: #ffffff; font-size: 12px;")
        all_status_layout.addWidget(arm_label)
        
        self.robot_indicator1 = StatusIndicator()
        all_status_layout.addWidget(self.robot_indicator1)
        
        all_status_layout.addSpacing(15)
        
        # Camera indicators
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
        self.time_label.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        all_status_layout.addWidget(self.time_label)
        
        all_status_layout.addSpacing(15)
        
        # Action status
        self.action_label = QLabel("At home position")
        self.action_label.setStyleSheet("color: #ffffff; font-size: 12px;")
        all_status_layout.addWidget(self.action_label)
        
        all_status_layout.addSpacing(10)
        
        # Throbber
        self.throbber = CircularProgress()
        all_status_layout.addWidget(self.throbber)
        
        all_status_layout.addSpacing(15)
        
        # Branding
        branding_label = QLabel("NICE LABS Robotics")
        branding_label.setStyleSheet("color: #888888; font-size: 12px; font-weight: bold;")
        all_status_layout.addWidget(branding_label)
        
        all_status_layout.addStretch()
        status_layout.addLayout(all_status_layout)
        
        layout.addWidget(status_frame)
        
        # Unified RUN selector (Models, Sequences, Actions)
        run_frame = QFrame()
        run_frame.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border: 1px solid #404040;
                border-radius: 8px;
                padding: 4px 8px;
            }
        """)
        run_layout = QHBoxLayout(run_frame)
        run_layout.setSpacing(8)
        
        run_label = QLabel("RUN:")
        run_label.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        run_layout.addWidget(run_label)
        
        # Main selector (Models, Sequences, Actions)
        self.run_combo = QComboBox()
        self.run_combo.setMinimumHeight(60)
        self.run_combo.setStyleSheet("""
            QComboBox {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 15px;
                font-weight: bold;
            }
            QComboBox:hover {
                border-color: #2196F3;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 40px;
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 8px solid transparent;
                border-right: 8px solid transparent;
                border-top: 12px solid #ffffff;
                margin-right: 8px;
            }
            QComboBox QAbstractItemView {
                background-color: #404040;
                color: #ffffff;
                selection-background-color: #2196F3;
                font-size: 14px;
            }
        """)
        self.run_combo.currentTextChanged.connect(self.on_run_selection_changed)
        run_layout.addWidget(self.run_combo, stretch=3)
        
        # Checkpoint selector (only visible for models)
        self.checkpoint_combo = QComboBox()
        self.checkpoint_combo.setMinimumHeight(60)
        self.checkpoint_combo.setStyleSheet("""
            QComboBox {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QComboBox:hover {
                border-color: #2196F3;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 40px;
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 8px solid transparent;
                border-right: 8px solid transparent;
                border-top: 12px solid #ffffff;
                margin-right: 8px;
            }
            QComboBox QAbstractItemView {
                background-color: #404040;
                color: #ffffff;
                selection-background-color: #2196F3;
                font-size: 13px;
            }
        """)
        self.checkpoint_combo.currentTextChanged.connect(self.on_checkpoint_changed)
        run_layout.addWidget(self.checkpoint_combo, stretch=1)
        self.checkpoint_combo.hide()  # Hidden by default
        
        layout.addWidget(run_frame)
        
        # Populate run dropdown
        self.refresh_run_selector()
        
        # Main controls - simplified for smaller screen
        main_control_layout = QHBoxLayout()
        main_control_layout.setSpacing(10)
        
        # Episodes control (compact)
        episodes_container = QVBoxLayout()
        episodes_container.setSpacing(3)
        
        episodes_label = QLabel("Episodes")
        episodes_label.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: bold;")
        episodes_label.setAlignment(Qt.AlignCenter)
        episodes_container.addWidget(episodes_label)
        
        self.episodes_up_btn = QPushButton("▲")
        self.episodes_up_btn.setMinimumSize(60, 50)
        self.episodes_up_btn.setStyleSheet("""
            QPushButton {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 6px;
                font-size: 24px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
        """)
        self.episodes_up_btn.clicked.connect(lambda: self.change_episodes(1))
        episodes_container.addWidget(self.episodes_up_btn)
        
        self.episodes_display = QLabel("3")
        self.episodes_display.setStyleSheet("""
            color: #ffffff;
            background-color: #2d2d2d;
            border: 2px solid #404040;
            border-radius: 6px;
            font-size: 24px;
            font-weight: bold;
            padding: 5px;
        """)
        self.episodes_display.setAlignment(Qt.AlignCenter)
        self.episodes_display.setMinimumSize(60, 40)
        episodes_container.addWidget(self.episodes_display)
        
        self.episodes_down_btn = QPushButton("▼")
        self.episodes_down_btn.setMinimumSize(60, 50)
        self.episodes_down_btn.setStyleSheet("""
            QPushButton {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 6px;
                font-size: 24px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
        """)
        self.episodes_down_btn.clicked.connect(lambda: self.change_episodes(-1))
        episodes_container.addWidget(self.episodes_down_btn)
        
        main_control_layout.addLayout(episodes_container)
        
        # Time controls (compact)
        time_container = QVBoxLayout()
        time_container.setSpacing(3)
        
        time_label = QLabel("Time (m:s)")
        time_label.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: bold;")
        time_label.setAlignment(Qt.AlignCenter)
        time_container.addWidget(time_label)
        
        time_displays = QHBoxLayout()
        time_displays.setSpacing(5)
        
        # Minutes
        min_layout = QVBoxLayout()
        min_layout.setSpacing(3)
        
        min_up = QPushButton("▲")
        min_up.setMinimumSize(50, 30)
        min_up.setStyleSheet("""
            QPushButton {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 4px;
                font-size: 18px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
        """)
        min_up.clicked.connect(lambda: self.change_time('minutes', 1))
        min_layout.addWidget(min_up)
        
        self.minutes_display = QLabel("0")
        self.minutes_display.setStyleSheet("""
            color: #ffffff;
            background-color: #2d2d2d;
            border: 2px solid #404040;
            border-radius: 4px;
            font-size: 20px;
            font-weight: bold;
            padding: 3px;
        """)
        self.minutes_display.setAlignment(Qt.AlignCenter)
        self.minutes_display.setMinimumSize(50, 35)
        min_layout.addWidget(self.minutes_display)
        
        min_down = QPushButton("▼")
        min_down.setMinimumSize(50, 30)
        min_down.setStyleSheet("""
            QPushButton {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 4px;
                font-size: 18px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
        """)
        min_down.clicked.connect(lambda: self.change_time('minutes', -1))
        min_layout.addWidget(min_down)
        
        time_displays.addLayout(min_layout)
        
        # Seconds
        sec_layout = QVBoxLayout()
        sec_layout.setSpacing(3)
        
        sec_up = QPushButton("▲")
        sec_up.setMinimumSize(50, 30)
        sec_up.setStyleSheet("""
            QPushButton {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 4px;
                font-size: 18px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
        """)
        sec_up.clicked.connect(lambda: self.change_time('seconds', 5))
        sec_layout.addWidget(sec_up)
        
        self.seconds_display = QLabel("25")
        self.seconds_display.setStyleSheet("""
            color: #ffffff;
            background-color: #2d2d2d;
            border: 2px solid #404040;
            border-radius: 4px;
            font-size: 20px;
            font-weight: bold;
            padding: 3px;
        """)
        self.seconds_display.setAlignment(Qt.AlignCenter)
        self.seconds_display.setMinimumSize(50, 35)
        sec_layout.addWidget(self.seconds_display)
        
        sec_down = QPushButton("▼")
        sec_down.setMinimumSize(50, 30)
        sec_down.setStyleSheet("""
            QPushButton {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 4px;
                font-size: 18px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
        """)
        sec_down.clicked.connect(lambda: self.change_time('seconds', -5))
        sec_layout.addWidget(sec_down)
        
        time_displays.addLayout(sec_layout)
        time_container.addLayout(time_displays)
        
        main_control_layout.addLayout(time_container)
        
        # START/STOP and HOME buttons
        buttons_layout = QVBoxLayout()
        buttons_layout.setSpacing(10)
        
        self.start_stop_btn = QPushButton("START")
        self.start_stop_btn.setMinimumHeight(80)
        self.start_stop_btn.setCheckable(True)
        self.start_stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #2e7d32;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 28px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1b5e20;
            }
            QPushButton:checked {
                background-color: #c62828;
            }
            QPushButton:checked:hover {
                background-color: #b71c1c;
            }
        """)
        self.start_stop_btn.clicked.connect(self.toggle_start_stop)
        buttons_layout.addWidget(self.start_stop_btn)
        
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)
        
        self.home_btn = QPushButton("⌂")
        self.home_btn.setMinimumHeight(60)
        self.home_btn.setMinimumWidth(80)
        self.home_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: 2px solid #1976D2;
                border-radius: 8px;
                font-size: 36px;
            }
            QPushButton:hover {
                background-color: #1E88E5;
            }
        """)
        self.home_btn.clicked.connect(self.go_home)
        bottom_row.addWidget(self.home_btn)
        
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setMinimumHeight(60)
        self.settings_btn.setMinimumWidth(80)
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #757575;
                color: white;
                border: 2px solid #616161;
                border-radius: 8px;
                font-size: 28px;
            }
            QPushButton:hover {
                background-color: #616161;
            }
        """)
        self.settings_btn.clicked.connect(self.open_settings)
        bottom_row.addWidget(self.settings_btn)
        
        buttons_layout.addLayout(bottom_row)
        
        main_control_layout.addLayout(buttons_layout, stretch=1)
        
        layout.addLayout(main_control_layout)
        
        # Log text area (compact)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #2d2d2d;
                color: #ffffff;
                font-family: monospace;
                font-size: 13px;
                border: 1px solid #404040;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.log_text)
        
        # Welcome message
        self.log_text.append("=== NICE LABS Robotics ===")
        self.log_text.append("Dashboard ready. Select Record or Sequence tabs to get started.")
        
        # Load initial values from config
        episode_time = self.config["control"].get("episode_time_s", 25.0)
        minutes = int(episode_time // 60)
        seconds = int(episode_time % 60)
        self.minutes_display.setText(str(minutes))
        self.seconds_display.setText(str(seconds))
        
        self.episodes_display.setText(str(self.config["control"].get("num_episodes", 3)))
        
        # Populate run selector
        self.refresh_run_selector()
    
    def refresh_run_selector(self):
        """Populate RUN dropdown with Models, Sequences, and Actions"""
        self.run_combo.blockSignals(True)
        self.run_combo.clear()
        
        # Add header (disabled item)
        self.run_combo.addItem("-- Select Item --")
        self.run_combo.model().item(0).setEnabled(False)
        
        # Import managers
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from utils.actions_manager import ActionsManager
        from utils.sequences_manager import SequencesManager
        
        actions_mgr = ActionsManager()
        sequences_mgr = SequencesManager()
        
        # Add Models first (Green)
        try:
            train_dir = Path(self.config["policy"].get("base_path", ""))
            if train_dir.exists():
                for item in sorted(train_dir.iterdir()):
                    if item.is_dir() and (item / "checkpoints").exists():
                        self.run_combo.addItem(f"🤖 Model: {item.name}")
        except Exception as e:
            print(f"[DASHBOARD] Error loading models: {e}")
        
        # Add Sequences (Purple)
        sequences = sequences_mgr.list_sequences()
        if sequences:
            for seq in sequences:
                self.run_combo.addItem(f"🔗 Sequence: {seq}")
        
        # Add Actions (Blue)
        actions = actions_mgr.list_actions()
        if actions:
            for action in actions:
                self.run_combo.addItem(f"🎬 Action: {action}")
        
        self.run_combo.blockSignals(False)
    
    def on_run_selection_changed(self, text):
        """Handle RUN selector change - show/hide checkpoint dropdown"""
        print(f"[DASHBOARD] Run selection changed: {text}")
        
        if text.startswith("🤖 Model:"):
            # Show checkpoint dropdown for models
            self.checkpoint_combo.show()
            
            # Extract model name and load checkpoints
            model_name = text.replace("🤖 Model: ", "")
            self.load_checkpoints_for_model(model_name)
        else:
            # Hide checkpoint dropdown for sequences and actions
            self.checkpoint_combo.hide()
            self.checkpoint_combo.clear()
    
    def load_checkpoints_for_model(self, model_name: str):
        """Load checkpoints for the selected model"""
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
                
                # Auto-select "last"
                for i in range(self.checkpoint_combo.count()):
                    if self.checkpoint_combo.itemData(i) == "last":
                        self.checkpoint_combo.setCurrentIndex(i)
                        break
            else:
                self.checkpoint_combo.addItem("No checkpoints")
                
        except Exception as e:
            print(f"[DASHBOARD] Error loading checkpoints: {e}")
            self.checkpoint_combo.addItem("Error loading")
        
        self.checkpoint_combo.blockSignals(False)
    
    def on_checkpoint_changed(self, text):
        """Handle checkpoint selection"""
        # Update config when checkpoint changes
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
                    except Exception as e:
                        print(f"[DASHBOARD] Error updating policy path: {e}")
    
    def refresh_policy_list(self):
        """Legacy method - now uses refresh_run_selector"""
        self.refresh_run_selector()
    
    def validate_config(self):
        """Validate configuration"""
        # Check robot port
        port = self.config["robot"]["port"]
        if not os.path.exists(port):
            self.robot_indicator1.set_connected(False)
        else:
            self.robot_indicator1.set_connected(True)
        
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
        except:
            pass
        
        self.camera_indicator1.set_connected(camera_count >= 1)
        self.camera_indicator2.set_connected(camera_count >= 2)
        self.camera_indicator3.set_connected(camera_count >= 3)
    
    def update_throbber_progress(self):
        """Update throbber"""
        self.throbber_progress += 1
        if self.throbber_progress > 100:
            self.throbber_progress = 0
        self.throbber.set_progress(self.throbber_progress)
    
    def check_connections_background(self):
        """Check connections"""
        if self.worker and self.worker.isRunning():
            return
        self.validate_config()
    
    def change_episodes(self, delta):
        """Change episode count"""
        current = int(self.episodes_display.text())
        new_value = max(1, min(99, current + delta))
        self.episodes_display.setText(str(new_value))
        self.config["control"]["num_episodes"] = new_value
    
    def change_time(self, unit, delta):
        """Change time"""
        if unit == 'minutes':
            current = int(self.minutes_display.text())
            new_value = max(0, min(99, current + delta))
            self.minutes_display.setText(str(new_value))
        else:
            current = int(self.seconds_display.text())
            new_value = max(0, min(59, current + delta))
            self.seconds_display.setText(str(new_value))
        
        minutes = int(self.minutes_display.text())
        seconds = int(self.seconds_display.text())
        total_seconds = minutes * 60 + seconds
        self.config["control"]["episode_time_s"] = float(total_seconds)
    
    def toggle_start_stop(self):
        """Toggle start/stop"""
        if self.start_stop_btn.isChecked():
            self.start_run()
        else:
            self.stop_run()
    
    def start_run(self):
        """Start robot run"""
        self.start_stop_btn.setText("STOP")
        self.log_text.append("[info] Starting robot...")
        # Implementation from original app.py
    
    def stop_run(self):
        """Stop robot run"""
        self.start_stop_btn.setChecked(False)
        self.start_stop_btn.setText("START")
        self.log_text.append("[info] Stopping robot...")
    
    def go_home(self):
        """Go to home position"""
        self.action_label.setText("Moving to home...")
        self.log_text.append("[info] Moving to home position...")
        
        try:
            result = subprocess.run(
                [sys.executable, str(ROOT / "rest_pos.py"), "--go"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                self.action_label.setText("✓ At home position")
                self.log_text.append("[info] ✓ Home position reached")
            else:
                self.action_label.setText("⚠️ Home failed")
                self.log_text.append(f"[error] Home failed: {result.stderr}")
        except Exception as e:
            self.action_label.setText("⚠️ Home error")
            self.log_text.append(f"[error] Home error: {e}")
    
    def open_settings(self):
        """Open settings"""
        self.settings_requested.emit()
    
    def update_elapsed_time(self):
        """Update elapsed time"""
        if self.start_time:
            self.elapsed_seconds = int((datetime.now() - self.start_time).total_seconds())
            minutes = self.elapsed_seconds // 60
            seconds = self.elapsed_seconds % 60
            self.time_label.setText(f"Time: {minutes:02d}:{seconds:02d}")

