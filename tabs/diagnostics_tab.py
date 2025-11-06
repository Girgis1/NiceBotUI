"""
Diagnostics Tab - Real-time motor diagnostics in a compact table view
"""

import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QRadioButton, QButtonGroup,
    QComboBox, QHeaderView, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont


class DiagnosticsTab(QWidget):
    """Real-time motor diagnostics with compact table view"""
    
    status_changed = Signal(str)  # Emit status messages
    
    # Thresholds for color coding
    TEMP_WARNING = 45  # °C
    TEMP_CRITICAL = 60  # °C
    LOAD_WARNING = 80  # %
    LOAD_CRITICAL = 95  # %
    VOLTAGE_MIN = 11.0  # V
    VOLTAGE_MAX = 13.0  # V
    
    MOTOR_NAMES = [
        "Shoulder Pan",
        "Shoulder Lift", 
        "Elbow Flex",
        "Wrist Flex",
        "Wrist Roll",
        "Gripper"
    ]
    
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.motor_controller = None
        self.current_arm_index = 0
        self.is_connected = False
        
        self.init_ui()
        
        # Setup auto-refresh timer (0.2s = 5 Hz)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_data)
        
        # Auto-connect on startup
        QTimer.singleShot(500, self.connect_motors)
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        
        # ========== HEADER ROW (Simplified) ==========
        header_row = QHBoxLayout()
        
        title = QLabel("🔧 Motor Diagnostics - Real-time (5 Hz)")
        title.setStyleSheet("color: #4CAF50; font-size: 16px; font-weight: bold;")
        header_row.addWidget(title)
        
        header_row.addStretch()
        
        # Arm selector
        arm_label = QLabel("Arm:")
        arm_label.setStyleSheet("color: #e0e0e0; font-size: 15px; font-weight: bold;")
        header_row.addWidget(arm_label)
        
        self.arm_group = QButtonGroup(self)
        
        self.arm1_radio = QRadioButton("Arm 1")
        self.arm1_radio.setChecked(True)
        self.arm1_radio.setMinimumHeight(35)
        self.arm1_radio.setStyleSheet("""
            QRadioButton {
                color: #e0e0e0;
                font-size: 15px;
                font-weight: bold;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 20px;
                height: 20px;
                border: 2px solid #4CAF50;
                border-radius: 10px;
                background-color: #2d2d2d;
            }
            QRadioButton::indicator:checked {
                background-color: #4CAF50;
                border: 3px solid #2E7D32;
            }
        """)
        self.arm1_radio.toggled.connect(lambda checked: self.on_arm_changed(0) if checked else None)
        self.arm_group.addButton(self.arm1_radio)
        header_row.addWidget(self.arm1_radio)
        
        self.arm2_radio = QRadioButton("Arm 2")
        self.arm2_radio.setMinimumHeight(35)
        self.arm2_radio.setStyleSheet("""
            QRadioButton {
                color: #e0e0e0;
                font-size: 15px;
                font-weight: bold;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 20px;
                height: 20px;
                border: 2px solid #4CAF50;
                border-radius: 10px;
                background-color: #2d2d2d;
            }
            QRadioButton::indicator:checked {
                background-color: #4CAF50;
                border: 3px solid #2E7D32;
            }
        """)
        self.arm2_radio.toggled.connect(lambda checked: self.on_arm_changed(1) if checked else None)
        self.arm_group.addButton(self.arm2_radio)
        header_row.addWidget(self.arm2_radio)
        
        layout.addLayout(header_row)
        
        # ========== DIAGNOSTICS TABLE (Maximized) ==========
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "Motor", "Position", "Goal", "Velocity", "Load", 
            "Temp", "Current", "Voltage", "Moving"
        ])
        self.table.setRowCount(6)
        
        # Style the table
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                gridline-color: #444444;
                font-size: 13px;
            }
            QTableWidget::item {
                padding: 8px;
                color: #e0e0e0;
            }
            QHeaderView::section {
                background-color: #3a3a3a;
                color: #4CAF50;
                padding: 8px;
                border: none;
                border-bottom: 2px solid #4CAF50;
                font-weight: bold;
                font-size: 13px;
            }
        """)
        
        # Set column widths
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Motor name
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # Position
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Goal
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Velocity
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Load
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Temp
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Current
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)  # Voltage
        header.setSectionResizeMode(8, QHeaderView.ResizeToContents)  # Moving
        
        # Populate motor names
        for row, name in enumerate(self.MOTOR_NAMES):
            item = QTableWidgetItem(f"{row + 1}. {name}")
            item.setFont(QFont("", -1, QFont.Bold))
            self.table.setItem(row, 0, item)
        
        # Fill with placeholder data
        self.clear_table_data()
        
        # Make table expand to fill available space
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        layout.addWidget(self.table, stretch=1)  # Give it a stretch factor
    
    def clear_table_data(self):
        """Fill table with placeholder data"""
        for row in range(6):
            for col in range(1, 9):
                item = QTableWidgetItem("--")
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)
    
    def on_arm_changed(self, arm_index: int):
        """Handle arm selection change"""
        if arm_index == self.current_arm_index:
            return
        
        was_connected = self.is_connected
        
        # Disconnect current arm
        if self.is_connected:
            self.disconnect_motors()
        
        self.current_arm_index = arm_index
        
        # Reconnect to new arm if we were connected
        if was_connected:
            self.connect_motors()
    
    def connect_motors(self):
        """Connect to motor bus and start auto-refresh at 0.2s (5 Hz)"""
        try:
            from utils.motor_controller import MotorController
            
            self.motor_controller = MotorController(self.config, arm_index=self.current_arm_index)
            
            if not self.motor_controller.connect():
                self.status_changed.emit(f"❌ Failed to connect to Arm {self.current_arm_index + 1}")
                self.motor_controller = None
                return
            
            self.is_connected = True
            
            # Start auto-refresh at 200ms (0.2s = 5 Hz)
            self.refresh_timer.start(200)
            
            # Do initial refresh
            self.refresh_data()
            
            self.status_changed.emit(f"✓ Connected to Arm {self.current_arm_index + 1}")
            
        except Exception as e:
            self.status_changed.emit(f"❌ Connection error: {str(e)}")
            self.motor_controller = None
    
    def disconnect_motors(self):
        """Disconnect from motor bus"""
        self.refresh_timer.stop()
        
        if self.motor_controller:
            self.motor_controller.disconnect()
            self.motor_controller = None
        
        self.is_connected = False
        
        # Clear table
        self.clear_table_data()
        
        self.status_changed.emit(f"Disconnected from Arm {self.current_arm_index + 1}")
    
    def refresh_data(self):
        """Read and display current motor diagnostics"""
        if not self.is_connected or not self.motor_controller:
            return
        
        try:
            bus = self.motor_controller.bus
            if not bus:
                return
            
            # Read all diagnostic data for all motors
            motor_data = []
            for idx, name in enumerate(self.motor_controller.motor_names):
                try:
                    data = {
                        'position': int(bus.read("Present_Position", name, normalize=False)),
                        'goal': int(bus.read("Goal_Position", name, normalize=False)),
                        'velocity': int(bus.read("Present_Velocity", name, normalize=False)),
                        'load': int(bus.read("Present_Load", name, normalize=False)),
                        'temperature': int(bus.read("Present_Temperature", name, normalize=False)),
                        'current': int(bus.read("Present_Current", name, normalize=False)),
                        'voltage': int(bus.read("Present_Voltage", name, normalize=False)),
                        'moving': int(bus.read("Moving", name, normalize=False))
                    }
                    motor_data.append(data)
                except Exception as e:
                    print(f"Error reading motor {idx + 1}: {e}")
                    motor_data.append(None)
            
            # Update table
            self.update_table(motor_data)
            
        except Exception as e:
            self.status_changed.emit(f"❌ Error reading data: {str(e)}")
    
    def update_table(self, motor_data: list):
        """Update table with motor data and color coding"""
        for row, data in enumerate(motor_data):
            if data is None:
                for col in range(1, 9):
                    item = self.table.item(row, col)
                    item.setText("ERROR")
                    item.setBackground(QColor("#f44336"))
                continue
            
            # Position
            pos_item = self.table.item(row, 1)
            pos_item.setText(f"{data['position']}/4095")
            pos_item.setBackground(QColor("#2d2d2d"))
            
            # Goal
            goal_item = self.table.item(row, 2)
            goal_item.setText(str(data['goal']))
            goal_item.setBackground(QColor("#2d2d2d"))
            
            # Velocity
            vel_item = self.table.item(row, 3)
            vel_item.setText(str(data['velocity']))
            vel_item.setBackground(QColor("#2d2d2d"))
            
            # Load (with color coding)
            load_item = self.table.item(row, 4)
            load_percent = abs(data['load']) / 10  # Rough conversion to percentage
            load_item.setText(f"{int(load_percent)}%")
            if load_percent > self.LOAD_CRITICAL:
                load_item.setBackground(QColor("#f44336"))  # Red
            elif load_percent > self.LOAD_WARNING:
                load_item.setBackground(QColor("#FF9800"))  # Orange
            else:
                load_item.setBackground(QColor("#4CAF50"))  # Green
            
            # Temperature (with color coding)
            temp_item = self.table.item(row, 5)
            temp = data['temperature']
            temp_item.setText(f"{temp}°C")
            if temp > self.TEMP_CRITICAL:
                temp_item.setBackground(QColor("#f44336"))  # Red
            elif temp > self.TEMP_WARNING:
                temp_item.setBackground(QColor("#FF9800"))  # Orange
            else:
                temp_item.setBackground(QColor("#4CAF50"))  # Green
            
            # Current
            curr_item = self.table.item(row, 6)
            curr_item.setText(f"{data['current']}mA")
            curr_item.setBackground(QColor("#2d2d2d"))
            
            # Voltage (with color coding)
            volt_item = self.table.item(row, 7)
            voltage = data['voltage'] / 10.0  # Convert to volts
            volt_item.setText(f"{voltage:.1f}V")
            if voltage < self.VOLTAGE_MIN or voltage > self.VOLTAGE_MAX:
                volt_item.setBackground(QColor("#FF9800"))  # Orange
            else:
                volt_item.setBackground(QColor("#4CAF50"))  # Green
            
            # Moving
            move_item = self.table.item(row, 8)
            is_moving = data['moving'] == 1
            move_item.setText("Yes" if is_moving else "No")
            move_item.setBackground(QColor("#2196F3") if is_moving else QColor("#2d2d2d"))
    
    def cleanup(self):
        """Cleanup when tab is closed"""
        self.refresh_timer.stop()
        if self.motor_controller:
            self.motor_controller.disconnect()

