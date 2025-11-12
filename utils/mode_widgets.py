"""
Solo/Bimanual Mode Configuration Widgets
Simpler replacement for the add/remove arms system
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QComboBox, QRadioButton, QButtonGroup, QFrame, QSpinBox, QCheckBox
)
from PySide6.QtCore import Qt, Signal


class ModeSelector(QWidget):
    """Radio button selector for Solo/Bimanual mode"""
    mode_changed = Signal(str)  # Emits "solo" or "bimanual"
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        
        label = QLabel("Mode:")
        label.setStyleSheet("color: #e0e0e0; font-size: 16px; font-weight: bold;")
        layout.addWidget(label)
        
        self.button_group = QButtonGroup(self)
        
        self.solo_radio = QRadioButton("👤 Solo")
        self.solo_radio.setMinimumHeight(50)
        self.solo_radio.setStyleSheet("""
            QRadioButton {
                color: #e0e0e0;
                font-size: 16px;
                font-weight: bold;
                spacing: 12px;
                padding: 8px;
            }
            QRadioButton::indicator {
                width: 30px;
                height: 30px;
                border: 3px solid #4CAF50;
                border-radius: 16px;
                background-color: #2d2d2d;
            }
            QRadioButton::indicator:checked {
                background-color: #4CAF50;
                border: 4px solid #2E7D32;
            }
            QRadioButton::indicator:hover {
                border-color: #66BB6A;
            }
        """)
        self.solo_radio.setChecked(True)
        self.button_group.addButton(self.solo_radio)
        layout.addWidget(self.solo_radio)
        
        self.bimanual_radio = QRadioButton("👥 Bimanual")
        self.bimanual_radio.setMinimumHeight(50)
        self.bimanual_radio.setStyleSheet("""
            QRadioButton {
                color: #e0e0e0;
                font-size: 16px;
                font-weight: bold;
                spacing: 12px;
                padding: 8px;
            }
            QRadioButton::indicator {
                width: 30px;
                height: 30px;
                border: 3px solid #4CAF50;
                border-radius: 16px;
                background-color: #2d2d2d;
            }
            QRadioButton::indicator:checked {
                background-color: #4CAF50;
                border: 4px solid #2E7D32;
            }
            QRadioButton::indicator:hover {
                border-color: #66BB6A;
            }
        """)
        self.button_group.addButton(self.bimanual_radio)
        layout.addWidget(self.bimanual_radio)
        
        layout.addStretch()
        
        # Connect signals
        self.solo_radio.toggled.connect(self._on_mode_changed)
    
    def _on_mode_changed(self):
        if self.solo_radio.isChecked():
            self.mode_changed.emit("solo")
        else:
            self.mode_changed.emit("bimanual")
    
    def get_mode(self) -> str:
        return "solo" if self.solo_radio.isChecked() else "bimanual"
    
    def set_mode(self, mode: str):
        if mode == "solo":
            self.solo_radio.setChecked(True)
        else:
            self.bimanual_radio.setChecked(True)


class SingleArmConfig(QFrame):
    """Configuration widget for a single arm"""
    home_clicked = Signal()
    set_home_clicked = Signal()
    calibrate_clicked = Signal()
    test_clicked = Signal()
    
    def __init__(self, arm_name="Arm 1", show_home_controls=True, parent=None):
        super().__init__(parent)
        self.arm_name = arm_name
        self.show_home_controls = show_home_controls
        self.init_ui()
    
    def init_ui(self):
        self.setFrameStyle(QFrame.Box | QFrame.Raised)
        self.setStyleSheet("""
            SingleArmConfig {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # Arm name label
        name_label = QLabel(f"🤖 {self.arm_name}")
        name_label.setStyleSheet("color: #4CAF50; font-size: 15px; font-weight: bold;")
        layout.addWidget(name_label)
        
        # Port dropdown
        port_row = QHBoxLayout()
        port_label = QLabel("Port:")
        port_label.setStyleSheet("color: #e0e0e0; font-size: 14px; min-width: 100px;")
        port_row.addWidget(port_label)
        
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.addItems(["ACM0", "ACM1", "ACM2", "ACM3", "ACM4", "ACM5"])
        self.port_combo.setStyleSheet("""
            QComboBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
            }
            QComboBox:focus {
                border-color: #4CAF50;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #ffffff;
                margin-right: 10px;
            }
            QComboBox QAbstractItemView {
                background-color: #505050;
                color: #ffffff;
                selection-background-color: #4CAF50;
                border: 2px solid #707070;
            }
        """)
        port_row.addWidget(self.port_combo)
        layout.addLayout(port_row)
        
        # Calibration ID dropdown
        id_row = QHBoxLayout()
        id_label = QLabel("Calib ID:")
        id_label.setStyleSheet("color: #e0e0e0; font-size: 14px; min-width: 100px;")
        id_row.addWidget(id_label)
        
        self.id_combo = QComboBox()
        self.id_combo.setEditable(True)
        self._populate_calibration_ids()
        self.id_combo.setStyleSheet("""
            QComboBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
            }
            QComboBox:focus {
                border-color: #4CAF50;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #ffffff;
                margin-right: 10px;
            }
            QComboBox QAbstractItemView {
                background-color: #505050;
                color: #ffffff;
                selection-background-color: #4CAF50;
                border: 2px solid #707070;
            }
        """)
        id_row.addWidget(self.id_combo)
        layout.addLayout(id_row)
        
        # Home positions (only for robot arms, not teleop)
        if self.show_home_controls:
            home_row = QHBoxLayout()
            home_label = QLabel("Home:")
            home_label.setStyleSheet("color: #e0e0e0; font-size: 14px; min-width: 100px;")
            home_row.addWidget(home_label)
            
            self.home_edit = QLineEdit()
            self.home_edit.setPlaceholderText("[2048, 2048, 2048, 2048, 2048, 2048]")
            self.home_edit.setStyleSheet("""
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
                }
            """)
            home_row.addWidget(self.home_edit)
            layout.addLayout(home_row)
            
            # Control buttons
            btn_row = QHBoxLayout()
            
            self.home_btn = QPushButton("🏠 Home")
            self.home_btn.setFixedHeight(35)
            self.home_btn.clicked.connect(self.home_clicked.emit)
            btn_row.addWidget(self.home_btn)
            
            self.set_home_btn = QPushButton("Set Home")
            self.set_home_btn.setFixedHeight(35)
            self.set_home_btn.clicked.connect(self.set_home_clicked.emit)
            btn_row.addWidget(self.set_home_btn)
            
            self.calib_btn = QPushButton("Calibrate")
            self.calib_btn.setFixedHeight(35)
            self.calib_btn.clicked.connect(self.calibrate_clicked.emit)
            btn_row.addWidget(self.calib_btn)

            self.test_btn = QPushButton("Test")
            self.test_btn.setFixedHeight(35)
            self.test_btn.clicked.connect(self.test_clicked.emit)
            btn_row.addWidget(self.test_btn)
            
            layout.addLayout(btn_row)
        else:
            # For teleop arms, only show calibrate button
            btn_row = QHBoxLayout()
            
            self.calib_btn = QPushButton("Calibrate")
            self.calib_btn.setFixedHeight(35)
            self.calib_btn.clicked.connect(self.calibrate_clicked.emit)
            btn_row.addWidget(self.calib_btn)

            self.test_btn = QPushButton("Test")
            self.test_btn.setFixedHeight(35)
            self.test_btn.clicked.connect(self.test_clicked.emit)
            btn_row.addWidget(self.test_btn)
            btn_row.addStretch()
            
            layout.addLayout(btn_row)
    
    def _populate_calibration_ids(self):
        """Load available calibration files from LeRobot cache"""
        from pathlib import Path
        
        self.id_combo.clear()
        found_ids = set()
        
        # Scan both robots and teleoperators directories
        base_dir = Path.home() / ".cache" / "huggingface" / "lerobot" / "calibration"
        
        for subdir in ["robots", "teleoperators"]:
            calib_subdir = base_dir / subdir
            if calib_subdir.exists():
                # Recursively find all .json files
                for json_file in calib_subdir.rglob("*.json"):
                    calib_id = json_file.stem  # Filename without extension
                    found_ids.add(calib_id)
        
        # Add found calibration IDs
        for calib_id in sorted(found_ids):
            self.id_combo.addItem(calib_id)
        
        # Add common defaults if not already present
        for default_id in ["follower_arm", "leader_arm", "follower_arm_2", "leader_arm_2", 
                          "follower_white", "leader_white"]:
            if self.id_combo.findText(default_id) == -1:
                self.id_combo.addItem(default_id)
    
    # Getters and setters
    def get_port(self):
        """Get port in full path format"""
        port_text = self.port_combo.currentText()
        if not port_text.startswith("/dev/"):
            return f"/dev/tty{port_text}"
        return port_text
    
    def set_port(self, port):
        """Set port from full path, display short form"""
        if port.startswith("/dev/tty"):
            short_form = port.replace("/dev/tty", "")
            self.port_combo.setCurrentText(short_form)
        else:
            self.port_combo.setCurrentText(port)
    
    def get_id(self): return self.id_combo.currentText()
    def set_id(self, calib_id): self.id_combo.setCurrentText(calib_id)
    def get_home_positions(self):
        try:
            import json
            return json.loads(self.home_edit.text())
        except:
            return []
    def set_home_positions(self, positions):
        import json
        self.home_edit.setText(json.dumps(positions))
