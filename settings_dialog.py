#!/usr/bin/env python3
"""
Settings dialog for LeRobot Operator Console.
Provides tabbed interface to edit all configuration parameters.
"""

import json
import os
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox,
    QPushButton, QFileDialog, QComboBox, QGroupBox, QFormLayout,
    QMessageBox, QTextEdit, QApplication, QScrollArea, QFrame
)
from PySide6.QtCore import Qt, QTimer


class SettingsDialog(QDialog):
    """Settings editor with tabbed interface"""
    
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config.copy()  # Work on a copy
        self.original_config = config
        
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(800, 700)
        
        # Storage for dynamic camera/robot widgets
        self.camera_widgets = []
        self.robot_widgets = []
        
        self.init_ui()
        self.load_values()
        
    def init_ui(self):
        """Initialize UI"""
        layout = QVBoxLayout(self)
        
        # Tab widget
        self.tabs = QTabWidget()
        self.tabs.addTab(self.create_robot_tab(), "Robot")
        self.tabs.addTab(self.create_camera_tab(), "Cameras")
        self.tabs.addTab(self.create_policy_tab(), "Policy")
        self.tabs.addTab(self.create_control_tab(), "Control")
        self.tabs.addTab(self.create_advanced_tab(), "Advanced")
        layout.addWidget(self.tabs)
        
        # Buttons - Make them touch-friendly
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(50)
        self.cancel_btn.setStyleSheet("font-size: 16px; padding: 10px 30px;")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        
        self.save_btn = QPushButton("Save")
        self.save_btn.setMinimumHeight(50)
        self.save_btn.setStyleSheet("font-size: 16px; padding: 10px 30px; background-color: #4CAF50; color: white; font-weight: bold;")
        self.save_btn.clicked.connect(self.save_settings)
        self.save_btn.setDefault(True)
        btn_layout.addWidget(self.save_btn)
        
        layout.addLayout(btn_layout)
        
    def create_robot_tab(self):
        """Robot settings tab with main robot + additional arms"""
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
        
        # Main robot (follower) settings in a group
        main_robot_group = QGroupBox("Main Robot (Follower)")
        main_robot_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; padding-top: 15px; }")
        layout = QFormLayout(main_robot_group)
        
        # Robot type
        self.robot_type = QLineEdit()
        layout.addRow("Robot Type:", self.robot_type)
        
        # Port selection
        port_layout = QHBoxLayout()
        self.robot_port = QComboBox()
        self.robot_port.setEditable(True)
        self._populate_serial_ports()
        port_layout.addWidget(self.robot_port, 1)
        
        refresh_btn = QPushButton("🔄")
        refresh_btn.setMaximumWidth(40)
        refresh_btn.clicked.connect(self._populate_serial_ports)
        refresh_btn.setToolTip("Refresh port list")
        port_layout.addWidget(refresh_btn)
        
        layout.addRow("Serial Port:", port_layout)
        
        # Robot ID
        self.robot_id = QLineEdit()
        layout.addRow("Robot ID:", self.robot_id)
        
        # FPS
        self.robot_fps = QSpinBox()
        self.robot_fps.setRange(1, 120)
        layout.addRow("FPS:", self.robot_fps)
        
        # Min time to move multiplier
        self.min_time_multiplier = QDoubleSpinBox()
        self.min_time_multiplier.setRange(0.1, 10.0)
        self.min_time_multiplier.setSingleStep(0.1)
        self.min_time_multiplier.setDecimals(1)
        layout.addRow("Min Time Multiplier:", self.min_time_multiplier)
        
        # Enable motor torque
        self.enable_torque = QCheckBox()
        layout.addRow("Enable Motor Torque:", self.enable_torque)
        
        main_layout.addWidget(main_robot_group)
        
        # Additional arms section (leader arms, etc)
        additional_label = QLabel("Additional Arms (Leader, etc)")
        additional_label.setStyleSheet("font-weight: bold; font-size: 13px; margin-top: 10px;")
        main_layout.addWidget(additional_label)
        
        # Scroll area for additional robots
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        scroll_widget = QWidget()
        self.robots_layout = QVBoxLayout(scroll_widget)
        self.robots_layout.setAlignment(Qt.AlignTop)
        
        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)
        
        # Add button
        add_btn = QPushButton("➕ Add Robot")
        add_btn.setMinimumHeight(50)
        add_btn.setStyleSheet("""
            QPushButton {
                font-size: 16px;
                font-weight: bold;
                background-color: #4CAF50;
                color: white;
                border-radius: 8px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        add_btn.clicked.connect(self._add_robot_widget)
        main_layout.addWidget(add_btn)
        
        return widget
        
    def create_camera_tab(self):
        """Camera settings tab with dynamic camera addition"""
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
        
        # Scroll area for cameras
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        scroll_widget = QWidget()
        self.cameras_layout = QVBoxLayout(scroll_widget)
        self.cameras_layout.setAlignment(Qt.AlignTop)
        
        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)
        
        # Add button
        add_btn = QPushButton("➕ Add Camera")
        add_btn.setMinimumHeight(50)
        add_btn.setStyleSheet("""
            QPushButton {
                font-size: 16px;
                font-weight: bold;
                background-color: #4CAF50;
                color: white;
                border-radius: 8px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        add_btn.clicked.connect(self._add_camera_widget)
        main_layout.addWidget(add_btn)
        
        return widget
        
        
    def create_policy_tab(self):
        """Policy settings tab"""
        widget = QWidget()
        layout = QFormLayout(widget)
        
        # Base Path (train directory)
        base_path_layout = QHBoxLayout()
        self.policy_base_path = QLineEdit()
        self.policy_base_path.setPlaceholderText("/home/username/lerobot/outputs/train")
        base_path_layout.addWidget(self.policy_base_path, 1)
        
        browse_base_btn = QPushButton("Browse...")
        browse_base_btn.clicked.connect(self._browse_base_path)
        base_path_layout.addWidget(browse_base_btn)
        
        layout.addRow("Training Base Path:", base_path_layout)
        
        layout.addRow(QLabel(""))  # Spacer
        
        # Policy path with file browser
        path_layout = QHBoxLayout()
        self.policy_path = QLineEdit()
        path_layout.addWidget(self.policy_path, 1)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_policy)
        path_layout.addWidget(browse_btn)
        
        layout.addRow("Full Checkpoint Path:", path_layout)
        
        # Device
        self.policy_device = QComboBox()
        self.policy_device.addItems(["cpu", "cuda", "mps"])
        self.policy_device.setMinimumHeight(35)
        layout.addRow("Device:", self.policy_device)
        
        layout.addRow(QLabel(""))  # Spacer
        info = QLabel("ℹ️ Base Path: Directory containing all training tasks\n"
                     "Full Path: Complete path to specific checkpoint\n"
                     "Format: /path/to/train/TASK/checkpoints/STEP/pretrained_model")
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; font-size: 11px;")
        layout.addRow(info)
        
        return widget
    
    def _browse_base_path(self):
        """Open file browser for base training path"""
        current_path = self.policy_base_path.text() or os.path.expanduser("~")
        
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Training Base Directory",
            current_path
        )
        
        if path:
            self.policy_base_path.setText(path)
        
    def create_control_tab(self):
        """Control parameters tab"""
        widget = QWidget()
        layout = QFormLayout(widget)
        
        # Episodes
        self.num_episodes = QSpinBox()
        self.num_episodes.setRange(1, 9999)
        layout.addRow("Number of Episodes:", self.num_episodes)
        
        # Timings
        self.warmup_time = QDoubleSpinBox()
        self.warmup_time.setRange(0, 60)
        self.warmup_time.setSuffix(" s")
        layout.addRow("Warmup Time:", self.warmup_time)
        
        self.episode_time = QDoubleSpinBox()
        self.episode_time.setRange(1, 300)
        self.episode_time.setSuffix(" s")
        layout.addRow("Episode Time:", self.episode_time)
        
        self.reset_time = QDoubleSpinBox()
        self.reset_time.setRange(0, 60)
        self.reset_time.setSuffix(" s")
        layout.addRow("Reset Time:", self.reset_time)
        
        # Task name
        self.task_name = QLineEdit()
        layout.addRow("Task Name:", self.task_name)
        
        # Push to hub
        self.push_to_hub = QCheckBox()
        layout.addRow("Push to Hub:", self.push_to_hub)
        
        # Repo ID
        self.repo_id = QLineEdit()
        self.repo_id.setPlaceholderText("username/repo-name")
        layout.addRow("Hub Repo ID:", self.repo_id)
        
        return widget
        
    def create_advanced_tab(self):
        """Advanced settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Rest Position group
        rest_group = QGroupBox("Rest Position")
        rest_layout = QVBoxLayout(rest_group)
        
        # Set Home button
        set_home_btn = QPushButton("📍 SET HOME (Read Current Position)")
        set_home_btn.setMinimumHeight(50)
        set_home_btn.setStyleSheet("font-size: 14px; font-weight: bold;")
        set_home_btn.clicked.connect(self._set_home_position)
        rest_layout.addWidget(set_home_btn)
        
        rest_form = QFormLayout()
        
        # Rest positions
        self.rest_angles = QLineEdit()
        self.rest_angles.setPlaceholderText("[2048, 2048, 2048, 2048, 2048, 2048]")
        rest_form.addRow("Motor Positions:", self.rest_angles)
        
        # Velocity for going home
        self.rest_speed = QSpinBox()
        self.rest_speed.setRange(100, 4000)
        self.rest_speed.setSingleStep(100)
        self.rest_speed.setToolTip("Velocity when moving to home (100 = very slow, 1200 = safe, 4000 = max)")
        rest_form.addRow("Home Speed:", self.rest_speed)
        
        rest_layout.addLayout(rest_form)
        layout.addWidget(rest_group)
        
        # Object Gate group
        gate_group = QGroupBox("Object Presence Gate")
        gate_layout = QFormLayout(gate_group)
        
        self.object_gate_enabled = QCheckBox()
        gate_layout.addRow("Enable Gate:", self.object_gate_enabled)
        
        self.roi_coords = QLineEdit()
        self.roi_coords.setPlaceholderText("[x, y, width, height]")
        gate_layout.addRow("ROI Coordinates:", self.roi_coords)
        
        self.presence_threshold = QDoubleSpinBox()
        self.presence_threshold.setRange(0.0, 1.0)
        self.presence_threshold.setSingleStep(0.01)
        self.presence_threshold.setDecimals(2)
        gate_layout.addRow("Threshold:", self.presence_threshold)
        
        layout.addWidget(gate_group)
        
        # Safety group
        safety_group = QGroupBox("Safety Limits")
        safety_layout = QVBoxLayout(safety_group)
        
        self.soft_limits = QTextEdit()
        self.soft_limits.setMaximumHeight(100)
        self.soft_limits.setPlaceholderText("[[-90,90], [-60,60], ...]")
        safety_layout.addWidget(QLabel("Soft Limits (deg):"))
        safety_layout.addWidget(self.soft_limits)
        
        layout.addWidget(safety_group)
        
        layout.addStretch()
        return widget
        
    def _add_camera_widget(self, camera_name="", camera_data=None):
        """Add a camera configuration widget"""
        if camera_data is None:
            camera_data = {
                "type": "opencv",
                "index_or_path": "/dev/video0",
                "width": 640,
                "height": 480,
                "fps": 30
            }
        
        # Create group box
        group = QGroupBox(f"Camera: {camera_name or f'camera_{len(self.camera_widgets)+1}'}")
        group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; padding-top: 10px; }")
        layout = QFormLayout(group)
        
        # Camera name
        name_edit = QLineEdit(camera_name)
        name_edit.setPlaceholderText("e.g., front, wrist, top")
        name_edit.setMinimumHeight(35)
        layout.addRow("Name:", name_edit)
        
        # Camera index/path
        index_combo = QComboBox()
        index_combo.setEditable(True)
        index_combo.setMinimumHeight(35)
        # Populate with available cameras
        for i in range(10):
            if os.path.exists(f"/dev/video{i}"):
                index_combo.addItem(f"/dev/video{i}")
        index_combo.setCurrentText(str(camera_data.get("index_or_path", "/dev/video0")))
        layout.addRow("Device:", index_combo)
        
        # Resolution
        width_spin = QSpinBox()
        width_spin.setRange(160, 3840)
        width_spin.setSingleStep(160)
        width_spin.setValue(camera_data.get("width", 640))
        width_spin.setMinimumHeight(35)
        layout.addRow("Width:", width_spin)
        
        height_spin = QSpinBox()
        height_spin.setRange(120, 2160)
        height_spin.setSingleStep(120)
        height_spin.setValue(camera_data.get("height", 480))
        height_spin.setMinimumHeight(35)
        layout.addRow("Height:", height_spin)
        
        # FPS
        fps_spin = QSpinBox()
        fps_spin.setRange(1, 120)
        fps_spin.setValue(camera_data.get("fps", 30))
        fps_spin.setMinimumHeight(35)
        layout.addRow("FPS:", fps_spin)
        
        # Remove button
        remove_btn = QPushButton("🗑️ Remove Camera")
        remove_btn.setMinimumHeight(40)
        remove_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                border-radius: 5px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        """)
        remove_btn.clicked.connect(lambda: self._remove_camera_widget(group))
        layout.addRow(remove_btn)
        
        # Store references
        camera_widget = {
            'group': group,
            'name': name_edit,
            'index': index_combo,
            'width': width_spin,
            'height': height_spin,
            'fps': fps_spin
        }
        self.camera_widgets.append(camera_widget)
        
        # Add to layout
        self.cameras_layout.addWidget(group)
        
    def _remove_camera_widget(self, group):
        """Remove a camera widget"""
        for widget_dict in self.camera_widgets:
            if widget_dict['group'] == group:
                self.camera_widgets.remove(widget_dict)
                widget_dict['group'].deleteLater()
                break
    
    def _add_robot_widget(self, robot_name="", robot_data=None):
        """Add a robot arm configuration widget"""
        if robot_data is None:
            robot_data = {
                "type": "so100_leader",
                "port": "/dev/ttyACM1",
                "id": "leader_arm"
            }
        
        # Create group box
        group = QGroupBox(f"Arm: {robot_name or f'arm_{len(self.robot_widgets)+1}'}")
        group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; padding-top: 10px; }")
        layout = QFormLayout(group)
        
        # Arm name
        name_edit = QLineEdit(robot_name)
        name_edit.setPlaceholderText("e.g., leader, follower")
        name_edit.setMinimumHeight(35)
        layout.addRow("Name:", name_edit)
        
        # Type
        type_combo = QComboBox()
        type_combo.addItems(["so100_leader", "so100_follower", "so101_leader", "so101_follower"])
        type_combo.setCurrentText(robot_data.get("type", "so100_leader"))
        type_combo.setMinimumHeight(35)
        layout.addRow("Type:", type_combo)
        
        # Port
        port_combo = QComboBox()
        port_combo.setEditable(True)
        port_combo.setMinimumHeight(35)
        # Populate with available ports
        import glob
        for pattern in ['/dev/ttyACM*', '/dev/ttyUSB*']:
            for port in glob.glob(pattern):
                port_combo.addItem(port)
        port_combo.setCurrentText(robot_data.get("port", "/dev/ttyACM1"))
        layout.addRow("Port:", port_combo)
        
        # ID
        id_edit = QLineEdit(robot_data.get("id", "leader_arm"))
        id_edit.setMinimumHeight(35)
        layout.addRow("ID:", id_edit)
        
        # Remove button
        remove_btn = QPushButton("🗑️ Remove Arm")
        remove_btn.setMinimumHeight(40)
        remove_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                border-radius: 5px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        """)
        remove_btn.clicked.connect(lambda: self._remove_robot_widget(group))
        layout.addRow(remove_btn)
        
        # Store references
        robot_widget = {
            'group': group,
            'name': name_edit,
            'type': type_combo,
            'port': port_combo,
            'id': id_edit
        }
        self.robot_widgets.append(robot_widget)
        
        # Add to layout
        self.robots_layout.addWidget(group)
        
    def _remove_robot_widget(self, group):
        """Remove a robot widget"""
        for widget_dict in self.robot_widgets:
            if widget_dict['group'] == group:
                self.robot_widgets.remove(widget_dict)
                widget_dict['group'].deleteLater()
                break
    
    def _populate_serial_ports(self):
        """Find available serial ports"""
        self.robot_port.clear()
        ports = []
        
        # Check common serial port paths
        for pattern in ['/dev/ttyACM*', '/dev/ttyUSB*', '/dev/tty.usb*']:
            import glob
            ports.extend(glob.glob(pattern))
        
        # Also check for custom symlinks
        if os.path.exists('/dev/so100'):
            ports.append('/dev/so100')
        if os.path.exists('/dev/so101'):
            ports.append('/dev/so101')
            
        if ports:
            self.robot_port.addItems(sorted(ports))
        else:
            self.robot_port.addItem("/dev/ttyACM0")
            
    def _browse_policy(self):
        """Open file browser for policy path"""
        current_path = self.policy_path.text() or os.path.expanduser("~")
        
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Policy Checkpoint Directory",
            current_path
        )
        
        if path:
            self.policy_path.setText(path)
            
    def _set_home_position(self):
        """Read current joint positions and set as rest position"""
        try:
            # Import rest_pos module
            from rest_pos import read_current_position
            
            # Change button style to show it's working
            sender = self.sender()
            original_style = sender.styleSheet()
            sender.setStyleSheet("""
                QPushButton {
                    background-color: #f57c00;
                    color: white;
                    font-size: 14px;
                    font-weight: bold;
                    padding: 15px;
                }
            """)
            sender.setText("Reading position...")
            QApplication.processEvents()
            
            # Read current angles
            angles = read_current_position()
            
            # Update UI
            self.rest_angles.setText(str(angles))
            
            # Restore button
            sender.setText("📍 SET HOME (Read Current Position)")
            sender.setStyleSheet(original_style)
            
            # No popup, just visual feedback
            sender.setStyleSheet("""
                QPushButton {
                    background-color: #2e7d32;
                    color: white;
                    font-size: 14px;
                    font-weight: bold;
                    padding: 15px;
                }
            """)
            QTimer.singleShot(2000, lambda: sender.setStyleSheet(original_style))
            
        except NotImplementedError:
            sender = self.sender()
            sender.setText("📍 SET HOME (Read Current Position)")
            sender.setStyleSheet("background-color: #c62828;")
            QTimer.singleShot(2000, lambda: sender.setStyleSheet(""))
        except Exception as e:
            sender = self.sender()
            sender.setText("❌ ERROR")
            sender.setStyleSheet("background-color: #c62828;")
            QTimer.singleShot(2000, lambda: sender.setText("📍 SET HOME (Read Current Position)"))
            QTimer.singleShot(2000, lambda: sender.setStyleSheet(""))
            
    def load_values(self):
        """Load values from config into UI"""
        # Robot
        r = self.config["robot"]
        self.robot_type.setText(r["type"])
        self.robot_port.setCurrentText(r["port"])
        self.robot_id.setText(r["id"])
        self.robot_fps.setValue(r["fps"])
        self.min_time_multiplier.setValue(r["min_time_to_move_multiplier"])
        self.enable_torque.setChecked(r["enable_motor_torque"])
        
        # Load dynamic cameras
        cameras = self.config.get("cameras", {})
        for cam_name, cam_data in cameras.items():
            self._add_camera_widget(cam_name, cam_data)
        
        # Load dynamic teleop arms
        teleops = self.config.get("teleop", {})
        # Handle both single teleop (dict) and multiple (dict of dicts)
        if teleops and "type" in teleops:
            # Single teleop - old format
            self._add_robot_widget("teleop", teleops)
        elif teleops:
            # Multiple teleops - new format
            for arm_name, arm_data in teleops.items():
                self._add_robot_widget(arm_name, arm_data)
        
        # Policy
        p = self.config["policy"]
        self.policy_path.setText(p["path"])
        self.policy_base_path.setText(p.get("base_path", "/home/daniel/lerobot/outputs/train"))
        self.policy_device.setCurrentText(p.get("device", "cpu"))
        
        # Control
        ctrl = self.config["control"]
        self.num_episodes.setValue(ctrl["num_episodes"])
        self.warmup_time.setValue(ctrl["warmup_time_s"])
        self.episode_time.setValue(ctrl["episode_time_s"])
        self.reset_time.setValue(ctrl["reset_time_s"])
        self.task_name.setText(ctrl["single_task"])
        self.push_to_hub.setChecked(ctrl["push_to_hub"])
        self.repo_id.setText(ctrl.get("repo_id") or "")
        
        # Advanced - Rest
        rest = self.config["rest_position"]
        # Handle both old (angles_deg) and new (positions) format
        positions = rest.get("positions", rest.get("angles_deg", [2048, 2048, 2048, 2048, 2048, 2048]))
        self.rest_angles.setText(str(positions))
        # Handle both old (speed_scale) and new (velocity) format
        velocity = rest.get("velocity", int(rest.get("speed_scale", 0.3) * 4000))
        self.rest_speed.setValue(velocity)
        
        # Advanced - Gate
        ui = self.config["ui"]
        self.object_gate_enabled.setChecked(ui["object_gate"])
        self.roi_coords.setText(str(ui["roi"]))
        self.presence_threshold.setValue(ui["presence_threshold"])
        
        # Advanced - Safety
        safety = self.config["safety"]
        self.soft_limits.setPlainText(json.dumps(safety["soft_limits_deg"], indent=2))
        
    def save_settings(self):
        """Save settings from UI to config"""
        try:
            # Robot
            self.config["robot"]["type"] = self.robot_type.text()
            self.config["robot"]["port"] = self.robot_port.currentText()
            self.config["robot"]["id"] = self.robot_id.text()
            self.config["robot"]["fps"] = self.robot_fps.value()
            self.config["robot"]["min_time_to_move_multiplier"] = self.min_time_multiplier.value()
            self.config["robot"]["enable_motor_torque"] = self.enable_torque.isChecked()
            
            # Save dynamic cameras
            self.config["cameras"] = {}
            for cam_widget in self.camera_widgets:
                name = cam_widget['name'].text().strip()
                if not name:
                    continue
                    
                index_or_path = cam_widget['index'].currentText()
                # Try to convert to int if it's a number
                try:
                    if '/' not in index_or_path:
                        index_or_path = int(index_or_path)
                except ValueError:
                    pass
                    
                self.config["cameras"][name] = {
                    "type": "opencv",
                    "index_or_path": index_or_path,
                    "width": cam_widget['width'].value(),
                    "height": cam_widget['height'].value(),
                    "fps": cam_widget['fps'].value()
                }
            
            # Save dynamic teleop arms
            if len(self.robot_widgets) == 1:
                # Single teleop - save as dict (old format for compatibility)
                widget = self.robot_widgets[0]
                self.config["teleop"] = {
                    "type": widget['type'].currentText(),
                    "port": widget['port'].currentText(),
                    "id": widget['id'].text()
                }
            elif len(self.robot_widgets) > 1:
                # Multiple teleops - save as nested dict
                self.config["teleop"] = {}
                for arm_widget in self.robot_widgets:
                    name = arm_widget['name'].text().strip()
                    if not name:
                        continue
                    self.config["teleop"][name] = {
                        "type": arm_widget['type'].currentText(),
                        "port": arm_widget['port'].currentText(),
                        "id": arm_widget['id'].text()
                    }
            else:
                # No teleop arms
                self.config["teleop"] = {}
            
            # Policy
            self.config["policy"]["path"] = self.policy_path.text()
            self.config["policy"]["device"] = self.policy_device.currentText()
            self.config["policy"]["base_path"] = self.policy_base_path.text()
            
            # Control
            self.config["control"]["num_episodes"] = self.num_episodes.value()
            self.config["control"]["warmup_time_s"] = self.warmup_time.value()
            self.config["control"]["episode_time_s"] = self.episode_time.value()
            self.config["control"]["reset_time_s"] = self.reset_time.value()
            self.config["control"]["single_task"] = self.task_name.text()
            self.config["control"]["push_to_hub"] = self.push_to_hub.isChecked()
            self.config["control"]["repo_id"] = self.repo_id.text() or None
            
            # Advanced - Rest
            rest_angles_str = self.rest_angles.text()
            self.config["rest_position"]["positions"] = json.loads(rest_angles_str)
            self.config["rest_position"]["velocity"] = self.rest_speed.value()
            # Ensure disable_torque_on_arrival is set
            if "disable_torque_on_arrival" not in self.config["rest_position"]:
                self.config["rest_position"]["disable_torque_on_arrival"] = True
            # Remove old speed_scale if it exists
            if "speed_scale" in self.config["rest_position"]:
                del self.config["rest_position"]["speed_scale"]
            
            # Advanced - Gate
            self.config["ui"]["object_gate"] = self.object_gate_enabled.isChecked()
            roi_str = self.roi_coords.text()
            self.config["ui"]["roi"] = json.loads(roi_str)
            self.config["ui"]["presence_threshold"] = self.presence_threshold.value()
            
            # Advanced - Safety
            limits_str = self.soft_limits.toPlainText()
            self.config["safety"]["soft_limits_deg"] = json.loads(limits_str)
            
            # Validation passed, accept dialog
            self.accept()
            
        except json.JSONDecodeError as e:
            QMessageBox.critical(
                self,
                "Invalid JSON",
                f"Failed to parse JSON field:\n\n{e}\n\n"
                "Check angles, ROI, or limits fields."
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Failed to save settings:\n\n{e}"
            )

