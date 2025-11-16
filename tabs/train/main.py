"""
Train Tab - ACT Imitation Learning Data Collection
Dashboard-style horizontal layout for 1024×600px touchscreen
"""

import time
from typing import Optional, Dict, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QProgressBar, QComboBox, QTimer
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPalette, QColor


class TrainTab(QWidget):
    """ACT training data collection tab with dashboard-style layout."""

    # Signals
    training_started = Signal()
    training_stopped = Signal()
    episode_changed = Signal(int)  # episode number

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config

        # Training state
        self.current_model = "pick_and_place_v2"
        self.total_episodes = 50
        self.current_episode = 1
        self.episode_time_limit = 30  # seconds
        self.episode_timer = 0
        self.is_recording = False
        self.is_training = False

        # UI components
        self.train_button = None
        self.control_buttons = []
        self.episode_combo = None
        self.progress_bar = None
        self.timer_label = None
        self.episode_timer_obj = None

        self.init_ui()

    def init_ui(self):
        """Initialize the dashboard-style horizontal UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Status bar (dashboard style)
        status_bar = self._create_status_bar()
        layout.addWidget(status_bar)

        # Main content area
        content_layout = QHBoxLayout()
        content_layout.setSpacing(0)

        # Left panel - Training control center (3/4 width)
        control_panel = self._create_control_panel()
        content_layout.addWidget(control_panel, 3)

        # Right panel - Model status (1/4 width)
        status_panel = self._create_status_panel()
        content_layout.addWidget(status_panel, 1)

        layout.addLayout(content_layout)

        # Full-width progress bar at bottom
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(40)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #424242;
                border-radius: 4px;
                text-align: center;
                background-color: #2d2d2d;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 2px;
            }
        """)
        layout.addWidget(self.progress_bar)

        # Set up episode timer
        self.episode_timer_obj = QTimer()
        self.episode_timer_obj.timeout.connect(self._update_episode_timer)

    def _create_status_bar(self) -> QWidget:
        """Create dashboard-style status bar."""
        status_bar = QFrame()
        status_bar.setFixedHeight(50)
        status_bar.setStyleSheet("""
            QFrame {
                background-color: #1f1f1f;
                border-bottom: 1px solid #363636;
            }
        """)

        layout = QHBoxLayout(status_bar)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(16)

        # Tab indicator
        tab_label = QLabel("🚂 TRAIN TAB")
        tab_label.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        layout.addWidget(tab_label)

        # Timer
        self.timer_label = QLabel("00:00")
        self.timer_label.setStyleSheet("color: #4CAF50; font-size: 14px; font-weight: bold;")
        layout.addWidget(self.timer_label)

        # Current training model
        model_label = QLabel(f"Training: {self.current_model}")
        model_label.setStyleSheet("color: #2196F3; font-size: 12px;")
        layout.addWidget(model_label)

        # Robot/Camera status
        status_label = QLabel("🤖 R:2/2 C:2/2")
        status_label.setStyleSheet("color: #4CAF50; font-size: 12px;")
        layout.addWidget(status_label)

        layout.addStretch()
        return status_bar

    def _create_control_panel(self) -> QWidget:
        """Create the main training control center."""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border-right: 1px solid #424242;
            }
        """)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # Title
        title = QLabel("🎯 TRAINING CONTROL CENTER")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 18px;
                font-weight: bold;
                margin-bottom: 20px;
            }
        """)
        layout.addWidget(title)

        # Big TRAIN button (initial state)
        self.train_button = QPushButton("TRAIN")
        self.train_button.setFixedSize(400, 150)
        self.train_button.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: #FFFFFF;
                border: none;
                border-radius: 20px;
                font-size: 36px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #FB8C00;
            }
            QPushButton:pressed {
                background-color: #EF6C00;
            }
        """)
        self.train_button.clicked.connect(self._toggle_training)
        layout.addWidget(self.train_button, alignment=Qt.AlignCenter)

        # Control buttons (initially hidden)
        self._create_control_buttons(layout)

        layout.addStretch()
        return panel

    def _create_control_buttons(self, parent_layout):
        """Create the control buttons that appear when training starts."""
        buttons_frame = QFrame()
        buttons_layout = QHBoxLayout(buttons_frame)
        buttons_layout.setSpacing(20)

        # Previous episode button
        prev_btn = self._create_control_button("[<]\nPrevious\nEpisode", "#2196F3")
        prev_btn.clicked.connect(self._previous_episode)
        buttons_layout.addWidget(prev_btn)
        self.control_buttons.append(prev_btn)

        # Pause/Resume button
        self.pause_btn = self._create_control_button("[PAUSE]\nTraining", "#FF9800")
        self.pause_btn.clicked.connect(self._toggle_pause)
        buttons_layout.addWidget(self.pause_btn)
        self.control_buttons.append(self.pause_btn)

        # Next episode button
        next_btn = self._create_control_button("[>]\nNext\nEpisode", "#4CAF50")
        next_btn.clicked.connect(self._next_episode)
        buttons_layout.addWidget(next_btn)
        self.control_buttons.append(next_btn)

        # Initially hide control buttons
        buttons_frame.hide()
        self.control_buttons_frame = buttons_frame
        parent_layout.addWidget(buttons_frame, alignment=Qt.AlignCenter)

    def _create_control_button(self, text: str, color: str) -> QPushButton:
        """Create a control button with consistent styling."""
        btn = QPushButton(text)
        btn.setFixedSize(180, 120)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 15px;
                font-size: 16px;
                font-weight: bold;
                text-align: center;
            }}
            QPushButton:hover {{
                background-color: {self._adjust_color(color, 1.1)};
            }}
            QPushButton:pressed {{
                background-color: {self._adjust_color(color, 0.9)};
            }}
        """)
        return btn

    def _create_status_panel(self) -> QWidget:
        """Create the right-side status panel with model and episode info."""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #252525;
            }
        """)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Model Status Section
        model_group = self._create_model_status()
        layout.addWidget(model_group)

        # Episode Status Section
        episode_group = self._create_episode_status()
        layout.addWidget(episode_group)

        layout.addStretch()
        return panel

    def _create_model_status(self) -> QFrame:
        """Create the model status section."""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #1f1f1f;
                border: 1px solid #363636;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("MODEL STATUS")
        title.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: bold;")
        layout.addWidget(title)

        # Model info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        model_name = QLabel(f"Name: {self.current_model}")
        model_name.setStyleSheet("color: #B0BEC5; font-size: 11px;")
        info_layout.addWidget(model_name)

        episodes = QLabel(f"Episodes: {self.total_episodes}")
        episodes.setStyleSheet("color: #B0BEC5; font-size: 11px;")
        info_layout.addWidget(episodes)

        size = QLabel("Size: 2.4GB")
        size.setStyleSheet("color: #B0BEC5; font-size: 11px;")
        info_layout.addWidget(size)

        status = QLabel("Status: Ready")
        status.setStyleSheet("color: #4CAF50; font-size: 11px; font-weight: bold;")
        info_layout.addWidget(status)

        layout.addLayout(info_layout)

        # Action buttons
        sync_btn = QPushButton("SYNC TO PC")
        sync_btn.setFixedHeight(35)
        sync_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        layout.addWidget(sync_btn)

        train_btn = QPushButton("TRAIN REMOTE")
        train_btn.setFixedHeight(35)
        train_btn.setStyleSheet("""
            QPushButton {
                background-color: #666666;
                color: #999999;
                border: none;
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:enabled {
                background-color: #4CAF50;
                color: white;
            }
        """)
        train_btn.setEnabled(False)  # Disabled on Jetson
        layout.addWidget(train_btn)

        return frame

    def _create_episode_status(self) -> QFrame:
        """Create the episode status section."""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #1f1f1f;
                border: 1px solid #363636;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("EPISODE STATUS")
        title.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: bold;")
        layout.addWidget(title)

        # Episode selector and navigation
        selector_layout = QHBoxLayout()
        selector_layout.setSpacing(8)

        episode_label = QLabel("Episode:")
        episode_label.setStyleSheet("color: #B0BEC5; font-size: 11px;")
        selector_layout.addWidget(episode_label)

        self.episode_combo = QComboBox()
        self.episode_combo.addItems([f"{i}" for i in range(1, self.total_episodes + 1)])
        self.episode_combo.setCurrentIndex(self.current_episode - 1)
        self.episode_combo.setFixedWidth(60)
        self.episode_combo.currentIndexChanged.connect(self._episode_selected)
        selector_layout.addWidget(self.episode_combo)

        # Navigation arrows
        prev_arrow = QPushButton("◀️")
        prev_arrow.setFixedSize(30, 25)
        prev_arrow.clicked.connect(self._previous_episode)
        selector_layout.addWidget(prev_arrow)

        next_arrow = QPushButton("▶️")
        next_arrow.setFixedSize(30, 25)
        next_arrow.clicked.connect(self._next_episode)
        selector_layout.addWidget(next_arrow)

        # Progress indicator
        progress_label = QLabel("Progress: ████░░░")
        progress_label.setStyleSheet("color: #FF9800; font-size: 11px; font-family: monospace;")
        selector_layout.addWidget(progress_label)

        layout.addLayout(selector_layout)

        # Episode details
        details_layout = QVBoxLayout()
        details_layout.setSpacing(4)

        timer = QLabel("Timer: 00:15 / 00:30")
        timer.setStyleSheet("color: #B0BEC5; font-size: 11px;")
        details_layout.addWidget(timer)

        recording_status = QLabel("Status: READY")
        recording_status.setStyleSheet("color: #4CAF50; font-size: 11px; font-weight: bold;")
        details_layout.addWidget(recording_status)

        actions = QLabel("Actions: 0")
        actions.setStyleSheet("color: #B0BEC5; font-size: 11px;")
        details_layout.addWidget(actions)

        quality = QLabel("Quality: ✓")
        quality.setStyleSheet("color: #4CAF50; font-size: 11px;")
        details_layout.addWidget(quality)

        layout.addLayout(details_layout)

        return frame

    def _adjust_color(self, color: str, factor: float) -> str:
        """Adjust color brightness by factor."""
        # Simple color adjustment for hover/press effects
        if color.startswith('#'):
            # For now, just return the original color
            # Could implement proper color adjustment if needed
            return color
        return color

    def _toggle_training(self):
        """Toggle training mode - morph the UI."""
        if not self.is_training:
            self._start_training()
        else:
            self._stop_training()

    def _start_training(self):
        """Start training mode - show control buttons."""
        self.is_training = True
        self.training_started.emit()

        # Hide big TRAIN button
        self.train_button.hide()

        # Show control buttons
        self.control_buttons_frame.show()

        # Update UI state
        self._update_ui_state()

    def _stop_training(self):
        """Stop training mode - show big TRAIN button."""
        self.is_training = False
        self.training_stopped.emit()

        # Stop episode timer
        if self.episode_timer_obj and self.episode_timer_obj.isActive():
            self.episode_timer_obj.stop()

        # Hide control buttons
        self.control_buttons_frame.hide()

        # Show big TRAIN button
        self.train_button.show()

        # Update UI state
        self._update_ui_state()

    def _toggle_pause(self):
        """Toggle recording pause state."""
        self.is_recording = not self.is_recording

        if self.is_recording:
            self.pause_btn.setText("[PAUSE]\nTraining")
            self.pause_btn.setStyleSheet("""
                QPushButton {
                    background-color: #FF5722;
                    color: white;
                    border: none;
                    border-radius: 15px;
                    font-size: 16px;
                    font-weight: bold;
                    text-align: center;
                }
            """)
            self._start_episode_timer()
        else:
            self.pause_btn.setText("[RESUME]\nTraining")
            self.pause_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    border-radius: 15px;
                    font-size: 16px;
                    font-weight: bold;
                    text-align: center;
                }
            """)
            if self.episode_timer_obj and self.episode_timer_obj.isActive():
                self.episode_timer_obj.stop()

    def _previous_episode(self):
        """Navigate to previous episode."""
        if self.current_episode > 1:
            self.current_episode -= 1
            self._update_episode_display()
            self.episode_changed.emit(self.current_episode)

    def _next_episode(self):
        """Navigate to next episode."""
        if self.current_episode < self.total_episodes:
            self.current_episode += 1
            self._update_episode_display()
            self.episode_changed.emit(self.current_episode)

    def _episode_selected(self, index: int):
        """Handle episode selection from dropdown."""
        self.current_episode = index + 1
        self.episode_changed.emit(self.current_episode)

    def _start_episode_timer(self):
        """Start the episode recording timer."""
        self.episode_timer = 0
        self.episode_timer_obj.start(1000)  # Update every second

    def _update_episode_timer(self):
        """Update the episode timer display."""
        self.episode_timer += 1

        minutes = self.episode_timer // 60
        seconds = self.episode_timer % 60
        current_time = f"{minutes:02d}:{seconds:02d}"

        total_minutes = self.episode_time_limit // 60
        total_seconds = self.episode_time_limit % 60
        total_time = f"{total_minutes:02d}:{total_seconds:02d}"

        self.timer_label.setText(f"{current_time} / {total_time}")

        # Update progress bar
        if self.progress_bar:
            progress = min(100, (self.episode_timer / self.episode_time_limit) * 100)
            self.progress_bar.setValue(int(progress))

        # Auto-stop when time limit reached
        if self.episode_timer >= self.episode_time_limit:
            self._toggle_pause()

    def _update_episode_display(self):
        """Update episode display in UI."""
        if self.episode_combo:
            self.episode_combo.blockSignals(True)
            self.episode_combo.setCurrentIndex(self.current_episode - 1)
            self.episode_combo.blockSignals(False)

    def _update_ui_state(self):
        """Update the overall UI state."""
        # Update progress bar based on training state
        if self.progress_bar:
            if self.is_training:
                self.progress_bar.setValue(0)
                self.progress_bar.show()
            else:
                self.progress_bar.hide()

    def closeEvent(self, event):
        """Clean up on close."""
        if self.episode_timer_obj and self.episode_timer_obj.isActive():
            self.episode_timer_obj.stop()
        super().closeEvent(event)
