"""
Touch-screen robot teleop control panel.
Based on HIL-SERL keyboard teleop system from LeRobot.

Provides:
- XY movement control (4-way directional)
- Z-axis control (up/down)
- Gripper control (open/close)
- Manual mode (torque toggle - press & hold)
- Speed adjustment
- Live position display
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QFrame
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
import logging


class TouchTeleopPanel(QWidget):
    """Touch-screen teleop control panel for robot arm"""
    
    # Signals
    position_updated = Signal(dict)  # Emits current X/Y/Z position
    torque_changed = Signal(bool)    # Emits torque state (True=enabled)
    
    def __init__(self, motor_controller, config, parent=None):
        super().__init__(parent)
        self.motor_controller = motor_controller
        self.config = config
        
        # State
        self.torque_enabled = True
        self.speed_level = 2  # 1=slow, 2=medium, 3=fast
        self.step_sizes = {
            1: 0.005,  # 0.5mm per press
            2: 0.01,   # 1.0mm per press
            3: 0.02    # 2.0mm per press
        }
        
        # Track all movement buttons for enable/disable
        self.movement_buttons = []
        
        self.init_ui()
        self.setup_position_update_timer()
        
    def init_ui(self):
        """Build the compact 3x3 grid touch panel UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        
        # Header
        header = QLabel("TELEOP")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("""
            QLabel {
                background: #1F2937;
                color: white;
                font-size: 13px;
                font-weight: bold;
                padding: 4px;
                border-radius: 3px;
            }
        """)
        layout.addWidget(header)
        
        # Manual Mode Warning (hidden by default)
        self.manual_mode_warning = QLabel("⚠️ MANUAL MODE ⚠️")
        self.manual_mode_warning.setAlignment(Qt.AlignCenter)
        self.manual_mode_warning.setStyleSheet("""
            QLabel {
                background: #EF4444;
                color: white;
                font-size: 10px;
                font-weight: bold;
                padding: 3px;
                border: 2px solid #991B1B;
                border-radius: 3px;
            }
        """)
        self.manual_mode_warning.setVisible(False)
        layout.addWidget(self.manual_mode_warning)
        
        # Row 1: Manual Mode Button (full width)
        self.manual_mode_btn = QPushButton("🔓 MANUAL MODE")
        self.manual_mode_btn.setFixedHeight(45)
        self.manual_mode_btn.pressed.connect(self.on_torque_disable)
        self.manual_mode_btn.released.connect(self.on_torque_enable)
        self.manual_mode_btn.setStyleSheet(self.get_manual_mode_style(False))
        layout.addWidget(self.manual_mode_btn)
        
        # Main 3x3 Grid
        grid = QGridLayout()
        grid.setSpacing(3)
        
        # Row 1: Z Up | Forward | Z Down
        self.btn_z_up = self.create_grid_button("▲", "#10B981")
        self.btn_z_up.clicked.connect(lambda: self.on_move_delta(0, 0, 1))
        grid.addWidget(self.btn_z_up, 0, 0)
        
        self.btn_forward = self.create_grid_button("↑", "#3B82F6")
        self.btn_forward.clicked.connect(lambda: self.on_move_delta(0, -1, 0))
        grid.addWidget(self.btn_forward, 0, 1)
        
        self.btn_z_down = self.create_grid_button("▼", "#10B981")
        self.btn_z_down.clicked.connect(lambda: self.on_move_delta(0, 0, -1))
        grid.addWidget(self.btn_z_down, 0, 2)
        
        # Row 2: Left | None | Right
        self.btn_left = self.create_grid_button("←", "#3B82F6")
        self.btn_left.clicked.connect(lambda: self.on_move_delta(1, 0, 0))
        grid.addWidget(self.btn_left, 1, 0)
        
        # Center: Empty space
        center_spacer = QLabel()
        center_spacer.setStyleSheet("background: #1F2937; border-radius: 3px;")
        grid.addWidget(center_spacer, 1, 1)
        
        self.btn_right = self.create_grid_button("→", "#3B82F6")
        self.btn_right.clicked.connect(lambda: self.on_move_delta(-1, 0, 0))
        grid.addWidget(self.btn_right, 1, 2)
        
        # Row 3: Close | Backward | Open
        self.btn_gripper_close = self.create_grid_button("CLOSE", "#F59E0B", text=True)
        self.btn_gripper_close.clicked.connect(lambda: self.on_gripper_action(0))
        grid.addWidget(self.btn_gripper_close, 2, 0)
        
        self.btn_backward = self.create_grid_button("↓", "#3B82F6")
        self.btn_backward.clicked.connect(lambda: self.on_move_delta(0, 1, 0))
        grid.addWidget(self.btn_backward, 2, 1)
        
        self.btn_gripper_open = self.create_grid_button("OPEN", "#F59E0B", text=True)
        self.btn_gripper_open.clicked.connect(lambda: self.on_gripper_action(2))
        grid.addWidget(self.btn_gripper_open, 2, 2)
        
        layout.addLayout(grid)
        
        # Speed Control Row
        speed_row = QGridLayout()
        speed_row.setSpacing(3)
        
        btn_speed_down = QPushButton("▼")
        btn_speed_down.setFixedHeight(35)
        btn_speed_down.clicked.connect(self.on_speed_decrease)
        btn_speed_down.setStyleSheet(self.get_speed_button_style())
        speed_row.addWidget(btn_speed_down, 0, 0)
        
        self.speed_display = QLabel(f"{self.speed_level}")
        self.speed_display.setAlignment(Qt.AlignCenter)
        self.speed_display.setFixedHeight(35)
        self.speed_display.setStyleSheet("""
            QLabel {
                background: #111827;
                color: #10B981;
                border: 1px solid #374151;
                border-radius: 3px;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        speed_row.addWidget(self.speed_display, 0, 1)
        
        btn_speed_up = QPushButton("▲")
        btn_speed_up.setFixedHeight(35)
        btn_speed_up.clicked.connect(self.on_speed_increase)
        btn_speed_up.setStyleSheet(self.get_speed_button_style())
        speed_row.addWidget(btn_speed_up, 0, 2)
        
        layout.addLayout(speed_row)
        
        # Position Display (All 6 motors)
        self.position_label = QLabel("M1:0 M2:0 M3:0\nM4:0 M5:0 M6:0")
        self.position_label.setAlignment(Qt.AlignCenter)
        self.position_label.setStyleSheet("""
            QLabel {
                background: #111827;
                color: #10B981;
                font-family: 'Courier New', monospace;
                font-size: 9px;
                padding: 4px;
                border: 1px solid #374151;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.position_label)
        
        # Step size display
        self.step_label = QLabel(f"Step: {self.step_sizes[self.speed_level]*1000:.1f}mm")
        self.step_label.setAlignment(Qt.AlignCenter)
        self.step_label.setStyleSheet("font-size: 9px; color: #6B7280;")
        layout.addWidget(self.step_label)
        
        layout.addStretch()
        
    def create_xy_controls(self):
        """Create XY movement control grid (4-way + home)"""
        grid = QGridLayout()
        grid.setSpacing(4)
        
        # Forward (↑)
        self.btn_forward = self.create_movement_button("↑", "#3B82F6")
        self.btn_forward.clicked.connect(lambda: self.on_move_delta(0, -1, 0))
        grid.addWidget(self.btn_forward, 0, 1)
        
        # Left (←)
        self.btn_left = self.create_movement_button("←", "#3B82F6")
        self.btn_left.clicked.connect(lambda: self.on_move_delta(1, 0, 0))
        grid.addWidget(self.btn_left, 1, 0)
        
        # Home (⊙)
        self.btn_home = self.create_movement_button("⊙", "#EF4444", small=True)
        self.btn_home.clicked.connect(self.on_go_home)
        grid.addWidget(self.btn_home, 1, 1)
        
        # Right (→)
        self.btn_right = self.create_movement_button("→", "#3B82F6")
        self.btn_right.clicked.connect(lambda: self.on_move_delta(-1, 0, 0))
        grid.addWidget(self.btn_right, 1, 2)
        
        # Backward (↓)
        self.btn_backward = self.create_movement_button("↓", "#3B82F6")
        self.btn_backward.clicked.connect(lambda: self.on_move_delta(0, 1, 0))
        grid.addWidget(self.btn_backward, 2, 1)
        
        return grid
        
    def create_z_controls(self):
        """Create Z-axis control buttons"""
        layout = QVBoxLayout()
        layout.setSpacing(4)
        
        # Up (▲)
        self.btn_z_up = self.create_movement_button("▲", "#10B981")
        self.btn_z_up.clicked.connect(lambda: self.on_move_delta(0, 0, 1))
        layout.addWidget(self.btn_z_up)
        
        # Down (▼)
        self.btn_z_down = self.create_movement_button("▼", "#10B981")
        self.btn_z_down.clicked.connect(lambda: self.on_move_delta(0, 0, -1))
        layout.addWidget(self.btn_z_down)
        
        return layout
        
    def create_gripper_controls(self):
        """Create gripper control buttons"""
        layout = QVBoxLayout()
        layout.setSpacing(4)
        
        # Open
        self.btn_gripper_open = self.create_movement_button("OPEN", "#F59E0B", text=True)
        self.btn_gripper_open.clicked.connect(lambda: self.on_gripper_action(2))
        layout.addWidget(self.btn_gripper_open)
        
        # Close
        self.btn_gripper_close = self.create_movement_button("CLOSE", "#F59E0B", text=True)
        self.btn_gripper_close.clicked.connect(lambda: self.on_gripper_action(0))
        layout.addWidget(self.btn_gripper_close)
        
        return layout
        
    def create_speed_controls(self):
        """Create speed adjustment controls"""
        layout = QHBoxLayout()
        layout.setSpacing(4)
        
        # Decrease speed
        btn_speed_down = QPushButton("▼")
        btn_speed_down.setFixedSize(50, 35)
        btn_speed_down.clicked.connect(self.on_speed_decrease)
        btn_speed_down.setStyleSheet("""
            QPushButton {
                background: #374151;
                color: white;
                border: 1px solid #4B5563;
                border-radius: 4px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #4B5563;
            }
            QPushButton:pressed {
                background: #1F2937;
            }
        """)
        layout.addWidget(btn_speed_down)
        
        # Speed display
        self.speed_display = QLabel(f"{self.speed_level}")
        self.speed_display.setAlignment(Qt.AlignCenter)
        self.speed_display.setFixedSize(60, 35)
        self.speed_display.setStyleSheet("""
            QLabel {
                background: #111827;
                color: #10B981;
                border: 1px solid #374151;
                border-radius: 4px;
                font-size: 20px;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.speed_display)
        
        # Increase speed
        btn_speed_up = QPushButton("▲")
        btn_speed_up.setFixedSize(50, 35)
        btn_speed_up.clicked.connect(self.on_speed_increase)
        btn_speed_up.setStyleSheet("""
            QPushButton {
                background: #374151;
                color: white;
                border: 1px solid #4B5563;
                border-radius: 4px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #4B5563;
            }
            QPushButton:pressed {
                background: #1F2937;
            }
        """)
        layout.addWidget(btn_speed_up)
        
        layout.addStretch()
        
        return layout
        
    def create_grid_button(self, label, color, text=False):
        """Create a compact grid button"""
        btn = QPushButton(label)
        btn.setFixedHeight(65)
        
        font_size = "11px" if text else "20px"
        
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {color};
                color: white;
                border: 2px solid {self.darken_color(color)};
                border-radius: 4px;
                font-size: {font_size};
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {self.lighten_color(color)};
                border: 2px solid {color};
            }}
            QPushButton:pressed {{
                background: {self.darken_color(color)};
            }}
            QPushButton:disabled {{
                background: #374151;
                color: #6B7280;
                border: 2px solid #4B5563;
            }}
        """)
        
        # Track for enable/disable
        self.movement_buttons.append(btn)
        
        return btn
    
    def get_speed_button_style(self):
        """Get stylesheet for speed control buttons"""
        return """
            QPushButton {
                background: #374151;
                color: white;
                border: 1px solid #4B5563;
                border-radius: 3px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #4B5563;
            }
            QPushButton:pressed {
                background: #1F2937;
            }
        """
        
    def get_manual_mode_style(self, active):
        """Get stylesheet for manual mode button"""
        if active:
            # Torque OFF - Red warning style
            return """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #DC2626, stop:0.5 #EF4444, stop:1 #DC2626);
                    color: white;
                    border: 3px solid #991B1B;
                    border-radius: 6px;
                    font-size: 14px;
                    font-weight: bold;
                }
            """
        else:
            # Torque ON - Normal gray style
            return """
                QPushButton {
                    background: #6B7280;
                    color: white;
                    border: 2px solid #4B5563;
                    border-radius: 6px;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #9CA3AF;
                }
                QPushButton:pressed {
                    background: #EF4444;
                }
            """
    
    def darken_color(self, hex_color):
        """Darken a hex color by 20%"""
        colors = {
            "#3B82F6": "#2563EB",  # Blue
            "#10B981": "#059669",  # Green
            "#F59E0B": "#D97706",  # Orange
            "#EF4444": "#DC2626",  # Red
        }
        return colors.get(hex_color, hex_color)
        
    def lighten_color(self, hex_color):
        """Lighten a hex color by 20%"""
        colors = {
            "#3B82F6": "#60A5FA",  # Blue
            "#10B981": "#34D399",  # Green
            "#F59E0B": "#FBBF24",  # Orange
            "#EF4444": "#F87171",  # Red
        }
        return colors.get(hex_color, hex_color)
        
    def setup_position_update_timer(self):
        """Set up timer to poll position at 10Hz"""
        self.position_timer = QTimer(self)
        self.position_timer.timeout.connect(self.update_position_display)
        self.position_timer.start(100)  # 10Hz
        
    def update_position_display(self):
        """Update the position display label with all 6 motor positions"""
        try:
            # Read raw joint positions
            joint_positions = self.motor_controller.read_positions()
            if joint_positions and len(joint_positions) == 6:
                self.position_label.setText(
                    f"M1:{joint_positions[0]:4d} M2:{joint_positions[1]:4d} M3:{joint_positions[2]:4d}\n"
                    f"M4:{joint_positions[3]:4d} M5:{joint_positions[4]:4d} M6:{joint_positions[5]:4d}"
                )
                # Emit position update with joint data
                self.position_updated.emit({
                    'joints': joint_positions,
                    'motor1': joint_positions[0],
                    'motor2': joint_positions[1],
                    'motor3': joint_positions[2],
                    'motor4': joint_positions[3],
                    'motor5': joint_positions[4],
                    'motor6': joint_positions[5]
                })
        except Exception as e:
            logging.debug(f"Position update error: {e}")
            
    # ============ Button Handlers ============
    
    def on_torque_disable(self):
        """Called when manual mode button is pressed"""
        logging.info("Manual mode activated - disabling torque")
        self.torque_enabled = False
        
        # Disable torque on robot
        try:
            self.motor_controller.set_torque_enable(False)
        except Exception as e:
            logging.error(f"Failed to disable torque: {e}")
            
        # Disable all movement buttons
        for btn in self.movement_buttons:
            btn.setEnabled(False)
            
        # Show warning
        self.manual_mode_warning.setVisible(True)
        
        # Update button style
        self.manual_mode_btn.setText("⚠️ TORQUE OFF ⚠️")
        self.manual_mode_btn.setStyleSheet(self.get_manual_mode_style(True))
        
        # Emit signal
        self.torque_changed.emit(False)
        
    def on_torque_enable(self):
        """Called when manual mode button is released"""
        logging.info("Manual mode deactivated - enabling torque")
        self.torque_enabled = True
        
        # Re-enable torque on robot
        try:
            self.motor_controller.set_torque_enable(True)
        except Exception as e:
            logging.error(f"Failed to enable torque: {e}")
            
        # Re-enable all movement buttons
        for btn in self.movement_buttons:
            btn.setEnabled(True)
            
        # Hide warning
        self.manual_mode_warning.setVisible(False)
        
        # Reset button style
        self.manual_mode_btn.setText("🔓 MANUAL MODE")
        self.manual_mode_btn.setStyleSheet(self.get_manual_mode_style(False))
        
        # Emit signal
        self.torque_changed.emit(True)
        
    def on_move_delta(self, dx, dy, dz):
        """Handle movement button press"""
        if not self.torque_enabled:
            logging.warning("Movement disabled - torque is off")
            return
            
        step = self.step_sizes[self.speed_level]
        
        # Scale deltas by step size
        actual_dx = dx * step
        actual_dy = dy * step
        actual_dz = dz * step
        
        logging.info(f"Move delta: dx={actual_dx:.4f}, dy={actual_dy:.4f}, dz={actual_dz:.4f}")
        
        try:
            self.motor_controller.move_end_effector_delta(actual_dx, actual_dy, actual_dz)
        except Exception as e:
            logging.error(f"Failed to move: {e}")
            
    def on_gripper_action(self, action):
        """Handle gripper button press"""
        if not self.torque_enabled:
            logging.warning("Gripper disabled - torque is off")
            return
            
        action_name = "OPEN" if action == 2 else "CLOSE"
        logging.info(f"Gripper action: {action_name}")
        
        try:
            self.motor_controller.set_gripper(action)
        except Exception as e:
            logging.error(f"Failed to control gripper: {e}")
            
    def on_go_home(self):
        """Handle home button press"""
        if not self.torque_enabled:
            logging.warning("Home disabled - torque is off")
            return
            
        logging.info("Moving to home position")
        
        try:
            self.motor_controller.go_to_home()
        except Exception as e:
            logging.error(f"Failed to go home: {e}")
            
    def on_speed_increase(self):
        """Increase movement speed"""
        self.speed_level = min(self.speed_level + 1, 3)
        self.speed_display.setText(f"{self.speed_level}")
        self.step_label.setText(f"Step: {self.step_sizes[self.speed_level]*1000:.1f}mm")
        logging.info(f"Speed level: {self.speed_level}")
        
    def on_speed_decrease(self):
        """Decrease movement speed"""
        self.speed_level = max(self.speed_level - 1, 1)
        self.speed_display.setText(f"{self.speed_level}")
        self.step_label.setText(f"Step: {self.step_sizes[self.speed_level]*1000:.1f}mm")
        logging.info(f"Speed level: {self.speed_level}")

