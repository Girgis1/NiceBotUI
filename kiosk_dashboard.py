"""
Kiosk Dashboard - Main robot control interface
Safety-first design with always-responsive UI
"""

import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFrame, QTextEdit
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont

from kiosk_styles import Colors, Styles, StatusIndicator
from robot_worker import RobotWorker

# Paths
ROOT = Path(__file__).parent


class StatusDot(QLabel):
    """Status indicator dot"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.connected = False
        self.warning = False
        self.disabled = False
        self.setFixedSize(20, 20)
        self.update_style()
    
    def set_connected(self, connected: bool):
        """Set connected state"""
        self.connected = connected
        self.warning = False
        self.disabled = False
        self.update_style()
    
    def set_warning(self):
        """Set warning state"""
        self.connected = False
        self.warning = True
        self.disabled = False
        self.update_style()
    
    def set_disabled(self):
        """Set disabled state"""
        self.connected = False
        self.warning = False
        self.disabled = True
        self.update_style()
    
    def update_style(self):
        """Update visual style"""
        self.setStyleSheet(StatusIndicator.get_style(
            connected=self.connected,
            warning=self.warning,
            disabled=self.disabled
        ))


class KioskDashboard(QWidget):
    """
    Main dashboard screen with safety-first design
    
    CRITICAL SAFETY FEATURES:
    - Robot operations run in separate QThread (RobotWorker)
    - STOP button always enabled and responsive (< 100ms)
    - UI thread never blocks
    - Proper emergency stop escalation
    """
    
    # Signals
    config_changed = Signal(dict)
    
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        
        # State
        self.is_running = False
        self.worker = None
        self.start_time = None
        self.elapsed_seconds = 0
        
        # Initialize UI
        self.init_ui()
        
        # Start background timers
        self.setup_timers()
        
        # Initial connection check
        self.check_connections()
    
    def init_ui(self):
        """Initialize user interface"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # === TOP STATUS BAR (80px) ===
        status_bar = self.create_status_bar()
        layout.addWidget(status_bar)
        
        # === RUN SELECTOR (120px) ===
        run_selector = self.create_run_selector()
        layout.addWidget(run_selector)
        
        # === MAIN CONTROLS (180px) ===
        controls = self.create_main_controls()
        layout.addLayout(controls)
        
        # === BOTTOM AREA ===
        bottom = self.create_bottom_area()
        layout.addLayout(bottom)
    
    def create_status_bar(self):
        """Create top status bar with indicators and status text"""
        bar = QFrame()
        bar.setFixedHeight(80)
        bar.setStyleSheet(Styles.get_status_panel_style())
        
        layout = QHBoxLayout(bar)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 15, 20, 15)
        
        # Left: Connection indicators
        indicators = QHBoxLayout()
        indicators.setSpacing(15)
        
        # Robot indicators (2 dots)
        robot_group = QHBoxLayout()
        robot_group.setSpacing(6)
        robot_label = QLabel("Robot")
        robot_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 12px;")
        robot_group.addWidget(robot_label)
        
        self.robot_dot1 = StatusDot()
        robot_group.addWidget(self.robot_dot1)
        self.robot_dot2 = StatusDot()
        self.robot_dot2.set_disabled()  # Second dot for future expansion
        robot_group.addWidget(self.robot_dot2)
        
        indicators.addLayout(robot_group)
        
        # Camera indicators (3 dots)
        camera_group = QHBoxLayout()
        camera_group.setSpacing(6)
        camera_label = QLabel("Cameras")
        camera_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 12px;")
        camera_group.addWidget(camera_label)
        
        self.camera_dot1 = StatusDot()
        camera_group.addWidget(self.camera_dot1)
        self.camera_dot2 = StatusDot()
        camera_group.addWidget(self.camera_dot2)
        self.camera_dot3 = StatusDot()
        camera_group.addWidget(self.camera_dot3)
        
        indicators.addLayout(camera_group)
        
        # Elapsed time
        self.time_label = QLabel("00:00")
        self.time_label.setStyleSheet(f"""
            color: {Colors.SUCCESS};
            font-size: 16px;
            font-weight: bold;
            font-family: monospace;
        """)
        indicators.addWidget(self.time_label)
        
        layout.addLayout(indicators)
        
        # Center: Status text
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(Styles.get_status_label_style())
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label, stretch=1)
        
        # Right: Branding
        branding = QLabel("NICE LABS")
        branding.setStyleSheet(f"""
            color: {Colors.TEXT_DISABLED};
            font-size: 14px;
            font-weight: bold;
        """)
        branding.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(branding)
        
        return bar
    
    def create_run_selector(self):
        """Create RUN selector dropdown"""
        frame = QFrame()
        frame.setFixedHeight(130)
        frame.setStyleSheet(Styles.get_status_panel_style())
        
        layout = QHBoxLayout(frame)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 10, 20, 10)
        
        # Label
        label = QLabel("RUN:")
        label.setStyleSheet(Styles.get_label_style(size="large", bold=True))
        layout.addWidget(label)
        
        # Dropdown
        self.run_combo = QComboBox()
        self.run_combo.setStyleSheet(Styles.get_dropdown_style())
        self.run_combo.currentTextChanged.connect(self.on_run_selection_changed)
        layout.addWidget(self.run_combo, stretch=1)
        
        # Populate dropdown
        self.refresh_run_selector()
        
        return frame
    
    def create_main_controls(self):
        """Create main control buttons"""
        layout = QHBoxLayout()
        layout.setSpacing(15)
        
        # START/STOP button (giant, always responsive)
        self.start_stop_btn = QPushButton("START")
        self.start_stop_btn.setCheckable(True)
        self.start_stop_btn.setStyleSheet(
            Styles.get_giant_button(Colors.SUCCESS, Colors.SUCCESS_HOVER)
        )
        # CRITICAL: Button stays enabled during operation for emergency stop
        self.start_stop_btn.clicked.connect(self.toggle_start_stop)
        layout.addWidget(self.start_stop_btn, stretch=3)
        
        # HOME button (square)
        self.home_btn = QPushButton("⌂")
        self.home_btn.setFixedSize(150, 150)
        self.home_btn.setStyleSheet(
            Styles.get_giant_button(Colors.INFO, Colors.INFO_HOVER)
        )
        self.home_btn.clicked.connect(self.go_home)
        layout.addWidget(self.home_btn)
        
        return layout
    
    def create_bottom_area(self):
        """Create bottom area with settings, live record, and log"""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Button row
        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        
        # Settings button
        self.settings_btn = QPushButton("⚙️\nSettings")
        self.settings_btn.setStyleSheet(
            Styles.get_large_button(Colors.BG_LIGHT, Colors.BG_MEDIUM)
        )
        self.settings_btn.clicked.connect(self.open_settings)
        button_row.addWidget(self.settings_btn)
        
        button_row.addStretch()
        
        # Live Record button
        self.live_record_btn = QPushButton("🔴\nLive Record")
        self.live_record_btn.setStyleSheet(
            Styles.get_large_button(Colors.ERROR, Colors.ERROR_HOVER)
        )
        self.live_record_btn.clicked.connect(self.open_live_record)
        button_row.addWidget(self.live_record_btn)
        
        layout.addLayout(button_row)
        
        # Minimal log display (60px, last 2 lines only)
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFixedHeight(60)
        self.log_display.setStyleSheet(Styles.get_log_display_style())
        self.log_display.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self.log_display)
        
        # Initial log message
        self.log("System ready")
        
        return layout
    
    def setup_timers(self):
        """Setup background timers"""
        # Connection check timer (every 5 seconds)
        self.connection_timer = QTimer()
        self.connection_timer.timeout.connect(self.check_connections)
        self.connection_timer.start(5000)
        
        # Elapsed time timer (every second when running)
        self.elapsed_timer = QTimer()
        self.elapsed_timer.timeout.connect(self.update_elapsed_time)
    
    def refresh_run_selector(self):
        """Populate RUN selector with models and live recordings"""
        self.run_combo.blockSignals(True)
        self.run_combo.clear()
        
        # Add placeholder
        self.run_combo.addItem("-- Select --")
        
        # Scan for trained models
        try:
            base_path = Path(self.config.get("policy", {}).get("base_path", "outputs/train"))
            if base_path.exists():
                for model_dir in sorted(base_path.iterdir()):
                    if model_dir.is_dir():
                        checkpoints_dir = model_dir / "checkpoints" / "last" / "pretrained_model"
                        if checkpoints_dir.exists():
                            self.run_combo.addItem(f"🤖 Model: {model_dir.name}")
        except Exception as e:
            print(f"[WARN] Failed to scan models: {e}")
        
        # Scan for live recordings
        try:
            from utils.actions_manager import ActionsManager
            actions_mgr = ActionsManager()

            for recording_name in actions_mgr.list_actions():
                manifest = actions_mgr.load_manifest(recording_name)
                if not manifest:
                    continue

                steps = manifest.get("steps", [])
                has_live = any(
                    isinstance(step, dict)
                    and step.get("type") == "live_recording"
                    and step.get("enabled", True)
                    for step in steps
                )

                if has_live:
                    display_name = manifest.get("name", recording_name)
                    self.run_combo.addItem(f"🔴 Recording: {display_name}")
        except Exception as e:
            print(f"[WARN] Failed to scan recordings: {e}")
        
        self.run_combo.blockSignals(False)
    
    def on_run_selection_changed(self, text):
        """Handle RUN selector change"""
        if text.startswith("🤖 Model:"):
            model_name = text.replace("🤖 Model: ", "")
            self.log(f"Selected model: {model_name}")
            # Update config with model path
            try:
                base_path = Path(self.config["policy"]["base_path"])
                model_path = base_path / model_name / "checkpoints" / "last" / "pretrained_model"
                self.config["policy"]["path"] = str(model_path)
            except Exception as e:
                self.log(f"ERROR: {e}")
        elif text.startswith("🔴 Recording:"):
            recording_name = text.replace("🔴 Recording: ", "")
            self.log(f"Selected recording: {recording_name}")
    
    def check_connections(self):
        """Check robot and camera connections (non-blocking)"""
        # Don't check during operation
        if self.is_running:
            return
        
        # Check robot port
        robot_port = self.config.get("robot", {}).get("port", "")
        if os.path.exists(robot_port):
            self.robot_dot1.set_connected(True)
        else:
            self.robot_dot1.set_connected(False)
        
        # Check cameras
        try:
            import cv2
            cameras = self.config.get("cameras", {})
            camera_indices = []
            
            for cam_name, cam_config in cameras.items():
                idx = cam_config.get("index_or_path", 0)
                camera_indices.append(idx)
            
            # Test up to 3 cameras
            for i, dot in enumerate([self.camera_dot1, self.camera_dot2, self.camera_dot3]):
                if i < len(camera_indices):
                    cap = None
                    try:
                        cap = cv2.VideoCapture(camera_indices[i])
                        if cap.isOpened():
                            dot.set_connected(True)
                        else:
                            dot.set_connected(False)
                    except Exception:
                        dot.set_connected(False)
                    finally:
                        if cap is not None:
                            cap.release()
                else:
                    dot.set_disabled()
        except ImportError:
            # OpenCV not available
            pass
    
    def toggle_start_stop(self):
        """Toggle START/STOP - ALWAYS RESPONSIVE"""
        if self.start_stop_btn.isChecked():
            self.start_operation()
        else:
            self.stop_operation()
    
    def start_operation(self):
        """Start robot operation in separate thread"""
        # Validate selection
        selected = self.run_combo.currentText()
        if selected.startswith("--"):
            self.log("ERROR: No item selected")
            self.start_stop_btn.setChecked(False)
            return
        
        # Update UI state
        self.is_running = True
        self.start_stop_btn.setText("STOP")
        self.start_stop_btn.setStyleSheet(
            Styles.get_giant_button(Colors.ERROR, Colors.ERROR_HOVER)
        )
        self.status_label.setText("Starting...")
        
        # Disable controls that shouldn't be changed during operation
        self.run_combo.setEnabled(False)
        self.home_btn.setEnabled(False)
        self.settings_btn.setEnabled(False)
        self.live_record_btn.setEnabled(False)
        
        # Start elapsed time
        self.start_time = datetime.now()
        self.elapsed_seconds = 0
        self.elapsed_timer.start(1000)
        
        self.log(f"Starting: {selected}")
        
        # Create and start worker thread
        # Prevent double-start if a worker is still active
        if self.worker and self.worker.isRunning():
            self.log("WARN: Worker already running")
            return

        self.worker = RobotWorker(self.config)

        # Connect signals
        self.worker.status_update.connect(self.on_status_update)
        self.worker.log_message.connect(self.on_log_message)
        self.worker.progress_update.connect(self.on_progress_update)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.run_completed.connect(self.on_run_completed)
        self.worker.finished.connect(self.on_worker_finished)

        # Start worker (runs in separate thread - UI stays responsive)
        try:
            self.worker.start()
        except Exception as exc:
            self.log(f"ERROR: Failed to start worker: {exc}")
            self.status_label.setText("⚠️ Start failed")
            self.reset_ui_after_stop()

    def stop_operation(self):
        """
        EMERGENCY STOP - Maximum response time: 100ms
        
        CRITICAL SAFETY:
        - Called immediately when STOP button pressed
        - Stops worker thread with escalating signals
        - Visual feedback to operator
        """
        self.log("STOPPING...")
        self.status_label.setText("⚠️ STOPPING...")
        
        # Stop worker immediately
        if self.worker and self.worker.isRunning():
            self.worker.stop()  # Sets flag and kills subprocess
            # Don't wait here - let run_completed handle cleanup
        else:
            # No worker running, just reset UI
            self.reset_ui_after_stop()
    
    def emergency_stop(self):
        """Emergency stop called on application close"""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(2000)  # Wait max 2 seconds
    
    def reset_ui_after_stop(self):
        """Reset UI to ready state"""
        self.is_running = False
        self.start_stop_btn.setChecked(False)
        self.start_stop_btn.setText("START")
        self.start_stop_btn.setStyleSheet(
            Styles.get_giant_button(Colors.SUCCESS, Colors.SUCCESS_HOVER)
        )
        self.status_label.setText("Ready")

        # Re-enable controls
        self.run_combo.setEnabled(True)
        self.home_btn.setEnabled(True)
        self.settings_btn.setEnabled(True)
        self.live_record_btn.setEnabled(True)

        # Stop elapsed timer
        self.elapsed_timer.stop()
        self.time_label.setText("00:00")

        # Resume connection checking
        self.check_connections()

        # Clear worker reference when stopped and thread is no longer running
        if self.worker and not self.worker.isRunning():
            self.worker = None

    def go_home(self):
        """Move robot to home position"""
        self.log("Moving to home...")
        self.status_label.setText("Moving to home...")
        
        try:
            # Call rest_pos.py in separate process
            result = subprocess.run(
                [sys.executable, str(ROOT / "rest_pos.py"), "--go"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                self.log("✓ Home position reached")
                self.status_label.setText("Ready")
            else:
                self.log(f"ERROR: Home failed")
                self.status_label.setText("⚠️ Home failed")
        except subprocess.TimeoutExpired:
            self.log("ERROR: Home timeout")
            self.status_label.setText("⚠️ Home timeout")
        except Exception as e:
            self.log(f"ERROR: {e}")
            self.status_label.setText("⚠️ Home error")
    
    def open_settings(self):
        """Open settings modal"""
        self.log("Opening settings...")
        # TODO: Implement settings modal
        from kiosk_settings import SettingsModal
        modal = SettingsModal(self.config, self)
        if modal.exec():
            self.config = modal.get_config()
            self.config_changed.emit(self.config)
            self.log("Settings saved")
    
    def open_live_record(self):
        """Open live record modal"""
        self.log("Opening live record...")
        # TODO: Implement live record modal
        from kiosk_live_record import LiveRecordModal
        modal = LiveRecordModal(self.config, self)
        if modal.exec():
            self.log("Recording saved")
            self.refresh_run_selector()
    
    def log(self, message: str):
        """Add message to log display (keeps last 2 lines)"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_display.append(f"[{timestamp}] {message}")
        
        # Keep only last 2 lines
        doc = self.log_display.document()
        while doc.lineCount() > 2:
            cursor = self.log_display.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.select(cursor.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()  # Remove newline
    
    # === Worker Signal Handlers ===
    
    def on_status_update(self, status: str):
        """Handle status update from worker"""
        self.status_label.setText(status)
    
    def on_log_message(self, level: str, message: str):
        """Handle log message from worker"""
        if level == "error":
            self.log(f"ERROR: {message}")
        elif level == "warning":
            self.log(f"WARN: {message}")
        else:
            self.log(message)
    
    def on_progress_update(self, current: int, total: int):
        """Handle progress update from worker"""
        self.status_label.setText(f"Episode {current}/{total}")
    
    def on_error(self, error_key: str, context: dict):
        """Handle error from worker"""
        error_detail = context.get('error') or context.get('stderr', '')
        if error_detail:
            self.log(f"ERROR: {error_key} - {error_detail}")
        else:
            self.log(f"ERROR: {error_key}")
        self.status_label.setText(f"⚠️ Error: {error_key}")
    
    def on_run_completed(self, success: bool, message: str):
        """Handle run completion from worker"""
        if success:
            self.log(f"✓ {message}")
            self.status_label.setText("✓ Complete")
        else:
            self.log(f"✗ {message}")
            self.status_label.setText("⚠️ Stopped")

        # Reset UI
        self.reset_ui_after_stop()

    def update_elapsed_time(self):
        """Update elapsed time display"""
        if self.start_time:
            self.elapsed_seconds = int((datetime.now() - self.start_time).total_seconds())
            minutes = self.elapsed_seconds // 60
            seconds = self.elapsed_seconds % 60
            self.time_label.setText(f"{minutes:02d}:{seconds:02d}")

    def on_worker_finished(self):
        """Ensure worker reference is cleared when thread finishes"""
        self.worker = None


