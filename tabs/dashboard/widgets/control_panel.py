"""
Control Panel Widgets - Extracted from dashboard_tab.py

Provides reusable control panel components for robot operation.
"""

from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QComboBox, QSlider, QTextEdit, QSizePolicy
)
from PySide6.QtCore import Qt, Signal


class RunSelector(QFrame):
    """Unified run selector with camera toggle button"""

    run_selection_changed = Signal(str)
    checkpoint_changed = Signal(str)
    camera_toggled = Signal(bool)

    def __init__(self, camera_order: Optional[List[str]] = None, parent=None):
        super().__init__(parent)
        self.camera_order = camera_order or []
        self.setFixedHeight(95)
        self.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border: 1px solid #404040;
                border-radius: 6px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 6, 10, 6)

        # Camera toggle button
        self.camera_toggle_btn = QPushButton("Cameras")
        self.camera_toggle_btn.setCheckable(True)
        self.camera_toggle_btn.setMinimumHeight(85)
        self.camera_toggle_btn.setMaximumHeight(85)
        self.camera_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 6px;
                font-size: 18px;
                font-weight: bold;
                padding: 0 12px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
            QPushButton:checked {
                background-color: #c62828;
                border-color: #c62828;
                color: white;
            }
            QPushButton:checked:hover {
                background-color: #b71c1c;
            }
        """)
        self.camera_toggle_btn.toggled.connect(self.camera_toggled.emit)
        self._camera_toggle_default_width = 150
        self.camera_toggle_btn.setMinimumWidth(self._camera_toggle_default_width)
        self.camera_toggle_btn.setMaximumWidth(self._camera_toggle_default_width)
        layout.addWidget(self.camera_toggle_btn)
        self.camera_toggle_btn.setEnabled(bool(self.camera_order))

        # RUN label
        self.run_label = QLabel("RUN:")
        self.run_label.setStyleSheet("color: #ffffff; font-size: 19px; font-weight: bold;")
        layout.addWidget(self.run_label)

        # Main selector (Models, Sequences, Actions)
        self.run_combo = QComboBox()
        self.run_combo.setMinimumHeight(85)
        self.run_combo.setMaximumHeight(85)
        self.run_combo.setStyleSheet("""
            QComboBox {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 6px;
                padding: 6px 40px 6px 12px;
                font-size: 19px;
                font-weight: bold;
            }
            QComboBox:hover {
                border-color: #4CAF50;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 40px;
                border: none;
                padding-right: 6px;
            }
            QComboBox::down-arrow {
                width: 0;
                height: 0;
                border-style: solid;
                border-width: 8px 6px 0 6px;
                border-color: #ffffff transparent transparent transparent;
            }
            QComboBox QAbstractItemView {
                background-color: #404040;
                color: #ffffff;
                selection-background-color: #4CAF50;
                font-size: 16px;
            }
        """)
        self.run_combo.currentTextChanged.connect(self.run_selection_changed.emit)
        layout.addWidget(self.run_combo, stretch=3)

        # Checkpoint selector (only visible for models)
        self.checkpoint_combo = QComboBox()
        self.checkpoint_combo.setMinimumHeight(85)
        self.checkpoint_combo.setMaximumHeight(85)
        self.checkpoint_combo.setStyleSheet("""
            QComboBox {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 6px;
                padding: 6px 40px 6px 12px;
                font-size: 17px;
            }
            QComboBox:hover {
                border-color: #4CAF50;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 40px;
                border: none;
                padding-right: 6px;
            }
            QComboBox::down-arrow {
                width: 0;
                height: 0;
                border-style: solid;
                border-width: 8px 6px 0 6px;
                border-color: #ffffff transparent transparent transparent;
            }
            QComboBox QAbstractItemView {
                background-color: #404040;
                color: #ffffff;
                selection-background-color: #4CAF50;
                font-size: 15px;
            }
        """)
        self.checkpoint_combo.currentTextChanged.connect(self.checkpoint_changed.emit)
        layout.addWidget(self.checkpoint_combo, stretch=1)
        self.checkpoint_combo.hide()  # Hidden by default

    def show_checkpoint_selector(self, visible: bool = True):
        """Show or hide the checkpoint selector"""
        if visible:
            self.checkpoint_combo.show()
        else:
            self.checkpoint_combo.hide()

    def set_run_options(self, options: List[str]):
        """Set the available run options"""
        self.run_combo.clear()
        self.run_combo.addItems(options)

    def set_checkpoint_options(self, options: List[str]):
        """Set the available checkpoint options"""
        self.checkpoint_combo.clear()
        self.checkpoint_combo.addItems(options)

    def get_current_run_selection(self) -> str:
        """Get the currently selected run option"""
        return self.run_combo.currentText()

    def get_current_checkpoint(self) -> str:
        """Get the currently selected checkpoint"""
        return self.checkpoint_combo.currentText()


class ControlButtons(QWidget):
    """Control buttons for robot operation"""

    start_stop_clicked = Signal()
    home_clicked = Signal()
    loop_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(0, 0, 0, 0)

        # Loop button
        self.loop_button = QPushButton("Loop: OFF")
        self.loop_button.setCheckable(True)
        self.loop_button.setMinimumSize(160, 150)
        self.loop_button.setStyleSheet("""
            QPushButton {
                background-color: #666666;
                color: #ffffff;
                border: 2px solid #777777;
                border-radius: 10px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #777777;
            }
            QPushButton:checked {
                background-color: #FF9800;
                border-color: #F57C00;
                color: #000000;
            }
            QPushButton:checked:hover {
                background-color: #F57C00;
            }
        """)
        self.loop_button.toggled.connect(self.loop_toggled.emit)
        layout.addWidget(self.loop_button)

        # START/STOP button
        self.start_stop_btn = QPushButton("START")
        self.start_stop_btn.setMinimumHeight(150)
        self.start_stop_btn.setCheckable(True)
        self.start_stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 32px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
            QPushButton:checked {
                background-color: #c62828;
            }
            QPushButton:checked:hover {
                background-color: #b71c1c;
            }
        """)
        self.start_stop_btn.clicked.connect(self.start_stop_clicked.emit)
        layout.addWidget(self.start_stop_btn, stretch=2)

        # HOME button
        self.home_btn = QPushButton("⌂")
        self.home_btn.setMinimumSize(150, 150)
        self.home_btn.setMaximumWidth(150)
        self.home_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: 2px solid #1976D2;
                border-radius: 10px;
                font-size: 48px;
            }
            QPushButton:hover {
                background-color: #1E88E5;
            }
        """)
        self.home_btn.clicked.connect(self.home_clicked.emit)
        layout.addWidget(self.home_btn)

    def set_loop_enabled(self, enabled: bool):
        """Set the loop button state"""
        self.loop_button.blockSignals(True)
        self.loop_button.setChecked(enabled)
        self.loop_button.blockSignals(False)
        self._update_loop_button_text()

    def _update_loop_button_text(self):
        """Update the loop button text based on state"""
        if self.loop_button.isChecked():
            self.loop_button.setText("Loop: ON")
        else:
            self.loop_button.setText("Loop: OFF")

    def set_start_stop_text(self, text: str):
        """Set the start/stop button text"""
        self.start_stop_btn.setText(text)


class SpeedControl(QWidget):
    """Speed control slider"""

    speed_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignTop)

        self.speed_slider = QSlider(Qt.Vertical)
        self.speed_slider.setRange(10, 120)
        self.speed_slider.setSingleStep(5)
        self.speed_slider.setPageStep(5)
        self.speed_slider.setTickPosition(QSlider.TicksBothSides)
        self.speed_slider.setTickInterval(10)
        self.speed_slider.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.speed_slider.setFixedWidth(40)
        self.speed_slider.setStyleSheet("""
            QSlider::groove:vertical {
                border: 2px solid #4CAF50;
                width: 16px;
                background: #2e2e2e;
                border-radius: 10px;
            }
            QSlider::sub-page:vertical {
                background: #1f1f1f;
                border-radius: 10px;
            }
            QSlider::add-page:vertical {
                background: #4CAF50;
                border-radius: 10px;
            }
            QSlider::handle:vertical {
                background: #4CAF50;
                border: 2px solid #388E3C;
                width: 30px;
                height: 20px;
                margin: -7px 0;
                border-radius: 10px;
            }
            QSlider::handle:vertical:hover {
                background: #388E3C;
            }
        """)
        self.speed_slider.valueChanged.connect(self.speed_changed.emit)
        layout.addWidget(self.speed_slider)

    def set_speed(self, speed: int):
        """Set the speed slider value"""
        self.speed_slider.blockSignals(True)
        self.speed_slider.setValue(speed)
        self.speed_slider.blockSignals(False)

    def get_speed(self) -> int:
        """Get the current speed value"""
        return self.speed_slider.value()


class LogDisplay(QTextEdit):
    """Log display widget"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setStyleSheet("""
            QTextEdit {
                background-color: #2d2d2d;
                color: #ffffff;
                font-family: monospace;
                font-size: 13px;
                border: 1px solid #404040;
                border-radius: 4px;
            }
        """)

    def append_log_entry(self, entry: str):
        """Append a log entry to the display"""
        self.append(entry)
        # Auto-scroll to bottom
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear_logs(self):
        """Clear all log entries"""
        self.clear()
