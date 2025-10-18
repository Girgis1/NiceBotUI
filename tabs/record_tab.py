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
        self.live_record_rate = 20  # Hz - INDUSTRIAL: 20Hz for high precision
        self.last_recorded_position = None
        self.live_position_threshold = 3  # INDUSTRIAL: 3 units for tighter precision
        self.live_recorded_data = []  # Store {positions, timestamp, velocity}
        self.live_record_start_time = None
        
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
        
        # Live recording button - far right
        self.live_record_btn = QPushButton("🔴 LIVE RECORD")
        self.live_record_btn.setMinimumHeight(50)
        self.live_record_btn.setMinimumWidth(140)
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
        
        layout.addLayout(control_bar)
        
        # Speed controls - Velocity and Playback Speed Scale
        velocity_frame = QHBoxLayout()
        velocity_frame.setSpacing(15)
        
        # Recording velocity
        velocity_label = QLabel("Record Speed:")
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
    
    def _notify_parent_refresh(self):
        """Notify parent window to refresh dropdowns"""
        try:
            # Walk up to find main window and refresh dashboard
            parent = self.parent()
            while parent:
                if hasattr(parent, 'dashboard_tab'):
                    parent.dashboard_tab.refresh_run_selector()
                    print("[RECORD] ✓ Refreshed dashboard dropdown")
                    break
                parent = parent.parent()
        except Exception as e:
            print(f"[WARNING] Could not refresh parent: {e}")
    
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
        """Load action data into table using new API"""
        self.table.setRowCount(0)
        self.position_counter = 1
        
        action_type = action_data.get("type", "position")
        speed = action_data.get("speed", 100)
        
        print(f"[LOAD] Loading {action_type} from file")
        
        if action_type == "live_recording":
            # Load live recording
            recorded_data = action_data.get("recorded_data", [])
            print(f"[LOAD] Live recording has {len(recorded_data)} points in file")
            if recorded_data:
                name = action_data.get("name", f"Recording {self.position_counter}")
                self.table.add_live_recording(name, recorded_data, speed)
                print(f"[LOAD] ✓ Added live recording to table: {name}")
                self.position_counter += 1
            else:
                print(f"[LOAD] ⚠️ Warning: recorded_data is empty!")
        else:
            # Load positions
            positions = action_data.get("positions", [])
            print(f"[LOAD] Position recording has {len(positions)} positions")
            for pos_data in positions:
                if isinstance(pos_data, dict):
                    name = pos_data.get("name", f"Position {self.position_counter}")
                    motor_positions = pos_data.get("motor_positions", pos_data.get("positions", []))
                    self.table.add_single_position(name, motor_positions, speed)
                    self.position_counter += 1
        
        print(f"[LOAD] ✓ Loaded {action_type} with {self.position_counter - 1} item(s) in table")
    
    def record_position(self):
        """Record ONE single position action"""
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
            
            # Add ONE single position action with 100% speed
            name = f"Position {self.position_counter}"
            speed = 100  # Default 100% speed
            
            self.table.add_single_position(name, positions, speed)
            self.position_counter += 1
            
            self.status_label.setText(f"✓ Recorded {name}")
            print(f"[RECORD] Added single position action: {name}")
            
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
        """Toggle INDUSTRIAL precision live recording - creates ONE complete action"""
        if not self.is_live_recording:
            # Start live recording
            self.is_live_recording = True
            self.last_recorded_position = None
            self.live_recorded_data = []  # Reset recording data
            self.live_record_start_time = None  # Will be set on first capture
            
            # Disable other controls during recording
            self.set_btn.setEnabled(False)
            self.play_btn.setEnabled(False)
            self.delay_btn.setEnabled(False)
            self.save_btn.setEnabled(False)
            self.action_combo.setEnabled(False)
            
            # Start timer at INDUSTRIAL rate (20Hz = 50ms)
            interval_ms = int(1000 / self.live_record_rate)
            self.live_record_timer.start(interval_ms)
            
            self.live_record_btn.setText("⏹ STOP")
            self.status_label.setText(f"🔴 LIVE RECORDING @ {self.live_record_rate}Hz - Move the arm...")
            print(f"[LIVE RECORD] 🎬 STARTED: {self.live_record_rate}Hz, threshold={self.live_position_threshold} units")
            
        else:
            # Stop live recording
            self.stop_live_recording()
    
    def stop_live_recording(self):
        """Stop live recording and create ONE COMPLETE ACTION with all data"""
        self.is_live_recording = False
        self.live_record_timer.stop()
        
        # Re-enable controls
        self.set_btn.setEnabled(True)
        self.play_btn.setEnabled(True)
        self.delay_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.action_combo.setEnabled(True)
        
        # Reset button state - CRITICAL FIX
        self.live_record_btn.setChecked(False)
        self.live_record_btn.setText("🔴 LIVE RECORD")
        self.live_record_btn.setEnabled(True)  # Re-enable for next use!
        
        # Create ONE complete live recording action
        point_count = len(self.live_recorded_data)
        if point_count > 0:
            name = f"Recording {self.position_counter}"
            speed = 100  # Default 100% speed
            
            # Add ONE row containing the entire recording
            self.table.add_live_recording(name, self.live_recorded_data, speed)
            self.position_counter += 1
            
            duration = self.live_recorded_data[-1]['timestamp'] if self.live_recorded_data else 0
            self.status_label.setText(f"✓ Recording saved: {point_count} points, {duration:.1f}s")
            print(f"[LIVE RECORD] ✅ COMPLETE: {name} - {point_count} points, {duration:.1f}s duration")
        else:
            self.status_label.setText("⚠️ No positions captured")
            print(f"[LIVE RECORD] ⚠️ No positions captured")
        
        # Clear buffer for next recording
        self.live_recorded_data = []
        self.live_record_start_time = None
        self.last_recorded_position = None  # Reset this too!
    
    def capture_live_position(self):
        """INDUSTRIAL precision position capture at 20Hz with timestamps
        
        Captures:
        - Motor positions (6-axis)
        - Precise timestamp (for interpolation)
        - Velocity setting
        - Only records significant changes (threshold: 3 units)
        """
        if not self.is_live_recording:
            return
        
        try:
            import time
            
            # Initialize start time on first capture
            if self.live_record_start_time is None:
                self.live_record_start_time = time.time()
            
            # Read current position with high precision
            positions = self.motor_controller.read_positions()
            
            if not positions or len(positions) != 6:
                print("[LIVE RECORD] ⚠️ Failed to read positions")
                return
            
            # Calculate timestamp relative to recording start
            timestamp = time.time() - self.live_record_start_time
            
            # Check if position has changed significantly (INDUSTRIAL threshold: 3 units)
            max_change = 0
            if self.last_recorded_position is not None:
                max_change = max(abs(positions[i] - self.last_recorded_position[i]) for i in range(6))
                
                if max_change < self.live_position_threshold:
                    # Position hasn't changed enough - skip for efficiency
                    return
            
            # Store COMPLETE data point with timestamp for precision playback
            current_velocity = self.velocity_slider.value()
            self.live_recorded_data.append({
                'positions': positions,
                'timestamp': timestamp,
                'velocity': current_velocity
            })
            
            self.last_recorded_position = positions
            
            point_count = len(self.live_recorded_data)
            self.status_label.setText(f"🔴 REC: {point_count} pts, {timestamp:.1f}s")
            print(f"[LIVE RECORD] Point {point_count}: t={timestamp:.3f}s, Δ={max_change} units")
            
        except Exception as e:
            print(f"[LIVE RECORD] ❌ ERROR: {e}")
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
        
        # Get all data from table - NEW FORMAT
        actions = self.table.get_all_actions()
        
        if not actions:
            self.status_label.setText("❌ No positions to save")
            return
        
        print(f"[SAVE] Got {len(actions)} action(s) from table:")
        for i, action in enumerate(actions):
            print(f"  [{i}] type={action['type']}, name={action['name']}")
            if action['type'] == 'live_recording':
                point_count = len(action.get('recorded_data', []))
                print(f"      recorded_data has {point_count} points")
        
        # Build recording data for new ActionsManager
        # Determine type: if we have live recordings, use that; otherwise simple position
        has_live_recording = any(action['type'] == 'live_recording' for action in actions)
        
        if has_live_recording and len(actions) == 1:
            # Single live recording - save as live_recording
            recorded_data = actions[0].get("recorded_data", [])
            action_data = {
                "type": "live_recording",
                "speed": actions[0].get("speed", 100),
                "recorded_data": recorded_data,
                "delays": {}
            }
            print(f"[SAVE] Saving as live_recording with {len(recorded_data)} points")
        else:
            # Multiple positions or mixed
            positions_list = []
            for action in actions:
                if action['type'] == 'position':
                    positions_list.append({
                        "name": action['name'],
                        "motor_positions": action['positions'],
                        "velocity": 600
                    })
                elif action['type'] == 'live_recording':
                    # For live recordings in a mixed sequence, use first position
                    recorded_data = action.get('recorded_data', [])
                    if recorded_data and len(recorded_data) > 0:
                        first_pos = recorded_data[0]['positions']
                        positions_list.append({
                            "name": action['name'],
                            "motor_positions": first_pos,
                            "velocity": 600
                        })
            
            action_data = {
                "type": "position",
                "speed": 100,
                "positions": positions_list,
                "delays": {}
            }
        
        # Save to file using new API
        try:
            # Debug: Check what we're about to save
            if action_data['type'] == 'live_recording':
                print(f"[SAVE] About to save live_recording with {len(action_data['recorded_data'])} points")
            
            success = self.actions_manager.save_action(name, action_data)
            
            if success:
                self.current_action_name = name
                self.status_label.setText(f"✓ Saved: {name}")
                
                # Verify what was saved
                verify_data = self.actions_manager.load_action(name)
                if verify_data and verify_data['type'] == 'live_recording':
                    saved_points = len(verify_data.get('recorded_data', []))
                    print(f"[SAVE] ✓ Saved recording: {name} - VERIFIED {saved_points} points in file")
                else:
                    print(f"[SAVE] ✓ Saved recording: {name}")
                
                # Refresh dropdown AND signal parent to refresh dashboard
                self.refresh_action_list()
                self._notify_parent_refresh()
                
                # Select the saved action
                index = self.action_combo.findText(name)
                if index >= 0:
                    self.action_combo.setCurrentIndex(index)
            else:
                self.status_label.setText("❌ Failed to save")
                
        except Exception as e:
            import traceback
            self.status_label.setText(f"❌ Save error")
            print(f"[ERROR] Failed to save recording {name}: {e}")
            print(traceback.format_exc())
    
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
        """INDUSTRIAL precision playback of all actions"""
        print("[PLAYBACK] 🎬 STARTING PLAYBACK...")
        actions = self.table.get_all_actions()
        
        print(f"[PLAYBACK] Found {len(actions)} actions to execute")
        
        if not actions:
            print("[PLAYBACK] ❌ No actions to play")
            self.status_label.setText("❌ No actions to play")
            self.play_btn.setChecked(False)
            return
        
        self.is_playing = True
        self.play_btn.setText("⏹ STOP")
        self.set_btn.setEnabled(False)
        self.delay_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.live_record_btn.setEnabled(False)
        
        # Start playback sequence
        self.playback_actions = actions
        self.playback_index = 0
        
        self.status_label.setText("▶ Playing actions...")
        self.playback_status.emit("playing")
        
        # Start first action
        print("[PLAYBACK] Executing first action...")
        QTimer.singleShot(100, self.playback_step)
    
    def playback_step(self):
        """INDUSTRIAL precision playback - handles single positions AND live recordings"""
        if not self.is_playing:
            print("[PLAYBACK] Stopped")
            return
        
        if self.playback_index >= len(self.playback_actions):
            print(f"[PLAYBACK] ✅ COMPLETE")
            
            # In loop mode, restart
            if self.play_loop:
                print("[PLAYBACK] 🔁 LOOPING - keeping torque ON")
                self.playback_index = 0
                self.status_label.setText("🔁 Looping...")
                QTimer.singleShot(500, self.playback_step)
            else:
                print("[PLAYBACK] Disconnecting...")
                try:
                    self.motor_controller.disconnect()
                except:
                    pass
                self.stop_playback()
            return
        
        # Get current action
        action = self.playback_actions[self.playback_index]
        is_last = (self.playback_index == len(self.playback_actions) - 1)
        
        # Highlight current row
        self.table.selectRow(self.playback_index)
        
        print(f"[PLAYBACK] Action {self.playback_index + 1}/{len(self.playback_actions)}: {action['name']} ({action['type']})")
        
        try:
            if action['type'] == 'position':
                # SINGLE POSITION - move directly
                self._execute_single_position(action, is_last)
            elif action['type'] == 'live_recording':
                # LIVE RECORDING - time-based interpolation
                self._execute_live_recording(action, is_last)
                
        except Exception as e:
            print(f"[PLAYBACK] ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            self.status_label.setText(f"❌ Playback error: {str(e)}")
            try:
                self.motor_controller.disconnect()
            except:
                pass
            self.stop_playback()
    
    def _execute_single_position(self, action: dict, is_last: bool):
        """Execute a single position action with precision"""
        positions = action['positions']
        speed = action['speed']
        
        # Convert speed % to velocity (600 base * speed/100)
        velocity = int(600 * (speed / 100.0))
        
        print(f"[PLAYBACK]   Single position, speed={speed}%, velocity={velocity}")
        
        keep_alive = (not is_last) or self.play_loop
        
        self.status_label.setText(f"▶ {action['name']} @ {speed}%")
        self.motor_controller.set_positions(
            positions,
            velocity,
            wait=True,  # Wait for single positions
            keep_connection=keep_alive
        )
        
        print(f"[PLAYBACK]   ✓ Position reached")
        
        # Continue to next action
        QTimer.singleShot(100, self.continue_playback)
    
    def _execute_live_recording(self, action: dict, is_last: bool):
        """Execute live recording with TIME-BASED interpolation for precision"""
        recorded_data = action['recorded_data']
        speed = action['speed']
        point_count = action['point_count']
        
        print(f"[PLAYBACK]   Live recording: {point_count} points, speed={speed}%")
        
        # Connect and keep alive
        keep_alive = (not is_last) or self.play_loop
        if not self.motor_controller.bus:
            self.motor_controller.connect()
        
        # Enable torque
        for name in self.motor_controller.motor_names:
            self.motor_controller.bus.write("Torque_Enable", name, 1, normalize=False)
        
        # Time-based playback with speed scaling
        import time
        start_time = time.time()
        last_point_index = 0
        
        for i, point in enumerate(recorded_data):
            if not self.is_playing:
                return
            
            target_time = point['timestamp'] * (100.0 / speed)  # Scale by speed %
            
            # Wait until the correct time
            while (time.time() - start_time) < target_time:
                if not self.is_playing:
                    return
                time.sleep(0.001)  # 1ms precision
            
            # Send position command
            velocity = int(point['velocity'] * (speed / 100.0))
            
            for idx, name in enumerate(self.motor_controller.motor_names):
                self.motor_controller.bus.write("Goal_Velocity", name, velocity, normalize=False)
                self.motor_controller.bus.write("Goal_Position", name, point['positions'][idx], normalize=False)
            
            last_point_index = i
            
            # Update status periodically
            if i % 10 == 0:
                progress = int((i / point_count) * 100)
                self.status_label.setText(f"▶ {action['name']} {progress}% @ {speed}%")
        
        # Final position - wait for arrival if last action
        if is_last and not self.play_loop:
            time.sleep(0.5)  # Let final position settle
        
        print(f"[PLAYBACK]   ✓ Recording playback complete")
        
        # Disconnect if last and not looping
        if not keep_alive:
            self.motor_controller.disconnect()
        
        # Continue to next action
        QTimer.singleShot(100, self.continue_playback)
    
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

