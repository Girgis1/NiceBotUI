#!/usr/bin/env python3
"""
Kiosk Mode Robot Control Application
Production-ready bulletproof UI for industrial robot control
Designed for 1024x600px touchscreen on Nvidia Jetson Orin
"""

import sys
import json
import signal
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPalette, QColor

from kiosk_styles import Colors, Styles
from kiosk_dashboard import KioskDashboard

# Paths
ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.json"


class KioskApplication(QMainWindow):
    """
    Main kiosk application window
    
    Features:
    - Frameless fullscreen for kiosk mode
    - Always-responsive UI with proper threading
    - Clean shutdown handling
    - Touch-optimized for 1024x600px
    """
    
    def __init__(self):
        super().__init__()
        
        # Load configuration
        self.config = self.load_config()
        
        # Window setup
        self.setWindowTitle("Robot Control Kiosk")
        self.setFixedSize(1024, 600)
        
        # Frameless window for kiosk mode
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint
        )
        
        # Initialize UI
        self.init_ui()
        
        # Setup signal handlers for clean shutdown (Docker-friendly)
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def init_ui(self):
        """Initialize user interface"""
        # Set base style
        self.setStyleSheet(Styles.get_base_style())
        
        # Create stacked widget for screens
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        
        # Create dashboard (main screen)
        self.dashboard = KioskDashboard(self.config, self)
        self.stack.addWidget(self.dashboard)
        
        # Connect signals
        self.dashboard.config_changed.connect(self.on_config_changed)
        
        # Show dashboard
        self.stack.setCurrentWidget(self.dashboard)
    
    def load_config(self):
        """Load configuration from JSON"""
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[ERROR] Failed to load config: {e}")
                return self.create_default_config()
        else:
            config = self.create_default_config()
            self.save_config(config)
            return config
    
    def save_config(self, config=None):
        """Save configuration to JSON"""
        if config is None:
            config = self.config
        
        try:
            with open(CONFIG_PATH, 'w') as f:
                json.dump(config, f, indent=2)
            print("[INFO] Configuration saved")
        except Exception as e:
            print(f"[ERROR] Failed to save config: {e}")
    
    def create_default_config(self):
        """Create default configuration"""
        return {
            "robot": {
                "type": "so101_follower",
                "port": "/dev/ttyACM0",
                "id": "follower_arm",
                "fps": 30,
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
                "path": "outputs/train/act_so101/checkpoints/last/pretrained_model",
                "base_path": "outputs/train",
                "device": "cpu"
            },
            "control": {
                "warmup_time_s": 3,
                "episode_time_s": 25,
                "reset_time_s": 8,
                "num_episodes": 3,
            },
            "rest_position": {
                "positions": [2082, 1106, 2994, 2421, 1044, 2054],
                "velocity": 600,
                "disable_torque_on_arrival": True
            }
        }
    
    def on_config_changed(self, new_config):
        """Handle configuration changes from settings"""
        self.config = new_config
        self.save_config(new_config)
        # Update dashboard with new config
        self.dashboard.config = new_config
    
    def closeEvent(self, event):
        """Handle window close - clean shutdown"""
        print("[INFO] Shutting down application...")
        
        # Stop any running operations
        if hasattr(self.dashboard, 'emergency_stop'):
            self.dashboard.emergency_stop()
        
        # Give operations time to stop (max 2 seconds)
        QTimer.singleShot(2000, lambda: None)
        
        # Accept close
        event.accept()
        print("[INFO] Application closed cleanly")
    
    def signal_handler(self, signum, frame):
        """Handle Unix signals for Docker/systemd compatibility"""
        print(f"[INFO] Received signal {signum}, shutting down...")
        self.close()
        QApplication.quit()


def main():
    """Main entry point"""
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Robot Control Kiosk")
    parser.add_argument('--windowed', action='store_true',
                       help='Start in windowed mode (not fullscreen)')
    args = parser.parse_args()
    
    # Create application
    app = QApplication(sys.argv)
    
    # Set application style - Fusion for consistent look
    app.setStyle("Fusion")
    
    # Set dark palette
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(Colors.BG_DARKEST))
    palette.setColor(QPalette.WindowText, QColor(Colors.TEXT_PRIMARY))
    palette.setColor(QPalette.Base, QColor(Colors.BG_MEDIUM))
    palette.setColor(QPalette.AlternateBase, QColor(Colors.BG_DARK))
    palette.setColor(QPalette.ToolTipBase, QColor(Colors.TEXT_PRIMARY))
    palette.setColor(QPalette.ToolTipText, QColor(Colors.BG_DARKEST))
    palette.setColor(QPalette.Text, QColor(Colors.TEXT_PRIMARY))
    palette.setColor(QPalette.Button, QColor(Colors.BG_LIGHT))
    palette.setColor(QPalette.ButtonText, QColor(Colors.TEXT_PRIMARY))
    palette.setColor(QPalette.BrightText, QColor(Colors.ERROR))
    palette.setColor(QPalette.Link, QColor(Colors.INFO))
    palette.setColor(QPalette.Highlight, QColor(Colors.SUCCESS))
    palette.setColor(QPalette.HighlightedText, QColor(Colors.TEXT_PRIMARY))
    app.setPalette(palette)
    
    # Create and show main window
    window = KioskApplication()
    
    if args.windowed:
        window.show()
    else:
        window.showFullScreen()
    
    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()


