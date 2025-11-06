"""
Diagnostics Tab - Real-time motor diagnostics in a compact table view
"""

import json
from datetime import datetime
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QRadioButton, QButtonGroup,
    QComboBox, QHeaderView, QFrame
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
        self.last_update_time = None
        self.logging_enabled = False
        self.log_data = []
        
        self.init_ui()
        
        # Setup auto-refresh timer
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_data)
        # Don't start timer yet - wait for manual connection
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        
        # ========== HEADER ROW ==========
        header_row = QHBoxLayout()
        
        title = QLabel("🔧 Motor Diagnostics")
        title.setStyleSheet("color: #4CAF50; font-size: 16px; font-weight: bold;")
        header_row.addWidget(title)
        
        header_row.addStretch()
        
        # Arm selector
        arm_label = QLabel("Arm:")
        arm_label.setStyleSheet("color: #e0e0e0; font-size: 14px;")
        header_row.addWidget(arm_label)
        
        self.arm_group = QButtonGroup(self)
        
        self.arm1_radio = QRadioButton("Arm 1")
        self.arm1_radio.setChecked(True)
        self.arm1_radio.setStyleSheet("color: #e0e0e0; font-size: 14px;")
        self.arm1_radio.toggled.connect(lambda checked: self.on_arm_changed(0) if checked else None)
        self.arm_group.addButton(self.arm1_radio)
        header_row.addWidget(self.arm1_radio)
        
        self.arm2_radio = QRadioButton("Arm 2")
        self.arm2_radio.setStyleSheet("color: #e0e0e0; font-size: 14px;")
        self.arm2_radio.toggled.connect(lambda checked: self.on_arm_changed(1) if checked else None)
        self.arm_group.addButton(self.arm2_radio)
        header_row.addWidget(self.arm2_radio)
        
        # Refresh rate selector
        refresh_label = QLabel("Refresh:")
        refresh_label.setStyleSheet("color: #e0e0e0; font-size: 14px;")
        header_row.addWidget(refresh_label)
        
        self.refresh_combo = QComboBox()
        self.refresh_combo.addItems(["Manual", "0.5s", "1.0s", "2.0s"])
        self.refresh_combo.setCurrentText("1.0s")
        self.refresh_combo.setStyleSheet("""
            QComboBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 13px;
                min-width: 80px;
            }
        """)
        self.refresh_combo.currentTextChanged.connect(self.on_refresh_rate_changed)
        header_row.addWidget(self.refresh_combo)
        
        layout.addLayout(header_row)
        
        # ========== CONNECTION STATUS ==========
        status_frame = QFrame()
        status_frame.setStyleSheet("""
            QFrame {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(8, 4, 8, 4)
        
        self.connection_label = QLabel("● Disconnected")
        self.connection_label.setStyleSheet("color: #f44336; font-size: 13px; font-weight: bold;")
        status_layout.addWidget(self.connection_label)
        
        self.port_label = QLabel("")
        self.port_label.setStyleSheet("color: #999999; font-size: 13px;")
        status_layout.addWidget(self.port_label)
        
        status_layout.addStretch()
        
        self.last_update_label = QLabel("Last: Never")
        self.last_update_label.setStyleSheet("color: #999999; font-size: 13px;")
        status_layout.addWidget(self.last_update_label)
        
        layout.addWidget(status_frame)
        
        # ========== DIAGNOSTICS TABLE ==========
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
        
        layout.addWidget(self.table)
        
        # ========== SUMMARY BAR ==========
        summary_frame = QFrame()
        summary_frame.setStyleSheet("""
            QFrame {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        summary_layout = QHBoxLayout(summary_frame)
        summary_layout.setContentsMargins(8, 4, 8, 4)
        
        self.summary_label = QLabel("Summary: Not connected")
        self.summary_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        summary_layout.addWidget(self.summary_label)
        
        summary_layout.addStretch()
        
        self.status_indicator = QLabel("Status: ⚪ Idle")
        self.status_indicator.setStyleSheet("color: #999999; font-size: 13px; font-weight: bold;")
        summary_layout.addWidget(self.status_indicator)
        
        layout.addWidget(summary_frame)
        
        # ========== CONTROL BUTTONS ==========
        button_row = QHBoxLayout()
        
        self.connect_btn = QPushButton("🔌 Connect")
        self.connect_btn.setFixedHeight(35)
        self.connect_btn.setStyleSheet(self.get_button_style("#4CAF50", "#388E3C"))
        self.connect_btn.clicked.connect(self.toggle_connection)
        button_row.addWidget(self.connect_btn)
        
        self.refresh_btn = QPushButton("🔄 Refresh Now")
        self.refresh_btn.setFixedHeight(35)
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setStyleSheet(self.get_button_style("#2196F3", "#1976D2"))
        self.refresh_btn.clicked.connect(self.refresh_data)
        button_row.addWidget(self.refresh_btn)
        
        self.log_btn = QPushButton("📊 Start Logging")
        self.log_btn.setFixedHeight(35)
        self.log_btn.setEnabled(False)
        self.log_btn.setStyleSheet(self.get_button_style("#FF9800", "#F57C00"))
        self.log_btn.clicked.connect(self.toggle_logging)
        button_row.addWidget(self.log_btn)
        
        self.export_btn = QPushButton("💾 Export CSV")
        self.export_btn.setFixedHeight(35)
        self.export_btn.setEnabled(False)
        self.export_btn.setStyleSheet(self.get_button_style("#9C27B0", "#7B1FA2"))
        self.export_btn.clicked.connect(self.export_data)
        button_row.addWidget(self.export_btn)
        
        button_row.addStretch()
        
        layout.addLayout(button_row)
    
    def get_button_style(self, color: str, hover_color: str) -> str:
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {color};
            }}
            QPushButton:disabled {{
                background-color: #555555;
                color: #999999;
            }}
        """
    
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
    
    def on_refresh_rate_changed(self, rate_text: str):
        """Handle refresh rate change"""
        self.refresh_timer.stop()
        
        if rate_text == "Manual":
            return
        
        # Extract seconds from text
        rate_ms = int(float(rate_text.replace("s", "")) * 1000)
        
        if self.is_connected:
            self.refresh_timer.start(rate_ms)
    
    def toggle_connection(self):
        """Connect or disconnect from motors"""
        if self.is_connected:
            self.disconnect_motors()
        else:
            self.connect_motors()
    
    def connect_motors(self):
        """Connect to motor bus"""
        try:
            from utils.motor_controller import MotorController
            
            self.motor_controller = MotorController(self.config, arm_index=self.current_arm_index)
            
            if not self.motor_controller.connect():
                self.status_changed.emit(f"❌ Failed to connect to Arm {self.current_arm_index + 1}")
                self.motor_controller = None
                return
            
            self.is_connected = True
            port = self.motor_controller.port
            
            # Update UI
            self.connection_label.setText("● Connected")
            self.connection_label.setStyleSheet("color: #4CAF50; font-size: 13px; font-weight: bold;")
            self.port_label.setText(port)
            self.port_label.setStyleSheet("color: #4CAF50; font-size: 13px;")
            self.connect_btn.setText("🔌 Disconnect")
            self.refresh_btn.setEnabled(True)
            self.log_btn.setEnabled(True)
            self.export_btn.setEnabled(True)
            
            # Start auto-refresh if enabled
            rate_text = self.refresh_combo.currentText()
            if rate_text != "Manual":
                rate_ms = int(float(rate_text.replace("s", "")) * 1000)
                self.refresh_timer.start(rate_ms)
            
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
        
        # Update UI
        self.connection_label.setText("● Disconnected")
        self.connection_label.setStyleSheet("color: #f44336; font-size: 13px; font-weight: bold;")
        self.port_label.setText("")
        self.connect_btn.setText("🔌 Connect")
        self.refresh_btn.setEnabled(False)
        self.log_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        
        self.clear_table_data()
        self.summary_label.setText("Summary: Disconnected")
        self.status_indicator.setText("Status: ⚪ Idle")
        self.status_indicator.setStyleSheet("color: #999999; font-size: 13px; font-weight: bold;")
        
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
            
            # Update summary
            self.update_summary(motor_data)
            
            # Update last update time
            self.last_update_time = datetime.now()
            self.last_update_label.setText(f"Last: {self.last_update_time.strftime('%H:%M:%S')}")
            
            # Log data if enabled
            if self.logging_enabled:
                self.log_data.append({
                    'timestamp': self.last_update_time.isoformat(),
                    'arm': self.current_arm_index + 1,
                    'motors': motor_data
                })
            
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
    
    def update_summary(self, motor_data: list):
        """Update summary bar with system-wide metrics"""
        valid_data = [d for d in motor_data if d is not None]
        
        if not valid_data:
            self.summary_label.setText("Summary: No data")
            self.status_indicator.setText("Status: ❌ Error")
            self.status_indicator.setStyleSheet("color: #f44336; font-size: 13px; font-weight: bold;")
            return
        
        # Calculate metrics
        max_temp = max(d['temperature'] for d in valid_data)
        total_current = sum(d['current'] for d in valid_data)
        avg_voltage = sum(d['voltage'] for d in valid_data) / len(valid_data) / 10.0
        
        # Determine status
        if max_temp > self.TEMP_CRITICAL:
            status = "🔴 CRITICAL"
            status_color = "#f44336"
        elif max_temp > self.TEMP_WARNING:
            status = "🟡 WARNING"
            status_color = "#FF9800"
        else:
            status = "✓ OK"
            status_color = "#4CAF50"
        
        self.summary_label.setText(
            f"Summary: Max Temp {max_temp}°C │ Total Current {total_current}mA │ "
            f"Avg Voltage {avg_voltage:.1f}V"
        )
        
        self.status_indicator.setText(f"Status: {status}")
        self.status_indicator.setStyleSheet(f"color: {status_color}; font-size: 13px; font-weight: bold;")
    
    def toggle_logging(self):
        """Toggle data logging"""
        self.logging_enabled = not self.logging_enabled
        
        if self.logging_enabled:
            self.log_btn.setText("📊 Stop Logging")
            self.log_data = []
            self.status_changed.emit("Started logging diagnostics data")
        else:
            self.log_btn.setText("📊 Start Logging")
            self.status_changed.emit(f"Stopped logging ({len(self.log_data)} samples)")
    
    def export_data(self):
        """Export diagnostic data to CSV"""
        if not self.log_data:
            self.status_changed.emit("⚠️ No data to export. Start logging first.")
            return
        
        try:
            # Create logs directory
            logs_dir = Path("logs/diagnostics")
            logs_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            arm_num = self.current_arm_index + 1
            filename = logs_dir / f"diagnostics_arm{arm_num}_{timestamp}.csv"
            
            # Write CSV
            with open(filename, 'w') as f:
                # Header
                f.write("Timestamp,Arm,Motor,Position,Goal,Velocity,Load,Temperature,Current,Voltage,Moving\n")
                
                # Data
                for entry in self.log_data:
                    ts = entry['timestamp']
                    arm = entry['arm']
                    for idx, motor_data in enumerate(entry['motors']):
                        if motor_data:
                            f.write(f"{ts},{arm},{idx+1},{motor_data['position']},{motor_data['goal']},"
                                   f"{motor_data['velocity']},{motor_data['load']},{motor_data['temperature']},"
                                   f"{motor_data['current']},{motor_data['voltage']},{motor_data['moving']}\n")
            
            self.status_changed.emit(f"✓ Exported {len(self.log_data)} samples to {filename}")
            
        except Exception as e:
            self.status_changed.emit(f"❌ Export failed: {str(e)}")
    
    def cleanup(self):
        """Cleanup when tab is closed"""
        self.refresh_timer.stop()
        if self.motor_controller:
            self.motor_controller.disconnect()

