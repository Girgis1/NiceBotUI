"""
Touch-screen robot teleop control panel - Direct Joint Control.
Based on HIL-SERL keyboard teleop system from LeRobot.

Provides:
- Direct joint control (6 joints mapped to buttons)
- Wrist roll control (Joint 5)
- Gripper control (Joint 6)
- HOLD button for manual positioning (torque disable)
- Torque toggle for persistent control
- Adjustable step size (user-controlled)
- Live position display
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QSpinBox
)
from PySide6.QtCore import Qt, QTimer, Signal
import logging


class TouchTeleopPanel(QWidget):
    """Touch-screen teleop control panel for robot arm - Direct Joint Control"""
    
    # Signals
    position_updated = Signal(dict)  # Emits current joint positions
    torque_changed = Signal(bool)    # Emits torque state (True=enabled)
    
    def __init__(self, motor_controller, config, parent=None):
        super().__init__(parent)
        self.motor_controller = motor_controller
        self.config = config
        
        # State
        self.torque_enabled = True  # True = motors locked (holding position)
        self.current_step_size = 10  # Default step size in motor units (1-100)
        
        # Track all movement buttons for enable/disable
        self.movement_buttons = []
        
        self.init_ui()
        self.setup_position_update_timer()
        
    def init_ui(self):
        """Build the compact touch panel UI with direct joint control"""
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
        
        # HOLD Button (press to disable torque temporarily for manual positioning)
        self.hold_btn = QPushButton("HOLD")
        self.hold_btn.setFixedHeight(40)
        self.hold_btn.pressed.connect(self.on_hold_pressed)
        self.hold_btn.released.connect(self.on_hold_released)
        self.hold_btn.setStyleSheet("""
            QPushButton {
                background: #6B7280;
                color: white;
                border: 2px solid #4B5563;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #9CA3AF;
            }
            QPushButton:pressed {
                background: #EF4444;
                border-color: #DC2626;
            }
        """)
        layout.addWidget(self.hold_btn)
        
        # Add spacing between HOLD and arrows
        layout.addSpacing(8)
        
        # Main 3x3 Grid for Joints 1-3
        grid = QGridLayout()
        grid.setSpacing(3)
        
        # Row 1: Joint 3 Up (Elbow) | Joint 2 Up (Shoulder) | Joint 3 Down (Elbow)
        self.btn_joint3_up = self.create_grid_button("▲\nJ3", "#10B981")
        self.btn_joint3_up.clicked.connect(lambda: self.on_joint_move(2, 1))  # Joint 2 (0-indexed), positive
        grid.addWidget(self.btn_joint3_up, 0, 0)
        
        self.btn_joint2_up = self.create_grid_button("↑\nJ2", "#3B82F6")
        self.btn_joint2_up.clicked.connect(lambda: self.on_joint_move(1, 1))  # Joint 1, positive
        grid.addWidget(self.btn_joint2_up, 0, 1)
        
        self.btn_joint3_down = self.create_grid_button("▼\nJ3", "#10B981")
        self.btn_joint3_down.clicked.connect(lambda: self.on_joint_move(2, -1))  # Joint 2, negative
        grid.addWidget(self.btn_joint3_down, 0, 2)
        
        # Row 2: Joint 1 Left (Base) | Empty | Joint 1 Right (Base)
        self.btn_joint1_left = self.create_grid_button("←\nJ1", "#3B82F6")
        self.btn_joint1_left.clicked.connect(lambda: self.on_joint_move(0, -1))  # Joint 0, negative
        grid.addWidget(self.btn_joint1_left, 1, 0)
        
        # Center: Empty space
        center_spacer = QLabel()
        center_spacer.setStyleSheet("background: #1F2937; border-radius: 3px;")
        grid.addWidget(center_spacer, 1, 1)
        
        self.btn_joint1_right = self.create_grid_button("→\nJ1", "#3B82F6")
        self.btn_joint1_right.clicked.connect(lambda: self.on_joint_move(0, 1))  # Joint 0, positive
        grid.addWidget(self.btn_joint1_right, 1, 2)
        
        # Row 3: Wrist Roll CCW (J5) | Joint 2 Down (Shoulder) | Wrist Roll CW (J5)
        self.btn_wrist_ccw = self.create_grid_button("◀\nJ5", "#F59E0B")
        self.btn_wrist_ccw.clicked.connect(lambda: self.on_joint_move(4, -1))  # Joint 4 (wrist roll), CCW
        grid.addWidget(self.btn_wrist_ccw, 2, 0)
        
        self.btn_joint2_down = self.create_grid_button("↓\nJ2", "#3B82F6")
        self.btn_joint2_down.clicked.connect(lambda: self.on_joint_move(1, -1))  # Joint 1, negative
        grid.addWidget(self.btn_joint2_down, 2, 1)
        
        self.btn_wrist_cw = self.create_grid_button("▶\nJ5", "#F59E0B")
        self.btn_wrist_cw.clicked.connect(lambda: self.on_joint_move(4, 1))  # Joint 4 (wrist roll), CW
        grid.addWidget(self.btn_wrist_cw, 2, 2)
        
        layout.addLayout(grid)
        
        # Gripper Control Row (below grid) - Joint 6
        gripper_row = QHBoxLayout()
        gripper_row.setSpacing(3)
        
        self.btn_gripper_close = self.create_gripper_button("CLOSE\nJ6")
        self.btn_gripper_close.clicked.connect(lambda: self.on_gripper_action(0))
        gripper_row.addWidget(self.btn_gripper_close)
        
        self.btn_gripper_open = self.create_gripper_button("OPEN\nJ6")
        self.btn_gripper_open.clicked.connect(lambda: self.on_gripper_action(2))
        gripper_row.addWidget(self.btn_gripper_open)
        
        layout.addLayout(gripper_row)
        
        # Step Size Control (User-adjustable)
        step_row = QHBoxLayout()
        step_row.setSpacing(4)
        
        step_label = QLabel("Step:")
        step_label.setStyleSheet("font-size: 10px; color: #9CA3AF; font-weight: bold;")
        step_row.addWidget(step_label)
        
        self.step_spinbox = QSpinBox()
        self.step_spinbox.setRange(1, 100)  # 1-100 motor units
        self.step_spinbox.setValue(self.current_step_size)
        self.step_spinbox.setSuffix(" units")
        self.step_spinbox.setFixedHeight(32)
        self.step_spinbox.valueChanged.connect(self.on_step_size_changed)
        self.step_spinbox.setStyleSheet("""
            QSpinBox {
                background: #111827;
                color: #10B981;
                border: 1px solid #374151;
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
                padding: 2px 4px;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                background: #374151;
                border: none;
                width: 16px;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background: #4B5563;
            }
        """)
        step_row.addWidget(self.step_spinbox)
        
        layout.addLayout(step_row)
        
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
        
        # Torque Toggle Button (bottom right corner)
        torque_row = QHBoxLayout()
        torque_row.addStretch()
        
        torque_label = QLabel("Torque:")
        torque_label.setStyleSheet("font-size: 11px; color: #9CA3AF; font-weight: bold;")
        torque_row.addWidget(torque_label)
        
        self.torque_toggle_btn = QPushButton()
        self.torque_toggle_btn.setFixedSize(40, 40)
        self.torque_toggle_btn.setCheckable(True)
        self.torque_toggle_btn.setChecked(True)  # ON by default
        self.torque_toggle_btn.clicked.connect(self.on_torque_toggle)
        self.update_torque_button_style()
        torque_row.addWidget(self.torque_toggle_btn)
        
        layout.addLayout(torque_row)
        
        layout.addStretch()
        
    def create_grid_button(self, label, color):
        """Create a compact grid button for joint control"""
        btn = QPushButton(label)
        btn.setFixedHeight(65)
        
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {color};
                color: white;
                border: 2px solid {self.darken_color(color)};
                border-radius: 4px;
                font-size: 13px;
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
    
    def create_gripper_button(self, label):
        """Create a gripper control button"""
        btn = QPushButton(label)
        btn.setFixedHeight(45)
        
        btn.setStyleSheet("""
            QPushButton {
                background: #9333EA;
                color: white;
                border: 2px solid #7C3AED;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #A855F7;
                border: 2px solid #9333EA;
            }
            QPushButton:pressed {
                background: #7C3AED;
            }
            QPushButton:disabled {
                background: #374151;
                color: #6B7280;
                border: 2px solid #4B5563;
            }
        """)
        
        # Track for enable/disable
        self.movement_buttons.append(btn)
        
        return btn
    
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
    
    def on_hold_pressed(self):
        """Called when HOLD button is pressed - disable torque for manual positioning"""
        logging.info("HOLD pressed - disabling torque for manual positioning")
        
        try:
            self.motor_controller.set_torque_enable(False)
        except Exception as e:
            logging.error(f"Failed to disable torque: {e}")
        
        # Disable movement buttons during hold
        for btn in self.movement_buttons:
            btn.setEnabled(False)
    
    def on_hold_released(self):
        """Called when HOLD button is released - re-enable torque to lock position"""
        logging.info("HOLD released - re-enabling torque to lock position")
        
        try:
            self.motor_controller.set_torque_enable(True)
        except Exception as e:
            logging.error(f"Failed to enable torque: {e}")
        
        # Re-enable movement buttons
        for btn in self.movement_buttons:
            btn.setEnabled(True)
    
    def on_torque_toggle(self, checked):
        """Handle torque toggle button click"""
        self.torque_enabled = checked
        
        logging.info(f"Torque {'enabled' if checked else 'disabled'}")
        
        # Enable/disable torque on robot
        try:
            self.motor_controller.set_torque_enable(checked)
        except Exception as e:
            logging.error(f"Failed to set torque: {e}")
        
        # Update button appearance
        self.update_torque_button_style()
        
        # Emit signal
        self.torque_changed.emit(checked)
    
    def update_torque_button_style(self):
        """Update torque button appearance based on state"""
        if self.torque_toggle_btn.isChecked():
            # Torque ON - Green lit square
            self.torque_toggle_btn.setStyleSheet("""
                QPushButton {
                    background: #10B981;
                    border: 2px solid #059669;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background: #34D399;
                }
                QPushButton:pressed {
                    background: #059669;
                }
            """)
        else:
            # Torque OFF - Dark gray null square
            self.torque_toggle_btn.setStyleSheet("""
                QPushButton {
                    background: #374151;
                    border: 2px solid #4B5563;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background: #4B5563;
                }
                QPushButton:pressed {
                    background: #1F2937;
                }
            """)
        
    def on_joint_move(self, joint_index, direction):
        """
        Handle joint movement button press.
        
        Args:
            joint_index: Joint number (0-5)
            direction: -1 for negative, +1 for positive
        """
        if not self.torque_enabled:
            logging.warning("Movement disabled - torque is off")
            return
        
        # Calculate delta steps
        delta_steps = direction * self.current_step_size
        
        joint_names = ["Base", "Shoulder", "Elbow", "Wrist1", "Wrist Roll", "Gripper"]
        logging.info(
            f"Moving Joint {joint_index + 1} ({joint_names[joint_index]}): "
            f"{'+' if direction > 0 else ''}{delta_steps} steps"
        )
        
        try:
            self.motor_controller.move_joint_delta(joint_index, delta_steps)
        except Exception as e:
            logging.error(f"Failed to move joint {joint_index}: {e}")
            
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
    
    def on_step_size_changed(self, value):
        """Handle step size spinbox value change"""
        self.current_step_size = value
        logging.info(f"Step size changed to {value} units")
