"""
Dashboard Tab - Main robot control interface
This is the existing UI refactored as a tab
"""

import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional
import pytz

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QFrame, QTextEdit, QComboBox, QSizePolicy, QSpinBox, QCheckBox
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QColor, QPainter, QPen

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from robot_worker import RobotWorker
from utils.execution_manager import ExecutionWorker
from utils.hand_safety import HandSafetyMonitor, HandSafetySettings

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
        self.setVisible(True)  # Always visible
    
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
        self.null = False  # Initialize null attribute
        self.update_style()
    
    def set_connected(self, connected):
        self.connected = connected
        self.warning = False
        self.null = False  # Clear null state when setting connected
        self.update_style()
    
    def set_warning(self):
        self.connected = False
        self.warning = True
        self.null = False  # Clear null state when setting warning
        self.update_style()
    
    def set_null(self):
        """Set as null/empty indicator"""
        self.connected = False
        self.warning = False
        self.null = True
        self.update_style()
    
    def update_style(self):
        if hasattr(self, 'null') and self.null:
            # Null indicator - unfilled black circle
            self.setFixedSize(20, 20)
            self.setStyleSheet("""
                QLabel {
                    background-color: transparent;
                    border: 2px solid #606060;
                    border-radius: 10px;
                }
            """)
        elif self.warning:
            color = "#FF9800"
            self.setFixedSize(20, 20)
            self.setStyleSheet(f"""
                QLabel {{
                    background-color: {color};
                    border-radius: 10px;
                }}
            """)
        elif self.connected:
            color = "#2e7d32"
            self.setFixedSize(20, 20)
            self.setStyleSheet(f"""
                QLabel {{
                    background-color: {color};
                    border-radius: 10px;
                }}
            """)
        else:
            color = "#f44336"
            self.setFixedSize(20, 20)
            self.setStyleSheet(f"""
                QLabel {{
                    background-color: {color};
                    border-radius: 10px;
                }}
            """)


