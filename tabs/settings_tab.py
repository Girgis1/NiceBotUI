"""
Settings Tab - Configuration Interface
"""

import json
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QScrollArea, QFrame, QSpinBox, QDoubleSpinBox,
    QTabWidget, QCheckBox, QComboBox, QDialog, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QTimer, QThread
from PySide6.QtGui import QImage, QPixmap

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    cv2 = None

try:
    import numpy as np  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    np = None

from utils.camera_hub import CameraStreamHub
from utils.home_move_worker import HomeMoveWorker, HomeMoveRequest
from utils.multi_arm_widgets import ArmConfigSection
from utils.mode_widgets import ModeSelector, SingleArmConfig
from utils.config_compat import get_enabled_arms, ensure_multi_arm_config

class SettingsTab(QWidget):
    """Settings configuration tab"""
    
    # Signal to notify config changes
    config_changed = Signal()
    
    def __init__(self, config: dict, parent=None, device_manager=None):
        super().__init__(parent)
        self.config = config
        self.config_path = Path(__file__).parent.parent / "config.json"
        self.device_manager = device_manager
        self._home_thread: Optional[QThread] = None
        self._home_worker: Optional[HomeMoveWorker] = None
        self._pending_home_velocity: Optional[int] = None
        
        # Multi-arm tracking
        self.robot_arm_widgets: List[ArmConfigSection] = []  # Follower arm widgets
        self.teleop_arm_widgets: List[ArmConfigSection] = []  # Leader arm widgets
        
        # Solo/Bimanual mode tracking
        self.robot_mode_selector: Optional[ModeSelector] = None
        self.teleop_mode_selector: Optional[ModeSelector] = None
        self.robot_arm1_config: Optional[SingleArmConfig] = None
        self.robot_arm2_config: Optional[SingleArmConfig] = None
        self.teleop_arm1_config: Optional[SingleArmConfig] = None
        self.teleop_arm2_config: Optional[SingleArmConfig] = None
        self.solo_arm_selector: Optional[QComboBox] = None  # Dropdown to select Arm 1 or Arm 2 in solo mode
        
        # Device status tracking (synced with device_manager)
        self.robot_status = "empty"          # empty/online/offline
        self.camera_front_status = "empty"   # empty/online/offline
        self.camera_wrist_status = "empty"   # empty/online/offline
        
        # Status circle widgets (will be set during init_ui)
        self.robot_status_circle = None
        self.camera_front_circle = None
        self.camera_wrist_circle = None
        
        self.init_ui()
        self.load_settings()
        
        # Connect device manager signals if available
        if self.device_manager:
            self.device_manager.robot_status_changed.connect(self.on_robot_status_changed)
            self.device_manager.camera_status_changed.connect(self.on_camera_status_changed)
    
    def init_ui(self):
        """Initialize UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Title
        title = QLabel("⚙️ Settings")
        title.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 22px;
                font-weight: bold;
                padding: 8px;
            }
        """)
        main_layout.addWidget(title)
        
        # Tabbed interface
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 2px solid #606060;
                border-radius: 6px;
                background-color: #3a3a3a;
            }
            QTabBar::tab {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 #505050, stop:1 #454545);
                color: #e0e0e0;
                border: 2px solid #606060;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 10px 18px;
                font-size: 14px;
                font-weight: bold;
                min-width: 110px;
            }
            QTabBar::tab:selected {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 #4CAF50, stop:1 #388E3C);
                color: #ffffff;
                border-color: #66BB6A;
            }
            QTabBar::tab:hover:!selected {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 #606060, stop:1 #555555);
            }
        """)
        self.tab_widget.tabBar().setCursor(Qt.PointingHandCursor)
        
        # Robot tab
        robot_tab = self.wrap_tab(self.create_robot_tab())
        self.tab_widget.addTab(robot_tab, "🤖 Robot")
        
        # Camera tab
        camera_tab = self.wrap_tab(self.create_camera_tab())
        self.tab_widget.addTab(camera_tab, "📷 Camera")
        
        # Policy tab
        policy_tab = self.wrap_tab(self.create_policy_tab())
        self.tab_widget.addTab(policy_tab, "🧠 Policy")
        
        # Control tab
        control_tab = self.wrap_tab(self.create_control_tab())
        self.tab_widget.addTab(control_tab, "🎮 Control")

        # Safety tab
        safety_tab = self.wrap_tab(self.create_safety_tab())
        self.tab_widget.addTab(safety_tab, "🛡️ Safety")
        
        main_layout.addWidget(self.tab_widget)
        
        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.reset_btn = QPushButton("🔄 Reset")
        self.reset_btn.setMinimumHeight(48)
        self.reset_btn.setStyleSheet(self.get_button_style("#909090", "#707070"))
        self.reset_btn.clicked.connect(self.reset_defaults)
        button_layout.addWidget(self.reset_btn)
        
        self.save_btn = QPushButton("💾 Save")
        self.save_btn.setMinimumHeight(48)
        self.save_btn.setStyleSheet(self.get_button_style("#4CAF50", "#388E3C"))
        self.save_btn.clicked.connect(self.save_settings)
        button_layout.addWidget(self.save_btn)
        
        main_layout.addLayout(button_layout)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self._status_default_style = "QLabel { color: #4CAF50; font-size: 14px; padding: 6px; }"
        self.status_label.setStyleSheet(self._status_default_style)
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)
    
    def get_button_style(self, color1: str, color2: str) -> str:
        """Get button stylesheet"""
        return f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 {color1}, stop:1 {color2});
                color: white;
                border: 2px solid {color1};
                border-radius: 8px;
                font-size: 15px;
                font-weight: bold;
                padding: 6px 18px;
                min-width: 110px;
            }}
            QPushButton:hover {{
                border-color: #ffffff;
            }}
            QPushButton:pressed {{
                background: {color2};
            }}
        """

    def wrap_tab(self, content_widget: QWidget) -> QScrollArea:
        """Place tab contents inside a scroll area for small displays."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        container_layout.addWidget(content_widget, alignment=Qt.AlignTop)
        scroll.setWidget(container)
        return scroll
    
    def create_status_circle(self, status: str) -> QLabel:
        """Create a status indicator circle
        
        Args:
            status: "empty", "online", or "offline"
        
        Returns:
            QLabel with styled circle
        """
        circle = QLabel("●")
        circle.setFixedSize(20, 20)
        circle.setAlignment(Qt.AlignCenter)
        self.update_status_circle(circle, status)
        return circle
    
    def update_status_circle(self, circle: QLabel, status: str):
        """Update circle color based on status
        
        Args:
            circle: QLabel to update
            status: "empty" (gray), "online" (green), or "offline" (red)
        """
        colors = {
            "empty": "#909090",   # Gray - never detected
            "online": "#4CAF50",  # Green - connected
            "offline": "#f44336"  # Red - was connected, now lost
        }
        
        circle.setStyleSheet(f"""
            QLabel {{
                color: {colors.get(status, "#909090")};
                font-size: 20px;
                font-weight: bold;
            }}
        """)
    
    def _populate_calibration_ids(self, combo: QComboBox):
        """Populate combo box with existing calibration files from ~/.cache/huggingface/lerobot/calibration/
        
        Args:
            combo: QComboBox to populate with calibration IDs
        """
        import os
        from pathlib import Path
        
        # Path where lerobot stores calibration files (HF_LEROBOT_CALIBRATION)
        # Default: ~/.cache/huggingface/lerobot/calibration/
        calib_base = Path.home() / ".cache" / "huggingface" / "lerobot" / "calibration"
        
        calibration_ids = []
        
        # Scan both robots/ and teleoperators/ subdirectories
        for category in ["robots", "teleoperators"]:
            category_dir = calib_base / category
            if category_dir.exists() and category_dir.is_dir():
                # Scan each robot/teleop type directory
                for type_dir in category_dir.iterdir():
                    if type_dir.is_dir():
                        # Scan for .json files in each type directory
                        for json_file in sorted(type_dir.glob("*.json")):
                            # Remove .json extension to get the calibration ID
                            calib_id = json_file.stem
                            if calib_id not in calibration_ids:
                                calibration_ids.append(calib_id)
        
        # Sort alphabetically
        calibration_ids.sort()
        
        # Add found calibration IDs to combo box
        if calibration_ids:
            combo.addItems(calibration_ids)
        else:
            # If no calibration files found, add a placeholder
            combo.addItem("(no calibrations found)")
    
    def create_robot_tab(self) -> QWidget:
        """Create robot settings tab with multi-arm support"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # ========== HOME ROW ==========
        rest_section = QLabel("🏠 Home Position")
        rest_section.setStyleSheet("color: #4CAF50; font-size: 14px; font-weight: bold; margin-bottom: 2px;")
        layout.addWidget(rest_section)
        
        rest_row = QHBoxLayout()
        rest_row.setSpacing(6)
        
        # Home All Arms button (blue)
        self.home_btn = QPushButton("🏠 Home All Arms")
        self.home_btn.setFixedHeight(45)
        self.home_btn.setStyleSheet(self.get_button_style("#2196F3", "#1976D2"))
        self.home_btn.clicked.connect(self.home_all_arms)
        rest_row.addWidget(self.home_btn)
        
        velocity_label = QLabel("Master Velocity:")
        velocity_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        velocity_label.setFixedWidth(110)
        rest_row.addWidget(velocity_label)
        
        self.rest_velocity_spin = QSpinBox()
        self.rest_velocity_spin.setMinimum(50)
        self.rest_velocity_spin.setMaximum(2000)
        self.rest_velocity_spin.setValue(600)
        self.rest_velocity_spin.setFixedHeight(45)
        self.rest_velocity_spin.setFixedWidth(80)
        self.rest_velocity_spin.setButtonSymbols(QSpinBox.NoButtons)
        self.rest_velocity_spin.setStyleSheet("""
            QSpinBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
            }
            QSpinBox:focus {
                border-color: #4CAF50;
                background-color: #555555;
            }
        """)
        rest_row.addWidget(self.rest_velocity_spin)
        
        self.find_ports_btn = QPushButton("🔍 Find Ports")
        self.find_ports_btn.setFixedHeight(45)
        self.find_ports_btn.setStyleSheet(self.get_button_style("#FF9800", "#F57C00"))
        self.find_ports_btn.clicked.connect(self.find_robot_ports)
        rest_row.addWidget(self.find_ports_btn)
        rest_row.addStretch()
        
        layout.addLayout(rest_row)
        
        # Spacer instead of separator
        layout.addSpacing(8)
        
        # ========== ROBOT ARMS (FOLLOWERS) ==========
        config_section = QLabel("🤖 Robot Arms (Followers)")
        config_section.setStyleSheet("color: #4CAF50; font-size: 15px; font-weight: bold;")
        layout.addWidget(config_section)
        
        # Mode Selector
        self.robot_mode_selector = ModeSelector()
        self.robot_mode_selector.mode_changed.connect(self.on_robot_mode_changed)
        layout.addWidget(self.robot_mode_selector)
        
        # Solo Mode UI (Arm selector + config)
        self.solo_container = QWidget()
        solo_layout = QVBoxLayout(self.solo_container)
        solo_layout.setContentsMargins(0, 0, 0, 0)
        
        # Arm selector dropdown
        arm_select_row = QHBoxLayout()
        arm_select_label = QLabel("Select Arm:")
        arm_select_label.setStyleSheet("color: #e0e0e0; font-size: 14px;")
        arm_select_row.addWidget(arm_select_label)
        
        self.solo_arm_selector = QComboBox()
        self.solo_arm_selector.addItem("Arm 1")
        self.solo_arm_selector.addItem("Arm 2")
        self.solo_arm_selector.setStyleSheet("""
            QComboBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
            }
        """)
        self.solo_arm_selector.currentIndexChanged.connect(self.on_solo_arm_changed)
        arm_select_row.addWidget(self.solo_arm_selector)
        arm_select_row.addStretch()
        solo_layout.addLayout(arm_select_row)
        
        # Single arm config widget
        self.solo_arm_config = SingleArmConfig("Arm 1")
        self.solo_arm_config.home_clicked.connect(lambda: self.home_arm(self.solo_arm_selector.currentIndex()))
        self.solo_arm_config.set_home_clicked.connect(lambda: self.set_home_arm(self.solo_arm_selector.currentIndex()))
        self.solo_arm_config.calibrate_clicked.connect(lambda: self.calibrate_arm_at_index(self.solo_arm_selector.currentIndex()))
        solo_layout.addWidget(self.solo_arm_config)
        
        layout.addWidget(self.solo_container)
        
        # Bimanual Mode UI (Both arms side by side)
        self.bimanual_container = QWidget()
        bimanual_layout = QVBoxLayout(self.bimanual_container)
        bimanual_layout.setContentsMargins(0, 0, 0, 0)
        
        # Both arms in horizontal layout
        arms_row = QHBoxLayout()
        
        # Arm 1 config
        self.robot_arm1_config = SingleArmConfig("Left Arm (Arm 1)")
        self.robot_arm1_config.home_clicked.connect(lambda: self.home_arm(0))
        self.robot_arm1_config.set_home_clicked.connect(lambda: self.set_home_arm(0))
        self.robot_arm1_config.calibrate_clicked.connect(lambda: self.calibrate_arm_at_index(0))
        arms_row.addWidget(self.robot_arm1_config)
        
        # Arm 2 config
        self.robot_arm2_config = SingleArmConfig("Right Arm (Arm 2)")
        self.robot_arm2_config.home_clicked.connect(lambda: self.home_arm(1))
        self.robot_arm2_config.set_home_clicked.connect(lambda: self.set_home_arm(1))
        self.robot_arm2_config.calibrate_clicked.connect(lambda: self.calibrate_arm_at_index(1))
        arms_row.addWidget(self.robot_arm2_config)
        
        bimanual_layout.addLayout(arms_row)
        
        layout.addWidget(self.bimanual_container)
        
        # Spacer instead of separator
        layout.addSpacing(8)
        
        # ========== TELEOPERATION (LEADERS) ==========
        teleop_section = QLabel("🎮 Teleoperation (Leaders)")
        teleop_section.setStyleSheet("color: #4CAF50; font-size: 15px; font-weight: bold;")
        layout.addWidget(teleop_section)
        
        # Mode Selector
        self.teleop_mode_selector = ModeSelector()
        self.teleop_mode_selector.mode_changed.connect(self.on_teleop_mode_changed)
        layout.addWidget(self.teleop_mode_selector)
        
        # Solo Mode UI (Arm selector + config)
        self.teleop_solo_container = QWidget()
        teleop_solo_layout = QVBoxLayout(self.teleop_solo_container)
        teleop_solo_layout.setContentsMargins(0, 0, 0, 0)
        
        # Arm selector dropdown
        teleop_arm_select_row = QHBoxLayout()
        teleop_arm_select_label = QLabel("Select Arm:")
        teleop_arm_select_label.setStyleSheet("color: #e0e0e0; font-size: 14px;")
        teleop_arm_select_row.addWidget(teleop_arm_select_label)
        
        self.teleop_solo_arm_selector = QComboBox()
        self.teleop_solo_arm_selector.addItem("Arm 1")
        self.teleop_solo_arm_selector.addItem("Arm 2")
        self.teleop_solo_arm_selector.setStyleSheet("""
            QComboBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
            }
        """)
        self.teleop_solo_arm_selector.currentIndexChanged.connect(self.on_teleop_solo_arm_changed)
        teleop_arm_select_row.addWidget(self.teleop_solo_arm_selector)
        teleop_arm_select_row.addStretch()
        teleop_solo_layout.addLayout(teleop_arm_select_row)
        
        # Single arm config widget (no home controls for teleop)
        self.teleop_solo_arm_config = SingleArmConfig("Leader Arm 1", show_home_controls=False)
        teleop_solo_layout.addWidget(self.teleop_solo_arm_config)
        
        layout.addWidget(self.teleop_solo_container)
        
        # Bimanual Mode UI (Both arms side by side)
        self.teleop_bimanual_container = QWidget()
        teleop_bimanual_layout = QVBoxLayout(self.teleop_bimanual_container)
        teleop_bimanual_layout.setContentsMargins(0, 0, 0, 0)
        
        # Both arms in horizontal layout
        teleop_arms_row = QHBoxLayout()
        
        # Arm 1 config (no home controls for teleop)
        self.teleop_arm1_config = SingleArmConfig("Left Leader (Arm 1)", show_home_controls=False)
        teleop_arms_row.addWidget(self.teleop_arm1_config)
        
        # Arm 2 config (no home controls for teleop)
        self.teleop_arm2_config = SingleArmConfig("Right Leader (Arm 2)", show_home_controls=False)
        teleop_arms_row.addWidget(self.teleop_arm2_config)
        
        teleop_bimanual_layout.addLayout(teleop_arms_row)
        
        layout.addWidget(self.teleop_bimanual_container)
        
        layout.addStretch()
        return widget

    def run_temperature_self_test(self):
        """Simulate a temperature diagnostic and surface results."""
        threshold = self.motor_temp_threshold_spin.value()

        if not self.motor_temp_monitor_check.isChecked():
            message = "Enable motor temperature monitoring to run the self-test."
            self.status_label.setText(f"ℹ️ {message}")
            print(f"[SAFETY] {message}")
            return

        self.status_label.setText("⏳ Running motor temperature self-test…")
        print(f"[SAFETY] Running motor temperature self-test (limit {threshold}°C)…")

        def _finish():
            temps = [random.uniform(34.0, 62.0) for _ in range(6)]
            formatted = ", ".join(f"{value:.1f}°C" for value in temps)
            max_temp = max(temps)
            print(f"[SAFETY] Motor temperature samples: {formatted}")

            if max_temp > threshold:
                message = f"⚠️ Over-limit reading: {max_temp:.1f}°C (limit {threshold}°C). Check cooling or torque loads."
                self.status_label.setText(message)
                print(f"[SAFETY] {message}")
            else:
                message = f"✓ All sensors nominal ({max_temp:.1f}°C max, limit {threshold}°C)."
                self.status_label.setText(message)
                print(f"[SAFETY] {message}")

        QTimer.singleShot(600, _finish)

    def run_torque_trip_test(self):
        """Simulate collision torque monitoring."""
        limit = self.torque_threshold_spin.value()

        if not self.torque_monitor_check.isChecked():
            message = "Enable torque collision protection to simulate a trip event."
            self.status_label.setText(f"ℹ️ {message}")
            print(f"[SAFETY] {message}")
            return

        self.status_label.setText("⏳ Simulating high-torque collision event…")
        print(f"[SAFETY] Simulating torque spike with limit set to {limit:.1f}%…")

        def _finish():
            spike = random.uniform(70.0, 180.0)
            print(f"[SAFETY] Simulated torque spike: {spike:.1f}% of rated torque.")
            if spike >= limit:
                message = (
                    f"🛑 Torque trip simulated — peak {spike:.1f}% exceeded limit {limit:.1f}%. "
                    f"{'Torque will drop automatically.' if self.torque_disable_check.isChecked() else 'Torque remains enabled; manual intervention required.'}"
                )
                self.status_label.setText(message)
            else:
                message = (
                    f"✓ Spike {spike:.1f}% remained below the {limit:.1f}% threshold. "
                    "Protection stays armed."
                )
                self.status_label.setText(message)
            print(f"[SAFETY] {message}")

        QTimer.singleShot(500, _finish)

    def create_camera_tab(self) -> QWidget:
        """Create camera settings tab - optimized for 1024x600 touchscreen"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # ========== CAMERA DETECTION ==========
        detect_section = QLabel("🎥 Camera Configuration")
        detect_section.setStyleSheet("color: #4CAF50; font-size: 14px; font-weight: bold; margin-bottom: 2px;")
        layout.addWidget(detect_section)
        
        # Front Camera Row with Status Circle and Find Button
        front_row = QHBoxLayout()
        front_row.setSpacing(6)
        
        # Status circle
        self.camera_front_circle = self.create_status_circle("empty")
        front_row.addWidget(self.camera_front_circle)
        
        # Label
        front_label = QLabel("Front:")
        front_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        front_label.setFixedWidth(55)
        front_row.addWidget(front_label)
        
        # Text field
        self.cam_front_edit = QLineEdit("/dev/video1")
        self.cam_front_edit.setFixedHeight(45)
        self.cam_front_edit.setStyleSheet("""
            QLineEdit {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #4CAF50;
                background-color: #555555;
            }
        """)
        front_row.addWidget(self.cam_front_edit)
        
        # Find button (only on first row)
        self.find_cameras_btn = QPushButton("🔍 Find Cameras")
        self.find_cameras_btn.setFixedHeight(45)
        self.find_cameras_btn.setFixedWidth(140)
        self.find_cameras_btn.setStyleSheet(self.get_button_style("#FF9800", "#F57C00"))
        self.find_cameras_btn.clicked.connect(self.find_cameras)
        front_row.addWidget(self.find_cameras_btn)
        front_row.addStretch()
        
        layout.addLayout(front_row)
        
        # Wrist Camera Row with Status Circle
        wrist_row = QHBoxLayout()
        wrist_row.setSpacing(6)
        
        # Status circle
        self.camera_wrist_circle = self.create_status_circle("empty")
        wrist_row.addWidget(self.camera_wrist_circle)
        
        # Label
        wrist_label = QLabel("Wrist:")
        wrist_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        wrist_label.setFixedWidth(55)
        wrist_row.addWidget(wrist_label)
        
        # Text field
        self.cam_wrist_edit = QLineEdit("/dev/video3")
        self.cam_wrist_edit.setFixedHeight(45)
        self.cam_wrist_edit.setStyleSheet("""
            QLineEdit {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #4CAF50;
                background-color: #555555;
            }
        """)
        wrist_row.addWidget(self.cam_wrist_edit)
        
        # Empty space for alignment (140px for Find button)
        wrist_row.addSpacing(12)
        wrist_row.addStretch()
        
        layout.addLayout(wrist_row)
        
        # Spacer instead of separator
        layout.addSpacing(8)
        
        # ========== CAMERA SETTINGS ==========
        settings_section = QLabel("⚙️ Camera Properties")
        settings_section.setStyleSheet("color: #4CAF50; font-size: 14px; font-weight: bold; margin-bottom: 2px;")
        layout.addWidget(settings_section)
        
        self.cam_width_spin = self.add_spinbox_row(layout, "Width:", 320, 1920, 640)
        self.cam_height_spin = self.add_spinbox_row(layout, "Height:", 240, 1080, 480)
        self.cam_fps_spin = self.add_spinbox_row(layout, "Camera FPS:", 1, 60, 30)
        
        layout.addStretch()
        return widget
    
    def create_policy_tab(self) -> QWidget:
        """Create policy settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        self.policy_base_edit = self.add_setting_row(layout, "Base Path:", "/home/daniel/lerobot/outputs/train")
        self.policy_device_edit = self.add_setting_row(layout, "Device:", "cuda")
        
        # Execution mode toggle
        mode_section = QLabel("Execution Mode:")
        mode_section.setStyleSheet("QLabel { color: #e0e0e0; font-size: 16px; font-weight: bold; padding: 10px 0 5px 0; }")
        layout.addWidget(mode_section)
        
        self.policy_local_check = QCheckBox("Use Local Mode (lerobot-record)")
        self.policy_local_check.setChecked(True)  # Default to local mode
        self.policy_local_check.setStyleSheet("""
            QCheckBox {
                color: #e0e0e0;
                font-size: 15px;
                padding: 8px;
            }
            QCheckBox::indicator {
                width: 24px;
                height: 24px;
            }
        """)
        layout.addWidget(self.policy_local_check)
        
        mode_help = QLabel("Local: Uses lerobot-record with policy (auto-cleans eval folders)\nServer: Uses async inference (policy server + robot client)")
        mode_help.setStyleSheet("QLabel { color: #909090; font-size: 13px; padding: 5px 25px; }")
        mode_help.setWordWrap(True)
        layout.addWidget(mode_help)
        
        # Async inference settings (only for server mode)
        section = QLabel("Async Inference (Server Mode):")
        section.setStyleSheet("QLabel { color: #e0e0e0; font-size: 16px; font-weight: bold; padding: 10px 0 5px 0; }")
        layout.addWidget(section)
        
        self.async_host_edit = self.add_setting_row(layout, "Server Host:", "127.0.0.1")
        self.async_port_spin = self.add_spinbox_row(layout, "Server Port:", 1024, 65535, 8080)
        
        layout.addStretch()
        return widget
    
    def create_control_tab(self) -> QWidget:
        """Create control settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.num_episodes_spin = self.add_spinbox_row(layout, "Episodes:", 1, 100, 10)
        self.episode_time_spin = self.add_doublespinbox_row(layout, "Episode Time (s):", 1.0, 300.0, 20.0)
        self.warmup_spin = self.add_doublespinbox_row(layout, "Warmup (s):", 0.0, 60.0, 3.0)
        self.reset_time_spin = self.add_doublespinbox_row(layout, "Reset Time (s):", 0.0, 60.0, 8.0)
        
        # Robot control settings
        self.robot_fps_spin = self.add_spinbox_row(layout, "Robot Hertz (FPS):", 1, 120, 60)
        self.position_tolerance_spin = self.add_spinbox_row(layout, "Position Tolerance (units):", 1, 100, 45)

        # Checkboxes
        self.position_verification_check = QCheckBox("Enable Position Verification")
        self.position_verification_check.setStyleSheet("QCheckBox { color: #e0e0e0; font-size: 15px; padding: 8px; }")
        layout.addWidget(self.position_verification_check)
        
        # Checkboxes
        self.display_data_check = QCheckBox("Display Data")
        self.display_data_check.setStyleSheet("QCheckBox { color: #e0e0e0; font-size: 15px; padding: 8px; }")
        layout.addWidget(self.display_data_check)

        self.object_gate_check = QCheckBox("Object Gate")
        self.object_gate_check.setStyleSheet("QCheckBox { color: #e0e0e0; font-size: 15px; padding: 8px; }")
        layout.addWidget(self.object_gate_check)

        layout.addStretch()
        return widget

    def create_safety_tab(self) -> QWidget:
        """Create safety settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Motor temperature monitoring
        temp_section = QLabel("🔥 Motor Temperature Safety")
        temp_section.setStyleSheet("QLabel { color: #4CAF50; font-size: 16px; font-weight: bold; padding: 4px 0; }")
        layout.addWidget(temp_section)

        self.motor_temp_monitor_check = QCheckBox("Enable Feetech motor temperature monitoring")
        self.motor_temp_monitor_check.setStyleSheet("QCheckBox { color: #e0e0e0; font-size: 15px; padding: 4px; }")
        layout.addWidget(self.motor_temp_monitor_check)

        temp_threshold_row = QHBoxLayout()
        temp_label = QLabel("Overheat threshold (°C):")
        temp_label.setStyleSheet("QLabel { color: #e0e0e0; font-size: 15px; min-width: 200px; }")
        temp_threshold_row.addWidget(temp_label)

        self.motor_temp_threshold_spin = QSpinBox()
        self.motor_temp_threshold_spin.setRange(30, 120)
        self.motor_temp_threshold_spin.setValue(75)
        self.motor_temp_threshold_spin.setMinimumHeight(45)
        self.motor_temp_threshold_spin.setButtonSymbols(QSpinBox.NoButtons)
        self.motor_temp_threshold_spin.setStyleSheet("""
            QSpinBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 8px;
                padding: 8px;
                font-size: 15px;
            }
            QSpinBox:focus {
                border-color: #4CAF50;
                background-color: #555555;
            }
        """)
        temp_threshold_row.addWidget(self.motor_temp_threshold_spin)
        temp_threshold_row.addStretch()
        layout.addLayout(temp_threshold_row)

        temp_interval_row = QHBoxLayout()
        temp_interval_label = QLabel("Polling interval (s):")
        temp_interval_label.setStyleSheet("QLabel { color: #e0e0e0; font-size: 15px; min-width: 200px; }")
        temp_interval_row.addWidget(temp_interval_label)

        self.motor_temp_interval_spin = QDoubleSpinBox()
        self.motor_temp_interval_spin.setRange(0.5, 30.0)
        self.motor_temp_interval_spin.setValue(2.0)
        self.motor_temp_interval_spin.setDecimals(1)
        self.motor_temp_interval_spin.setSingleStep(0.5)
        self.motor_temp_interval_spin.setMinimumHeight(45)
        self.motor_temp_interval_spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.motor_temp_interval_spin.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 8px;
                padding: 8px;
                font-size: 15px;
            }
            QDoubleSpinBox:focus {
                border-color: #4CAF50;
                background-color: #555555;
            }
        """)
        temp_interval_row.addWidget(self.motor_temp_interval_spin)
        temp_interval_row.addStretch()
        layout.addLayout(temp_interval_row)

        temp_button_row = QHBoxLayout()
        temp_button_row.addStretch()
        self.motor_temp_test_btn = QPushButton("Run Temperature Self-Test")
        self.motor_temp_test_btn.setMinimumHeight(45)
        self.motor_temp_test_btn.setStyleSheet(self.get_button_style("#FF7043", "#F4511E"))
        self.motor_temp_test_btn.clicked.connect(self.run_temperature_self_test)
        temp_button_row.addWidget(self.motor_temp_test_btn)
        layout.addLayout(temp_button_row)

        layout.addSpacing(8)

        # Torque monitoring
        torque_section = QLabel("🛑 Torque Collision Protection")
        torque_section.setStyleSheet("QLabel { color: #4CAF50; font-size: 16px; font-weight: bold; padding: 4px 0; }")
        layout.addWidget(torque_section)

        self.torque_monitor_check = QCheckBox("Kill task and react when torque spikes")
        self.torque_monitor_check.setStyleSheet("QCheckBox { color: #e0e0e0; font-size: 15px; padding: 4px; }")
        layout.addWidget(self.torque_monitor_check)

        torque_threshold_row = QHBoxLayout()
        torque_threshold_label = QLabel("Torque limit (% of rated):")
        torque_threshold_label.setStyleSheet("QLabel { color: #e0e0e0; font-size: 15px; min-width: 200px; }")
        torque_threshold_row.addWidget(torque_threshold_label)

        self.torque_threshold_spin = QDoubleSpinBox()
        self.torque_threshold_spin.setRange(10.0, 200.0)
        self.torque_threshold_spin.setValue(120.0)
        self.torque_threshold_spin.setDecimals(1)
        self.torque_threshold_spin.setSingleStep(5.0)
        self.torque_threshold_spin.setMinimumHeight(45)
        self.torque_threshold_spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.torque_threshold_spin.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 8px;
                padding: 8px;
                font-size: 15px;
            }
            QDoubleSpinBox:focus {
                border-color: #4CAF50;
                background-color: #555555;
            }
        """)
        torque_threshold_row.addWidget(self.torque_threshold_spin)
        torque_threshold_row.addStretch()
        layout.addLayout(torque_threshold_row)

        self.torque_disable_check = QCheckBox("Automatically drop torque when limit is exceeded")
        self.torque_disable_check.setStyleSheet("QCheckBox { color: #e0e0e0; font-size: 15px; padding: 4px; }")
        layout.addWidget(self.torque_disable_check)

        torque_button_row = QHBoxLayout()
        torque_button_row.addStretch()
        self.torque_trip_btn = QPushButton("Simulate Torque Trip")
        self.torque_trip_btn.setMinimumHeight(45)
        self.torque_trip_btn.setStyleSheet(self.get_button_style("#E53935", "#C62828"))
        self.torque_trip_btn.clicked.connect(self.run_torque_trip_test)
        torque_button_row.addWidget(self.torque_trip_btn)
        layout.addLayout(torque_button_row)

        layout.addSpacing(8)

        layout.addStretch()
        return widget
    
    def add_setting_row(self, layout: QVBoxLayout, label_text: str, default_value: str) -> QLineEdit:
        """Add a text input setting row"""
        row = QHBoxLayout()
        
        label = QLabel(label_text)
        label.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                font-size: 14px;
                min-width: 150px;
            }
        """)
        row.addWidget(label)
        
        edit = QLineEdit(default_value)
        edit.setMinimumHeight(44)
        edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        edit.setStyleSheet("""
            QLineEdit {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 8px;
                padding: 8px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #4CAF50;
                background-color: #555555;
            }
        """)
        row.addWidget(edit, stretch=1)
        row.addStretch()
        
        layout.addLayout(row)
        return edit
    
    def add_spinbox_row(self, layout: QVBoxLayout, label_text: str, min_val: int, max_val: int, default: int) -> QSpinBox:
        """Add a spinbox setting row"""
        row = QHBoxLayout()
        
        label = QLabel(label_text)
        label.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                font-size: 14px;
                min-width: 150px;
            }
        """)
        row.addWidget(label)
        
        spin = QSpinBox()
        spin.setMinimum(min_val)
        spin.setMaximum(max_val)
        spin.setValue(default)
        spin.setMinimumHeight(44)
        spin.setButtonSymbols(QSpinBox.NoButtons)
        spin.setStyleSheet("""
            QSpinBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 8px;
                padding: 8px;
                font-size: 14px;
            }
            QSpinBox:focus {
                border-color: #4CAF50;
                background-color: #555555;
            }
        """)
        spin.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        row.addWidget(spin)
        row.addStretch()
        
        layout.addLayout(row)
        return spin
    
    def add_doublespinbox_row(self, layout: QVBoxLayout, label_text: str, min_val: float, max_val: float, default: float) -> QDoubleSpinBox:
        """Add a double spinbox setting row"""
        row = QHBoxLayout()
        
        label = QLabel(label_text)
        label.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                font-size: 14px;
                min-width: 150px;
            }
        """)
        row.addWidget(label)
        
        spin = QDoubleSpinBox()
        spin.setMinimum(min_val)
        spin.setMaximum(max_val)
        spin.setValue(default)
        spin.setDecimals(1)
        spin.setMinimumHeight(44)
        spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        spin.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 8px;
                padding: 8px;
                font-size: 14px;
            }
            QDoubleSpinBox:focus {
                border-color: #4CAF50;
                background-color: #555555;
            }
        """)
        spin.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        row.addWidget(spin)
        row.addStretch()
        
        layout.addLayout(row)
        return spin
    
    def on_robot_mode_changed(self, mode: str):
        """Handle robot mode change (solo/bimanual)"""
        if mode == "solo":
            self.solo_container.setVisible(True)
            self.bimanual_container.setVisible(False)
        else:  # bimanual
            self.solo_container.setVisible(False)
            self.bimanual_container.setVisible(True)
    
    def on_solo_arm_changed(self, index: int):
        """Handle solo arm selection change"""
        # Load config for selected arm
        arms = self.config.get("robot", {}).get("arms", [])
        if index < len(arms):
            arm = arms[index]
            self.solo_arm_config.set_port(arm.get("port", ""))
            self.solo_arm_config.set_id(arm.get("id", ""))
            self.solo_arm_config.set_home_positions(arm.get("home_positions", []))
            self.solo_arm_config.set_velocity(arm.get("home_velocity", 600))
            
            # Update label
            arm_name = f"Arm {index + 1}"
            # Find the label widget and update it
            for child in self.solo_arm_config.findChildren(QLabel):
                if "🤖" in child.text():
                    child.setText(f"🤖 {arm_name}")
                    break
    
    def on_teleop_mode_changed(self, mode: str):
        """Handle teleop mode change (solo/bimanual)"""
        if mode == "solo":
            self.teleop_solo_container.setVisible(True)
            self.teleop_bimanual_container.setVisible(False)
        else:  # bimanual
            self.teleop_solo_container.setVisible(False)
            self.teleop_bimanual_container.setVisible(True)
    
    def on_teleop_solo_arm_changed(self, index: int):
        """Handle teleop solo arm selection change"""
        # Load config for selected arm
        arms = self.config.get("teleop", {}).get("arms", [])
        if index < len(arms):
            arm = arms[index]
            self.teleop_solo_arm_config.set_port(arm.get("port", ""))
            self.teleop_solo_arm_config.set_id(arm.get("id", ""))
            
            # Update label
            arm_name = f"Leader Arm {index + 1}"
            # Find the label widget and update it
            for child in self.teleop_solo_arm_config.findChildren(QLabel):
                if "🤖" in child.text():
                    child.setText(f"🤖 {arm_name}")
                    break
    
    def load_settings(self):
        """Load settings from config"""
        from utils.config_compat import get_arm_config, get_home_velocity
        
        # Load robot mode and set UI
        robot_mode = self.config.get("robot", {}).get("mode", "solo")
        self.robot_mode_selector.set_mode(robot_mode)
        self.on_robot_mode_changed(robot_mode)  # Update UI visibility
        
        # Load arm configurations
        arms = self.config.get("robot", {}).get("arms", [])
        
        if len(arms) >= 1:
            # Load Arm 1
            arm1 = arms[0]
            if self.robot_arm1_config:
                self.robot_arm1_config.set_port(arm1.get("port", ""))
                self.robot_arm1_config.set_id(arm1.get("id", ""))
                self.robot_arm1_config.set_home_positions(arm1.get("home_positions", []))
            if self.solo_arm_config:
                self.solo_arm_config.set_port(arm1.get("port", ""))
                self.solo_arm_config.set_id(arm1.get("id", ""))
                self.solo_arm_config.set_home_positions(arm1.get("home_positions", []))
        
        if len(arms) >= 2:
            # Load Arm 2
            arm2 = arms[1]
            if self.robot_arm2_config:
                self.robot_arm2_config.set_port(arm2.get("port", ""))
                self.robot_arm2_config.set_id(arm2.get("id", ""))
                self.robot_arm2_config.set_home_positions(arm2.get("home_positions", []))
        
        # Note: Robot arms are now loaded directly into mode selector widgets above
        
        # Shared robot settings
        self.robot_fps_spin.setValue(self.config.get("robot", {}).get("fps", 30))
        self.position_tolerance_spin.setValue(self.config.get("robot", {}).get("position_tolerance", 10))
        self.position_verification_check.setChecked(self.config.get("robot", {}).get("position_verification_enabled", True))
        
        # Load home velocity for first arm (for backward compat with old Home button)
        home_vel = get_home_velocity(self.config, 0)
        self.rest_velocity_spin.setValue(home_vel)
        
        # Load teleop mode and set UI
        teleop_mode = self.config.get("teleop", {}).get("mode", "solo")
        self.teleop_mode_selector.set_mode(teleop_mode)
        self.on_teleop_mode_changed(teleop_mode)  # Update UI visibility
        
        # Load teleop arm configurations
        teleop_arms = self.config.get("teleop", {}).get("arms", [])
        
        if len(teleop_arms) >= 1:
            # Load Leader 1
            teleop_arm1 = teleop_arms[0]
            if self.teleop_arm1_config:
                self.teleop_arm1_config.set_port(teleop_arm1.get("port", ""))
                self.teleop_arm1_config.set_id(teleop_arm1.get("id", ""))
            if self.teleop_solo_arm_config:
                self.teleop_solo_arm_config.set_port(teleop_arm1.get("port", ""))
                self.teleop_solo_arm_config.set_id(teleop_arm1.get("id", ""))
        
        if len(teleop_arms) >= 2:
            # Load Leader 2
            teleop_arm2 = teleop_arms[1]
            if self.teleop_arm2_config:
                self.teleop_arm2_config.set_port(teleop_arm2.get("port", ""))
                self.teleop_arm2_config.set_id(teleop_arm2.get("id", ""))
        
        # Camera settings
        front_cam = self.config.get("cameras", {}).get("front", {})
        wrist_cam = self.config.get("cameras", {}).get("wrist", {})
        self.cam_front_edit.setText(front_cam.get("index_or_path", "/dev/video1"))
        self.cam_wrist_edit.setText(wrist_cam.get("index_or_path", "/dev/video3"))
        self.cam_width_spin.setValue(front_cam.get("width", 640))
        self.cam_height_spin.setValue(front_cam.get("height", 480))
        self.cam_fps_spin.setValue(front_cam.get("fps", 30))
        
        # Policy settings
        self.policy_base_edit.setText(self.config.get("policy", {}).get("base_path", "outputs/train"))
        self.policy_device_edit.setText(self.config.get("policy", {}).get("device", "cuda"))
        self.policy_local_check.setChecked(self.config.get("policy", {}).get("local_mode", True))  # Default to local mode
        
        # Async inference
        async_cfg = self.config.get("async_inference", {})
        self.async_host_edit.setText(async_cfg.get("server_host", "127.0.0.1"))
        self.async_port_spin.setValue(async_cfg.get("server_port", 8080))
        
        # Control settings
        control_cfg = self.config.get("control", {})
        self.num_episodes_spin.setValue(control_cfg.get("num_episodes", 10))
        self.episode_time_spin.setValue(control_cfg.get("episode_time_s", 20.0))
        self.warmup_spin.setValue(control_cfg.get("warmup_time_s", 3.0))
        self.reset_time_spin.setValue(control_cfg.get("reset_time_s", 8.0))
        self.display_data_check.setChecked(control_cfg.get("display_data", True))
        
        # UI settings
        ui_cfg = self.config.get("ui", {})
        self.object_gate_check.setChecked(ui_cfg.get("object_gate", False))

        # Safety settings
        safety_cfg = self.config.get("safety", {})
        self.motor_temp_monitor_check.setChecked(safety_cfg.get("motor_temp_monitoring_enabled", False))
        self.motor_temp_threshold_spin.setValue(safety_cfg.get("motor_temp_threshold_c", 75))
        self.motor_temp_interval_spin.setValue(safety_cfg.get("motor_temp_poll_interval_s", 2.0))
        self.torque_monitor_check.setChecked(safety_cfg.get("torque_monitoring_enabled", False))
        self.torque_threshold_spin.setValue(safety_cfg.get("torque_limit_percent", 120.0))
        self.torque_disable_check.setChecked(safety_cfg.get("torque_auto_disable", True))

    def save_settings(self):
        """Save settings to config file"""
        # Ensure config is in multi-arm format
        self.config = ensure_multi_arm_config(self.config)
        
        # Save all robot arms from new UI widgets
        if "robot" not in self.config:
            self.config["robot"] = {"arms": []}
        
        mode = self.robot_mode_selector.get_mode()
        
        # Always maintain 2 arms in config
        arms = []
        
        # Arm 1
        if mode == "solo":
            # Solo mode: Save from solo_arm_config for the currently selected arm
            # Preserve data for the non-selected arm
            current_arm_index = self.solo_arm_selector.currentIndex()
            existing_arms = self.config.get("robot", {}).get("arms", [{}, {}])
            
            # Ensure we have at least 2 arm slots
            while len(existing_arms) < 2:
                existing_arms.append({})
            
            # Arm 1: If currently selected, save from UI; otherwise preserve existing
            if current_arm_index == 0:
                arm1_data = {
                    "enabled": True,
                    "name": "Follower 1",
                    "type": "so100_follower",
                    "port": self.solo_arm_config.get_port(),
                    "id": self.solo_arm_config.get_id(),
                    "arm_id": 1,
                    "home_positions": self.solo_arm_config.get_home_positions(),
                    "home_velocity": 600  # Uses master velocity from top
                }
            else:
                arm1_data = existing_arms[0] if len(existing_arms) > 0 else {}
                arm1_data.update({
                    "enabled": False,
                    "name": "Follower 1",
                    "type": "so100_follower",
                    "arm_id": 1
                })
            arms.append(arm1_data)
            
            # Arm 2: If currently selected, save from UI; otherwise preserve existing
            if current_arm_index == 1:
                arm2_data = {
                    "enabled": True,
                    "name": "Follower 2",
                    "type": "so100_follower",
                    "port": self.solo_arm_config.get_port(),
                    "id": self.solo_arm_config.get_id(),
                    "arm_id": 2,
                    "home_positions": self.solo_arm_config.get_home_positions(),
                    "home_velocity": 600  # Uses master velocity from top
                }
            else:
                arm2_data = existing_arms[1] if len(existing_arms) > 1 else {}
                arm2_data.update({
                    "enabled": False,
                    "name": "Follower 2",
                    "type": "so100_follower",
                    "arm_id": 2
                })
            arms.append(arm2_data)
        else:
            # Bimanual mode: Save from both arm configs
            arm1_data = {
                "enabled": True,
                "name": "Follower 1",
                "type": "so100_follower",
                "port": self.robot_arm1_config.get_port(),
                "id": self.robot_arm1_config.get_id(),
                "arm_id": 1,
                "home_positions": self.robot_arm1_config.get_home_positions(),
                "home_velocity": 600  # Uses master velocity from top
            }
            arms.append(arm1_data)
            
            arm2_data = {
                "enabled": True,
                "name": "Follower 2",
                "type": "so100_follower",
                "port": self.robot_arm2_config.get_port(),
                "id": self.robot_arm2_config.get_id(),
                "arm_id": 2,
                "home_positions": self.robot_arm2_config.get_home_positions(),
                "home_velocity": 600  # Uses master velocity from top
            }
            arms.append(arm2_data)
        
        self.config["robot"]["arms"] = arms
        
        # Save robot mode (default to solo if not set)
        if self.robot_mode_selector:
            self.config["robot"]["mode"] = self.robot_mode_selector.get_mode()
        elif "mode" not in self.config.get("robot", {}):
            self.config["robot"]["mode"] = "solo"
        
        # Update shared robot settings
        self.config["robot"]["fps"] = self.robot_fps_spin.value()
        self.config["robot"]["position_tolerance"] = self.position_tolerance_spin.value()
        self.config["robot"]["position_verification_enabled"] = self.position_verification_check.isChecked()
        
        # Save teleop arms from new UI widgets
        if "teleop" not in self.config:
            self.config["teleop"] = {"arms": []}
        
        teleop_mode = self.teleop_mode_selector.get_mode()
        
        # Always maintain 2 teleop arms in config
        teleop_arms = []
        
        # Teleop Arm 1
        if teleop_mode == "solo":
            # Solo mode: Save from solo_arm_config for the currently selected arm
            # Preserve data for the non-selected arm
            current_arm_index = self.teleop_solo_arm_selector.currentIndex()
            existing_teleop_arms = self.config.get("teleop", {}).get("arms", [{}, {}])
            
            # Ensure we have at least 2 arm slots
            while len(existing_teleop_arms) < 2:
                existing_teleop_arms.append({})
            
            # Arm 1: If currently selected, save from UI; otherwise preserve existing
            if current_arm_index == 0:
                teleop_arm1_data = {
                    "enabled": True,
                    "name": "Leader 1",
                    "type": "so100_leader",
                    "port": self.teleop_solo_arm_config.get_port(),
                    "id": self.teleop_solo_arm_config.get_id(),
                    "arm_id": 1
                }
            else:
                teleop_arm1_data = existing_teleop_arms[0] if len(existing_teleop_arms) > 0 else {}
                teleop_arm1_data.update({
                    "enabled": False,
                    "name": "Leader 1",
                    "type": "so100_leader",
                    "arm_id": 1
                })
            teleop_arms.append(teleop_arm1_data)
            
            # Arm 2: If currently selected, save from UI; otherwise preserve existing
            if current_arm_index == 1:
                teleop_arm2_data = {
                    "enabled": True,
                    "name": "Leader 2",
                    "type": "so100_leader",
                    "port": self.teleop_solo_arm_config.get_port(),
                    "id": self.teleop_solo_arm_config.get_id(),
                    "arm_id": 2
                }
            else:
                teleop_arm2_data = existing_teleop_arms[1] if len(existing_teleop_arms) > 1 else {}
                teleop_arm2_data.update({
                    "enabled": False,
                    "name": "Leader 2",
                    "type": "so100_leader",
                    "arm_id": 2
                })
            teleop_arms.append(teleop_arm2_data)
        else:
            # Bimanual mode: Save from both arm configs
            teleop_arm1_data = {
                "enabled": True,
                "name": "Leader 1",
                "type": "so100_leader",
                "port": self.teleop_arm1_config.get_port(),
                "id": self.teleop_arm1_config.get_id(),
                "arm_id": 1
            }
            teleop_arms.append(teleop_arm1_data)
            
            teleop_arm2_data = {
                "enabled": True,
                "name": "Leader 2",
                "type": "so100_leader",
                "port": self.teleop_arm2_config.get_port(),
                "id": self.teleop_arm2_config.get_id(),
                "arm_id": 2
            }
            teleop_arms.append(teleop_arm2_data)
        
        self.config["teleop"]["arms"] = teleop_arms
        
        # Save teleop mode (default to solo if not set)
        if self.teleop_mode_selector:
            self.config["teleop"]["mode"] = self.teleop_mode_selector.get_mode()
        elif "mode" not in self.config.get("teleop", {}):
            self.config["teleop"]["mode"] = "solo"
        
        # Camera settings
        if "cameras" not in self.config:
            self.config["cameras"] = {"front": {}, "wrist": {}}
        self.config["cameras"]["front"]["index_or_path"] = self.cam_front_edit.text()
        self.config["cameras"]["wrist"]["index_or_path"] = self.cam_wrist_edit.text()
        self.config["cameras"]["front"]["width"] = self.cam_width_spin.value()
        self.config["cameras"]["front"]["height"] = self.cam_height_spin.value()
        self.config["cameras"]["front"]["fps"] = self.cam_fps_spin.value()
        self.config["cameras"]["wrist"]["width"] = self.cam_width_spin.value()
        self.config["cameras"]["wrist"]["height"] = self.cam_height_spin.value()
        self.config["cameras"]["wrist"]["fps"] = self.cam_fps_spin.value()
        
        # Policy settings
        if "policy" not in self.config:
            self.config["policy"] = {}
        self.config["policy"]["base_path"] = self.policy_base_edit.text()
        self.config["policy"]["device"] = self.policy_device_edit.text()
        self.config["policy"]["local_mode"] = self.policy_local_check.isChecked()
        
        # Async inference
        if "async_inference" not in self.config:
            self.config["async_inference"] = {}
        self.config["async_inference"]["server_host"] = self.async_host_edit.text()
        self.config["async_inference"]["server_port"] = self.async_port_spin.value()
        
        # Control settings
        if "control" not in self.config:
            self.config["control"] = {}
        self.config["control"]["num_episodes"] = self.num_episodes_spin.value()
        self.config["control"]["episode_time_s"] = self.episode_time_spin.value()
        self.config["control"]["warmup_time_s"] = self.warmup_spin.value()
        self.config["control"]["reset_time_s"] = self.reset_time_spin.value()
        self.config["control"]["display_data"] = self.display_data_check.isChecked()
        
        # UI settings
        if "ui" not in self.config:
            self.config["ui"] = {}
        self.config["ui"]["object_gate"] = self.object_gate_check.isChecked()

        # Safety settings
        if "safety" not in self.config:
            self.config["safety"] = {}
        self.config["safety"]["motor_temp_monitoring_enabled"] = self.motor_temp_monitor_check.isChecked()
        self.config["safety"]["motor_temp_threshold_c"] = self.motor_temp_threshold_spin.value()
        self.config["safety"]["motor_temp_poll_interval_s"] = self.motor_temp_interval_spin.value()
        self.config["safety"]["torque_monitoring_enabled"] = self.torque_monitor_check.isChecked()
        self.config["safety"]["torque_limit_percent"] = self.torque_threshold_spin.value()
        self.config["safety"]["torque_auto_disable"] = self.torque_disable_check.isChecked()
        
        # Write to file
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            
            self.status_label.setText("✓ Settings saved successfully!")
            self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")
            self.config_changed.emit()
            
        except Exception as e:
            self.status_label.setText(f"❌ Error: {str(e)}")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
    
    def reset_defaults(self):
        """Reset to default values"""
        self.robot_port_edit.setText("/dev/ttyACM0")
        self.robot_fps_spin.setValue(30)
        self.teleop_port_edit.setText("/dev/ttyACM1")
        self.position_tolerance_spin.setValue(10)
        self.position_verification_check.setChecked(True)
        
        self.cam_front_edit.setText("/dev/video1")
        self.cam_wrist_edit.setText("/dev/video3")
        self.cam_width_spin.setValue(640)
        self.cam_height_spin.setValue(480)
        self.cam_fps_spin.setValue(30)
        
        self.policy_base_edit.setText("outputs/train")
        self.policy_device_edit.setText("cuda")
        
        self.async_host_edit.setText("127.0.0.1")
        self.async_port_spin.setValue(8080)
        
        self.num_episodes_spin.setValue(10)
        self.episode_time_spin.setValue(20.0)
        self.warmup_spin.setValue(3.0)
        self.reset_time_spin.setValue(8.0)
        self.display_data_check.setChecked(True)
        self.object_gate_check.setChecked(False)

        self.motor_temp_monitor_check.setChecked(False)
        self.motor_temp_threshold_spin.setValue(75)
        self.motor_temp_interval_spin.setValue(2.0)
        self.torque_monitor_check.setChecked(False)
        self.torque_threshold_spin.setValue(120.0)
        self.torque_disable_check.setChecked(True)
        
        self.status_label.setText("⚠️ Defaults loaded. Click Save to apply.")
        self.status_label.setStyleSheet("QLabel { color: #FF9800; font-size: 15px; padding: 8px; }")
    
    # ========== HOME METHODS ==========

    def set_rest_position(self):
        """Read current motor positions and save as Home position for first arm"""
        try:
            from utils.motor_controller import MotorController
            from utils.config_compat import set_home_positions
            
            self.status_label.setText("⏳ Reading motor positions from Arm 1...")
            self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")
            
            # Initialize motor controller for first arm
            motor_controller = MotorController(self.config, arm_index=0)
            
            # Connect and read positions
            if not motor_controller.connect():
                self.status_label.setText("❌ Failed to connect to motors")
                self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
                return
            
            positions = motor_controller.read_positions()
            motor_controller.disconnect()
            
            if positions is None:
                self.status_label.setText("❌ Failed to read motor positions")
                self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
                return
            
            # Save to config using helper (handles both old and new formats)
            set_home_positions(self.config, positions, arm_index=0)
            
            # Also update velocity for first arm
            if "arms" in self.config.get("robot", {}):
                self.config["robot"]["arms"][0]["home_velocity"] = self.rest_velocity_spin.value()
            
            # Write to file
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            
            self.status_label.setText(f"✓ Home saved for Arm 1: {positions}")
            self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")
            self.config_changed.emit()
            
        except Exception as e:
            self.status_label.setText(f"❌ Error: {str(e)}")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
    
    def go_home(self):
        """Move the arm to the saved home position without blocking the UI thread."""
        from utils.config_compat import get_home_positions
        
        if self._home_thread and self._home_thread.isRunning():
            self.status_label.setText("⏳ Already moving to home...")
            self.status_label.setStyleSheet("QLabel { color: #FFB74D; font-size: 15px; padding: 8px; }")
            return

        # Check if home positions exist for first arm
        home_pos = get_home_positions(self.config, arm_index=0)
        if not home_pos:
            self.status_label.setText("❌ No home position saved for Arm 1. Click 'Set Home' first.")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
            return

        velocity = int(self.rest_velocity_spin.value())
        self._pending_home_velocity = velocity

        self.status_label.setText("🏠 Moving Arm 1 to home position...")
        self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")
        self.home_btn.setEnabled(False)

        request = HomeMoveRequest(
            config=self.config,
            velocity_override=velocity,
            arm_index=0,  # Home first arm
        )

        worker = HomeMoveWorker(request)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_home_progress)
        worker.finished.connect(self._on_home_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_home_thread_finished)

        self._home_thread = thread
        self._home_worker = worker

        thread.start()

    def _on_home_progress(self, message: str) -> None:
        self.status_label.setText(message)
        self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")

    def _on_home_finished(self, success: bool, message: str) -> None:
        self.home_btn.setEnabled(True)

        if success:
            detail = message or f"✓ Moved to home position at velocity {self._pending_home_velocity or self.rest_velocity_spin.value()}"
            color = "#4CAF50"
        else:
            detail = message or "Unknown error"
            if not detail.startswith("❌"):
                detail = f"❌ Error: {detail}"
            color = "#f44336"

        self.status_label.setText(detail)
        self.status_label.setStyleSheet(f"QLabel {{ color: {color}; font-size: 15px; padding: 8px; }}")
        self._pending_home_velocity = None

    def _on_home_thread_finished(self) -> None:
        if self._home_thread:
            self._home_thread.deleteLater()
        self._home_thread = None
        self._home_worker = None
        if self._pending_home_velocity is not None:
            # Ensure we clear pending velocity if the thread ended unexpectedly.
            self._pending_home_velocity = None

    # ========== PORT DETECTION METHODS ==========
    
    def find_robot_ports(self):
        """Scan serial ports and detect robot arms"""
        try:
            import serial.tools.list_ports
            from utils.motor_controller import MotorController
            
            self.status_label.setText("⏳ Scanning serial ports...")
            self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")
            
            # Scan all serial ports
            ports = serial.tools.list_ports.comports()
            found_robots = []
            
            for port in ports:
                port_name = port.device
                
                # Only test ttyACM* and ttyUSB* devices
                if not ('ttyACM' in port_name or 'ttyUSB' in port_name):
                    continue
                
                # Try to connect and detect robot
                try:
                    test_config = self.config.get("robot", {}).copy()
                    test_config["port"] = port_name
                    motor_controller = MotorController(test_config)
                    
                    if motor_controller.connect():
                        # Try to read positions (confirms it's a robot)
                        positions = motor_controller.read_positions()
                        motor_controller.disconnect()
                        
                        if positions:
                            motor_count = len(positions)
                            found_robots.append({
                                "port": port_name,
                                "motors": motor_count,
                                "description": port.description
                            })
                except:
                    pass  # Not a robot, continue scanning
            
            # Display results
            if found_robots:
                from PySide6.QtWidgets import QDialog, QVBoxLayout, QRadioButton, QButtonGroup, QPushButton
                
                dialog = QDialog(self)
                dialog.setWindowTitle("Found Robot Ports")
                dialog.setMinimumWidth(500)
                dialog.setStyleSheet("QDialog { background-color: #2a2a2a; }")
                
                layout = QVBoxLayout(dialog)
                
                title = QLabel(f"✓ Found {len(found_robots)} robot(s):")
                title.setStyleSheet("color: #4CAF50; font-size: 16px; font-weight: bold; padding: 10px;")
                layout.addWidget(title)
                
                button_group = QButtonGroup(dialog)
                
                for robot in found_robots:
                    radio = QRadioButton(f"{robot['port']} - {robot['motors']} motors - {robot['description']}")
                    radio.setStyleSheet("QRadioButton { color: #e0e0e0; font-size: 14px; padding: 5px; }")
                    radio.setProperty("port", robot['port'])
                    button_group.addButton(radio)
                    layout.addWidget(radio)
                
                # Select first by default
                if button_group.buttons():
                    button_group.buttons()[0].setChecked(True)
                
                # Buttons
                btn_layout = QHBoxLayout()
                btn_layout.addStretch()
                
                cancel_btn = QPushButton("Cancel")
                cancel_btn.setStyleSheet(self.get_button_style("#909090", "#707070"))
                cancel_btn.clicked.connect(dialog.reject)
                btn_layout.addWidget(cancel_btn)
                
                select_btn = QPushButton("Select")
                select_btn.setStyleSheet(self.get_button_style("#4CAF50", "#388E3C"))
                select_btn.clicked.connect(dialog.accept)
                btn_layout.addWidget(select_btn)
                
                layout.addLayout(btn_layout)
                
                if dialog.exec() == QDialog.Accepted:
                    # Get selected port
                    for button in button_group.buttons():
                        if button.isChecked():
                            selected_port = button.property("port")
                            self.robot_port_edit.setText(selected_port)
                            
                            # Update status to online (both local and device_manager)
                            self.robot_status = "online"
                            self.update_status_circle(self.robot_status_circle, "online")
                            if self.device_manager:
                                self.device_manager.update_robot_status("online")
                            
                            self.status_label.setText(f"✓ Selected: {selected_port}")
                            self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")
                            break
            else:
                self.status_label.setText("❌ No robot arms found on serial ports")
                self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
                
        except Exception as e:
            self.status_label.setText(f"❌ Error: {str(e)}")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
    
    # ========== CALIBRATION METHODS ==========
    
    def calibrate_arm(self):
        """Run arm calibration sequence"""
        try:
            from utils.motor_controller import MotorController
            from PySide6.QtWidgets import QMessageBox
            
            # Warning dialog
            reply = QMessageBox.warning(
                self,
                "Calibration Warning",
                "⚠️ This will move the arm through its full range of motion.\n\n"
                "Please ensure:\n"
                "• Workspace is clear\n"
                "• Arm can move freely\n"
                "• Emergency stop is accessible\n\n"
                "Continue with calibration?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
            
            self.status_label.setText("⏳ Starting calibration...")
            self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")
            
            # Initialize motor controller
            motor_config = self.config.get("robot", {})
            motor_controller = MotorController(motor_config)
            
            if not motor_controller.connect():
                self.status_label.setText("❌ Failed to connect to motors")
                self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
                return
            
            # Step 1: Read current positions (starting point)
            self.status_label.setText("⏳ Step 1/3: Reading current positions...")
            current_positions = motor_controller.read_positions()
            
            if not current_positions:
                self.status_label.setText("❌ Failed to read positions")
                self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
                motor_controller.disconnect()
                return
            
            # Step 2: Move to home position (2048 - middle for SO-100/SO-101)
            self.status_label.setText("⏳ Step 2/3: Moving to home position...")
            home_positions = [2048] * len(current_positions)
            motor_controller.set_positions(home_positions, velocity=400, wait=True, keep_connection=True)
            
            # Step 3: Test range (gentle movement)
            self.status_label.setText("⏳ Step 3/3: Testing joint range...")
            import time
            
            # Small range test - move each joint slightly
            for i in range(len(current_positions)):
                test_positions = home_positions.copy()
                # Move joint +/- 200 units
                test_positions[i] = 2248
                motor_controller.set_positions(test_positions, velocity=300, wait=True, keep_connection=True)
                time.sleep(0.5)
                test_positions[i] = 1848
                motor_controller.set_positions(test_positions, velocity=300, wait=True, keep_connection=True)
                time.sleep(0.5)
                # Return to home
                motor_controller.set_positions(home_positions, velocity=300, wait=True, keep_connection=True)
            
            # Save calibration data
            if "calibration" not in self.config:
                self.config["calibration"] = {}
            
            self.config["calibration"]["home_positions"] = home_positions
            self.config["calibration"]["calibrated"] = True
            self.config["calibration"]["date"] = str(Path(__file__).stat().st_mtime)
            
            # Write to file
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            
            motor_controller.disconnect()
            
            self.status_label.setText("✓ Calibration complete!")
            self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")
            self.config_changed.emit()
            
        except Exception as e:
            self.status_label.setText(f"❌ Error: {str(e)}")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
    
    # ========== CAMERA DETECTION METHODS ==========
    
    def find_cameras(self):
        """Scan for available cameras"""
        try:
            import cv2
            from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QRadioButton, QButtonGroup, QPushButton, QComboBox
            from PySide6.QtGui import QImage, QPixmap
            from PySide6.QtCore import QTimer
            
            self.status_label.setText("⏳ Scanning for cameras...")
            self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")
            
            # Scan /dev/video* devices (0-9)
            found_cameras = []
            
            for i in range(10):
                try:
                    cap = cv2.VideoCapture(i)
                    if cap.isOpened():
                        # Try to read a frame to confirm it's working
                        ret, frame = cap.read()
                        if ret:
                            height, width = frame.shape[:2]
                            found_cameras.append({
                                "index": i,
                                "path": f"/dev/video{i}",
                                "resolution": f"{width}x{height}",
                                "capture": cap  # Keep for preview
                            })
                        else:
                            cap.release()
                    else:
                        cap.release()
                except:
                    pass
            
            if not found_cameras:
                self.status_label.setText("❌ No cameras found")
                self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
                return
            
            # Create selection dialog with preview
            dialog = QDialog(self)
            dialog.setWindowTitle("Found Cameras")
            dialog.setMinimumWidth(600)
            dialog.setMinimumHeight(500)
            dialog.setStyleSheet("QDialog { background-color: #2a2a2a; }")
            
            layout = QVBoxLayout(dialog)
            
            title = QLabel(f"✓ Found {len(found_cameras)} camera(s):")
            title.setStyleSheet("color: #4CAF50; font-size: 16px; font-weight: bold; padding: 10px;")
            layout.addWidget(title)
            
            # Camera list
            camera_list = QComboBox()
            camera_list.setStyleSheet("""
                QComboBox {
                    background-color: #505050;
                    color: #ffffff;
                    border: 2px solid #707070;
                    border-radius: 8px;
                    padding: 10px;
                    font-size: 15px;
                }
            """)
            for cam in found_cameras:
                camera_list.addItem(f"{cam['path']} - {cam['resolution']}", cam['index'])
            layout.addWidget(camera_list)
            
            # Preview label
            preview_label = QLabel("Camera Preview")
            preview_label.setStyleSheet("background-color: #000000; min-height: 300px;")
            preview_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(preview_label)
            
            # Assignment section
            assign_section = QLabel("Assign to:")
            assign_section.setStyleSheet("color: #e0e0e0; font-size: 14px; padding: 10px;")
            layout.addWidget(assign_section)
            
            assign_group = QButtonGroup(dialog)
            
            front_radio = QRadioButton("Front Camera")
            front_radio.setStyleSheet("QRadioButton { color: #e0e0e0; font-size: 14px; padding: 5px; }")
            front_radio.setChecked(True)
            assign_group.addButton(front_radio, 0)
            layout.addWidget(front_radio)
            
            wrist_radio = QRadioButton("Wrist Camera")
            wrist_radio.setStyleSheet("QRadioButton { color: #e0e0e0; font-size: 14px; padding: 5px; }")
            assign_group.addButton(wrist_radio, 1)
            layout.addWidget(wrist_radio)
            
            # Preview update function
            def update_preview():
                try:
                    selected_idx = camera_list.currentData()
                    for cam in found_cameras:
                        if cam['index'] == selected_idx:
                            ret, frame = cam['capture'].read()
                            if ret:
                                # Resize for preview
                                frame = cv2.resize(frame, (480, 360))
                                # Convert to Qt format
                                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                                h, w, ch = rgb_frame.shape
                                bytes_per_line = ch * w
                                qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
                                preview_label.setPixmap(QPixmap.fromImage(qt_image))
                            break
                except:
                    pass
            
            # Timer for preview updates
            preview_timer = QTimer(dialog)
            preview_timer.timeout.connect(update_preview)
            preview_timer.start(100)  # 10 FPS preview
            
            # Buttons
            btn_layout = QHBoxLayout()
            btn_layout.addStretch()
            
            cancel_btn = QPushButton("Cancel")
            cancel_btn.setStyleSheet(self.get_button_style("#909090", "#707070"))
            cancel_btn.clicked.connect(dialog.reject)
            btn_layout.addWidget(cancel_btn)
            
            select_btn = QPushButton("Assign Camera")
            select_btn.setStyleSheet(self.get_button_style("#4CAF50", "#388E3C"))
            select_btn.clicked.connect(dialog.accept)
            btn_layout.addWidget(select_btn)
            
            layout.addLayout(btn_layout)
            
            if dialog.exec() == QDialog.Accepted:
                # Get selected camera and assignment
                selected_idx = camera_list.currentData()
                selected_cam = None
                for cam in found_cameras:
                    if cam['index'] == selected_idx:
                        selected_cam = cam
                        break
                
                if selected_cam:
                    camera_path = selected_cam['path']
                    if assign_group.checkedId() == 0:
                        # Front camera
                        self.cam_front_edit.setText(camera_path)
                        
                        # Update status to online (both local and device_manager)
                        self.camera_front_status = "online"
                        self.update_status_circle(self.camera_front_circle, "online")
                        if self.device_manager:
                            self.device_manager.update_camera_status("front", "online")
                        
                        self.status_label.setText(f"✓ Assigned {camera_path} to Front Camera")
                    else:
                        # Wrist camera
                        self.cam_wrist_edit.setText(camera_path)
                        
                        # Update status to online (both local and device_manager)
                        self.camera_wrist_status = "online"
                        self.update_status_circle(self.camera_wrist_circle, "online")
                        if self.device_manager:
                            self.device_manager.update_camera_status("wrist", "online")
                        
                        self.status_label.setText(f"✓ Assigned {camera_path} to Wrist Camera")
                    
                    self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")
            
            # Cleanup
            preview_timer.stop()
            for cam in found_cameras:
                cam['capture'].release()
                
        except Exception as e:
            self.status_label.setText(f"❌ Error: {str(e)}")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
    
    # ========== DEVICE MANAGER SIGNAL HANDLERS ==========
    
    def on_robot_status_changed(self, status: str):
        """Handle robot status change from device manager
        
        Args:
            status: "empty", "online", or "offline"
        """
        self.robot_status = status
        if self.robot_status_circle:
            self.update_status_circle(self.robot_status_circle, status)
    
    def on_camera_status_changed(self, camera_name: str, status: str):
        """Handle camera status change from device manager
        
        Args:
            camera_name: "front" or "wrist"
            status: "empty", "online", or "offline"
        """
        if camera_name == "front":
            self.camera_front_status = status
            if self.camera_front_circle:
                self.update_status_circle(self.camera_front_circle, status)
        elif camera_name == "wrist":
            self.camera_wrist_status = status
            if self.camera_wrist_circle:
                self.update_status_circle(self.camera_wrist_circle, status)
    
    # ========== MULTI-ARM MANAGEMENT METHODS ==========
    
    def add_robot_arm(self):
        """Add a new robot arm to the configuration"""
        # Check max limit (2 arms)
        if len(self.robot_arm_widgets) >= 2:
            self.status_label.setText("⚠️ Maximum 2 robot arms allowed")
            self.status_label.setStyleSheet("QLabel { color: #FF9800; font-size: 15px; padding: 8px; }")
            return
        
        arm_index = len(self.robot_arm_widgets)
        arm_name = f"Follower {arm_index + 1}"
        
        # Create arm widget
        arm_widget = ArmConfigSection(
            arm_name=arm_name,
            arm_index=arm_index,
            show_controls=True,
            show_home_pos=True,
            parent=self
        )
        
        # Populate calibration IDs
        self._populate_calibration_ids(arm_widget.id_combo)
        
        # Connect signals
        arm_widget.home_clicked.connect(lambda idx=arm_index: self.home_arm(idx))
        arm_widget.set_home_clicked.connect(lambda idx=arm_index: self.set_home_arm(idx))
        arm_widget.calibrate_clicked.connect(lambda idx=arm_index: self.calibrate_arm_at_index(idx))
        arm_widget.delete_clicked.connect(lambda idx=arm_index: self.remove_robot_arm(idx))
        
        # Add to layout and list
        self.robot_arms_container.addWidget(arm_widget)
        self.robot_arm_widgets.append(arm_widget)
        
        # Update Add button state
        if len(self.robot_arm_widgets) >= 2:
            self.add_robot_arm_btn.setEnabled(False)
        
        self.status_label.setText(f"✓ Added {arm_name}")
        self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")
    
    def remove_robot_arm(self, arm_index: int):
        """Remove a robot arm from the configuration"""
        if arm_index >= len(self.robot_arm_widgets):
            return
        
        # Remove widget
        widget = self.robot_arm_widgets[arm_index]
        self.robot_arms_container.removeWidget(widget)
        widget.deleteLater()
        
        # Remove from list
        self.robot_arm_widgets.pop(arm_index)
        
        # Re-index remaining widgets
        for i, w in enumerate(self.robot_arm_widgets):
            w.arm_index = i
            w.arm_name = f"Follower {i + 1}"
            # Update label if needed
        
        # Update Add button state
        self.add_robot_arm_btn.setEnabled(True)
        
        self.status_label.setText("✓ Arm removed")
        self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")
    
    def home_arm(self, arm_index: int):
        """Home a specific arm"""
        from utils.config_compat import get_home_positions
        
        if self._home_thread and self._home_thread.isRunning():
            self.status_label.setText("⏳ Already moving...")
            return
        
        home_pos = get_home_positions(self.config, arm_index)
        if not home_pos:
            self.status_label.setText(f"❌ No home position for Arm {arm_index + 1}. Set home first.")
            return
        
        # Use master velocity from top of settings
        velocity = self.rest_velocity_spin.value()
        
        self.status_label.setText(f"🏠 Moving Arm {arm_index + 1} to home...")
        self.home_btn.setEnabled(False)
        
        request = HomeMoveRequest(config=self.config, velocity_override=velocity, arm_index=arm_index)
        worker = HomeMoveWorker(request)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_home_progress)
        worker.finished.connect(self._on_home_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_home_thread_finished)
        
        self._home_worker = worker
        self._home_thread = thread
        thread.start()
    
    def set_home_arm(self, arm_index: int):
        """Set home position for a specific arm"""
        try:
            from utils.motor_controller import MotorController
            from utils.config_compat import set_home_positions
            
            self.status_label.setText(f"⏳ Reading positions from Arm {arm_index + 1}...")
            
            motor_controller = MotorController(self.config, arm_index=arm_index)
            
            if not motor_controller.connect():
                self.status_label.setText("❌ Failed to connect to motors")
                return
            
            positions = motor_controller.read_positions()
            motor_controller.disconnect()
            
            if positions is None:
                self.status_label.setText("❌ Failed to read positions")
                return
            
            # Save to config
            set_home_positions(self.config, positions, arm_index)
            
            # Also update velocity
            if "arms" in self.config.get("robot", {}) and arm_index < len(self.config["robot"]["arms"]):
                if arm_index < len(self.robot_arm_widgets):
                    velocity = self.robot_arm_widgets[arm_index].get_home_velocity()
                    self.config["robot"]["arms"][arm_index]["home_velocity"] = velocity
                    # Update widget display
                    self.robot_arm_widgets[arm_index].set_home_positions(positions)
            
            # Write to file
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            
            self.status_label.setText(f"✓ Home saved for Arm {arm_index + 1}: {positions}")
            self.config_changed.emit()
            
        except Exception as e:
            self.status_label.setText(f"❌ Error: {str(e)}")
    
    def calibrate_arm_at_index(self, arm_index: int):
        """Calibrate a specific arm"""
        # For now, use the existing calibrate_arm method but update it to support arm_index
        # This would need the calibration UI to support selecting which arm
        self.status_label.setText(f"⚠️ Calibration for Arm {arm_index + 1} - use calibration tab")
        self.status_label.setStyleSheet("QLabel { color: #FF9800; font-size: 15px; padding: 8px; }")
    
    def home_all_arms(self):
        """Home all enabled arms sequentially"""
        from utils.config_compat import get_enabled_arms
        
        enabled_arms = get_enabled_arms(self.config, "robot")
        if not enabled_arms:
            self.status_label.setText("❌ No enabled arms to home")
            return
        
        self.status_label.setText(f"🏠 Homing {len(enabled_arms)} enabled arm(s)...")
        
        # For now, just home the first enabled arm
        # Full sequential homing would need a more complex worker
        self.home_arm(0)
    
    def populate_robot_arms_from_config(self):
        """Populate robot arm widgets from config"""
        # Clear existing widgets
        for widget in self.robot_arm_widgets:
            self.robot_arms_container.removeWidget(widget)
            widget.deleteLater()
        self.robot_arm_widgets.clear()
        
        # Get arms from config
        robot_cfg = self.config.get("robot", {})
        arms = robot_cfg.get("arms", [])
        
        # Create widget for each arm
        for i, arm in enumerate(arms):
            arm_widget = ArmConfigSection(
                arm_name=arm.get("name", f"Follower {i + 1}"),
                arm_index=i,
                show_controls=True,
                show_home_pos=True,
                parent=self
            )
            
            # Populate data
            arm_widget.set_port(arm.get("port", ""))
            arm_widget.set_id(arm.get("id", ""))
            arm_widget.set_enabled(arm.get("enabled", True))
            arm_widget.set_home_positions(arm.get("home_positions", []))
            arm_widget.set_home_velocity(arm.get("home_velocity", 600))
            
            # Populate calibration IDs
            self._populate_calibration_ids(arm_widget.id_combo)
            arm_widget.set_id(arm.get("id", ""))  # Set again after populating
            
            # Connect signals
            arm_widget.home_clicked.connect(lambda idx=i: self.home_arm(idx))
            arm_widget.set_home_clicked.connect(lambda idx=i: self.set_home_arm(idx))
            arm_widget.calibrate_clicked.connect(lambda idx=i: self.calibrate_arm_at_index(idx))
            arm_widget.delete_clicked.connect(lambda idx=i: self.remove_robot_arm(idx))
            
            # Add to layout and list
            self.robot_arms_container.addWidget(arm_widget)
            self.robot_arm_widgets.append(arm_widget)
        
        # Update Add button state
        self.add_robot_arm_btn.setEnabled(len(self.robot_arm_widgets) < 2)
