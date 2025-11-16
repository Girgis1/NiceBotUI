#!/usr/bin/env python3
"""
LeRobot Operator Console - Main Application with Tab System
Touch-friendly interface for SO-100/101 robot control with action recording
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QPushButton, QButtonGroup, QMessageBox, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, QThread, QObject, Signal
from PySide6.QtGui import QShortcut, QKeySequence

from tabs.dashboard_tab import DashboardTab
from tabs.record_tab import RecordTab
from tabs.sequence_tab import SequenceTab
from tabs.train_tab import TrainTab
from utils.config_store import ConfigStore
from utils.device_manager import DeviceManager
from utils.camera_hub import shutdown_camera_hub

from app.config import (
    CONFIG_PATH,
    create_default_config as build_default_config,
    load_config as load_app_config,
    save_config as save_app_config,
)

from app.bootstrap import create_application, parse_args, should_use_fullscreen
from app.instance_guard import SingleInstanceError, SingleInstanceGuard


# Paths
ROOT = Path(__file__).parent


class MainWindow(QMainWindow):
    """Main application window with tab system"""
    
    def __init__(self, fullscreen=True):
        super().__init__()
        self.config_store = ConfigStore.instance()
        self.config = self.config_store.get_config()
        self.fullscreen_mode = fullscreen
        
        self.setWindowTitle("LeRobot Operator Console")
        self.setMinimumSize(1024, 600)
        
        # Create device manager (shared across all tabs)
        self.device_manager = DeviceManager(self.config)
        
        self.init_ui()
        
        # Add Ctrl+Q shortcut to quit
        quit_shortcut = QShortcut(QKeySequence("Ctrl+Q"), self)
        quit_shortcut.activated.connect(self.close)
        
        # Set fullscreen if requested
        if self.fullscreen_mode:
            self.showFullScreen()
        else:
            self.resize(1024, 600)
    
    def discover_devices_on_startup(self):
        """Run device discovery in a worker thread so UI stays responsive."""
        if getattr(self, "_discovery_thread", None):
            # Discovery already running
            return

        class _DiscoveryWorker(QObject):
            finished = Signal(dict)
            error = Signal(str)

            def __init__(self, manager: DeviceManager):
                super().__init__()
                self.manager = manager

            def run(self) -> None:
                try:
                    result = self.manager.discover_all_devices()
                    self.finished.emit(result)
                except Exception as exc:  # pragma: no cover - defensive
                    self.error.emit(str(exc))

        self._discovery_worker = _DiscoveryWorker(self.device_manager)
        self._discovery_thread = QThread(self)
        self._discovery_worker.moveToThread(self._discovery_thread)
        self._discovery_thread.started.connect(self._discovery_worker.run)
        self._discovery_worker.finished.connect(self._on_discovery_finished)
        self._discovery_worker.error.connect(self._on_discovery_error)
        # Ensure thread resources cleaned up
        self._discovery_worker.finished.connect(self._cleanup_discovery_thread)
        self._discovery_worker.error.connect(self._cleanup_discovery_thread)
        self._discovery_thread.start()

    def _cleanup_discovery_thread(self, *_) -> None:
        thread = getattr(self, "_discovery_thread", None)
        worker = getattr(self, "_discovery_worker", None)
        if worker:
            worker.deleteLater()
        if thread:
            thread.quit()
            thread.wait()
            thread.deleteLater()
        self._discovery_thread = None
        self._discovery_worker = None

    def _on_discovery_finished(self, result: dict) -> None:  # pragma: no cover - UI callback
        # Nothing extra for now; hook available for future UI updates
        _ = result

    def _on_discovery_error(self, message: str) -> None:  # pragma: no cover - UI callback
        QMessageBox.warning(self, "Device Discovery", f"Device discovery error: {message}")
    
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
        sidebar_layout.setSpacing(4)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        
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
                padding: 16px 8px;
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
        
        # Secret hold-to-action timers (define before button bindings)
        self.dashboard_hold_timer = QTimer()
        self.dashboard_hold_timer.setSingleShot(True)
        self.dashboard_hold_timer.setInterval(3500)  # 3.5 seconds
        self.dashboard_hold_timer.timeout.connect(self._on_dashboard_long_press)

        self.settings_hold_timer = QTimer()
        self.settings_hold_timer.setSingleShot(True)
        self.settings_hold_timer.setInterval(3500)  # 3.5 seconds
        self.settings_hold_timer.timeout.connect(self._on_settings_long_press)

        self.dashboard_btn = QPushButton("📊\nDashboard")
        self.dashboard_btn.setCheckable(True)
        self.dashboard_btn.setChecked(True)
        self.dashboard_btn.setStyleSheet(button_style)
        self.dashboard_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.dashboard_btn.clicked.connect(lambda: self.switch_tab(0))
        self.dashboard_btn.pressed.connect(lambda: self._start_hold_timer(self.dashboard_hold_timer))
        self.dashboard_btn.released.connect(self.dashboard_hold_timer.stop)
        self.tab_buttons.addButton(self.dashboard_btn, 0)
        sidebar_layout.addWidget(self.dashboard_btn)
        
        self.sequence_btn = QPushButton("🔗\nSequence")
        self.sequence_btn.setCheckable(True)
        self.sequence_btn.setStyleSheet(button_style)
        self.sequence_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.sequence_btn.clicked.connect(lambda: self.switch_tab(1))
        self.tab_buttons.addButton(self.sequence_btn, 1)
        sidebar_layout.addWidget(self.sequence_btn)
        
        self.record_btn = QPushButton("⏺\nRecord")
        self.record_btn.setCheckable(True)
        self.record_btn.setStyleSheet(button_style)
        self.record_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.record_btn.clicked.connect(lambda: self.switch_tab(2))
        self.tab_buttons.addButton(self.record_btn, 2)
        sidebar_layout.addWidget(self.record_btn)

        self.train_btn = QPushButton("Train")
        self.train_btn.setCheckable(True)
        self.train_btn.setStyleSheet(button_style)
        self.train_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.train_btn.clicked.connect(lambda: self.switch_tab(3))
        self.tab_buttons.addButton(self.train_btn, 3)
        sidebar_layout.addWidget(self.train_btn)

        self.settings_btn = QPushButton("⚙️\nSettings")
        self.settings_btn.setCheckable(True)
        self.settings_btn.setStyleSheet(button_style)
        self.settings_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.settings_btn.clicked.connect(lambda: self.switch_tab(4))
        self.settings_btn.pressed.connect(lambda: self._start_hold_timer(self.settings_hold_timer))
        self.settings_btn.released.connect(self.settings_hold_timer.stop)
        self.tab_buttons.addButton(self.settings_btn, 4)
        sidebar_layout.addWidget(self.settings_btn)

        for index in range(sidebar_layout.count()):
            sidebar_layout.setStretch(index, 1)
        
        # Install event filters for hold detection
        self.dashboard_btn.installEventFilter(self)
        self.settings_btn.installEventFilter(self)
        
        # Content area with stacked widget (takes remaining width)
        self.content_stack = QStackedWidget()
        
        # Create tabs
        from tabs.settings_tab import SettingsTab
        
        self.dashboard_tab = DashboardTab(self.config, self, self.device_manager)
        self.sequence_tab = SequenceTab(self.config, self)
        self.record_tab = RecordTab(self.config, self)
        self.train_tab = TrainTab(self.config, self)
        
        # Connect sequence execution signal
        self.sequence_tab.execute_sequence_signal.connect(self.dashboard_tab.run_sequence)
        self.settings_tab = SettingsTab(self.config, self, self.device_manager)
        
        # Add tabs to stacked widget
        self.content_stack.addWidget(self.dashboard_tab)
        self.content_stack.addWidget(self.sequence_tab)
        self.content_stack.addWidget(self.record_tab)
        self.content_stack.addWidget(self.train_tab)
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

        self.tab5_shortcut = QShortcut(QKeySequence("Ctrl+5"), self)
        self.tab5_shortcut.activated.connect(lambda: self.switch_tab(4))
    
    def switch_tab(self, index: int):
        """Switch to a different tab"""
        previous_index = self.content_stack.currentIndex()
        if previous_index == 0 and index != 0 and hasattr(self, "dashboard_tab"):
            self.dashboard_tab.close_camera_panel()

        if 0 <= index < self.content_stack.count():
            self.content_stack.setCurrentIndex(index)
        # Update button states
        button = self.tab_buttons.button(index)
        if button is not None:
            button.setChecked(True)
    
    def load_config(self):
        """Load configuration using the shared config store."""
        return self.config_store.reload()
    
    def save_config(self):
        """Persist configuration to JSON."""
        self.config_store.save()
    
    def create_default_config(self):
        """Create default configuration with solo/bimanual mode support."""
        return build_default_config()
    
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
    
    def eventFilter(self, obj, event):
        """Handle button press/release events for hold detection"""
        from PySide6.QtCore import QEvent
        
        if obj == self.dashboard_btn:
            if event.type() == QEvent.Leave:
                self.dashboard_hold_timer.stop()
        
        elif obj == self.settings_btn:
            if event.type() == QEvent.Leave:
                self.settings_hold_timer.stop()
        
        return super().eventFilter(obj, event)
    
    def _start_hold_timer(self, timer: QTimer):
        """Start/restart a hold timer when a tab button is pressed."""
        try:
            if timer.isActive():
                timer.stop()
            timer.start(timer.interval())
        except Exception:
            timer.start()
    
    def _on_dashboard_long_press(self):
        """Secret: Hold Dashboard button for 3.5 seconds to restart app"""
        print("[SECRET] Dashboard long press detected - restarting app...")
        try:
            # Save config before restart
            self.save_config()
            # Close cleanly
            shutdown_camera_hub()
            # Restart the app
            import subprocess
            subprocess.Popen([sys.executable] + sys.argv)
            # Exit current instance
            QApplication.quit()
        except Exception as e:
            print(f"[ERROR] Failed to restart app: {e}")
    
    def _on_settings_long_press(self):
        """Secret: Hold Settings button for 3.5 seconds to close app"""
        print("[SECRET] Settings long press detected - closing app...")
        try:
            # Save config before closing
            self.save_config()
            shutdown_camera_hub()
            # Close the application
            QApplication.quit()
        except Exception as e:
            print(f"[ERROR] Failed to close app: {e}")
    
    def closeEvent(self, event):
        """Handle window close event"""
        try:
            # Stop any running operations
            if hasattr(self.dashboard_tab, 'worker') and self.dashboard_tab.worker:
                try:
                    if self.dashboard_tab.worker.isRunning():
                        self.dashboard_tab.worker.stop()
                        self.dashboard_tab.worker.wait(5000)
                except Exception as e:
                    print(f"[WARNING] Error stopping worker: {e}")
            
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


def main():
    """Main entry point."""
    import traceback

    # Protect stdout from BrokenPipeError throughout app lifecycle
    class SafeStdout:
        def __init__(self, original):
            self.original = original

        def write(self, data):
            try:
                self.original.write(data)
                self.original.flush()
            except (BrokenPipeError, OSError):
                pass  # Ignore pipe errors for GUI apps

        def flush(self):
            try:
                self.original.flush()
            except (BrokenPipeError, OSError):
                pass

        def __getattr__(self, name):
            return getattr(self.original, name)

    # Replace stdout and stderr globally
    sys.stdout = SafeStdout(sys.stdout)
    sys.stderr = SafeStdout(sys.stderr)

    sys.excepthook = exception_hook
    args = parse_args()
    fullscreen = should_use_fullscreen(args)

    try:
        with SingleInstanceGuard():
            app = create_application()

            if args.vision:
                from vision_ui import VisionDesignerWindow, create_default_vision_config

                window = VisionDesignerWindow(create_default_vision_config())
                window.show()
                sys.exit(app.exec())

            window = MainWindow(fullscreen=fullscreen)

            screens = app.screens()
            if args.screen < len(screens):
                target_screen = screens[args.screen]
                window.setScreen(target_screen)
                if fullscreen:
                    window.windowHandle().setScreen(target_screen)
                    window.showFullScreen()
                else:
                    screen_geometry = target_screen.geometry()
                    x = screen_geometry.x() + (screen_geometry.width() - 1024) // 2
                    y = screen_geometry.y() + (screen_geometry.height() - 600) // 2
                    window.move(x, y)
                    window.show()
            else:
                window.show()

            sys.exit(app.exec())

    except SingleInstanceError as err:
        print(err)
        sys.exit(1)
    except Exception as e:  # pragma: no cover - startup safety net
        print(f"\n{'='*60}")
        print("FATAL ERROR - Failed to start application")
        print(f"{'='*60}")
        print(f"Error: {e}")
        print(traceback.format_exc())
        print(f"{'='*60}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
