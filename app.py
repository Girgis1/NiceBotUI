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
from settings_dialog import SettingsDialog


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
        
        self.init_ui()
        
        # Set fullscreen if requested
        if self.fullscreen_mode:
            self.showFullScreen()
        else:
            self.resize(1024, 600)
    
    def init_ui(self):
        """Initialize user interface with tab system"""
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        # Dark mode styling
        central.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                color: #ffffff;
            }
        """)
        
        # Main layout: horizontal (tab buttons on left, content on right)
        main_layout = QHBoxLayout(central)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Left sidebar with tab buttons (70px wide)
        sidebar = QWidget()
        sidebar.setFixedWidth(70)
        sidebar.setStyleSheet("""
            QWidget {
                background-color: #2d2d2d;
            }
        """)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setSpacing(0)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        
        # Tab buttons
        self.tab_buttons = QButtonGroup(self)
        self.tab_buttons.setExclusive(True)
        
        button_style = """
            QPushButton {
                background-color: #2d2d2d;
                color: #ffffff;
                border: none;
                border-right: 3px solid transparent;
                padding: 20px 5px;
                min-height: 100px;
                font-size: 11px;
                font-weight: bold;
                text-align: center;
            }
            QPushButton:hover {
                background-color: #404040;
            }
            QPushButton:checked {
                background-color: #1e1e1e;
                border-right: 3px solid #2196F3;
                color: #2196F3;
            }
        """
        
        self.dashboard_btn = QPushButton("Dashboard")
        self.dashboard_btn.setCheckable(True)
        self.dashboard_btn.setChecked(True)
        self.dashboard_btn.setStyleSheet(button_style)
        self.dashboard_btn.clicked.connect(lambda: self.switch_tab(0))
        self.tab_buttons.addButton(self.dashboard_btn, 0)
        sidebar_layout.addWidget(self.dashboard_btn)
        
        self.sequence_btn = QPushButton("Sequence")
        self.sequence_btn.setCheckable(True)
        self.sequence_btn.setStyleSheet(button_style)
        self.sequence_btn.clicked.connect(lambda: self.switch_tab(1))
        self.tab_buttons.addButton(self.sequence_btn, 1)
        sidebar_layout.addWidget(self.sequence_btn)
        
        self.record_btn = QPushButton("Record")
        self.record_btn.setCheckable(True)
        self.record_btn.setStyleSheet(button_style)
        self.record_btn.clicked.connect(lambda: self.switch_tab(2))
        self.tab_buttons.addButton(self.record_btn, 2)
        sidebar_layout.addWidget(self.record_btn)
        
        sidebar_layout.addStretch()
        
        # Content area with stacked widget (takes remaining width)
        self.content_stack = QStackedWidget()
        
        # Create tabs
        self.dashboard_tab = DashboardTab(self.config, self)
        self.sequence_tab = SequenceTab(self.config, self)
        self.record_tab = RecordTab(self.config, self)
        
        # Connect signals
        self.dashboard_tab.settings_requested.connect(self.open_settings)
        
        # Add tabs to stacked widget
        self.content_stack.addWidget(self.dashboard_tab)
        self.content_stack.addWidget(self.sequence_tab)
        self.content_stack.addWidget(self.record_tab)
        
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
    
    def switch_tab(self, index: int):
        """Switch to a different tab"""
        self.content_stack.setCurrentIndex(index)
        # Update button states
        if index == 0:
            self.dashboard_btn.setChecked(True)
        elif index == 1:
            self.sequence_btn.setChecked(True)
        elif index == 2:
            self.record_btn.setChecked(True)
    
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
        """Open settings dialog"""
        dialog = SettingsDialog(self.config, self)
        if dialog.exec():
            self.config = dialog.config
            self.save_config()
            
            # Update tabs with new config
            self.dashboard_tab.config = self.config
            self.record_tab.config = self.config
            self.sequence_tab.config = self.config
            
            print("[info] Settings saved successfully")
    
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
        # Stop any running operations
        if hasattr(self.dashboard_tab, 'worker') and self.dashboard_tab.worker:
            if self.dashboard_tab.worker.isRunning():
                self.dashboard_tab.worker.stop()
                self.dashboard_tab.worker.wait(5000)
        
        if hasattr(self.record_tab, 'is_playing') and self.record_tab.is_playing:
            self.record_tab.stop_playback()
        
        if hasattr(self.sequence_tab, 'is_running') and self.sequence_tab.is_running:
            self.sequence_tab.stop_sequence()
        
        event.accept()


def main():
    """Main entry point"""
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="LeRobot Operator Console")
    parser.add_argument('--windowed', action='store_true',
                       help='Start in windowed mode instead of fullscreen')
    parser.add_argument('--no-fullscreen', action='store_true',
                       help='Disable fullscreen mode (same as --windowed)')
    args = parser.parse_args()
    
    # Determine fullscreen mode
    fullscreen = not (args.windowed or args.no_fullscreen)
    
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle("Fusion")
    
    # Set dark mode palette
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.WindowText, QColor(255, 255, 255))
    palette.setColor(QPalette.Base, QColor(45, 45, 45))
    palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
    palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
    palette.setColor(QPalette.Text, QColor(255, 255, 255))
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, QColor(255, 255, 255))
    palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
    app.setPalette(palette)
    
    # Create and show main window
    window = MainWindow(fullscreen=fullscreen)
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
