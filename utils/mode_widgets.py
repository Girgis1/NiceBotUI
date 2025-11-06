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
        label.setStyleSheet("color: #e0e0e0; font-size: 15px; font-weight: bold;")
        layout.addWidget(label)
        
        self.button_group = QButtonGroup(self)
        
        self.solo_radio = QRadioButton("👤 Solo")
        self.solo_radio.setStyleSheet("color: #e0e0e0; font-size: 15px;")
        self.solo_radio.setChecked(True)
        self.button_group.addButton(self.solo_radio)
        layout.addWidget(self.solo_radio)
        
        self.bimanual_radio = QRadioButton("👥 Bimanual")
        self.bimanual_radio.setStyleSheet("color: #e0e0e0; font-size: 15px;")
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
        
        # Port
        port_row = QHBoxLayout()
        port_label = QLabel("Port:")
        port_label.setStyleSheet("color: #e0e0e0; font-size: 14px; min-width: 100px;")
        port_row.addWidget(port_label)
        
        self.port_edit = QLineEdit()
        self.port_edit.setPlaceholderText("/dev/ttyACM0")
        self.port_edit.setStyleSheet("""
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
        port_row.addWidget(self.port_edit)
        layout.addLayout(port_row)
        
        # Calibration ID
        id_row = QHBoxLayout()
        id_label = QLabel("Calib ID:")
        id_label.setStyleSheet("color: #e0e0e0; font-size: 14px; min-width: 100px;")
        id_row.addWidget(id_label)
        
        self.id_edit = QLineEdit()
        self.id_edit.setPlaceholderText("follower_arm")
        self.id_edit.setStyleSheet("""
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
        id_row.addWidget(self.id_edit)
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
            
            # Home velocity
            vel_row = QHBoxLayout()
            vel_label = QLabel("Velocity:")
            vel_label.setStyleSheet("color: #e0e0e0; font-size: 14px; min-width: 100px;")
            vel_row.addWidget(vel_label)
            
            self.vel_spin = QSpinBox()
            self.vel_spin.setRange(50, 2000)
            self.vel_spin.setValue(600)
            self.vel_spin.setButtonSymbols(QSpinBox.NoButtons)
            self.vel_spin.setStyleSheet("""
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
                }
            """)
            vel_row.addWidget(self.vel_spin)
            vel_row.addStretch()
            layout.addLayout(vel_row)
            
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
            
            layout.addLayout(btn_row)
        else:
            # For teleop arms, only show calibrate button
            btn_row = QHBoxLayout()
            
            self.calib_btn = QPushButton("Calibrate")
            self.calib_btn.setFixedHeight(35)
            self.calib_btn.clicked.connect(self.calibrate_clicked.emit)
            btn_row.addWidget(self.calib_btn)
            btn_row.addStretch()
            
            layout.addLayout(btn_row)
    
    # Getters and setters
    def get_port(self): return self.port_edit.text()
    def set_port(self, port): self.port_edit.setText(port)
    def get_id(self): return self.id_edit.text()
    def set_id(self, calib_id): self.id_edit.setText(calib_id)
    def get_home_positions(self):
        try:
            import json
            return json.loads(self.home_edit.text())
        except:
            return []
    def set_home_positions(self, positions):
        import json
        self.home_edit.setText(json.dumps(positions))
    def get_velocity(self): return self.vel_spin.value()
    def set_velocity(self, vel): self.vel_spin.setValue(vel)

