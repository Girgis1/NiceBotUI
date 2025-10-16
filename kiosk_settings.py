"""
Settings Modal - Touch-friendly configuration
No text input - only dropdowns, spinboxes, and toggles
"""

import os
import subprocess
from pathlib import Path
from copy import deepcopy

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QFrame, QGridLayout, QCheckBox
)
from PySide6.QtCore import Qt

from kiosk_styles import Colors, Styles


class SettingsModal(QDialog):
    """
    Settings configuration modal
    
    Features:
    - Full-screen overlay
    - Touch-friendly controls (no text input)
    - Auto-detection for ports and cameras
    - Cannot dismiss by clicking outside
    """
    
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        
        # Make a deep copy to avoid modifying original until save
        self.config = deepcopy(config)
        self.original_config = config
        
        # Setup dialog
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setFixedSize(1024, 600)
        
        # Frameless for consistency
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        
        # Initialize UI
        self.init_ui()
    
    def init_ui(self):
        """Initialize user interface"""
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Semi-transparent dark overlay background
        self.setStyleSheet(f"""
            QDialog {{
                background-color: rgba(0, 0, 0, 200);
            }}
        """)
        
        # Center panel
        panel = QFrame()
        panel.setFixedSize(900, 520)
        panel.setStyleSheet(Styles.get_modal_panel_style())
        
        # Center the panel
        layout.addStretch()
        center_layout = QHBoxLayout()
        center_layout.addStretch()
        center_layout.addWidget(panel)
        center_layout.addStretch()
        layout.addLayout(center_layout)
        layout.addStretch()
        
        # Panel layout
        panel_layout = QVBoxLayout(panel)
        panel_layout.setSpacing(15)
        panel_layout.setContentsMargins(30, 30, 30, 30)
        
        # Title
        title = QLabel("⚙️ Settings")
        title.setStyleSheet(Styles.get_label_style(size="huge", bold=True))
        title.setAlignment(Qt.AlignCenter)
        panel_layout.addWidget(title)
        
        # Settings grid
        grid = QGridLayout()
        grid.setSpacing(15)
        grid.setColumnStretch(1, 1)
        
        row = 0
        
        # === ROBOT SETTINGS ===
        robot_header = QLabel("Robot")
        robot_header.setStyleSheet(Styles.get_label_style(size="large", bold=True))
        grid.addWidget(robot_header, row, 0, 1, 2)
        row += 1
        
        # Robot Port
        port_label = QLabel("Port:")
        port_label.setStyleSheet(Styles.get_label_style(size="normal"))
        grid.addWidget(port_label, row, 0)
        
        self.port_combo = QComboBox()
        self.port_combo.setMinimumHeight(60)
        self.port_combo.setStyleSheet(Styles.get_dropdown_style().replace("min-height: 100px", "min-height: 60px"))
        self.populate_ports()
        grid.addWidget(self.port_combo, row, 1)
        row += 1
        
        # Robot FPS
        fps_label = QLabel("FPS:")
        fps_label.setStyleSheet(Styles.get_label_style(size="normal"))
        grid.addWidget(fps_label, row, 0)
        
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(10, 60)
        self.fps_spin.setValue(self.config.get("robot", {}).get("fps", 30))
        self.fps_spin.setStyleSheet(Styles.get_spinbox_style())
        grid.addWidget(self.fps_spin, row, 1)
        row += 1
        
        # === CAMERA SETTINGS ===
        camera_header = QLabel("Cameras")
        camera_header.setStyleSheet(Styles.get_label_style(size="large", bold=True))
        grid.addWidget(camera_header, row, 0, 1, 2)
        row += 1
        
        # Front Camera
        front_cam_label = QLabel("Front Camera:")
        front_cam_label.setStyleSheet(Styles.get_label_style(size="normal"))
        grid.addWidget(front_cam_label, row, 0)
        
        self.front_cam_spin = QSpinBox()
        self.front_cam_spin.setRange(-1, 10)
        self.front_cam_spin.setSpecialValueText("Disabled")
        front_cam_idx = self.config.get("cameras", {}).get("front", {}).get("index_or_path", 0)
        self.front_cam_spin.setValue(front_cam_idx if isinstance(front_cam_idx, int) else 0)
        self.front_cam_spin.setStyleSheet(Styles.get_spinbox_style())
        grid.addWidget(self.front_cam_spin, row, 1)
        row += 1
        
        # === CONTROL SETTINGS ===
        control_header = QLabel("Control")
        control_header.setStyleSheet(Styles.get_label_style(size="large", bold=True))
        grid.addWidget(control_header, row, 0, 1, 2)
        row += 1
        
        # Episodes
        episodes_label = QLabel("Episodes:")
        episodes_label.setStyleSheet(Styles.get_label_style(size="normal"))
        grid.addWidget(episodes_label, row, 0)
        
        self.episodes_spin = QSpinBox()
        self.episodes_spin.setRange(1, 999)
        self.episodes_spin.setValue(self.config.get("control", {}).get("num_episodes", 3))
        self.episodes_spin.setStyleSheet(Styles.get_spinbox_style())
        grid.addWidget(self.episodes_spin, row, 1)
        row += 1
        
        # Episode Time
        time_label = QLabel("Episode Time (s):")
        time_label.setStyleSheet(Styles.get_label_style(size="normal"))
        grid.addWidget(time_label, row, 0)
        
        self.episode_time_spin = QSpinBox()
        self.episode_time_spin.setRange(5, 300)
        self.episode_time_spin.setValue(self.config.get("control", {}).get("episode_time_s", 25))
        self.episode_time_spin.setStyleSheet(Styles.get_spinbox_style())
        grid.addWidget(self.episode_time_spin, row, 1)
        row += 1
        
        panel_layout.addLayout(grid)
        panel_layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(Styles.get_large_button(Colors.BG_LIGHT, Colors.BG_MEDIUM))
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("💾 Save")
        save_btn.setStyleSheet(Styles.get_large_button(Colors.SUCCESS, Colors.SUCCESS_HOVER))
        save_btn.clicked.connect(self.save_and_close)
        button_layout.addWidget(save_btn)
        
        panel_layout.addLayout(button_layout)
    
    def populate_ports(self):
        """Auto-detect and populate serial ports"""
        self.port_combo.clear()
        
        # Try to auto-detect ports
        detected_ports = []
        
        # Check common Linux serial ports
        for port_pattern in ["/dev/ttyACM*", "/dev/ttyUSB*"]:
            import glob
            detected_ports.extend(glob.glob(port_pattern))
        
        # Try using lerobot-find-port if available
        try:
            result = subprocess.run(
                ["lerobot-find-port"],
                capture_output=True,
                text=True,
                timeout=5
            )
            # Parse output for ports
            for line in result.stdout.split('\n'):
                if '/dev/tty' in line:
                    # Extract port from line
                    parts = line.split()
                    for part in parts:
                        if part.startswith('/dev/tty'):
                            if part not in detected_ports:
                                detected_ports.append(part)
        except:
            pass
        
        # Add detected ports
        if detected_ports:
            for port in sorted(detected_ports):
                self.port_combo.addItem(port)
        
        # Add current configured port if not in list
        current_port = self.config.get("robot", {}).get("port", "")
        if current_port and current_port not in detected_ports:
            self.port_combo.addItem(current_port)
        
        # Add manual options
        self.port_combo.addItem("/dev/ttyACM0")
        self.port_combo.addItem("/dev/ttyACM1")
        self.port_combo.addItem("/dev/ttyUSB0")
        
        # Select current port
        index = self.port_combo.findText(current_port)
        if index >= 0:
            self.port_combo.setCurrentIndex(index)
    
    def save_and_close(self):
        """Save settings and close"""
        # Update config
        self.config["robot"]["port"] = self.port_combo.currentText()
        self.config["robot"]["fps"] = self.fps_spin.value()
        
        self.config["cameras"]["front"]["index_or_path"] = self.front_cam_spin.value()
        
        self.config["control"]["num_episodes"] = self.episodes_spin.value()
        self.config["control"]["episode_time_s"] = self.episode_time_spin.value()
        
        # Accept dialog
        self.accept()
    
    def get_config(self):
        """Get updated configuration"""
        return self.config