class DashboardTab(QWidget):
    """Main dashboard for robot control (existing UI)"""
    
    def __init__(self, config: dict, parent=None, device_manager=None):
        super().__init__(parent)
        self.config = config
        self.device_manager = device_manager
        self.worker = None
        self.execution_worker = None  # New unified execution worker
        self.start_time = None
        self.elapsed_seconds = 0
        self.is_running = False
        self.saved_runs_value = 1  # Remember runs value when toggling loop
        self._vision_state_active = False
        self._last_vision_signature = None
        self.hand_safety_monitor: Optional[HandSafetyMonitor] = None

        # Status circle widget (will be set during init_ui)
        self.robot_status_circle = None
        
        self.init_ui()
        self.validate_config()
        
        # Connect device manager signals if available
        if self.device_manager:
            self.device_manager.robot_status_changed.connect(self.on_robot_status_changed)
            self.device_manager.camera_status_changed.connect(self.on_camera_status_changed)
            self.device_manager.discovery_log.connect(self.on_discovery_log)
        
        # Timers
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_elapsed_time)
        
        # Connection checking is now handled by device_manager
        # self.connection_check_timer = QTimer()
        # self.connection_check_timer.timeout.connect(self.check_connections_background)
        # self.connection_check_timer.start(10000)
        
        self.throbber_progress = 0
        self.throbber_update_timer = QTimer()
        self.throbber_update_timer.timeout.connect(self.update_throbber_progress)
        # Don't start throbber timer until we actually need it
    
    def init_ui(self):
        """Initialize UI - same as original app.py"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Compact single-line status bar
        status_bar = QHBoxLayout()
        status_bar.setSpacing(20)
        
        # Left section: Status indicators
        status_left = QHBoxLayout()
        status_left.setSpacing(15)
        
        # Throbber
        self.throbber = CircularProgress()
        status_left.addWidget(self.throbber)
        
        # Robot (synced with device_manager)
        robot_group = QHBoxLayout()
        robot_group.setSpacing(6)
        robot_lbl = QLabel("Robot")
        robot_lbl.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        robot_group.addWidget(robot_lbl)
        self.robot_indicator1 = StatusIndicator()
        self.robot_indicator1.set_null()  # Start as empty until discovery
        robot_group.addWidget(self.robot_indicator1)
        self.robot_indicator2 = StatusIndicator()
        self.robot_indicator2.set_null()
        robot_group.addWidget(self.robot_indicator2)
        status_left.addLayout(robot_group)
        
        # Store reference for device_manager updates
        self.robot_status_circle = self.robot_indicator1
        
        # Cameras (synced with device_manager)
        camera_group = QHBoxLayout()
        camera_group.setSpacing(6)
        camera_lbl = QLabel("Cameras")
        camera_lbl.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        camera_group.addWidget(camera_lbl)
        self.camera_indicator1 = StatusIndicator()
        self.camera_indicator1.set_null()  # Front camera - start as empty until discovery
        camera_group.addWidget(self.camera_indicator1)
        self.camera_indicator2 = StatusIndicator()
        self.camera_indicator2.set_null()  # Wrist camera - start as empty until discovery
        camera_group.addWidget(self.camera_indicator2)
        self.camera_indicator3 = StatusIndicator()
        self.camera_indicator3.set_null()  # Extra indicator (unused)
        camera_group.addWidget(self.camera_indicator3)
        status_left.addLayout(camera_group)
        
        # Store references for device_manager updates
        self.camera_front_circle = self.camera_indicator1
        self.camera_wrist_circle = self.camera_indicator2
        
        # Time
        time_group = QHBoxLayout()
        time_group.setSpacing(6)
        self.time_label = QLabel("00:00")
        self.time_label.setStyleSheet("color: #4CAF50; font-size: 12px; font-weight: bold; font-family: monospace;")
        time_group.addWidget(self.time_label)
        status_left.addLayout(time_group)
        
        status_bar.addLayout(status_left)
        
        # Center: Action status with subtle background
        self.action_label = QLabel("At home position")
        self._action_label_style_template = (
            "color: #ffffff; font-size: 14px; font-weight: bold; "
            "background-color: {bg}; border-radius: 4px; padding: 8px 20px;"
        )
        self._set_action_label_style("#383838")
        self.action_label.setAlignment(Qt.AlignCenter)
        status_bar.addWidget(self.action_label, stretch=1)
        
        # Right: Branding
        branding = QLabel("NICE LABS Robotics")
        branding.setStyleSheet("color: #707070; font-size: 11px; font-weight: bold;")
        branding.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        status_bar.addWidget(branding)
        
        layout.addLayout(status_bar)
        
        # Unified RUN selector (Models, Sequences, Actions)
        run_frame = QFrame()
        run_frame.setFixedHeight(95)
        run_frame.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border: 1px solid #404040;
                border-radius: 6px;
            }
        """)
        run_layout = QHBoxLayout(run_frame)
        run_layout.setSpacing(10)
        run_layout.setContentsMargins(10, 6, 10, 6)
        
        run_label = QLabel("RUN:")
        run_label.setStyleSheet("color: #ffffff; font-size: 19px; font-weight: bold;")
        run_layout.addWidget(run_label)
        
        # Main selector (Models, Sequences, Actions)
        self.run_combo = QComboBox()
        self.run_combo.setMinimumHeight(85)
        self.run_combo.setMaximumHeight(85)
        self.run_combo.setStyleSheet("""
            QComboBox {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 6px;
                padding: 6px 40px 6px 12px;
                font-size: 19px;
                font-weight: bold;
            }
            QComboBox:hover {
                border-color: #4CAF50;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 40px;
                border: none;
                padding-right: 6px;
            }
            QComboBox::down-arrow {
                width: 0;
                height: 0;
                border-style: solid;
                border-width: 8px 6px 0 6px;
                border-color: #ffffff transparent transparent transparent;
            }
            QComboBox QAbstractItemView {
                background-color: #404040;
                color: #ffffff;
                selection-background-color: #4CAF50;
                font-size: 16px;
            }
        """)
        self.run_combo.currentTextChanged.connect(self.on_run_selection_changed)
        run_layout.addWidget(self.run_combo, stretch=3)
        
        # Checkpoint selector (only visible for models)
        self.checkpoint_combo = QComboBox()
        self.checkpoint_combo.setMinimumHeight(85)
        self.checkpoint_combo.setMaximumHeight(85)
        self.checkpoint_combo.setStyleSheet("""
            QComboBox {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 6px;
                padding: 6px 40px 6px 12px;
                font-size: 17px;
            }
            QComboBox:hover {
                border-color: #4CAF50;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 40px;
                border: none;
                padding-right: 6px;
            }
            QComboBox::down-arrow {
                width: 0;
                height: 0;
                border-style: solid;
                border-width: 8px 6px 0 6px;
                border-color: #ffffff transparent transparent transparent;
            }
            QComboBox QAbstractItemView {
                background-color: #404040;
                color: #ffffff;
                selection-background-color: #4CAF50;
                font-size: 15px;
            }
        """)
        self.checkpoint_combo.currentTextChanged.connect(self.on_checkpoint_changed)
        run_layout.addWidget(self.checkpoint_combo, stretch=1)
        self.checkpoint_combo.hide()  # Hidden by default
        
        layout.addWidget(run_frame)
        
        # Populate run dropdown
        self.refresh_run_selector()
        
        # Main controls - Clean single row
        controls_row = QHBoxLayout()
        controls_row.setSpacing(15)
        
        # Episodes - Simple labeled spinbox
        episodes_frame = QFrame()
        episodes_frame.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border: 1px solid #404040;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        episodes_layout = QVBoxLayout(episodes_frame)
        episodes_layout.setSpacing(5)
        episodes_layout.setContentsMargins(10, 10, 10, 10)
        
        # Header with Loop and Episodes labels
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)
        
        loop_label = QLabel("Loop")
        loop_label.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        loop_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(loop_label)
        
        runs_label = QLabel("Runs")
        runs_label.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        runs_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(runs_label, stretch=1)
        
        episodes_layout.addLayout(header_layout)
        
        # Loop checkbox and episodes spinner in same row
        episodes_controls = QHBoxLayout()
        episodes_controls.setSpacing(10)
        episodes_controls.setAlignment(Qt.AlignTop)  # Align all controls to top
        
        # Small loop checkbox (40x40) aligned to top
        self.loop_checkbox = QCheckBox("✓")
        self.loop_checkbox.setFixedSize(40, 40)
        self.loop_checkbox.setStyleSheet("""
            QCheckBox {
                background-color: #404040;
                border: 2px solid #505050;
                border-radius: 4px;
                color: transparent;
                font-size: 22px;
                font-weight: bold;
                text-align: center;
                padding: 0px;
            }
            QCheckBox:hover {
                border-color: #4CAF50;
                background-color: #4a4a4a;
            }
            QCheckBox:checked {
                background-color: #4CAF50;
                border-color: #4CAF50;
                color: white;
            }
            QCheckBox::indicator {
                width: 0px;
                height: 0px;
            }
        """)
        self.loop_checkbox.stateChanged.connect(self.on_loop_toggled)
        episodes_controls.addWidget(self.loop_checkbox)
        
        self.episodes_spin = QSpinBox()
        self.episodes_spin.setRange(1, 999)
        self.episodes_spin.setValue(self.config.get("num_episodes", 1))  # Default to 1 episode
        self.episodes_spin.setMinimumHeight(80)
        self.episodes_spin.setButtonSymbols(QSpinBox.NoButtons)
        self.episodes_spin.setAlignment(Qt.AlignCenter)
        self.episodes_spin.setStyleSheet("""
            QSpinBox {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 6px;
                padding: 8px;
                font-size: 32px;
                font-weight: bold;
            }
            QSpinBox:focus {
                border-color: #4CAF50;
            }
        """)
        episodes_controls.addWidget(self.episodes_spin, stretch=1)
        
        episodes_layout.addLayout(episodes_controls)
        controls_row.addWidget(episodes_frame)
        
        # Time - Simple labeled spinbox
        time_frame = QFrame()
        time_frame.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border: 1px solid #404040;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        time_layout = QVBoxLayout(time_frame)
        time_layout.setSpacing(5)
        time_layout.setContentsMargins(10, 10, 10, 10)
        
        time_label = QLabel("Time/Episode (s)")
        time_label.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        time_label.setAlignment(Qt.AlignCenter)
        time_layout.addWidget(time_label)
        
        self.episode_time_spin = QSpinBox()
        self.episode_time_spin.setRange(1, 3600)
        self.episode_time_spin.setValue(self.config.get("episode_time_s", 30))
        self.episode_time_spin.setMinimumHeight(80)
        self.episode_time_spin.setButtonSymbols(QSpinBox.NoButtons)
        self.episode_time_spin.setAlignment(Qt.AlignCenter)
        self.episode_time_spin.setStyleSheet("""
            QSpinBox {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 6px;
                padding: 8px;
                font-size: 32px;
                font-weight: bold;
            }
            QSpinBox:focus {
                border-color: #4CAF50;
            }
        """)
        time_layout.addWidget(self.episode_time_spin)
        controls_row.addWidget(time_frame)
        
        # START/STOP button
        self.start_stop_btn = QPushButton("START")
        self.start_stop_btn.setMinimumHeight(128)
        self.start_stop_btn.setCheckable(True)
        self.start_stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 32px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
            QPushButton:checked {
                background-color: #c62828;
            }
            QPushButton:checked:hover {
                background-color: #b71c1c;
            }
        """)
        self.start_stop_btn.clicked.connect(self.toggle_start_stop)
        controls_row.addWidget(self.start_stop_btn, stretch=2)
        
        # HOME button - always square (width = height)
        self.home_btn = QPushButton("⌂")
        self.home_btn.setFixedSize(128, 128)
        self.home_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: 2px solid #1976D2;
                border-radius: 10px;
                font-size: 48px;
            }
            QPushButton:hover {
                background-color: #1E88E5;
            }
        """)
        self.home_btn.clicked.connect(self.go_home)
        controls_row.addWidget(self.home_btn)
        
        layout.addLayout(controls_row)
        
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
        
        # Config values already set in spinbox initialization above
        
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
    
    def on_loop_toggled(self, state):
        """Handle loop checkbox toggle"""
        if state == Qt.Checked:
            # Loop mode ON - save current value and show infinity
            self.saved_runs_value = self.episodes_spin.value()
            self.episodes_spin.setEnabled(False)
            self.episodes_spin.setSpecialValueText("∞")
            self.episodes_spin.setValue(self.episodes_spin.minimum())  # Set to min to show special text
        else:
            # Loop mode OFF - restore previous value
            self.episodes_spin.setEnabled(True)
            self.episodes_spin.setSpecialValueText("")
            self.episodes_spin.setValue(self.saved_runs_value)  # Restore saved value
    
    def validate_config(self):
        """Validate configuration
        
        NOTE: Status indicators are now managed by device_manager
        This method is kept for backwards compatibility but doesn't update indicators
        """
        # Status indicators are now updated by device_manager signals
        # We don't override them here to avoid conflicts
        pass
    
    def update_throbber_progress(self):
        """Update throbber"""
        self.throbber_progress += 1
        if self.throbber_progress > 100:
            self.throbber_progress = 0
        self.throbber.set_progress(self.throbber_progress)
    
    def check_connections_background(self):
        """Check connections - now handled by device_manager"""
        # Connection checking is now centralized in device_manager
        pass
    
    
    def toggle_start_stop(self):
        """Toggle start/stop"""
        if self.start_stop_btn.isChecked():
            self.start_run()
        else:
            self.stop_run()
    
    def start_run(self):
        """Start robot run - unified execution for models, recordings, and sequences"""
        if self.is_running:
            self.log_text.append("[warning] Already running")
            return

        # Get selected item
        selected = self.run_combo.currentText()

        self._vision_state_active = False
        self._last_vision_signature = None
        
        if selected.startswith("--"):
            self.log_text.append("[warning] No item selected")
            self.start_stop_btn.setChecked(False)
            return
        
        # Parse selection
        execution_type, execution_name = self._parse_run_selection(selected)
        
        if not execution_type or not execution_name:
            self.log_text.append("[error] Invalid selection")
            self.start_stop_btn.setChecked(False)
            return
        
        # Update UI
        self.start_stop_btn.setText("STOP")
        self.is_running = True
        self.start_time = datetime.now()
        self.timer.start(1000)  # Update elapsed time every second
        
        # Start throbber
        self.throbber_update_timer.start(100)
        
        self.log_text.append(f"[info] Starting {execution_type}: {execution_name}")
        self.action_label.setText(f"Starting {execution_type}...")

        # Activate safety monitoring before motors start moving
        self._start_hand_safety_monitor()

        # Handle models based on execution mode
        if execution_type == "model":
            local_mode = self.config.get("policy", {}).get("local_mode", True)
            
            if local_mode:
                # Local mode: Use ExecutionWorker (which uses lerobot-record)
                self.log_text.append("[info] Using local mode (lerobot-record)")
                # Get checkpoint and episode settings from UI
                checkpoint_name = self.checkpoint_combo.currentData() if self.checkpoint_combo.isVisible() else "last"
                
                # Check if loop mode is enabled
                if self.loop_checkbox.isChecked():
                    num_episodes = -1  # Infinite loop
                    self.log_text.append("[info] Loop mode enabled (∞ episodes)")
                else:
                    num_episodes = self.episodes_spin.value()
                
                episode_time = self.episode_time_spin.value()
                
                self._start_execution_worker(execution_type, execution_name, {
                    "checkpoint": checkpoint_name,
                    "duration": episode_time,
                    "num_episodes": num_episodes
                })
            else:
                # Server mode: Use RobotWorker (async inference)
                self.log_text.append("[info] Using server mode (async inference)")
                self._start_model_execution(execution_name)
        else:
            # For recordings and sequences, use ExecutionWorker
            options = {}
            if execution_type == "sequence":
                options["loop"] = self.loop_checkbox.isChecked()
            self._start_execution_worker(execution_type, execution_name, options)
    
    def _start_model_execution(self, model_name: str):
        """Start model execution using RobotWorker directly"""
        # Get checkpoint path
        checkpoint_name = self.checkpoint_combo.currentData() if self.checkpoint_combo.isVisible() else "last"
        
        try:
            train_dir = Path(self.config["policy"].get("base_path", ""))
            checkpoint_path = train_dir / model_name / "checkpoints" / checkpoint_name / "pretrained_model"
            
            # Update config for this run
            model_config = self.config.copy()
            model_config["policy"]["path"] = str(checkpoint_path)
            
            self.log_text.append(f"[info] Loading model: {checkpoint_path}")
            
            # Stop any existing worker first
            if self.worker and self.worker.isRunning():
                self.log_text.append("[warning] Stopping previous worker...")
                self.worker.stop()
                self.worker.wait(2000)
            
            # Create RobotWorker directly (not nested in another thread)
            self.worker = RobotWorker(model_config)

            self._connect_safety_to_worker(self.worker)

            # Connect signals with error handling
            self.worker.status_update.connect(self._on_status_update)
            self.worker.log_message.connect(self._on_log_message)
            self.worker.progress_update.connect(self._on_progress_update)
            self.worker.run_completed.connect(self._on_model_completed)
            self.worker.finished.connect(self._on_worker_thread_finished)
            
            # Start worker
            self.worker.start()
            
        except Exception as e:
            import traceback
            self.log_text.append(f"[error] Failed to start model: {e}")
            self.log_text.append(f"[error] Traceback: {traceback.format_exc()}")
            self._reset_ui_after_run()
    
    def _start_execution_worker(self, execution_type: str, execution_name: str, options: dict = None):
        """Start ExecutionWorker for recordings and sequences"""
        # Create and start execution worker
        self.execution_worker = ExecutionWorker(
            self.config,
            execution_type,
            execution_name,
            options or {}
        )

        self._connect_safety_to_worker(self.execution_worker)

        # Connect signals
        self.execution_worker.status_update.connect(self._on_status_update)
        self.execution_worker.log_message.connect(self._on_log_message)
        self.execution_worker.progress_update.connect(self._on_progress_update)
        self.execution_worker.execution_completed.connect(self._on_execution_completed)
        self.execution_worker.sequence_step_started.connect(self._on_sequence_step_started)
        self.execution_worker.sequence_step_completed.connect(self._on_sequence_step_completed)
        self.execution_worker.vision_state_update.connect(self._on_vision_state_update)
        
        # Start execution
        self.execution_worker.start()
    
    def run_sequence(self, sequence_name: str, loop: bool = False):
        """Run a sequence from the Sequence tab
        
        Args:
            sequence_name: Name of the sequence to run
            loop: Whether to loop the sequence
        """
        if self.is_running:
            self.log_text.append("[warning] Already running, please stop first")
            return
        
        self.log_text.append(f"[info] Starting sequence: {sequence_name} (loop={loop})")

        # Update UI state
        self.is_running = True
        self.start_stop_btn.setChecked(True)
        self.start_stop_btn.setText("⏹ STOP")
        self.action_label.setText(f"Sequence: {sequence_name}")
        self._vision_state_active = False
        self._last_vision_signature = None

        self._start_hand_safety_monitor()

        # Start execution worker
        self._start_execution_worker("sequence", sequence_name, {"loop": loop})
    
    def stop_run(self):
        """Stop robot run"""
        if not self.is_running:
            return

        self.log_text.append("[info] Stopping...")
        self.action_label.setText("Stopping...")

        self._stop_hand_safety_monitor()

        # Stop execution worker (for recordings/sequences)
        if self.execution_worker and self.execution_worker.isRunning():
            self.execution_worker.stop()
            self.execution_worker.wait(5000)  # Wait up to 5 seconds
        
        # Stop robot worker (for models)
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(5000)  # Wait up to 5 seconds
        
        # Reset UI
        self._reset_ui_after_run()
    
    def _parse_run_selection(self, selected: str) -> tuple:
        """Parse run selection into (type, name)

        Returns:
            ("model", "GrabBlock") or ("recording", "Grab Cup v1") or ("sequence", "Production Run")
        """
        if selected.startswith("🤖 Model:"):
            return ("model", selected.replace("🤖 Model: ", ""))
        elif selected.startswith("🔗 Sequence:"):
            return ("sequence", selected.replace("🔗 Sequence: ", ""))
        elif selected.startswith("🎬 Action:"):
            # Note: "Action" in UI = "recording" in code
            return ("recording", selected.replace("🎬 Action: ", ""))
        else:
            return (None, None)

    def _set_action_label_style(self, background: str):
        self.action_label.setStyleSheet(self._action_label_style_template.format(bg=background))

    def record_vision_status(self, state: str, detail: str, payload: Optional[dict] = None):
        payload = payload or {}
        countdown = payload.get("countdown")
        metric = payload.get("metric")
        zones_raw = payload.get("zones") or []
        zones = [z if isinstance(z, str) else str(z) for z in zones_raw]

        color_map = {
            "triggered": "#4CAF50",
            "idle": "#FFB300",
            "watching": "#383838",
            "complete": "#4CAF50",
            "error": "#b71c1c",
            "clear": "#383838",
        }

        bg = color_map.get(state, "#383838")
        self._set_action_label_style(bg)

        message = detail
        if countdown is not None:
            message = f"{detail} • {countdown}s"
        if metric is not None and state == "triggered":
            message = f"{detail} • metric={metric:.3f}"

        if state in {"idle", "watching", "triggered"}:
            self._vision_state_active = True
        elif state in {"complete", "clear", "error"}:
            self._vision_state_active = False

        if not self._vision_state_active and state in {"complete", "clear"}:
            self._set_action_label_style("#383838")

        self.action_label.setText(message)

        signature = (state, countdown, tuple(zones))
        if signature != self._last_vision_signature:
            log_message = message
            if zones:
                zone_list = ", ".join(zones)
                log_message = f"{message} [{zone_list}]"
            self.log_text.append(f"[vision] {log_message}")
            self.log_text.verticalScrollBar().setValue(
                self.log_text.verticalScrollBar().maximum()
            )
            self._last_vision_signature = signature

    def _on_status_update(self, status: str):
        """Handle status update from worker"""
        if self._vision_state_active:
            return
        self._set_action_label_style("#383838")
        self.action_label.setText(status)

    def _on_log_message(self, level: str, message: str):
        """Handle log message from worker"""
        self.log_text.append(f"[{level}] {message}")
        # Auto-scroll to bottom
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
    
    def _on_progress_update(self, current: int, total: int):
        """Handle progress update from worker"""
        if total > 0:
            progress = int((current / total) * 100)
            # Could update a progress bar here if we add one

    def _on_sequence_step_started(self, index: int, total: int, step: dict):
        seq_tab = self._get_sequence_tab()
        if seq_tab:
            seq_tab.highlight_running_step(index, step)

    def _on_sequence_step_completed(self, index: int, total: int, step: dict):
        # Placeholder for future use (e.g., marking completed)
        pass

    def _on_vision_state_update(self, state: str, payload: dict):
        message = payload.get("message", state.title())
        self.record_vision_status(state, message, payload)
    
    def _on_execution_completed(self, success: bool, summary: str):
        """Handle execution completion (for recordings/sequences)"""
        self.log_text.append(f"[info] {'✓' if success else '✗'} {summary}")
        
        if success:
            self.action_label.setText("✓ Completed")
        else:
            self.action_label.setText("✗ Failed")
        seq_tab = self._get_sequence_tab()
        if seq_tab:
            seq_tab.clear_running_highlight()
        
        # Reset UI
        self._reset_ui_after_run()
    
    def _on_model_completed(self, success: bool, summary: str):
        """Handle model execution completion"""
        try:
            self.log_text.append(f"[info] {'✓' if success else '✗'} {summary}")
            
            if success:
                self.action_label.setText("✓ Model completed")
            else:
                self.action_label.setText("✗ Model failed")
                # Show user-friendly message
                self.log_text.append("[info] Check robot connection and policy path")
        except Exception as e:
            self.log_text.append(f"[error] Error handling completion: {e}")
        finally:
            # Always reset UI, even if there's an error
            self._reset_ui_after_run()

    def _get_sequence_tab(self):
        parent = self.parent()
        while parent:
            if hasattr(parent, "sequence_tab"):
                return getattr(parent, "sequence_tab")
            parent = parent.parent()
        return None

    def _on_worker_thread_finished(self):
        """Handle worker thread finished (cleanup)"""
        try:
            self.log_text.append("[debug] Worker thread finished")
            # Give worker time to clean up
            if self.worker:
                self.worker.deleteLater()
        except Exception as e:
            self.log_text.append(f"[error] Error in thread cleanup: {e}")

    def _build_hand_safety_settings(self) -> Optional[HandSafetySettings]:
        safety_cfg = self.config.get("safety", {})
        if not safety_cfg.get("hand_detection_enabled", False):
            return None

        cameras_cfg = self.config.get("cameras", {})
        camera_choice = safety_cfg.get("hand_detection_camera", "front")

        def normalize(value):
            if isinstance(value, str):
                stripped = value.strip()
                if stripped.isdigit():
                    return int(stripped)
                return stripped
            return value

        sources: list = []

        def add_source(key: str, fallback: int):
            cam_cfg = cameras_cfg.get(key, {})
            identifier = cam_cfg.get("index_or_path", fallback)
            identifier = normalize(identifier)
            if identifier in (None, ""):
                return
            sources.append(identifier)

        if camera_choice == "both":
            add_source("front", 0)
            add_source("wrist", 1)
        elif camera_choice == "wrist":
            add_source("wrist", 1)
        else:
            add_source("front", 0)

        if not sources:
            return None

        return HandSafetySettings(
            sources=sources,
            frame_width=320,
            frame_height=240,
            detection_confidence=0.45,
            tracking_confidence=0.35,
            trigger_frames=2,
            clear_frames=6,
            poll_interval_s=0.05,
        )

    def _start_hand_safety_monitor(self):
        if self.hand_safety_monitor:
            return

        settings = self._build_hand_safety_settings()
        if not settings:
            return

        self.hand_safety_monitor = HandSafetyMonitor(settings)
        self.hand_safety_monitor.hand_detected.connect(self._handle_hand_detected)
        self.hand_safety_monitor.hand_cleared.connect(self._handle_hand_cleared)
        self.hand_safety_monitor.status_message.connect(self._handle_safety_status)
        self.hand_safety_monitor.error_occurred.connect(self._handle_safety_error)
        self.hand_safety_monitor.start()
        self.log_text.append("[safety] Hand safety monitor started")

    def _stop_hand_safety_monitor(self):
        if not self.hand_safety_monitor:
            return

        monitor = self.hand_safety_monitor
        self.hand_safety_monitor = None

        try:
            monitor.hand_detected.disconnect(self._handle_hand_detected)
            monitor.hand_cleared.disconnect(self._handle_hand_cleared)
            monitor.status_message.disconnect(self._handle_safety_status)
            monitor.error_occurred.disconnect(self._handle_safety_error)
        except Exception:
            pass

        try:
            monitor.stop()
        except Exception:
            pass
        monitor.deleteLater()

        # Ensure workers resume before shutting down monitor
        if self.execution_worker and hasattr(self.execution_worker, "force_release_safety_pause"):
            self.execution_worker.force_release_safety_pause()
        if self.worker and hasattr(self.worker, "force_release_safety_pause"):
            self.worker.force_release_safety_pause()

        self.log_text.append("[safety] Hand safety monitor stopped")

    def _connect_safety_to_worker(self, worker):
        if not self.hand_safety_monitor or not worker:
            return
        try:
            self.hand_safety_monitor.hand_detected.connect(worker.handle_hand_detected)
            self.hand_safety_monitor.hand_cleared.connect(worker.handle_hand_cleared)
        except Exception as exc:
            self.log_text.append(f"[safety] Failed to connect safety monitor: {exc}")

    def _handle_hand_detected(self):
        self.log_text.append("[safety] Hand detected — pausing robot")
        self._set_action_label_style("#b71c1c")
        self.action_label.setText("⚠️ Hand detected — paused")

    def _handle_hand_cleared(self):
        self.log_text.append("[safety] Hand cleared — waiting to resume")
        self._set_action_label_style("#FFB300")
        self.action_label.setText("Hand cleared — resuming shortly")

    def _handle_safety_status(self, message: str):
        self.log_text.append(f"[safety] {message}")

    def _handle_safety_error(self, message: str):
        self.log_text.append(f"[safety] ERROR: {message}")
        self._set_action_label_style("#b71c1c")
        self.action_label.setText(f"Safety monitor error: {message}")
        self._stop_hand_safety_monitor()

    def _reset_ui_after_run(self):
        """Reset UI state after run completes or stops"""
        try:
            self.is_running = False
            self.start_stop_btn.setChecked(False)
            self.start_stop_btn.setText("START")
            self.timer.stop()
            self._vision_state_active = False
            self._last_vision_signature = None
            self._set_action_label_style("#383838")
            seq_tab = self._get_sequence_tab()
            if seq_tab:
                seq_tab.clear_running_highlight()
            
            # Stop throbber
            self.throbber_update_timer.stop()
            self.throbber_progress = 0
            self.throbber.set_progress(0)
            
            # Clean up execution worker (recordings/sequences)
            if self.execution_worker:
                try:
                    if self.execution_worker.isRunning():
                        self.execution_worker.quit()
                        self.execution_worker.wait(1000)
                except:
                    pass
                self.execution_worker = None
            
            # Clean up robot worker (models) - be very careful here
            if self.worker:
                try:
                    if self.worker.isRunning():
                        self.worker.quit()
                        self.worker.wait(2000)
                    # Mark for deletion but don't set to None yet
                    # Let Qt handle the cleanup
                    self.worker.deleteLater()
                except Exception as e:
                    self.log_text.append(f"[warning] Worker cleanup: {e}")
                finally:
                    self.worker = None

            self._stop_hand_safety_monitor()
        except Exception as e:
            self.log_text.append(f"[error] Error resetting UI: {e}")
    
    def go_home(self):
        """Go to home position"""
        self.action_label.setText("Moving to home...")
        self.log_text.append("[info] Moving to home position...")
        
        try:
            result = subprocess.run(
                [sys.executable, str(ROOT / "HomePos.py"), "--go"],
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
    
    def run_from_dashboard(self):
        """Execute the selected RUN item (same as pressing START)"""
        if not self.is_running:
            self.start_stop_btn.setChecked(True)
            self.start_run()
    
    
    def update_elapsed_time(self):
        """Update elapsed time"""
        if self.start_time:
            self.elapsed_seconds = int((datetime.now() - self.start_time).total_seconds())
            minutes = self.elapsed_seconds // 60
            seconds = self.elapsed_seconds % 60
            self.time_label.setText(f"Time: {minutes:02d}:{seconds:02d}")
    
    # ========== DEVICE MANAGER SIGNAL HANDLERS ==========
    
    def on_robot_status_changed(self, status: str):
        """Handle robot status change from device manager
        
        Args:
            status: "empty", "online", or "offline"
        """
        if status == "empty":
            self.robot_status_circle.set_null()
        elif status == "online":
            self.robot_status_circle.set_connected(True)
        else:  # offline
            self.robot_status_circle.set_connected(False)
    
    def on_camera_status_changed(self, camera_name: str, status: str):
        """Handle camera status change from device manager
        
        Args:
            camera_name: "front" or "wrist"
            status: "empty", "online", or "offline"
        """
        if camera_name == "front":
            if status == "empty":
                self.camera_front_circle.set_null()
            elif status == "online":
                self.camera_front_circle.set_connected(True)
            else:  # offline
                self.camera_front_circle.set_connected(False)
        elif camera_name == "wrist":
            if status == "empty":
                self.camera_wrist_circle.set_null()
            elif status == "online":
                self.camera_wrist_circle.set_connected(True)
            else:  # offline
                self.camera_wrist_circle.set_connected(False)
    
    def on_discovery_log(self, message: str):
        """Handle discovery log messages from device manager
        
        Args:
            message: Log message to display
        """
        self.log_text.append(f"[info] {message}")
