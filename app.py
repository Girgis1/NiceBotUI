#!/usr/bin/env python3
"""
LeRobot Operator Console - Main Application with Tab System
Touch-friendly interface for SO-100/101 robot control with action recording
"""

import sys
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QPushButton, QButtonGroup
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor, QShortcut, QKeySequence

from tabs.dashboard_tab import DashboardTab
from tabs.record_tab import RecordTab
from tabs.sequence_tab import SequenceTab
from utils.device_manager import DeviceManager
from utils.camera_hub import shutdown_camera_hub


# Paths
ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.json"


class MainWindow(QMainWindow):
    """Main application window with tab system"""
    
    def __init__(self, fullscreen=True):
        super().__init__()
        self.config = self.load_config()
        self.fullscreen_mode = fullscreen
        
        self.setWindowTitle("LeRobot Operator Console")
        self.setMinimumSize(1024, 600)
        
        # Create device manager (shared across all tabs)
        self.device_manager = DeviceManager(self.config)
        
        self.init_ui()
        
        # Set fullscreen if requested
        if self.fullscreen_mode:
            self.showFullScreen()
        else:
            self.resize(1024, 600)
    
    def discover_devices_on_startup(self):
        """Run device discovery and update all UI elements"""
        # This will print to terminal and emit signals
        self.device_manager.discover_all_devices()
    
    def showEvent(self, event):
        """Called when window is shown - run device discovery here"""
        super().showEvent(event)
        # Run discovery only once after window is shown
        if not hasattr(self, '_discovery_run'):
            self._discovery_run = True
            # Use QTimer to run discovery after event loop starts
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, self.discover_devices_on_startup)
    
    def init_ui(self):
        """Initialize user interface with tab system"""
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        # Dark mode styling
        # Improved contrast theme for cheap screens
        central.setStyleSheet("""
            QWidget {
                background-color: #2a2a2a;
                color: #ffffff;
            }
        """)
        
        # Main layout: horizontal (tab buttons on left, content on right)
        main_layout = QHBoxLayout(central)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Left sidebar with tab buttons (140px wide) - improved contrast
        sidebar = QWidget()
        sidebar.setFixedWidth(140)
        sidebar.setStyleSheet("""
            QWidget {
                background-color: #3a3a3a;
                border-right: 2px solid #555555;
            }
        """)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setSpacing(8)
        sidebar_layout.setContentsMargins(6, 12, 6, 12)
        
        # Tab buttons
        self.tab_buttons = QButtonGroup(self)
        self.tab_buttons.setExclusive(True)
        
        button_style = """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 #505050, stop:1 #454545);
                color: #e0e0e0;
                border: 2px solid #606060;
                border-radius: 10px;
                padding: 20px 8px;
                min-height: 85px;
                font-size: 18px;
                font-weight: bold;
                text-align: center;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 #606060, stop:1 #555555);
                border-color: #4CAF50;
                color: #ffffff;
            }
            QPushButton:checked {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 #4CAF50, stop:1 #388E3C);
                border: 3px solid #66BB6A;
                color: #ffffff;
            }
        """
        
        self.dashboard_btn = QPushButton("📊\nDashboard")
        self.dashboard_btn.setCheckable(True)
        self.dashboard_btn.setChecked(True)
        self.dashboard_btn.setStyleSheet(button_style)
        self.dashboard_btn.clicked.connect(lambda: self.switch_tab(0))
        self.tab_buttons.addButton(self.dashboard_btn, 0)
        sidebar_layout.addWidget(self.dashboard_btn)
        
        self.sequence_btn = QPushButton("🔗\nSequence")
        self.sequence_btn.setCheckable(True)
        self.sequence_btn.setStyleSheet(button_style)
        self.sequence_btn.clicked.connect(lambda: self.switch_tab(1))
        self.tab_buttons.addButton(self.sequence_btn, 1)
        sidebar_layout.addWidget(self.sequence_btn)
        
        self.record_btn = QPushButton("⏺\nRecord")
        self.record_btn.setCheckable(True)
        self.record_btn.setStyleSheet(button_style)
        self.record_btn.clicked.connect(lambda: self.switch_tab(2))
        self.tab_buttons.addButton(self.record_btn, 2)
        sidebar_layout.addWidget(self.record_btn)
        
        sidebar_layout.addStretch()
        
        self.settings_btn = QPushButton("⚙️\nSettings")
        self.settings_btn.setCheckable(True)
        self.settings_btn.setStyleSheet(button_style)
        self.settings_btn.clicked.connect(lambda: self.switch_tab(3))
        self.tab_buttons.addButton(self.settings_btn, 3)
        sidebar_layout.addWidget(self.settings_btn)
        
        # Content area with stacked widget (takes remaining width)
        self.content_stack = QStackedWidget()
        
        # Create tabs
        from tabs.settings_tab import SettingsTab
        
        self.dashboard_tab = DashboardTab(self.config, self, self.device_manager)
        self.sequence_tab = SequenceTab(self.config, self)
        self.record_tab = RecordTab(self.config, self)
        
        # Connect sequence execution signal
        self.sequence_tab.execute_sequence_signal.connect(self.dashboard_tab.execution_ctrl.run_sequence)
        self.settings_tab = SettingsTab(self.config, self, self.device_manager)
        
        # Add tabs to stacked widget
        self.content_stack.addWidget(self.dashboard_tab)
        self.content_stack.addWidget(self.sequence_tab)
        self.content_stack.addWidget(self.record_tab)
        self.content_stack.addWidget(self.settings_tab)
        
        # Set default tab
        self.content_stack.setCurrentIndex(0)
        
        # Add to main layout
        main_layout.addWidget(sidebar)
        main_layout.addWidget(self.content_stack, stretch=1)
        
        # Add keyboard shortcuts
        # F11 or Escape to toggle fullscreen
        self.fullscreen_shortcut = QShortcut(QKeySequence("F11"), self)
        self.fullscreen_shortcut.activated.connect(self.toggle_fullscreen)
        
        self.escape_shortcut = QShortcut(QKeySequence("Escape"), self)
        self.escape_shortcut.activated.connect(self.exit_fullscreen)
        
        # Tab navigation shortcuts
        self.tab1_shortcut = QShortcut(QKeySequence("Ctrl+1"), self)
        self.tab1_shortcut.activated.connect(lambda: self.switch_tab(0))
        
        self.tab2_shortcut = QShortcut(QKeySequence("Ctrl+2"), self)
        self.tab2_shortcut.activated.connect(lambda: self.switch_tab(1))
        
        self.tab3_shortcut = QShortcut(QKeySequence("Ctrl+3"), self)
        self.tab3_shortcut.activated.connect(lambda: self.switch_tab(2))
        
        self.tab4_shortcut = QShortcut(QKeySequence("Ctrl+4"), self)
        self.tab4_shortcut.activated.connect(lambda: self.switch_tab(3))
    
    def switch_tab(self, index: int):
        """Switch to a different tab"""
        previous_index = self.content_stack.currentIndex()
        if previous_index == 0 and index != 0 and hasattr(self, "dashboard_tab"):
            if hasattr(self.dashboard_tab, 'camera_ctrl'):
                self.dashboard_tab.camera_ctrl.exit_camera_mode()

        self.content_stack.setCurrentIndex(index)
        # Update button states
        if index == 0:
            self.dashboard_btn.setChecked(True)
        elif index == 1:
            self.sequence_btn.setChecked(True)
        elif index == 2:
            self.record_btn.setChecked(True)
        elif index == 3:
            self.settings_btn.setChecked(True)
        else:
            # Guard for future tabs to keep button states in sync
            button = self.tab_buttons.button(index)
            if button is not None:
                button.setChecked(True)
    
    def load_config(self):
        """Load configuration from JSON"""
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, 'r') as f:
                return json.load(f)
        else:
            return self.create_default_config()
    
    def save_config(self):
        """Save configuration to JSON"""
        with open(CONFIG_PATH, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def create_default_config(self):
        """Create default configuration"""
        return {
            "robot": {
                "type": "so100_follower",
                "port": "/dev/ttyACM0",
                "id": "follower_arm",
                "fps": 30,
                "min_time_to_move_multiplier": 3.0,
                "enable_motor_torque": True
            },
            "cameras": {
                "front": {
                    "type": "opencv",
                    "index_or_path": 0,
                    "width": 640,
                    "height": 480,
                    "fps": 30
                }
            },
            "policy": {
                "path": "outputs/train/act_so100/checkpoints/last/pretrained_model",
                "device": "cpu"
            },
            "control": {
                "warmup_time_s": 3,
                "episode_time_s": 25,
                "reset_time_s": 8,
                "num_episodes": 3,
                "single_task": "PickPlace v1",
                "push_to_hub": False,
                "repo_id": None,
                "num_image_writer_processes": 0
            },
            "rest_position": {
                "positions": [2082, 1106, 2994, 2421, 1044, 2054],
                "velocity": 600,
                "disable_torque_on_arrival": True
            },
            "ui": {
                "object_gate": False,
                "roi": [220, 140, 200, 180],
                "presence_threshold": 0.12
            },
            "safety": {
                "soft_limits_deg": [
                    [-90, 90], [-60, 60], [-60, 60],
                    [-90, 90], [-180, 180], [0, 100]
                ],
                "max_speed_scale": 1.0
            }
        }
    
    def open_settings(self):
        """Open settings - now handled by SettingsTab"""
        # Settings are now in the Settings tab (tab 3)
        # This method is kept for compatibility but just switches to settings tab
        self.switch_tab(3)
    
    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        if self.isFullScreen():
            self.showNormal()
            self.resize(1024, 600)
        else:
            self.showFullScreen()
    
    def exit_fullscreen(self):
        """Exit fullscreen mode"""
        if self.isFullScreen():
            self.showNormal()
            self.resize(1024, 600)
    
    def closeEvent(self, event):
        """Handle window close event"""
        try:
            # Stop any running operations through controllers
            if hasattr(self.dashboard_tab, 'execution_ctrl'):
                try:
                    self.dashboard_tab.execution_ctrl.stop_run()
                except Exception as e:
                    print(f"[WARNING] Error stopping execution: {e}")

            if hasattr(self.dashboard_tab, 'camera_ctrl'):
                try:
                    self.dashboard_tab.camera_ctrl.exit_camera_mode()
                except Exception as e:
                    print(f"[WARNING] Error stopping camera: {e}")
            
            if hasattr(self.record_tab, 'is_playing') and self.record_tab.is_playing:
                try:
                    self.record_tab.stop_playback()
                except Exception as e:
                    print(f"[WARNING] Error stopping playback: {e}")
            
            if hasattr(self.sequence_tab, 'is_running') and self.sequence_tab.is_running:
                try:
                    self.sequence_tab.stop_sequence()
                except Exception as e:
                    print(f"[WARNING] Error stopping sequence: {e}")
        except Exception as e:
            print(f"[WARNING] Error in closeEvent: {e}")
        finally:
            # Always accept the close event
            try:
                shutdown_camera_hub()
            except Exception:
                pass
            event.accept()


def exception_hook(exctype, value, traceback_obj):
    """Global exception handler to prevent crashes"""
    import traceback
    error_msg = ''.join(traceback.format_exception(exctype, value, traceback_obj))
    print(f"\n{'='*60}")
    print("CRITICAL ERROR CAUGHT - App will NOT crash!")
    print(f"{'='*60}")
    print(error_msg)
    print(f"{'='*60}\n")
    
    # Try to show error in a message box (if Qt is available)
    try:
        from PySide6.QtWidgets import QMessageBox
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Error Caught")
        msg.setText("An error occurred but the app will continue running.")
        msg.setDetailedText(error_msg)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()
    except:
        pass


def configure_app_palette(app: QApplication):
    """Apply consistent dark palette across entry points."""
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(42, 42, 42))
    palette.setColor(QPalette.WindowText, QColor(255, 255, 255))
    palette.setColor(QPalette.Base, QColor(64, 64, 64))
    palette.setColor(QPalette.AlternateBase, QColor(72, 72, 72))
    palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
    palette.setColor(QPalette.ToolTipText, QColor(0, 0, 0))
    palette.setColor(QPalette.Text, QColor(255, 255, 255))
    palette.setColor(QPalette.Button, QColor(70, 70, 70))
    palette.setColor(QPalette.ButtonText, QColor(255, 255, 255))
    palette.setColor(QPalette.BrightText, QColor(255, 100, 100))
    palette.setColor(QPalette.Link, QColor(76, 175, 80))
    palette.setColor(QPalette.Highlight, QColor(76, 175, 80))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)


