"""
Multi-Arm UI Widgets - Reusable components for single/dual arm configuration
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QComboBox, QRadioButton, QButtonGroup, QFrame, QSpinBox
)
from PySide6.QtCore import Qt, Signal


class ArmModeSelector(QWidget):
    """Radio button selector for Single vs Dual arm mode"""
    
    mode_changed = Signal(str)  # Emits "single" or "dual"
    
    def __init__(self, current_mode="single", parent=None):
        super().__init__(parent)
        self.init_ui(current_mode)
    
    def init_ui(self, current_mode):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        # Button group for mutual exclusivity
        self.button_group = QButtonGroup(self)
        
        # Single arm radio
        self.single_radio = QRadioButton("Single Arm")
        self.single_radio.setStyleSheet("""
            QRadioButton {
                color: #e0e0e0;
                font-size: 14px;
                font-weight: bold;
            }
            QRadioButton::indicator {
                width: 20px;
                height: 20px;
            }
            QRadioButton::indicator:unchecked {
                border: 2px solid #707070;
                border-radius: 10px;
                background-color: #3a3a3a;
            }
            QRadioButton::indicator:checked {
                border: 2px solid #4CAF50;
                border-radius: 10px;
                background-color: #4CAF50;
            }
        """)
        self.button_group.addButton(self.single_radio)
        layout.addWidget(self.single_radio)
        
        # Dual arms radio
        self.dual_radio = QRadioButton("Dual Arms")
        self.dual_radio.setStyleSheet(self.single_radio.styleSheet())
        self.button_group.addButton(self.dual_radio)
        layout.addWidget(self.dual_radio)
        
        layout.addStretch()
        
        # Set initial state
        if current_mode == "dual":
            self.dual_radio.setChecked(True)
        else:
            self.single_radio.setChecked(True)
        
        # Connect signals
        self.single_radio.toggled.connect(lambda checked: self.mode_changed.emit("single") if checked else None)
        self.dual_radio.toggled.connect(lambda checked: self.mode_changed.emit("dual") if checked else None)
    
    def get_mode(self):
        return "dual" if self.dual_radio.isChecked() else "single"
    
    def set_mode(self, mode):
        if mode == "dual":
            self.dual_radio.setChecked(True)
        else:
            self.single_radio.setChecked(True)


class ArmConfigSection(QFrame):
    """Configuration section for a single arm (port, calibration ID, control buttons)"""
    
    home_clicked = Signal()
    set_home_clicked = Signal()
    calibrate_clicked = Signal()
    
    def __init__(self, arm_name="", show_controls=True, parent=None):
        super().__init__(parent)
        self.arm_name = arm_name
        self.show_controls = show_controls
        self.init_ui()
    
    def init_ui(self):
        # Frame styling
        self.setFrameShape(QFrame.Box)
        self.setStyleSheet("""
            QFrame {
                background-color: #353535;
                border: 2px solid #606060;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Title if arm name provided
        if self.arm_name:
            title = QLabel(f"{'●' if 'Left' in self.arm_name else '●'} {self.arm_name}")
            title.setStyleSheet(f"""
                QLabel {{
                    color: {'#2196F3' if 'Left' in self.arm_name else '#FF9800'};
                    font-size: 14px;
                    font-weight: bold;
                }}
            """)
            layout.addWidget(title)
        
        # Port row
        port_row = QHBoxLayout()
        port_row.setSpacing(6)
        
        port_label = QLabel("Port:")
        port_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        port_label.setFixedWidth(60)
        port_row.addWidget(port_label)
        
        self.port_edit = QLineEdit()
        self.port_edit.setPlaceholderText("/dev/ttyACM0")
        self.port_edit.setFixedHeight(40)
        self.port_edit.setStyleSheet("""
            QLineEdit {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 6px;
                padding: 6px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #4CAF50;
            }
        """)
        port_row.addWidget(self.port_edit)
        layout.addLayout(port_row)
        
        # Calibration ID row
        id_row = QHBoxLayout()
        id_row.setSpacing(6)
        
        id_label = QLabel("Calib ID:")
        id_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        id_label.setFixedWidth(60)
        id_row.addWidget(id_label)
        
        self.id_combo = QComboBox()
        self.id_combo.setEditable(True)
        self.id_combo.setFixedHeight(40)
        self.id_combo.setStyleSheet("""
            QComboBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 6px;
                padding: 6px;
                font-size: 13px;
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
        
        # Control buttons (if enabled)
        if self.show_controls:
            btn_row = QHBoxLayout()
            btn_row.setSpacing(6)
            
            self.home_btn = QPushButton("🏠 Home")
            self.home_btn.setFixedHeight(38)
            self.home_btn.setStyleSheet(self._get_button_style("#2196F3", "#1976D2"))
            self.home_btn.clicked.connect(self.home_clicked.emit)
            btn_row.addWidget(self.home_btn)
            
            self.set_home_btn = QPushButton("Set Home")
            self.set_home_btn.setFixedHeight(38)
            self.set_home_btn.setStyleSheet(self._get_button_style("#4CAF50", "#388E3C"))
            self.set_home_btn.clicked.connect(self.set_home_clicked.emit)
            btn_row.addWidget(self.set_home_btn)
            
            self.calibrate_btn = QPushButton("⚙️ Calib")
            self.calibrate_btn.setFixedHeight(38)
            self.calibrate_btn.setStyleSheet(self._get_button_style("#9C27B0", "#7B1FA2"))
            self.calibrate_btn.clicked.connect(self.calibrate_clicked.emit)
            btn_row.addWidget(self.calibrate_btn)
            
            layout.addLayout(btn_row)
    
    def _get_button_style(self, color1, color2):
        return f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 {color1}, stop:1 {color2});
                color: white;
                border: 2px solid {color2};
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
                padding: 6px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 {color2}, stop:1 {color1});
            }}
            QPushButton:pressed {{
                background: {color2};
            }}
        """
    
    def get_port(self):
        return self.port_edit.text()
    
    def set_port(self, port):
        self.port_edit.setText(port)
    
    def get_id(self):
        return self.id_combo.currentText()
    
    def set_id(self, calib_id):
        self.id_combo.setCurrentText(calib_id)
    
    def populate_calibration_ids(self, ids):
        """Populate the calibration ID dropdown"""
        self.id_combo.clear()
        if ids:
            self.id_combo.addItems(ids)
        else:
            self.id_combo.addItem("(no calibrations found)")

