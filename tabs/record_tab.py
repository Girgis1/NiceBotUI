"""
Record Tab - Action Recorder
Allows recording sequences of motor positions for playback
"""

import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QInputDialog, QMessageBox, QLineEdit, QSlider
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from widgets.action_table import ActionTableWidget
from utils.actions_manager import ActionsManager
from utils.motor_controller import MotorController


class RecordTab(QWidget):
    """Action recorder tab - record and playback motor position sequences"""
    
    # Signal when playback status changes
    playback_status = Signal(str)  # "playing", "stopped", "idle"
    
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.actions_manager = ActionsManager()
        self.motor_controller = MotorController(config)
        
        self.current_action_name = "NewAction01"
        self.is_playing = False
        self.play_loop = False
        self.position_counter = 1
        self.default_velocity = 600  # Default velocity
        
        # Live recording state
        self.is_live_recording = False
        self.live_record_timer = QTimer()
        self.live_record_timer.timeout.connect(self.capture_live_position)
        self.live_record_rate = 10  # Hz - configurable recording rate
        self.last_recorded_position = None
        self.live_position_threshold = 5  # Minimum change to record new position (units)
        
        self.init_ui()
        self.refresh_action_list()
    
    def init_ui(self):
        """Initialize UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Top bar: Action selector and Save button
        top_bar = QHBoxLayout()
        
        action_label = QLabel("ACTION:")
        action_label.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        top_bar.addWidget(action_label)
        
        self.action_combo = QComboBox()
        self.action_combo.setEditable(True)
        self.action_combo.setMinimumHeight(60)
        self.action_combo.setStyleSheet("""
            QComboBox {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 16px;
                font-weight: bold;
            }
            QComboBox:hover {
                border-color: #2196F3;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 30px;
                border: none;
            }
            QComboBox::down-arrow {
                width: 0;
                height: 0;
                border-style: solid;
                border-width: 6px 4px 0 4px;
                border-color: #ffffff transparent transparent transparent;
            }
            QComboBox QAbstractItemView {
                background-color: #404040;
                color: #ffffff;
                selection-background-color: #2196F3;
                border: 1px solid #505050;
                font-size: 15px;
            }
        """)
        self.action_combo.currentTextChanged.connect(self.on_action_changed)
        top_bar.addWidget(self.action_combo, stretch=3)
        
        # New action button
        self.new_action_btn = QPushButton("➕")
        self.new_action_btn.setMinimumHeight(45)
        self.new_action_btn.setMinimumWidth(50)
        self.new_action_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
        """)
        self.new_action_btn.clicked.connect(self.create_new_action)
        top_bar.addWidget(self.new_action_btn)
        
        self.save_btn = QPushButton("💾 SAVE")
        self.save_btn.setMinimumHeight(45)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
            QPushButton:pressed {
                background-color: #2E7D32;
            }
        """)
        self.save_btn.clicked.connect(self.save_action)
        top_bar.addWidget(self.save_btn)
        
        layout.addLayout(top_bar)
        
        # Control bar: SET, PLAY/STOP, Loop, Delay buttons
        control_bar = QHBoxLayout()
        control_bar.setSpacing(10)
        
        self.set_btn = QPushButton("📍 SET")
        self.set_btn.setMinimumHeight(50)
        self.set_btn.setMinimumWidth(120)
        self.set_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #1565C0;
            }
        """)
        self.set_btn.clicked.connect(self.record_position)
        control_bar.addWidget(self.set_btn)
        
        # Live recording button
        self.live_record_btn = QPushButton("🔴 LIVE")
        self.live_record_btn.setMinimumHeight(50)
        self.live_record_btn.setMinimumWidth(120)
        self.live_record_btn.setCheckable(True)
        self.live_record_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e57373;
            }
            QPushButton:checked {
                background-color: #4CAF50;
                border: 2px solid #81C784;
            }
            QPushButton:checked:hover {
                background-color: #66BB6A;
            }
        """)
        self.live_record_btn.clicked.connect(self.toggle_live_recording)
        control_bar.addWidget(self.live_record_btn)
        
        self.play_btn = QPushButton("▶ PLAY")
        self.play_btn.setMinimumHeight(50)
        self.play_btn.setMinimumWidth(150)
        self.play_btn.setCheckable(True)
        self.play_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
            QPushButton:checked {
                background-color: #f44336;
            }
            QPushButton:checked:hover {
                background-color: #c62828;
            }
        """)
        self.play_btn.clicked.connect(self.toggle_playback)
        control_bar.addWidget(self.play_btn)
        
        self.loop_btn = QPushButton("🔁 Loop")
        self.loop_btn.setMinimumHeight(50)
        self.loop_btn.setCheckable(True)
        self.loop_btn.setStyleSheet("""
            QPushButton {
                background-color: #909090;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #616161;
            }
            QPushButton:checked {
                background-color: #FF9800;
            }
        """)
        self.loop_btn.clicked.connect(self.toggle_loop)
        control_bar.addWidget(self.loop_btn)
        
        self.delay_btn = QPushButton("+ Delay")
        self.delay_btn.setMinimumHeight(50)
        self.delay_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
        """)
        self.delay_btn.clicked.connect(self.add_delay)
        control_bar.addWidget(self.delay_btn)
        
        control_bar.addStretch()
        
        layout.addLayout(control_bar)
        
        # Velocity slider control
        velocity_frame = QHBoxLayout()
        velocity_frame.setSpacing(10)
        
        velocity_label = QLabel("Speed:")
        velocity_label.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        velocity_frame.addWidget(velocity_label)
        
        self.velocity_slider = QSlider(Qt.Horizontal)
        self.velocity_slider.setMinimum(10)
        self.velocity_slider.setMaximum(1000)
        self.velocity_slider.setValue(600)
        self.velocity_slider.setSingleStep(10)
        self.velocity_slider.setPageStep(100)
        self.velocity_slider.setTickPosition(QSlider.TicksBelow)
        self.velocity_slider.setTickInterval(100)
        self.velocity_slider.setMinimumWidth(300)
        self.velocity_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #404040;
                height: 8px;
                background: #2d2d2d;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #2196F3;
                border: 2px solid #1976D2;
                width: 20px;
                margin: -6px 0;
                border-radius: 10px;
            }
            QSlider::handle:horizontal:hover {
                background: #1E88E5;
            }
            QSlider::sub-page:horizontal {
                background: #2196F3;
                border-radius: 4px;
            }
        """)
        self.velocity_slider.valueChanged.connect(self.on_velocity_changed)
        velocity_frame.addWidget(self.velocity_slider)
        
        self.velocity_display = QLabel("600")
        self.velocity_display.setStyleSheet("""
            color: #ffffff;
            background-color: #404040;
            border: 2px solid #505050;
            border-radius: 4px;
            font-size: 16px;
            font-weight: bold;
            padding: 5px 10px;
            min-width: 50px;
        """)
        self.velocity_display.setAlignment(Qt.AlignCenter)
        velocity_frame.addWidget(self.velocity_display)
        
        velocity_frame.addStretch()
        
        layout.addLayout(velocity_frame)
        
        # Table for recorded positions
        self.table = ActionTableWidget()
        self.table.delete_clicked.connect(self.delete_position)
        self.table.itemChanged.connect(self.on_table_item_changed)
        layout.addWidget(self.table, stretch=1)
        
        # Status label
        self.status_label = QLabel("Ready to record. Move robot to desired position and press SET.")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                background-color: #2d2d2d;
                border: 1px solid #404040;
                border-radius: 4px;
                padding: 10px;
                font-size: 13px;
            }
        """)
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
    
    def refresh_action_list(self):
        """Refresh the action dropdown list"""
        self.action_combo.blockSignals(True)
        current = self.action_combo.currentText()
        
        self.action_combo.clear()
        self.action_combo.addItem("NewAction01")
        
        actions = self.actions_manager.list_actions()
        for action in actions:
            self.action_combo.addItem(action)
        
        # Restore current selection if it exists
        index = self.action_combo.findText(current)
        if index >= 0:
            self.action_combo.setCurrentIndex(index)
        
        self.action_combo.blockSignals(False)
    
    def on_action_changed(self, name: str):
        """Handle action selection change"""
        if not name or name == "NewAction01":
            self.current_action_name = "NewAction01"
            self.table.setRowCount(0)
            self.position_counter = 1
            return
        
        # Load action
        action_data = self.actions_manager.load_action(name)
        if action_data:
            self.current_action_name = name
            self.load_action_to_table(action_data)
            self.status_label.setText(f"Loaded action: {name}")
    
    def load_action_to_table(self, action_data: dict):
        """Load action data into table"""
        self.table.setRowCount(0)
        self.position_counter = 1
        
        positions = action_data.get("positions", [])
        delays = action_data.get("delays", {})
        
        for idx, pos_data in enumerate(positions):
            self.table.add_position_row(
                pos_data["name"],
                pos_data["motor_positions"],
                pos_data.get("velocity", 600)
            )
            
            # Add delay if exists after this position
            if str(idx) in delays:
                self.table.add_delay_row(delays[str(idx)])
        
        self.position_counter = len(positions) + 1
    
    def record_position(self):
        """Record current motor position"""
        try:
            # Read current positions
            print("[RECORD] Reading motor positions...")
            self.status_label.setText("Reading motor positions...")
            positions = self.motor_controller.read_positions()
            
            if not positions or len(positions) != 6:
                print(f"[RECORD] ❌ Failed to read positions: {positions}")
                self.status_label.setText("❌ Failed to read motor positions")
                return
            
            print(f"[RECORD] ✓ Read positions: {positions}")
            
            # Add to table with current velocity from slider
            name = f"Pos {self.position_counter}"
            velocity = self.default_velocity
            
            self.table.add_position_row(name, positions, velocity)
            self.position_counter += 1
            
            self.status_label.setText(f"✓ Recorded {name}: {positions}")
            
        except Exception as e:
            self.status_label.setText(f"❌ Error: {str(e)}")
            print(f"Error recording position: {e}")
    
    def add_delay(self):
        """Add a delay after selected position"""
        current_row = self.table.currentRow()
        
        if current_row < 0:
            # No selection, add at end
            current_row = self.table.rowCount()
        else:
            # Add after selected row
            current_row += 1
        
        # Ask for delay duration
        delay, ok = QInputDialog.getDouble(
            self, "Add Delay", "Delay duration (seconds):",
            1.0, 0.1, 60.0, 1
        )
        
        if ok:
            self.table.add_delay_row(delay, current_row)
            self.status_label.setText(f"✓ Added {delay:.1f}s delay")
    
    def toggle_live_recording(self):
        """Toggle live position recording for smooth, repeatable captures"""
        if not self.is_live_recording:
            # Start live recording
            self.is_live_recording = True
            self.last_recorded_position = None
            
            # Disable other controls
            self.set_btn.setEnabled(False)
            self.play_btn.setEnabled(False)
            self.delay_btn.setEnabled(False)
            self.save_btn.setEnabled(False)
            
            # Start timer at configured rate (10Hz = every 100ms)
            interval_ms = int(1000 / self.live_record_rate)
            self.live_record_timer.start(interval_ms)
            
            self.live_record_btn.setText("⏹ STOP")
            self.status_label.setText(f"🔴 Live recording at {self.live_record_rate}Hz - move the arm...")
            print(f"[LIVE RECORD] Started at {self.live_record_rate}Hz (threshold: {self.live_position_threshold} units)")
            
        else:
            # Stop live recording
            self.stop_live_recording()
    
    def stop_live_recording(self):
        """Stop live recording"""
        self.is_live_recording = False
        self.live_record_timer.stop()
        
        # Re-enable controls
        self.set_btn.setEnabled(True)
        self.play_btn.setEnabled(True)
        self.delay_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        
        self.live_record_btn.setChecked(False)
        self.live_record_btn.setText("🔴 LIVE")
        
        positions_count = self.table.rowCount()
        self.status_label.setText(f"✓ Live recording stopped - captured {positions_count} positions")
        print(f"[LIVE RECORD] Stopped - total positions: {positions_count}")
    
    def capture_live_position(self):
        """Capture one position during live recording (called by timer at 10Hz)
        
        Uses intelligent position filtering to:
        1. Only record when position changes significantly (reduces redundancy)
        2. Capture smooth motion at optimal Jetson-friendly rate
        3. Maintain high repeatability for playback
        """
        if not self.is_live_recording:
            return
        
        try:
            # Read current position
            positions = self.motor_controller.read_positions()
            
            if not positions or len(positions) != 6:
                print("[LIVE RECORD] ⚠️ Failed to read positions")
                return
            
            # Check if position has changed significantly from last recorded
            max_change = 0
            if self.last_recorded_position is not None:
                # Calculate max movement from last recorded position
                max_change = max(abs(positions[i] - self.last_recorded_position[i]) for i in range(6))
                
                if max_change < self.live_position_threshold:
                    # Position hasn't changed enough, skip this sample (reduces redundancy)
                    return
            
            # Record this position
            current_velocity = self.velocity_slider.value()
            self.table.add_position_row(
                f"Pos {self.position_counter}",
                positions,
                current_velocity
            )
            
            self.last_recorded_position = positions
            self.position_counter += 1
            
            positions_count = self.table.rowCount()
            self.status_label.setText(f"🔴 Recording... ({positions_count} positions)")
            print(f"[LIVE RECORD] ✓ Captured position {positions_count}: max_change={max_change}")
            
        except Exception as e:
            print(f"[LIVE RECORD] ❌ Error: {e}")
            import traceback
            traceback.print_exc()
            self.stop_live_recording()
            self.status_label.setText(f"❌ Recording error: {str(e)}")
    
    def on_table_item_changed(self, item):
        """Handle table item changes - ensure delete buttons persist"""
        # Ensure all rows still have delete buttons after editing
        self.table.ensure_delete_buttons()
    
    def create_new_action(self):
        """Create a new action"""
        # Ask for name
        name, ok = QInputDialog.getText(
            self, "New Action", "Enter action name:"
        )
        
        if ok and name:
            name = name.strip()
            if name:
                # Add to combo box
                self.action_combo.addItem(name)
                self.action_combo.setCurrentText(name)
                
                # Clear the table
                self.table.setRowCount(0)
                self.position_counter = 1
                
                self.status_label.setText(f"✓ Created new action: {name}")
    
    def on_velocity_changed(self, value: int):
        """Handle velocity slider change - snap to multiples of 10"""
        snapped_value = round(value / 10) * 10
        if snapped_value != value:
            self.velocity_slider.setValue(snapped_value)
        else:
            self.default_velocity = snapped_value
            self.velocity_display.setText(str(snapped_value))
    
    def delete_position(self, row: int):
        """Delete a position"""
        # Allow deletion even if it's the only row
        reply = QMessageBox.question(
            self, "Delete Position",
            "Are you sure you want to delete this position?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.table.removeRow(row)
            
            # If this was the last position, reset counter
            if self.table.rowCount() == 0:
                self.position_counter = 1
            
            self.status_label.setText("✓ Position deleted")
    
    def save_action(self):
        """Save current action to file"""
        name = self.action_combo.currentText().strip()
        
        if not name or name == "NewAction01":
            # Ask for name
            name, ok = QInputDialog.getText(
                self, "Save Action", "Action name:"
            )
            if not ok or not name:
                return
        
        # Get all data from table
        positions, delays = self.table.get_all_data()
        
        if not positions:
            self.status_label.setText("❌ No positions to save")
            return
        
        # Save to file
        success = self.actions_manager.save_action(name, positions, delays)
        
        if success:
            self.current_action_name = name
            self.status_label.setText(f"✓ Saved action: {name}")
            self.refresh_action_list()
            
            # Select the saved action
            index = self.action_combo.findText(name)
            if index >= 0:
                self.action_combo.setCurrentIndex(index)
        else:
            self.status_label.setText("❌ Failed to save action")
    
    def toggle_playback(self):
        """Toggle between play and stop"""
        if self.play_btn.isChecked():
            self.start_playback()
        else:
            self.stop_playback()
    
    def toggle_loop(self):
        """Toggle loop mode"""
        self.play_loop = self.loop_btn.isChecked()
        if self.play_loop:
            self.status_label.setText("🔁 Loop enabled")
        else:
            self.status_label.setText("Loop disabled")
    
    def start_playback(self):
        """Start playing the recorded sequence"""
        print("[PLAYBACK] Starting playback...")
        positions, delays = self.table.get_all_data()
        
        print(f"[PLAYBACK] Found {len(positions)} positions, {len(delays)} delays")
        
        if not positions:
            print("[PLAYBACK] ❌ No positions to play")
            self.status_label.setText("❌ No positions to play")
            self.play_btn.setChecked(False)
            return
        
        self.is_playing = True
        self.play_btn.setText("⏹ STOP")
        self.set_btn.setEnabled(False)
        self.delay_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        
        # Start playback in background
        self.playback_positions = positions
        self.playback_delays = delays
        self.playback_index = 0
        
        self.status_label.setText("▶ Playing sequence...")
        self.playback_status.emit("playing")
        
        # Start first move
        print("[PLAYBACK] Starting first move...")
        QTimer.singleShot(100, self.playback_step)
    
    def playback_step(self):
        """Execute one step of playback with smooth transitions"""
        if not self.is_playing:
            print("[PLAYBACK] Stopped (not playing)")
            return
        
        if self.playback_index >= len(self.playback_positions):
            print(f"[PLAYBACK] Sequence complete (index {self.playback_index})")
            
            # In loop mode, NEVER disconnect - keep torque on
            if self.play_loop:
                print("[PLAYBACK] 🔁 Looping - keeping torque ON")
                # Restart from beginning - keep connection alive
                self.playback_index = 0
                self.status_label.setText("🔁 Looping sequence...")
                QTimer.singleShot(500, self.playback_step)
            else:
                # Not looping - disconnect and clean up
                print("[PLAYBACK] Not looping - disconnecting")
                try:
                    self.motor_controller.disconnect()
                except:
                    pass
                self.stop_playback()
            return
        
        # Get current position
        pos_data = self.playback_positions[self.playback_index]
        is_last_position = (self.playback_index == len(self.playback_positions) - 1)
        
        # Highlight current row
        self.table.selectRow(self.playback_index)
        
        print(f"[PLAYBACK] Step {self.playback_index + 1}/{len(self.playback_positions)}: {pos_data['name']}")
        print(f"[PLAYBACK]   Positions: {pos_data['motor_positions']}")
        print(f"[PLAYBACK]   Velocity: {pos_data.get('velocity', 600)}")
        
        try:
            # Move to position - keep connection open for smooth transitions
            # In loop mode, always keep connection (even on last position)
            keep_alive = (not is_last_position) or self.play_loop
            
            self.status_label.setText(f"▶ Moving to {pos_data['name']}...")
            self.motor_controller.set_positions(
                pos_data["motor_positions"],
                pos_data.get("velocity", 600),
                wait=True,
                keep_connection=keep_alive
            )
            
            print(f"[PLAYBACK]   ✓ Move complete (kept connection: {keep_alive})")
            
            # Check for delay after this position
            if str(self.playback_index) in self.playback_delays:
                delay = self.playback_delays[str(self.playback_index)]
                print(f"[PLAYBACK]   ⏱️ Delay: {delay:.1f}s")
                self.status_label.setText(f"⏱️ Waiting {delay:.1f}s...")
                QTimer.singleShot(int(delay * 1000), self.continue_playback)
            else:
                # No delay, continue immediately for smooth flow
                self.continue_playback()
                
        except Exception as e:
            print(f"[PLAYBACK] ❌ Error: {e}")
            import traceback
            traceback.print_exc()
            self.status_label.setText(f"❌ Playback error: {str(e)}")
            try:
                self.motor_controller.disconnect()
            except:
                pass
            self.stop_playback()
    
    def continue_playback(self):
        """Continue to next position"""
        self.playback_index += 1
        QTimer.singleShot(100, self.playback_step)
    
    def stop_playback(self):
        """Stop playback"""
        print("[PLAYBACK] Stopping playback")
        self.is_playing = False
        self.play_btn.setChecked(False)
        self.play_btn.setText("▶ PLAY")
        self.set_btn.setEnabled(True)
        self.delay_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        
        # Clear row selection
        self.table.clearSelection()
        
        # Ensure motor connection is closed (unless we're about to loop)
        if not self.play_loop:
            print("[PLAYBACK] Disconnecting motors")
            try:
                self.motor_controller.disconnect()
            except:
                pass
        
        self.status_label.setText("⏹ Playback stopped")
        self.playback_status.emit("stopped")

