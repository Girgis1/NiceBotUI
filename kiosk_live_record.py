"""
Live Record Modal - Record robot movements
High-precision recording at 20Hz with timestamps
"""

import time
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame
)
from PySide6.QtCore import Qt, QTimer

from kiosk_styles import Colors, Styles
from utils.motor_controller import MotorController
from utils.actions_manager import ActionsManager


class LiveRecordModal(QDialog):
    """
    Live recording modal
    
    Features:
    - Full-screen overlay
    - High-precision recording (20Hz)
    - Real-time feedback
    - Automatic naming
    """
    
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        
        self.config = config
        self.motor_controller = MotorController(config)
        self.actions_manager = ActionsManager()
        
        # Recording state
        self.is_recording = False
        self.recorded_data = []
        self.start_time = None
        self.last_position = None
        self.position_threshold = 3  # Minimum change in motor units
        
        # Setup dialog
        self.setWindowTitle("Live Record")
        self.setModal(True)
        self.setFixedSize(1024, 600)
        
        # Frameless for consistency
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        
        # Timer for recording
        self.record_timer = QTimer()
        self.record_timer.timeout.connect(self.capture_position)
        
        # Initialize UI
        self.init_ui()
    
    def init_ui(self):
        """Initialize user interface"""
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Semi-transparent dark overlay background
        self.setStyleSheet(f"""
            QDialog {{
                background-color: rgba(0, 0, 0, 200);
            }}
        """)
        
        # Center panel
        panel = QFrame()
        panel.setFixedSize(800, 500)
        panel.setStyleSheet(Styles.get_modal_panel_style())
        
        # Center the panel
        layout.addStretch()
        center_layout = QHBoxLayout()
        center_layout.addStretch()
        center_layout.addWidget(panel)
        center_layout.addStretch()
        layout.addLayout(center_layout)
        layout.addStretch()
        
        # Panel layout
        panel_layout = QVBoxLayout(panel)
        panel_layout.setSpacing(20)
        panel_layout.setContentsMargins(40, 40, 40, 40)
        
        # Title
        title = QLabel("🔴 Live Recording")
        title.setStyleSheet(Styles.get_label_style(size="huge", bold=True))
        title.setAlignment(Qt.AlignCenter)
        panel_layout.addWidget(title)
        
        panel_layout.addSpacing(20)
        
        # Status display
        self.status_label = QLabel("Ready to record\nMove the robot arm to record positions")
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: 18px;
                background-color: {Colors.BG_MEDIUM};
                border-radius: 10px;
                padding: 30px;
            }}
        """)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        panel_layout.addWidget(self.status_label)
        
        # Recording stats
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(30)
        
        # Points captured
        points_frame = QVBoxLayout()
        points_label = QLabel("Points")
        points_label.setStyleSheet(Styles.get_label_style(size="small"))
        points_label.setAlignment(Qt.AlignCenter)
        points_frame.addWidget(points_label)
        
        self.points_value = QLabel("0")
        self.points_value.setStyleSheet(f"""
            QLabel {{
                color: {Colors.SUCCESS};
                font-size: 48px;
                font-weight: bold;
            }}
        """)
        self.points_value.setAlignment(Qt.AlignCenter)
        points_frame.addWidget(self.points_value)
        
        stats_layout.addLayout(points_frame)
        
        # Duration
        duration_frame = QVBoxLayout()
        duration_label = QLabel("Duration")
        duration_label.setStyleSheet(Styles.get_label_style(size="small"))
        duration_label.setAlignment(Qt.AlignCenter)
        duration_frame.addWidget(duration_label)
        
        self.duration_value = QLabel("0.0s")
        self.duration_value.setStyleSheet(f"""
            QLabel {{
                color: {Colors.INFO};
                font-size: 48px;
                font-weight: bold;
            }}
        """)
        self.duration_value.setAlignment(Qt.AlignCenter)
        duration_frame.addWidget(self.duration_value)
        
        stats_layout.addLayout(duration_frame)
        
        panel_layout.addLayout(stats_layout)
        
        panel_layout.addStretch()
        
        # Control buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)
        
        # Cancel button
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet(Styles.get_large_button(Colors.BG_LIGHT, Colors.BG_MEDIUM))
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        # Start/Stop recording button
        self.record_btn = QPushButton("🔴 START RECORDING")
        self.record_btn.setStyleSheet(Styles.get_large_button(Colors.ERROR, Colors.ERROR_HOVER))
        self.record_btn.setMinimumHeight(100)
        self.record_btn.clicked.connect(self.toggle_recording)
        button_layout.addWidget(self.record_btn, stretch=2)
        
        # Save button (initially hidden)
        self.save_btn = QPushButton("💾 SAVE")
        self.save_btn.setStyleSheet(Styles.get_large_button(Colors.SUCCESS, Colors.SUCCESS_HOVER))
        self.save_btn.clicked.connect(self.save_recording)
        self.save_btn.hide()
        button_layout.addWidget(self.save_btn)
        
        panel_layout.addLayout(button_layout)
    
    def toggle_recording(self):
        """Toggle recording on/off"""
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()
    
    def start_recording(self):
        """Start live recording"""
        self.is_recording = True
        self.recorded_data = []
        self.start_time = time.time()
        self.last_position = None
        
        # Update UI
        self.record_btn.setText("⏹ STOP RECORDING")
        self.record_btn.setStyleSheet(Styles.get_large_button(Colors.SUCCESS, Colors.SUCCESS_HOVER))
        self.status_label.setText("🔴 RECORDING\nMove the robot arm...")
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: 18px;
                background-color: {Colors.ERROR_DARK};
                border-radius: 10px;
                padding: 30px;
            }}
        """)
        self.cancel_btn.setEnabled(False)
        
        # Start recording at 20Hz (50ms interval)
        self.record_timer.start(50)
        
        print("[LIVE RECORD] Started recording at 20Hz")
    
    def stop_recording(self):
        """Stop live recording"""
        self.is_recording = False
        self.record_timer.stop()
        
        # Update UI
        self.record_btn.hide()
        self.save_btn.show()
        self.cancel_btn.setEnabled(True)
        
        point_count = len(self.recorded_data)
        duration = self.recorded_data[-1]['timestamp'] if self.recorded_data else 0
        
        self.status_label.setText(f"✓ Recording Complete\n{point_count} points, {duration:.1f}s")
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: 18px;
                background-color: {Colors.BG_MEDIUM};
                border-radius: 10px;
                padding: 30px;
            }}
        """)
        
        print(f"[LIVE RECORD] Stopped: {point_count} points, {duration:.1f}s")
    
    def capture_position(self):
        """Capture current robot position (called at 20Hz)"""
        if not self.is_recording:
            return
        
        try:
            # Read current position
            positions = self.motor_controller.read_positions()
            
            if not positions or len(positions) != 6:
                print("[LIVE RECORD] Failed to read positions")
                return
            
            # Calculate timestamp
            timestamp = time.time() - self.start_time
            
            # Check if position changed significantly
            if self.last_position is not None:
                max_change = max(abs(positions[i] - self.last_position[i]) for i in range(6))
                if max_change < self.position_threshold:
                    # Position hasn't changed enough, skip
                    return
            
            # Record position
            self.recorded_data.append({
                'positions': positions,
                'timestamp': timestamp,
                'velocity': 600  # Default velocity
            })
            
            self.last_position = positions
            
            # Update UI
            self.points_value.setText(str(len(self.recorded_data)))
            self.duration_value.setText(f"{timestamp:.1f}s")
            
        except Exception as e:
            print(f"[LIVE RECORD] Error: {e}")
    
    def save_recording(self):
        """Save recorded data"""
        if not self.recorded_data:
            self.status_label.setText("⚠️ No data to save")
            return
        
        # Generate name with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"Recording_{timestamp}"
        
        # Create action data structure
        positions = [{
            "name": name,
            "type": "live_recording",
            "recorded_data": self.recorded_data,
            "point_count": len(self.recorded_data),
            "motor_positions": self.recorded_data[0]['positions'],  # First position for compatibility
            "velocity": 600
        }]
        
        # Save to file
        success = self.actions_manager.save_action(name, positions, {})
        
        if success:
            print(f"[LIVE RECORD] Saved: {name}")
            self.status_label.setText(f"✓ Saved as:\n{name}")
            
            # Close after short delay
            QTimer.singleShot(1500, self.accept)
        else:
            self.status_label.setText("⚠️ Failed to save")
    
    def closeEvent(self, event):
        """Handle dialog close"""
        # Stop recording if active
        if self.is_recording:
            self.record_timer.stop()
        
        # Disconnect motor controller
        try:
            self.motor_controller.disconnect()
        except:
            pass
        
        event.accept()