def main():
    """Main entry point"""
    import argparse
    import traceback
    
    # Install global exception handler
    sys.excepthook = exception_hook
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="LeRobot Operator Console")
    parser.add_argument('--windowed', action='store_true',
                       help='Start in windowed mode instead of fullscreen')
    parser.add_argument('--no-fullscreen', action='store_true',
                       help='Disable fullscreen mode (same as --windowed)')
    parser.add_argument('--screen', type=int, default=0,
                       help='Screen number to display on (0=primary, 1=secondary, etc.)')
    parser.add_argument('--vision', action='store_true',
                       help='Launch only the vision designer interface')
    args = parser.parse_args()

    # Determine fullscreen mode
    fullscreen = not (args.windowed or args.no_fullscreen)

    try:
        app = QApplication(sys.argv)
        
        # Set application style and palette once
        app.setStyle("Fusion")
        configure_app_palette(app)

        if args.vision:
            from vision_ui import VisionDesignerWindow, create_default_vision_config

            window = VisionDesignerWindow(create_default_vision_config())
            window.show()
            sys.exit(app.exec())
    
        # Create and show main window
        window = MainWindow(fullscreen=fullscreen)
        
        # Move to specified screen
        screens = app.screens()
        if args.screen < len(screens):
            target_screen = screens[args.screen]
            window.setScreen(target_screen)
            if fullscreen:
                # Fullscreen on the target screen
                window.windowHandle().setScreen(target_screen)
                window.showFullScreen()
            else:
                # Center on target screen
                screen_geometry = target_screen.geometry()
                x = screen_geometry.x() + (screen_geometry.width() - 1024) // 2
                y = screen_geometry.y() + (screen_geometry.height() - 600) // 2
                window.move(x, y)
                window.show()
        else:
            window.show()
        
        # Run the application
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"\n{'='*60}")
        print("FATAL ERROR - Failed to start application")
        print(f"{'='*60}")
        print(f"Error: {e}")
        print(traceback.format_exc())
        print(f"{'='*60}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
