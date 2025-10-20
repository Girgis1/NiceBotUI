"""
Touch-screen robot teleop control panel - Signal-based control.
Emits signals to parent (RecordTab) which handles motor commands.

Provides:
- Direct joint control buttons (all 6 joints)
- User-adjustable step size
- HOLD button for manual positioning
- Torque toggle
- Live position display
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QSpinBox
)
from PySide6.QtCore import Qt, Signal


class TouchTeleopPanel(QWidget):
    """Touch-screen teleop control panel - emits signals for parent to handle"""
    
    # Signals emitted to parent (RecordTab)
    move_joint_requested = Signal(int, int)  # (joint_index, delta_steps)
    gripper_requested = Signal(int)  # (action: 0=close, 2=open)
    torque_change_requested = Signal(bool)  # (enable: True/False)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # State
        self.current_step_size = 10  # Default step size in motor units (1-100)
        self.torque_enabled = True  # True = motors locked (holding position)
        
        # Track all movement buttons for enable/disable
        self.movement_buttons = []
        
        self.init_ui()
        
    def init_ui(self):
        """Build the 5-row teleop panel UI with all 6 joints"""
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
        
        # HOLD Button (press to disable torque temporarily)
        self.hold_btn = QPushButton("HOLD")
        self.hold_btn.setFixedHeight(35)
        self.hold_btn.pressed.connect(self.on_hold_pressed)
        self.hold_btn.released.connect(self.on_hold_released)
        self.hold_btn.setStyleSheet("""
            QPushButton {
                background: #6B7280;
                color: white;
                border: 2px solid #4B5563;
                border-radius: 4px;
                font-size: 12px;
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
        
        # Add spacing
        layout.addSpacing(6)
        
        # ROW 1: Joint 3 (Elbow) + Joint 2 (Shoulder)
        row1 = QGridLayout()
        row1.setSpacing(3)
        
        self.btn_j3_up = self.create_button("▲ J3\nElbow", "#10B981")
        self.btn_j3_up.clicked.connect(lambda: self.on_joint_move(2, 1))
        row1.addWidget(self.btn_j3_up, 0, 0)
        
        self.btn_j2_up = self.create_button("↑ J2\nShoulder", "#3B82F6")
        self.btn_j2_up.clicked.connect(lambda: self.on_joint_move(1, 1))
        row1.addWidget(self.btn_j2_up, 0, 1)
        
        self.btn_j3_down = self.create_button("▼ J3\nElbow", "#10B981")
        self.btn_j3_down.clicked.connect(lambda: self.on_joint_move(2, -1))
        row1.addWidget(self.btn_j3_down, 0, 2)
        
        layout.addLayout(row1)
        
        # ROW 2: Joint 1 (Base)
        row2 = QGridLayout()
        row2.setSpacing(3)
        
        self.btn_j1_left = self.create_button("← J1\nBase", "#3B82F6")
        self.btn_j1_left.clicked.connect(lambda: self.on_joint_move(0, -1))
        row2.addWidget(self.btn_j1_left, 0, 0)
        
        # Center: Empty space
        center_spacer = QLabel()
        center_spacer.setStyleSheet("background: #1F2937; border-radius: 3px;")
        row2.addWidget(center_spacer, 0, 1)
        
        self.btn_j1_right = self.create_button("→ J1\nBase", "#3B82F6")
        self.btn_j1_right.clicked.connect(lambda: self.on_joint_move(0, 1))
        row2.addWidget(self.btn_j1_right, 0, 2)
        
        layout.addLayout(row2)
        
        # ROW 3: Joint 4 (Wrist Pitch) + Joint 2 Down
        row3 = QGridLayout()
        row3.setSpacing(3)
        
        self.btn_j4_up = self.create_button("↑ J4\nPitch", "#F59E0B")
        self.btn_j4_up.clicked.connect(lambda: self.on_joint_move(3, 1))
        row3.addWidget(self.btn_j4_up, 0, 0)
        
        self.btn_j2_down = self.create_button("↓ J2\nShoulder", "#3B82F6")
        self.btn_j2_down.clicked.connect(lambda: self.on_joint_move(1, -1))
        row3.addWidget(self.btn_j2_down, 0, 1)
        
        self.btn_j4_down = self.create_button("↓ J4\nPitch", "#F59E0B")
        self.btn_j4_down.clicked.connect(lambda: self.on_joint_move(3, -1))
        row3.addWidget(self.btn_j4_down, 0, 2)
        
        layout.addLayout(row3)
        
        # ROW 4: Joint 5 (Wrist Roll) - Full Width
        row4 = QHBoxLayout()
        row4.setSpacing(3)
        
        self.btn_j5_left = self.create_wide_button("◀ J5  Roll", "#F59E0B")
        self.btn_j5_left.clicked.connect(lambda: self.on_joint_move(4, -1))
        row4.addWidget(self.btn_j5_left)
        
        self.btn_j5_right = self.create_wide_button("▶ J5  Roll", "#F59E0B")
        self.btn_j5_right.clicked.connect(lambda: self.on_joint_move(4, 1))
        row4.addWidget(self.btn_j5_right)
        
        layout.addLayout(row4)
        
        # ROW 5: Joint 6 (Gripper) - Full Width
        row5 = QHBoxLayout()
        row5.setSpacing(3)
        
        self.btn_gripper_close = self.create_wide_button("CLOSE J6", "#9333EA")
        self.btn_gripper_close.clicked.connect(lambda: self.on_gripper_action(0))
        row5.addWidget(self.btn_gripper_close)
        
        self.btn_gripper_open = self.create_wide_button("OPEN J6", "#9333EA")
        self.btn_gripper_open.clicked.connect(lambda: self.on_gripper_action(2))
        row5.addWidget(self.btn_gripper_open)
        
        layout.addLayout(row5)
        
        # Step Size Control
        step_row = QHBoxLayout()
        step_row.setSpacing(4)
        
        step_label = QLabel("Step:")
        step_label.setStyleSheet("font-size: 10px; color: #9CA3AF; font-weight: bold;")
        step_row.addWidget(step_label)
        
        self.step_spinbox = QSpinBox()
        self.step_spinbox.setRange(1, 100)
        self.step_spinbox.setValue(self.current_step_size)
        self.step_spinbox.setSuffix(" units")
        self.step_spinbox.setFixedHeight(30)
        self.step_spinbox.valueChanged.connect(self.on_step_size_changed)
        self.step_spinbox.setStyleSheet("""
            QSpinBox {
                background: #111827;
                color: #10B981;
                border: 1px solid #374151;
                border-radius: 3px;
                font-size: 10px;
                font-weight: bold;
                padding: 2px 4px;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                background: #374151;
                border: none;
                width: 14px;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background: #4B5563;
            }
        """)
        step_row.addWidget(self.step_spinbox)
        
        layout.addLayout(step_row)
        
        # Position Display Label (updated by parent)
        self.position_label = QLabel("M1:---- M2:---- M3:----\nM4:---- M5:---- M6:----")
        self.position_label.setAlignment(Qt.AlignCenter)
        self.position_label.setStyleSheet("""
            QLabel {
                background: #111827;
                color: #10B981;
                font-family: 'Courier New', monospace;
                font-size: 8px;
                padding: 3px;
                border: 1px solid #374151;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.position_label)
        
        # Torque Toggle
        torque_row = QHBoxLayout()
        torque_row.addStretch()
        
        torque_label = QLabel("Torque:")
        torque_label.setStyleSheet("font-size: 10px; color: #9CA3AF; font-weight: bold;")
        torque_row.addWidget(torque_label)
        
        self.torque_toggle_btn = QPushButton()
        self.torque_toggle_btn.setFixedSize(35, 35)
        self.torque_toggle_btn.setCheckable(True)
        self.torque_toggle_btn.setChecked(True)
        self.torque_toggle_btn.clicked.connect(self.on_torque_toggle)
        self.update_torque_button_style()
        torque_row.addWidget(self.torque_toggle_btn)
        
        layout.addLayout(torque_row)
        
        layout.addStretch()
        
    def create_button(self, label, color):
        """Create a 3-column grid button"""
        btn = QPushButton(label)
        btn.setFixedHeight(55)
        
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {color};
                color: white;
                border: 2px solid {self.darken_color(color)};
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {self.lighten_color(color)};
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
        
        self.movement_buttons.append(btn)
        return btn
    
    def create_wide_button(self, label, color):
        """Create a full-width button"""
        btn = QPushButton(label)
        btn.setFixedHeight(40)
        
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {color};
                color: white;
                border: 2px solid {self.darken_color(color)};
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {self.lighten_color(color)};
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
        
        self.movement_buttons.append(btn)
        return btn
    
    def darken_color(self, hex_color):
        """Darken a hex color by 20%"""
        colors = {
            "#3B82F6": "#2563EB",
            "#10B981": "#059669",
            "#F59E0B": "#D97706",
            "#9333EA": "#7C3AED",
        }
        return colors.get(hex_color, hex_color)
        
    def lighten_color(self, hex_color):
        """Lighten a hex color by 20%"""
        colors = {
            "#3B82F6": "#60A5FA",
            "#10B981": "#34D399",
            "#F59E0B": "#FBBF24",
            "#9333EA": "#A855F7",
        }
        return colors.get(hex_color, hex_color)
    
    def update_position_display(self, positions: list[int]):
        """Update position display (called by parent)"""
        if positions and len(positions) == 6:
            self.position_label.setText(
                f"M1:{positions[0]:4d} M2:{positions[1]:4d} M3:{positions[2]:4d}\n"
                f"M4:{positions[3]:4d} M5:{positions[4]:4d} M6:{positions[5]:4d}"
            )
        
    # ============ Button Handlers (Emit Signals) ============
    
    def on_hold_pressed(self):
        """HOLD pressed - request torque disable"""
        self.torque_change_requested.emit(False)
        
        # Disable movement buttons during hold
        for btn in self.movement_buttons:
            btn.setEnabled(False)
    
    def on_hold_released(self):
        """HOLD released - request torque enable"""
        self.torque_change_requested.emit(True)
        
        # Re-enable movement buttons
        for btn in self.movement_buttons:
            btn.setEnabled(True)
    
    def on_torque_toggle(self, checked):
        """Torque toggle - emit signal to parent"""
        self.torque_enabled = checked
        self.torque_change_requested.emit(checked)
        self.update_torque_button_style()
    
    def update_torque_button_style(self):
        """Update torque button appearance"""
        if self.torque_toggle_btn.isChecked():
            self.torque_toggle_btn.setStyleSheet("""
                QPushButton {
                    background: #10B981;
                    border: 2px solid #059669;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background: #34D399;
                }
            """)
        else:
            self.torque_toggle_btn.setStyleSheet("""
                QPushButton {
                    background: #374151;
                    border: 2px solid #4B5563;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background: #4B5563;
                }
            """)
        
    def on_joint_move(self, joint_index, direction):
        """Joint movement requested - emit signal"""
        if not self.torque_enabled:
            return
        
        delta_steps = direction * self.current_step_size
        self.move_joint_requested.emit(joint_index, delta_steps)
            
    def on_gripper_action(self, action):
        """Gripper action requested - emit signal"""
        if not self.torque_enabled:
            return
        
        self.gripper_requested.emit(action)
    
    def on_step_size_changed(self, value):
        """Step size changed"""
        self.current_step_size = value
