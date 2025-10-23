"""
Dashboard Tab - Main robot control interface
This is the existing UI refactored as a tab
"""

import sys
import os
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple
import pytz

try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    cv2 = None
    np = None

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTextEdit, QComboBox, QSizePolicy, QSpinBox, QSlider,
    QStackedWidget, QDialog
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QImage, QPixmap

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from robot_worker import RobotWorker
from utils.execution_manager import ExecutionWorker
from utils.camera_hub import CameraStreamHub

# Timezone
TIMEZONE = pytz.timezone('Australia/Sydney')
ROOT = Path(__file__).parent.parent
HISTORY_PATH = ROOT / "run_history.json"


class CircularProgress(QWidget):
    """Circular progress indicator"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.progress = 0
        self.setFixedSize(24, 24)
        self.setVisible(True)  # Always visible
    
    def set_progress(self, value):
        self.progress = value
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        pen = QPen(QColor("#555555"), 2)
        painter.setPen(pen)
        painter.setBrush(QColor("#2d2d2d"))
        painter.drawEllipse(2, 2, 20, 20)
        
        if self.progress > 0:
            pen = QPen(QColor("#4CAF50"), 3)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            
            start_angle = -90 * 16
            span_angle = -(self.progress * 360 // 100) * 16
            
            painter.drawArc(3, 3, 18, 18, start_angle, span_angle)


class StatusIndicator(QLabel):
    """Colored dot indicator"""
    
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.connected = False
        self.warning = False
        self.null = False  # Initialize null attribute
        self.update_style()
    
    def set_connected(self, connected):
        self.connected = connected
        self.warning = False
        self.null = False  # Clear null state when setting connected
        self.update_style()
    
    def set_warning(self):
        self.connected = False
        self.warning = True
        self.null = False  # Clear null state when setting warning
        self.update_style()
    
    def set_null(self):
        """Set as null/empty indicator"""
        self.connected = False
        self.warning = False
        self.null = True
        self.update_style()
    
    def update_style(self):
        if hasattr(self, 'null') and self.null:
            # Null indicator - unfilled black circle
            self.setFixedSize(20, 20)
            self.setStyleSheet("""
                QLabel {
                    background-color: transparent;
                    border: 2px solid #606060;
                    border-radius: 10px;
                }
            """)
        elif self.warning:
            color = "#FF9800"
            self.setFixedSize(20, 20)
            self.setStyleSheet(f"""
                QLabel {{
                    background-color: {color};
                    border-radius: 10px;
                }}
            """)
        elif self.connected:
            color = "#2e7d32"
            self.setFixedSize(20, 20)
            self.setStyleSheet(f"""
                QLabel {{
                    background-color: {color};
                    border-radius: 10px;
                }}
            """)
        else:
            color = "#f44336"
            self.setFixedSize(20, 20)
            self.setStyleSheet(f"""
                QLabel {{
                    background-color: {color};
                    border-radius: 10px;
                }}
            """)


class CameraPreviewWidget(QFrame):
    """Single camera preview with overlay-ready QLabel."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("singleCameraPreview")
        self.setStyleSheet("""
            #singleCameraPreview {
                border: 1px solid #404040;
                border-radius: 8px;
                background-color: #151515;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.header_row = QHBoxLayout()
        self.header_row.setContentsMargins(0, 0, 0, 0)
        self.header_row.setSpacing(8)

        self.camera_label = QLabel("Camera")
        self.camera_label.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: bold;")
        self.header_row.addWidget(self.camera_label)
        self.header_row.addStretch()

        self.status_chip = QLabel("")
        self.status_chip.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status_chip.setStyleSheet(
            "color: #a0a0a0; font-size: 11px; padding: 2px 6px; border-radius: 4px; background-color: #2b2b2b;"
        )
        self.status_chip.hide()
        self.header_row.addWidget(self.status_chip)

        layout.addLayout(self.header_row)

        self.preview_label = QLabel("Camera preview disabled")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("color: #777777; font-size: 12px;")
        self.preview_label.setScaledContents(True)
        self.preview_label.setMinimumSize(320, 200)
        layout.addWidget(self.preview_label, stretch=1)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def update_preview(
        self, pixmap: Optional[QPixmap], message: Optional[str] = None, status: Optional[str] = None
    ) -> None:
        if status:
            self.status_chip.setText(status)
            self.status_chip.show()
        else:
            self.status_chip.hide()

        if pixmap is None:
            if message:
                self.preview_label.setText(message)
            else:
                self.preview_label.setText("No camera feed")
            self.preview_label.setPixmap(QPixmap())
        else:
            self.preview_label.setPixmap(pixmap)
            self.preview_label.setText("")

    def set_camera_name(self, name: str) -> None:
        self.camera_label.setText(name)


class CameraDetailDialog(QDialog):
    """Large detailed camera preview in a dialog powered by the camera hub."""

    def __init__(
        self,
        camera_name: str,
        camera_config: dict,
        vision_zones: List[dict],
        render_callback,
        camera_hub: Optional[CameraStreamHub],
        parent=None,
    ):
        super().__init__(parent)
        self.camera_name = camera_name
        self.camera_config = camera_config
        self.vision_zones = vision_zones
        self.render_callback = render_callback
        self.camera_hub = camera_hub

        self.setWindowTitle(f"Camera Preview - {camera_name}")
        self.setModal(True)
        self.resize(900, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        self.preview_label = QLabel("Initializing camera…")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("color: #f0f0f0; font-size: 14px;")
        self.preview_label.setMinimumSize(640, 360)
        self.preview_label.setScaledContents(True)
        layout.addWidget(self.preview_label, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #f0f0f0; font-size: 12px;")
        layout.addWidget(self.status_label)

        self.timer = QTimer(self)
        self.timer.setInterval(70)  # ~14 FPS
        self.timer.timeout.connect(self._update_frame)
        self.timer.start()

    def _update_frame(self):
        if cv2 is None or np is None:
            self.status_label.setText("OpenCV/NumPy missing. Install dependencies.")
            return
        if not self.camera_hub:
            self.status_label.setText("Camera hub unavailable.")
            self.preview_label.setText("No shared camera stream.")
            return

        frame = self.camera_hub.get_frame(self.camera_name, preview=False)
        if frame is None:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("Camera offline.")
            self.status_label.setText("No frames available.")
            return

        render_frame, status = self.render_callback(self.camera_name, frame.copy(), self.vision_zones)
        rgb = cv2.cvtColor(render_frame, cv2.COLOR_BGR2RGB)
        height, width, channel = rgb.shape
        image = QImage(rgb.data, width, height, channel * width, QImage.Format_RGB888)
        self.preview_label.setPixmap(QPixmap.fromImage(image))
        status_text = {
            "triggered": "Active detection",
            "idle": "Monitoring",
            "nominal": "Live preview",
            "offline": "Offline",
            "no_vision": "No vision zones configured",
        }
        self.status_label.setText(status_text.get(status, ""))

    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)


class DashboardTab(QWidget):
    """Main dashboard for robot control (existing UI)"""
    
    def __init__(self, config: dict, parent=None, device_manager=None):
        super().__init__(parent)
        self.config = config
        self.device_manager = device_manager
        self.worker = None
        self.execution_worker = None  # New unified execution worker
        self.start_time = None
        self.elapsed_seconds = 0
        self.is_running = False
        self._vision_state_active = False
        self._last_vision_signature = None

        control_cfg = self.config.setdefault("control", {})
        self.master_speed = float(control_cfg.get("speed_multiplier", 1.0))
        if not 0.1 <= self.master_speed <= 1.2:
            self.master_speed = 1.0
        control_cfg["speed_multiplier"] = self.master_speed

        self.loop_enabled = control_cfg.get("loop_enabled", True)
        control_cfg["loop_enabled"] = self.loop_enabled

        self._speed_initialized = False

        self.camera_view_active = False
        self.camera_order: List[str] = list(self.config.get("cameras", {}).keys())
        self.vision_zones = self._load_vision_zones()
        self._robot_status = "empty"
        self._robot_total = 1 if self.config.get("robot") else 0
        self._camera_status: Dict[str, str] = {
            name: "empty" for name in self.camera_order
        }
        self.robot_indicator1: Optional[StatusIndicator] = None
        self.robot_indicator2: Optional[StatusIndicator] = None
        self.camera_indicator1: Optional[StatusIndicator] = None
        self.camera_indicator2: Optional[StatusIndicator] = None
        self.camera_indicator3: Optional[StatusIndicator] = None
        self.camera_front_circle: Optional[StatusIndicator] = None
        self.camera_wrist_circle: Optional[StatusIndicator] = None
        self.compact_throbber: Optional[CircularProgress] = None
        self.camera_hub: Optional[CameraStreamHub] = None
        if cv2 is not None and np is not None:
            try:
                self.camera_hub = CameraStreamHub.instance(self.config)
            except Exception:
                self.camera_hub = None
        self.active_camera_index = 0
        self.active_camera_name: Optional[str] = self.camera_order[0] if self.camera_order else None
        self.active_vision_zones: Dict[str, List[dict]] = {}
        self._last_preview_timestamp = 0.0

        self.camera_preview_timer = QTimer(self)
        self.camera_preview_timer.timeout.connect(self.update_camera_previews)
        
        self.init_ui()
        self._update_status_summaries()
        self.validate_config()
        
        # Connect device manager signals if available
        if self.device_manager:
            self.device_manager.robot_status_changed.connect(self.on_robot_status_changed)
            self.device_manager.camera_status_changed.connect(self.on_camera_status_changed)
            self.device_manager.discovery_log.connect(self.on_discovery_log)
        
        # Timers
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_elapsed_time)
        
        # Connection checking is now handled by device_manager
        # self.connection_check_timer = QTimer()
        # self.connection_check_timer.timeout.connect(self.check_connections_background)
        # self.connection_check_timer.start(10000)
        
        self.throbber_progress = 0
        self.throbber_update_timer = QTimer()
        self.throbber_update_timer.timeout.connect(self.update_throbber_progress)
        self.throbber_update_timer.start(100)
    
    def init_ui(self):
        """Initialize UI - same as original app.py"""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Compact single-line status bar
        status_bar = QHBoxLayout()
        status_bar.setSpacing(18)

        self.normal_status_container = QWidget()
        normal_status_layout = QHBoxLayout(self.normal_status_container)
        normal_status_layout.setSpacing(18)
        normal_status_layout.setContentsMargins(0, 0, 0, 0)

        self.throbber = CircularProgress()
        normal_status_layout.addWidget(self.throbber)

        robot_group = QHBoxLayout()
        robot_group.setSpacing(6)
        self.robot_lbl = QLabel("Robot")
        self.robot_lbl.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        robot_group.addWidget(self.robot_lbl)
        self.robot_indicator1 = StatusIndicator()
        self.robot_indicator1.set_null()
        robot_group.addWidget(self.robot_indicator1)
        self.robot_indicator2 = StatusIndicator()
        self.robot_indicator2.set_null()
        robot_group.addWidget(self.robot_indicator2)
        normal_status_layout.addLayout(robot_group)

        self.robot_status_circle = self.robot_indicator1

        camera_group = QHBoxLayout()
        camera_group.setSpacing(6)
        self.camera_lbl = QLabel("Cameras")
        self.camera_lbl.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        camera_group.addWidget(self.camera_lbl)
        self.camera_indicator1 = StatusIndicator()
        self.camera_indicator1.set_null()
        camera_group.addWidget(self.camera_indicator1)
        self.camera_indicator2 = StatusIndicator()
        self.camera_indicator2.set_null()
        camera_group.addWidget(self.camera_indicator2)
        self.camera_indicator3 = StatusIndicator()
        self.camera_indicator3.set_null()
        camera_group.addWidget(self.camera_indicator3)
        normal_status_layout.addLayout(camera_group)

        self.camera_front_circle = self.camera_indicator1
        self.camera_wrist_circle = self.camera_indicator2

        status_bar.addWidget(self.normal_status_container, stretch=0)

        self.status_summary_container = QWidget()
        summary_layout = QVBoxLayout(self.status_summary_container)
        summary_layout.setSpacing(2)
        summary_layout.setContentsMargins(0, 0, 0, 0)

        self.compact_throbber = CircularProgress()
        summary_layout.addWidget(self.compact_throbber, alignment=Qt.AlignHCenter)

        self.robot_summary_label = QLabel("R:0/1")
        self.robot_summary_label.setAlignment(Qt.AlignCenter)
        self.robot_summary_label.setStyleSheet("color: #a0a0a0; font-size: 11px; font-weight: bold;")
        summary_layout.addWidget(self.robot_summary_label)

        self.camera_summary_label = QLabel("C:0/0")
        self.camera_summary_label.setAlignment(Qt.AlignCenter)
        self.camera_summary_label.setStyleSheet("color: #a0a0a0; font-size: 11px; font-weight: bold;")
        summary_layout.addWidget(self.camera_summary_label)

        self.status_summary_container.hide()
        status_bar.addWidget(self.status_summary_container, stretch=0)

        self.time_label = QLabel("00:00")
        self.time_label.setStyleSheet("color: #4CAF50; font-size: 12px; font-weight: bold; font-family: monospace;")
        status_bar.addWidget(self.time_label)

        self.action_label = QLabel("At home position")
        self._action_label_style_template = (
            "color: #ffffff; font-size: 14px; font-weight: bold; "
            "background-color: {bg}; border-radius: 4px; padding: 8px 20px;"
        )
        self._set_action_label_style("#383838")
        self.action_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        status_bar.addWidget(self.action_label, stretch=1)

        # Unified RUN selector with camera toggle button
        run_frame = QFrame()
        run_frame.setFixedHeight(95)
        run_frame.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border: 1px solid #404040;
                border-radius: 6px;
            }
        """)
        run_layout = QHBoxLayout(run_frame)
        run_layout.setSpacing(10)
        run_layout.setContentsMargins(10, 6, 10, 6)

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
        self.camera_toggle_btn.toggled.connect(self.on_camera_toggle)
        self._camera_toggle_default_width = 150
        self.camera_toggle_btn.setMinimumWidth(self._camera_toggle_default_width)
        self.camera_toggle_btn.setMaximumWidth(self._camera_toggle_default_width)
        run_layout.addWidget(self.camera_toggle_btn)
        self.camera_toggle_btn.setEnabled(bool(self.camera_order))

        # RUN label - hidden when cameras open
        self.run_label = QLabel("RUN:")
        self.run_label.setStyleSheet("color: #ffffff; font-size: 19px; font-weight: bold;")
        run_layout.addWidget(self.run_label)
        
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
        self.run_combo.currentTextChanged.connect(self.on_run_selection_changed)
        run_layout.addWidget(self.run_combo, stretch=3)
        
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
        self.checkpoint_combo.currentTextChanged.connect(self.on_checkpoint_changed)
        run_layout.addWidget(self.checkpoint_combo, stretch=1)
        self.checkpoint_combo.hide()  # Hidden by default
        
        # Assemble top container with optional camera panel
        top_container = QHBoxLayout()
        top_container.setSpacing(15)

        # Camera panel on LEFT (between tabs and status bar)
        self.camera_panel = QFrame()
        self.camera_panel.setStyleSheet("""
            QFrame {
                background-color: #1f1f1f;
                border: 1px solid #404040;
                border-radius: 8px;
            }
        """)
        self.camera_panel_layout = QVBoxLayout(self.camera_panel)
        self.camera_panel_layout.setContentsMargins(10, 10, 10, 10)
        self.camera_panel_layout.setSpacing(8)
        self.camera_panel.setVisible(False)

        self.single_camera_preview = CameraPreviewWidget()
        self.single_camera_preview.clicked.connect(
            lambda: self.open_camera_detail(self.active_camera_name) if self.active_camera_name else None
        )
        self.camera_panel_layout.addWidget(self.single_camera_preview, stretch=1)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        button_row.addStretch()
        self.camera_cycle_btn = QPushButton("⟳ Cycle")
        self.camera_cycle_btn.setCursor(Qt.PointingHandCursor)
        self.camera_cycle_btn.setStyleSheet("""
            QPushButton {
                background-color: #2f2f2f;
                color: #ffffff;
                border: 1px solid #505050;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
            }
        """)
        self.camera_cycle_btn.clicked.connect(self.cycle_active_camera)
        button_row.addWidget(self.camera_cycle_btn)
        self.camera_panel_layout.addLayout(button_row)

        top_container.addWidget(self.camera_panel, stretch=2)

        # Status bar and controls on RIGHT
        left_column = QVBoxLayout()
        left_column.setSpacing(12)
        left_column.addLayout(status_bar)
        left_column.addWidget(run_frame)
        top_container.addLayout(left_column, stretch=3)

        layout.addLayout(top_container)
        
        # Body layout: controls on left, speed override on right
        body_layout = QHBoxLayout()
        body_layout.setSpacing(15)

        controls_column = QVBoxLayout()
        controls_column.setSpacing(15)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(20)

        self.loop_button = QPushButton()
        self.loop_button.setCheckable(True)
        self.loop_button.setMinimumSize(160, 150)
        self.loop_button.toggled.connect(self.on_loop_button_toggled)
        controls_row.addWidget(self.loop_button)
        self.loop_button.blockSignals(True)
        self.loop_button.setChecked(self.loop_enabled)
        self.loop_button.blockSignals(False)
        self._refresh_loop_button()

        # Time - Simple labeled spinbox
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
        self.start_stop_btn.clicked.connect(self.toggle_start_stop)
        controls_row.addWidget(self.start_stop_btn, stretch=2)
        
        # HOME button - matches START button height
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
        self.home_btn.clicked.connect(self.go_home)
        controls_row.addWidget(self.home_btn)
        controls_column.addLayout(controls_row)

        # Log text area (expand to fill height)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #2d2d2d;
                color: #ffffff;
                font-family: monospace;
                font-size: 13px;
                border: 1px solid #404040;
                border-radius: 4px;
            }
        """)
        controls_column.addWidget(self.log_text, stretch=1)
        self._log_icon_map = {
            "info": "ℹ️",
            "success": "✅",
            "warning": "⚠️",
            "error": "❌",
            "action": "▶️",
            "vision": "👀",
        }

        # Speed slider column - fill maximum height
        speed_column = QVBoxLayout()
        speed_column.setSpacing(10)
        speed_column.setContentsMargins(0, 0, 0, 0)
        speed_column.setAlignment(Qt.AlignTop)

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
                background: #ffffff;
                border: 3px solid #4CAF50;
                height: 36px;
                width: 36px;
                margin: 0 -12px;
                border-radius: 18px;
            }
        """)
        speed_column.addWidget(self.speed_slider, alignment=Qt.AlignHCenter)
        self.speed_slider.valueChanged.connect(self.on_speed_slider_changed)

        self.speed_value_label = QLabel("")
        self.speed_value_label.setStyleSheet("color: #4CAF50; font-size: 28px; font-weight: bold; padding: 12px;")
        self.speed_value_label.setAlignment(Qt.AlignCenter)
        speed_column.addWidget(self.speed_value_label)

        body_layout.addLayout(controls_column, stretch=5)
        body_layout.addLayout(speed_column, stretch=1)
        layout.addLayout(body_layout)
        self._refresh_active_camera_label()

        # Welcome message
        self._append_log("NiceBot Dashboard ready.", level="success")
        self._append_log("Choose Record or Sequence to begin a run.")

        # Populate run selector
        self.refresh_run_selector()

        initial_speed = int(round(self.master_speed * 100))
        self.speed_slider.blockSignals(True)
        self.speed_slider.setValue(initial_speed)
        self.speed_slider.blockSignals(False)
        self.on_speed_slider_changed(initial_speed)
    
    def refresh_run_selector(self):
        """Populate RUN dropdown with Models, Sequences, and Actions"""
        self.run_combo.blockSignals(True)
        self.run_combo.clear()

        # Add header (disabled item)
        self.run_combo.addItem("-- Select Item --")
        self.run_combo.model().item(0).setEnabled(False)
        
        # Import managers
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from utils.actions_manager import ActionsManager
        from utils.sequences_manager import SequencesManager
        
        actions_mgr = ActionsManager()
        sequences_mgr = SequencesManager()
        
        # Add Models first (Green)
        try:
            train_dir = Path(self.config["policy"].get("base_path", ""))
            if train_dir.exists():
                for item in sorted(train_dir.iterdir()):
                    if item.is_dir() and (item / "checkpoints").exists():
                        self.run_combo.addItem(f"🤖 Model: {item.name}")
        except Exception as e:
            print(f"[DASHBOARD] Error loading models: {e}")
        
        # Add Sequences (Purple)
        sequences = sequences_mgr.list_sequences()
        if sequences:
            for seq in sequences:
                self.run_combo.addItem(f"🔗 Sequence: {seq}")
        
        # Add Actions (Blue)
        actions = actions_mgr.list_actions()
        if actions:
            for action in actions:
                self.run_combo.addItem(f"🎬 Action: {action}")

        self.run_combo.blockSignals(False)
        self.camera_order = list(self.config.get("cameras", {}).keys())
        self.vision_zones = self._load_vision_zones()
        self._robot_total = 1 if self.config.get("robot") else 0
        # Sync tracked camera statuses with current configuration
        for name in list(self._camera_status.keys()):
            if name not in self.camera_order:
                self._camera_status.pop(name)
        for name in self.camera_order:
            self._camera_status.setdefault(name, "empty")

        self.camera_toggle_btn.setEnabled(bool(self.camera_order))
        self._refresh_active_camera_label()
        if self.camera_view_active:
            self.update_camera_previews(force=True)
        elif not self.camera_order:
            self.single_camera_preview.update_preview(None, "No camera configured.")

        self._update_status_summaries()

    def _refresh_loop_button(self):
        if self.loop_enabled:
            text = "Loop\nON"
            style = """
                QPushButton {
                    background-color: #4CAF50;
                    color: #ffffff;
                    border: 2px solid #43A047;
                    border-radius: 10px;
                    font-size: 26px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #43A047;
                }
            """
        else:
            text = "Loop\nOFF"
            style = """
                QPushButton {
                    background-color: #424242;
                    color: #ffffff;
                    border: 2px solid #515151;
                    border-radius: 10px;
                    font-size: 26px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                }
            """
        self.loop_button.setText(text)
        self.loop_button.setStyleSheet(style)

    def on_loop_button_toggled(self, checked: bool):
        self.loop_enabled = checked
        self._refresh_loop_button()
        control_cfg = self.config.setdefault("control", {})
        control_cfg["loop_enabled"] = checked

        if checked:
            self._append_log("Loop mode is ON. The run will repeat until you stop it.")
        else:
            self._append_log("Loop mode is OFF. Runs will finish after one pass.")

    # ==================================================
    # Log helpers
    # ==================================================

    def _append_log(self, message: str, level: str = "info"):
        """Append a formatted message to the dashboard log."""
        if not message:
            return

        icon = self._log_icon_map.get(level, "•")
        prefix = f"{icon} " if icon else ""
        self.log_text.append(f"{prefix}{message}")
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

    def _translate_safety_log(self, message: str):
        text = message.strip()
        lower = text.lower()

        if "emergency stop" in lower:
            return ("error", "Emergency stop activated. Clear the workspace and re-enable the robot.")
        if "workspace clear" in lower:
            return ("info", "Safety check cleared. You can restart the robot when ready.")
        if "failed to initialize" in lower or "failed to start" in lower:
            return (
                "error",
                "Safety system could not start. Restart the app or review camera settings.",
            )
        if "failed to stop" in lower:
            return (
                "warning",
                "Safety monitor did not shut down cleanly. Restarting the app is recommended.",
            )
        if "monitoring disabled" in lower:
            return (
                "warning",
                "Safety monitoring is turned off in settings. Turn it on before running unattended.",
            )
        if "no cameras configured" in lower:
            return (
                "warning",
                "No safety cameras configured. Add a camera in Settings to enable monitoring.",
            )
        if "safety monitor initialized" in lower:
            return ("success", "Safety monitor ready.")

        return None

    def _translate_worker_log(self, level: str, message: str):
        """Convert technical worker logs into user-friendly messages."""
        text = (message or "").strip()
        if not text:
            return None

        lower = text.lower()

        if text.startswith("[lerobot]"):
            return None
        if text.startswith("===") or text.startswith("→") or text.startswith("  →"):
            return None

        if text.startswith("[safety]"):
            translated = self._translate_safety_log(text)
            if translated:
                return translated
            return None

        if "monitor error" in lower:
            return ("error", "Run monitor hit an issue. Stop the run and try again.")

        if "starting policy server" in lower:
            return ("info", "Preparing the model server...")
        if "policy server ready" in lower:
            return ("success", "Model server is ready.")
        if "starting robot client" in lower:
            return ("info", "Connecting to the robot controller...")
        if "robot client failed" in lower:
            return (
                "error",
                "Robot controller not responding. Check the USB cable and power cycle the robot.",
            )
        if "stopping robot client" in lower or "stopping model" in lower:
            return ("info", "Stopping the model run...")

        if "connecting to motors" in lower:
            return ("info", "Connecting to the robot arm...")
        if "failed to connect to motors" in lower:
            return (
                "error",
                "Robot arm not responding. Check the USB cable and ensure the robot is powered on.",
            )
        if "no permission to access" in lower:
            port = text.split()[-1]
            return (
                "error",
                f"No permission to access {port}. Run 'sudo chmod 666 {port}' then restart.",
            )
        if "robot port not found" in lower:
            port = text.split(":", 1)[-1].strip()
            return (
                "error",
                f"Robot port {port} not found. Confirm the robot is plugged in and powered.",
            )
        if "make sure the robot is connected" in lower:
            return (
                "error",
                "Robot connection missing. Plug it in and try again.",
            )

        if "loading model:" in lower:
            raw = text.split(":", 1)[-1].strip()
            try:
                folder = Path(raw).parent.name or Path(raw).name
            except Exception:
                folder = raw
            return ("info", f"Loading model files from {folder}...")
        if "loading model" in lower:
            name = text.split(":", 1)[-1].strip()
            return ("info", f"Loading model '{name}'...")
        if "loading recording" in lower:
            name = text.split(":", 1)[-1].strip()
            return ("info", f"Loading action '{name}'...")
        if "loading sequence" in lower:
            name = text.split(":", 1)[-1].strip()
            return ("info", f"Loading sequence '{name}'...")

        if "using local mode" in lower:
            return ("info", "Running the model directly on this device.")
        if "using server mode" in lower:
            return ("info", "Running the model through the server.")

        if "loop mode enabled" in lower:
            return ("info", "Loop mode is on. The run will repeat until you stop it.")
        if "stopped by user" in lower:
            return ("info", "Run stopped by you.")
        if "stopping by user request" in lower:
            return ("info", "Stopping the run...")

        if "run completed successfully" in lower:
            return ("success", "Run completed successfully.")
        if "model execution completed" in lower:
            return ("success", "Model run completed.")
        if "recording completed" in lower:
            return ("success", "Action completed.")
        if "sequence completed" in lower:
            return ("success", "Sequence finished.")
        if "loop iteration" in lower:
            return None

        if "recording not found" in lower:
            name = text.split(":", 1)[-1].strip()
            return (
                "error",
                f"Action '{name}' not found. Confirm it exists in the Recordings folder.",
            )
        if "model not found" in lower:
            raw = text.split(":", 1)[-1].strip()
            try:
                folder = Path(raw).parent.name or Path(raw).name
            except Exception:
                folder = raw
            return (
                "error",
                f"Model files missing for '{folder}'. Check the model folder in Settings.",
            )
        if "sequence not found" in lower:
            name = text.split(":", 1)[-1].strip()
            return (
                "error",
                f"Sequence '{name}' not found. Re-import or create it again.",
            )

        if "failed to start model" in lower or "model execution failed" in lower:
            return (
                "error",
                "Model failed to start. Verify the selected checkpoint and try again.",
            )
        if "failed to start policy server" in lower or "policy server failed to start" in lower:
            return (
                "error",
                "Model server did not start. Restart the dashboard or double-check the model path.",
            )
        if "failed with exit code" in lower or "process exited with code" in lower:
            return (
                "error",
                "The run ended unexpectedly. See the terminal for technical details.",
            )
        if "failed to start" in lower and "policy server" not in lower and "model" not in lower:
            return ("error", "Startup failed. See the terminal for more details.")
        if "output reading error" in lower:
            return ("warning", "Could not read all output. Check the terminal if issues persist.")
        if "failed to reach home" in lower:
            return (
                "error",
                "Could not reach the home position. Clear any obstacles and try again.",
            )
        if "vision step has no zones" in lower:
            return (
                "warning",
                "Vision step missing zones. Add a zone in the Vision tab before running.",
            )
        if "vision step: camera" in lower and "unavailable" in lower:
            cam = None
            if "'" in text:
                try:
                    cam = text.split("'")[1]
                except IndexError:
                    cam = None
            if not cam:
                parts = text.split()
                cam = parts[3] if len(parts) > 3 else "camera"
            cam = cam.strip("'\"")
            return (
                "error",
                f"Camera '{cam}' unavailable. Check the cable or assign the correct camera in settings.",
            )
        if "switching to demo feed" in lower:
            return (
                "warning",
                "Using demo video because the camera is offline.",
            )
        if "vision step skipped" in lower:
            return (
                "warning",
                "Vision step skipped due to an error. Check camera setup.",
            )
        if "waiting for vision trigger" in lower:
            return ("info", "Waiting for the vision trigger...")
        if "vision trigger confirmed" in lower:
            return ("success", "Vision trigger detected.")

        if level == "warning" and "failed" in lower:
            return ("warning", "Something didn't finish as expected. See terminal for details.")
        if level == "warning" and "no" in lower and "configured" in lower:
            return ("warning", text)

        if level == "error":
            return ("error", "An unexpected error occurred. See terminal for details.")

        if level == "warning":
            return ("warning", message)

        if level in {"info", "debug"}:
            return None

        return None

    def on_speed_slider_changed(self, value: int):
        aligned = max(10, min(120, 5 * round(value / 5)))
        if aligned != value:
            self.speed_slider.blockSignals(True)
            self.speed_slider.setValue(aligned)
            self.speed_slider.blockSignals(False)

        self.master_speed = aligned / 100.0
        self.speed_value_label.setText(f"{aligned}%")

        control_cfg = self.config.setdefault("control", {})
        control_cfg["speed_multiplier"] = self.master_speed

        if self.execution_worker and self.execution_worker.isRunning():
            try:
                self.execution_worker.set_speed_multiplier(self.master_speed)
            except Exception:
                pass
        if self.worker and hasattr(self.worker, "set_speed_multiplier"):
            try:
                self.worker.set_speed_multiplier(self.master_speed)
            except Exception:
                pass

        if not self._speed_initialized:
            self._speed_initialized = True

    def _camera_display_name(self, camera_name: str) -> str:
        return camera_name.replace("_", " ").title()

    def _refresh_active_camera_label(self):
        if not self.single_camera_preview:
            return

        if not self.camera_order:
            self.active_camera_name = None
            self.single_camera_preview.set_camera_name("No cameras")
            self.single_camera_preview.update_preview(None, "Configure cameras in Settings.")
            self.camera_cycle_btn.setEnabled(False)
            return

        if self.active_camera_name not in self.camera_order:
            self.active_camera_index = 0
            self.active_camera_name = self.camera_order[0]
            self._last_preview_timestamp = 0.0

        display = self._camera_display_name(self.active_camera_name)
        self.single_camera_preview.set_camera_name(display)
        self.camera_cycle_btn.setEnabled(len(self.camera_order) > 1)

    def cycle_active_camera(self):
        if not self.camera_order:
            return
        self.active_camera_index = (self.active_camera_index + 1) % len(self.camera_order)
        self.active_camera_name = self.camera_order[self.active_camera_index]
        self._last_preview_timestamp = 0.0
        self._refresh_active_camera_label()
        self.update_camera_previews(force=True)

    def on_camera_toggle(self, checked: bool):
        # Update button text (red with X when open)
        self.camera_toggle_btn.setText("✕" if checked else "Cameras")
        if checked:
            self.camera_toggle_btn.setMinimumWidth(85)
            self.camera_toggle_btn.setMaximumWidth(85)
        else:
            self.camera_toggle_btn.setMinimumWidth(self._camera_toggle_default_width)
            self.camera_toggle_btn.setMaximumWidth(self._camera_toggle_default_width)
        if checked:
            self.enter_camera_mode()
        else:
            self.exit_camera_mode()

    def enter_camera_mode(self):
        if self.camera_view_active:
            return
        if cv2 is None:
            self._append_log(
                "Live camera preview unavailable. Install OpenCV to enable previews.",
                level="warning",
            )
            self.camera_toggle_btn.blockSignals(True)
            self.camera_toggle_btn.setChecked(False)
            self.camera_toggle_btn.blockSignals(False)
            self.camera_toggle_btn.setMinimumWidth(self._camera_toggle_default_width)
            self.camera_toggle_btn.setMaximumWidth(self._camera_toggle_default_width)
            return
        
        # Hide status bar text labels and timer when cameras open
        self.normal_status_container.hide()
        self.status_summary_container.show()
        self.time_label.hide()
        self.run_label.hide()
        
        self._refresh_active_camera_label()
        self.camera_panel.setVisible(True)
        if not self.camera_order or not self.active_camera_name:
            self.camera_view_active = False
            self.single_camera_preview.update_preview(None, "No camera configured.")
            return

        self.camera_view_active = True
        self.camera_preview_timer.start(300)
        self.update_camera_previews(force=True)

    def exit_camera_mode(self):
        if not self.camera_view_active:
            return
        
        # Restore status bar text labels and timer
        self.status_summary_container.hide()
        self.normal_status_container.show()
        self.time_label.show()
        self.run_label.show()
        self.camera_toggle_btn.setMinimumWidth(self._camera_toggle_default_width)
        self.camera_toggle_btn.setMaximumWidth(self._camera_toggle_default_width)
        
        self.camera_view_active = False
        self.camera_preview_timer.stop()
        self.camera_panel.setVisible(False)
        self.single_camera_preview.update_preview(None, "Preview closed.")

    def close_camera_panel(self):
        """Close camera preview if it's currently open."""
        if self.camera_toggle_btn.isChecked():
            self.camera_toggle_btn.setChecked(False)
        elif self.camera_view_active:
            self.exit_camera_mode()

    def _load_vision_zones(self) -> Dict[str, List[dict]]:
        zones_map: Dict[str, List[dict]] = {}
        sequences_dir = ROOT / "data" / "sequences"
        if not sequences_dir.exists():
            return zones_map

        for manifest_path in sequences_dir.glob("*/manifest.json"):
            try:
                with open(manifest_path, "r") as handle:
                    manifest = json.load(handle)
            except Exception:
                continue

            for step in manifest.get("steps", []):
                if step.get("step_type") != "vision":
                    continue

                camera_name = self._match_camera_name(step.get("camera", {}))
                if not camera_name:
                    continue

                trigger = step.get("trigger", {})
                settings = trigger.get("settings", {})
                threshold = float(settings.get("threshold", 0.55))
                invert = bool(settings.get("invert", False))
                metric = settings.get("metric", "intensity")

                for zone in trigger.get("zones", []):
                    polygon = zone.get("polygon", [])
                    if not polygon:
                        continue
                    zones_map.setdefault(camera_name, []).append({
                        "polygon": polygon,
                        "threshold": threshold,
                        "invert": invert,
                        "metric": metric
                    })

        return zones_map

    def _normalize_camera_identifier(self, identifier) -> str:
        if isinstance(identifier, int):
            return str(identifier)
        if isinstance(identifier, str):
            stripped = identifier.strip()
            if stripped.startswith("/dev/video") and stripped[10:].isdigit():
                return stripped[10:]
            if stripped.startswith("camera:"):
                return stripped.split(":", 1)[-1]
            if stripped.isdigit():
                return stripped
            return stripped
        return str(identifier)

    def _match_camera_name(self, camera_info: dict) -> Optional[str]:
        if not camera_info:
            return None

        source_id = str(camera_info.get("source_id", ""))
        index = camera_info.get("index")
        normalized_source = self._normalize_camera_identifier(source_id) if source_id else None
        normalized_index = str(index) if index is not None else None

        for name, cfg in self.config.get("cameras", {}).items():
            identifier = cfg.get("index_or_path", 0)
            norm_identifier = self._normalize_camera_identifier(identifier)
            if normalized_source and norm_identifier == normalized_source:
                return name
            if normalized_index and norm_identifier == normalized_index:
                return name
            if source_id and str(identifier) == source_id:
                return name
        return None

    def _polygon_to_pixels(self, polygon: List[List[float]], width: int, height: int) -> "np.ndarray":
        if np is None:
            return np.zeros((0, 2), dtype=np.int32)

        pts = []
        for point in polygon:
            if len(point) != 2:
                continue
            x, y = point
            if isinstance(x, float) and isinstance(y, float) and 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
                px = int(round(x * (width - 1)))
                py = int(round(y * (height - 1)))
            else:
                px = int(round(float(x)))
                py = int(round(float(y)))
            pts.append([px, py])
        return np.array(pts, dtype=np.int32)

    def _evaluate_metric(self, frame, gray, mask, metric_type: str) -> float:
        if cv2 is None or np is None:
            return 0.0
        metric_type = (metric_type or "intensity").lower()
        if metric_type == "green_channel":
            return cv2.mean(frame[:, :, 1], mask=mask)[0] / 255.0
        if metric_type == "edge_density":
            edges = cv2.Canny(gray, 50, 150)
            masked_edges = cv2.bitwise_and(edges, edges, mask=mask)
            edge_pixels = np.count_nonzero(masked_edges)
            total_pixels = np.count_nonzero(mask)
            return edge_pixels / total_pixels if total_pixels else 0.0
        return cv2.mean(gray, mask=mask)[0] / 255.0

    def _render_camera_frame(self, camera_name: str, frame, zones: Optional[List[dict]] = None):
        if cv2 is None or np is None:
            return frame, "nominal"

        zones = zones if zones is not None else self.vision_zones.get(camera_name, [])
        if not zones:
            return frame, "nominal"

        height, width = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        triggered_any = False
        valid_zone = False

        for zone in zones:
            polygon = zone.get("polygon", [])
            pts = self._polygon_to_pixels(polygon, width, height)
            if pts.size == 0:
                continue
            valid_zone = True

            mask = np.zeros((height, width), dtype=np.uint8)
            cv2.fillPoly(mask, [pts], 255)

            metric = self._evaluate_metric(frame, gray, mask, zone.get("metric", "intensity"))
            threshold = float(zone.get("threshold", 0.5))
            invert = bool(zone.get("invert", False))
            triggered = metric <= threshold if invert else metric >= threshold
            if triggered:
                triggered_any = True

            color = (76, 175, 80) if triggered else (244, 67, 54)
            overlay = np.zeros_like(frame)
            cv2.fillPoly(overlay, [pts], color)
            frame = cv2.addWeighted(frame, 1.0, overlay, 0.28, 0)
            cv2.polylines(frame, [pts], True, color, 2, cv2.LINE_AA)

        if not valid_zone:
            return frame, "nominal"
        return frame, "triggered" if triggered_any else "idle"

    def _frame_to_pixmap(self, frame: "np.ndarray") -> QPixmap:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channel = rgb.shape
        image = QImage(rgb.data, width, height, channel * width, QImage.Format_RGB888)
        return QPixmap.fromImage(image)

    def _get_preview_zones(self, camera_name: str) -> List[dict]:
        zones = self.active_vision_zones.get(camera_name)
        if zones:
            return zones
        return []

    def update_camera_previews(self, force: bool = False):
        if not self.camera_view_active or cv2 is None or np is None:
            return

        if not self.active_camera_name:
            self.single_camera_preview.update_preview(None, "No camera configured.")
            return

        if not self.camera_hub:
            self.single_camera_preview.update_preview(None, "Camera hub unavailable.", status="Offline")
            return

        frame, timestamp = self.camera_hub.get_frame_with_timestamp(self.active_camera_name, preview=True)
        if frame is None:
            self.single_camera_preview.update_preview(None, "Camera offline.", status="Offline")
            return

        if not force and timestamp <= self._last_preview_timestamp:
            return

        zones = self._get_preview_zones(self.active_camera_name)
        render_frame, status = self._render_camera_frame(self.active_camera_name, frame.copy(), zones)
        pixmap = self._frame_to_pixmap(render_frame)
        status_text = {
            "triggered": "Triggered",
            "idle": "Watching",
            "nominal": "Live",
            "offline": "Offline",
            "no_vision": "No vision",
        }.get(status, "")
        self.single_camera_preview.update_preview(pixmap, status=status_text)
        self._last_preview_timestamp = timestamp

    def open_camera_detail(self, camera_name: str):
        camera_cfg = self.config.get("cameras", {}).get(camera_name)
        if not camera_cfg:
            return
        zones = self.active_vision_zones.get(camera_name) or self.vision_zones.get(camera_name, [])
        dialog = CameraDetailDialog(
            camera_name, camera_cfg, zones, self._render_camera_frame, self.camera_hub, self
        )
        dialog.exec()
    
    def on_run_selection_changed(self, text):
        """Handle RUN selector change - show/hide checkpoint dropdown"""
        print(f"[DASHBOARD] Run selection changed: {text}")
        
        if text.startswith("🤖 Model:"):
            # Show checkpoint dropdown for models
            self.checkpoint_combo.show()
            
            # Extract model name and load checkpoints
            model_name = text.replace("🤖 Model: ", "")
            self.load_checkpoints_for_model(model_name)
        else:
            # Hide checkpoint dropdown for sequences and actions
            self.checkpoint_combo.hide()
            self.checkpoint_combo.clear()
    
    def load_checkpoints_for_model(self, model_name: str):
        """Load checkpoints for the selected model"""
        self.checkpoint_combo.blockSignals(True)
        self.checkpoint_combo.clear()
        
        try:
            train_dir = Path(self.config["policy"].get("base_path", ""))
            checkpoints_dir = train_dir / model_name / "checkpoints"
            
            if checkpoints_dir.exists():
                checkpoints = []
                for item in checkpoints_dir.iterdir():
                    if item.is_dir() and (item / "pretrained_model").exists():
                        checkpoints.append(item.name)
                
                # Sort: "last" first, then numeric descending
                def sort_key(name):
                    if name == "last":
                        return (0, 0)
                    try:
                        return (1, -int(name))
                    except ValueError:
                        return (2, name)
                
                checkpoints.sort(key=sort_key)
                
                for ckpt in checkpoints:
                    display = f"✓ {ckpt}" if ckpt == "last" else ckpt
                    self.checkpoint_combo.addItem(display, ckpt)
                
                # Auto-select "last"
                for i in range(self.checkpoint_combo.count()):
                    if self.checkpoint_combo.itemData(i) == "last":
                        self.checkpoint_combo.setCurrentIndex(i)
                        break
            else:
                self.checkpoint_combo.addItem("No checkpoints")
                
        except Exception as e:
            print(f"[DASHBOARD] Error loading checkpoints: {e}")
            self.checkpoint_combo.addItem("Error loading")
        
        self.checkpoint_combo.blockSignals(False)
    
    def on_checkpoint_changed(self, text):
        """Handle checkpoint selection"""
        # Update config when checkpoint changes
        selected_run = self.run_combo.currentText()
        if selected_run.startswith("🤖 Model:"):
            model_name = selected_run.replace("🤖 Model: ", "")
            checkpoint_index = self.checkpoint_combo.currentIndex()
            
            if checkpoint_index >= 0:
                checkpoint_name = self.checkpoint_combo.itemData(checkpoint_index)
                if checkpoint_name:
                    try:
                        train_dir = Path(self.config["policy"].get("base_path", ""))
                        new_path = train_dir / model_name / "checkpoints" / checkpoint_name / "pretrained_model"
                        self.config["policy"]["path"] = str(new_path)
                        print(f"[DASHBOARD] Policy path updated to: {new_path}")
                    except Exception as e:
                        print(f"[DASHBOARD] Error updating policy path: {e}")
    
    def refresh_policy_list(self):
        """Legacy method - now uses refresh_run_selector"""
        self.refresh_run_selector()
    
    def validate_config(self):
        """Validate configuration
        
        NOTE: Status indicators are now managed by device_manager
        This method is kept for backwards compatibility but doesn't update indicators
        """
        # Status indicators are now updated by device_manager signals
        # We don't override them here to avoid conflicts
        pass
    
    def update_throbber_progress(self):
        """Update throbber"""
        self.throbber_progress += 1
        if self.throbber_progress > 100:
            self.throbber_progress = 0
        self.throbber.set_progress(self.throbber_progress)
        if self.compact_throbber:
            self.compact_throbber.set_progress(self.throbber_progress)
    
    def check_connections_background(self):
        """Check connections - now handled by device_manager"""
        # Connection checking is now centralized in device_manager
        pass
    
    
    def toggle_start_stop(self):
        """Toggle start/stop"""
        if self.start_stop_btn.isChecked():
            self.start_run()
        else:
            self.stop_run()
    
    def start_run(self):
        """Start robot run - unified execution for models, recordings, and sequences"""
        if self.is_running:
            self._append_log(
                "A run is already in progress. Stop it before starting another.",
                level="warning",
            )
            return

        # Get selected item
        selected = self.run_combo.currentText()

        self._vision_state_active = False
        self._last_vision_signature = None
        self.active_vision_zones.clear()
        self._last_preview_timestamp = 0.0
        if self.camera_view_active:
            self.update_camera_previews(force=True)
        
        if selected.startswith("--"):
            self._append_log(
                "Choose an item to run from the list first.",
                level="warning",
            )
            self.start_stop_btn.setChecked(False)
            return
        
        # Parse selection
        execution_type, execution_name = self._parse_run_selection(selected)
        
        if not execution_type or not execution_name:
            self._append_log(
                "Please select a valid model, sequence, or action to run.",
                level="error",
            )
            self.start_stop_btn.setChecked(False)
            return
        
        # Update UI
        self.start_stop_btn.setText("STOP")
        self.is_running = True
        self.start_time = datetime.now()
        self.timer.start(1000)  # Update elapsed time every second
        
        friendly_type = {
            "model": "model",
            "sequence": "sequence",
            "recording": "action",
        }.get(execution_type, "run")
        self._append_log(
            f"Starting {friendly_type}: {execution_name}",
            level="action",
        )
        self._append_log(
            f"Speed set to {int(self.master_speed * 100)}%.",
        )
        self.action_label.setText(f"Starting {execution_type}...")
        
        # Handle models based on execution mode
        if execution_type == "model":
            local_mode = self.config.get("policy", {}).get("local_mode", True)

            if local_mode:
                # Local mode: Use ExecutionWorker (which uses lerobot-record)
                self._append_log("Running the model directly on this device.")
                # Get checkpoint and episode settings from UI
                checkpoint_name = self.checkpoint_combo.currentData() if self.checkpoint_combo.isVisible() else "last"

                if self.loop_enabled:
                    num_episodes = -1  # Infinite loop
                    self._append_log("Loop mode enabled — repeating until you stop it.")
                else:
                    num_episodes = 1

                self._start_execution_worker(execution_type, execution_name, {
                    "checkpoint": checkpoint_name,
                    "duration": self.config.get("control", {}).get("episode_time_s", 30),
                    "num_episodes": num_episodes
                })
            else:
                # Server mode: Use RobotWorker (async inference)
                self._append_log("Connecting to the shared model server...")
                self._start_model_execution(execution_name)
        else:
            # For recordings and sequences, use ExecutionWorker
            options = {"loop": self.loop_enabled} if execution_type == "sequence" else {}
            self._start_execution_worker(execution_type, execution_name, options)
    
    def _start_model_execution(self, model_name: str):
        """Start model execution using RobotWorker directly"""
        # Get checkpoint path
        checkpoint_name = self.checkpoint_combo.currentData() if self.checkpoint_combo.isVisible() else "last"
        
        try:
            train_dir = Path(self.config["policy"].get("base_path", ""))
            checkpoint_path = train_dir / model_name / "checkpoints" / checkpoint_name / "pretrained_model"
            
            # Update config for this run
            model_config = self.config.copy()
            model_config.setdefault("control", {})["speed_multiplier"] = self.master_speed
            model_config["policy"]["path"] = str(checkpoint_path)
            
            checkpoint_label = checkpoint_name or Path(checkpoint_path).parent.name
            self._append_log(
                f"Loading model '{model_name}' ({checkpoint_label}).",
            )

            # Stop any existing worker first
            if self.worker and self.worker.isRunning():
                self._append_log(
                    "Stopping the previous model before starting a new one...",
                    level="warning",
                )
                self.worker.stop()
                self.worker.wait(2000)
            
            # Create RobotWorker directly (not nested in another thread)
            self.worker = RobotWorker(model_config)
            
            # Connect signals with error handling
            self.worker.status_update.connect(self._on_status_update)
            self.worker.log_message.connect(self._on_log_message)
            self.worker.progress_update.connect(self._on_progress_update)
            self.worker.run_completed.connect(self._on_model_completed)
            self.worker.finished.connect(self._on_worker_thread_finished)
            
            # Start worker
            self.worker.start()
            
        except Exception as e:
            import traceback
            self._append_log(
                "Could not start the model. Check the model files and try again.",
                level="error",
            )
            print("[DASHBOARD] Failed to start model:", e)
            print(traceback.format_exc())
            self._reset_ui_after_run()
    
    def _start_execution_worker(self, execution_type: str, execution_name: str, options: dict = None):
        """Start ExecutionWorker for recordings and sequences"""
        merged_options = dict(options or {})
        merged_options["speed_multiplier"] = self.master_speed

        # Create and start execution worker
        self.execution_worker = ExecutionWorker(
            self.config,
            execution_type,
            execution_name,
            merged_options
        )
        
        # Connect signals
        self.execution_worker.status_update.connect(self._on_status_update)
        self.execution_worker.log_message.connect(self._on_log_message)
        self.execution_worker.progress_update.connect(self._on_progress_update)
        self.execution_worker.execution_completed.connect(self._on_execution_completed)
        self.execution_worker.sequence_step_started.connect(self._on_sequence_step_started)
        self.execution_worker.sequence_step_completed.connect(self._on_sequence_step_completed)
        self.execution_worker.vision_state_update.connect(self._on_vision_state_update)

        # Start execution
        self.execution_worker.set_speed_multiplier(self.master_speed)
        self.execution_worker.start()
    
    def run_sequence(self, sequence_name: str, loop: bool = False):
        """Run a sequence from the Sequence tab

        Args:
            sequence_name: Name of the sequence to run
            loop: Whether to loop the sequence
        """
        if self.is_running:
            self._append_log(
                "A run is already in progress. Stop it before starting another.",
                level="warning",
            )
            return

        loop_text = " with loop" if loop else ""
        self._append_log(
            f"Starting sequence: {sequence_name}{loop_text}.",
            level="action",
        )

        # Update UI state
        self.is_running = True
        self.start_stop_btn.setChecked(True)
        self.start_stop_btn.setText("⏹ STOP")
        self.action_label.setText(f"Sequence: {sequence_name}")
        self._vision_state_active = False
        self._last_vision_signature = None

        # Start execution worker
        self._start_execution_worker("sequence", sequence_name, {"loop": loop})
    
    def stop_run(self):
        """Stop robot run"""
        if not self.is_running:
            return

        self._append_log("Stopping the current run...")
        self.action_label.setText("Stopping...")
        
        # Stop execution worker (for recordings/sequences)
        if self.execution_worker and self.execution_worker.isRunning():
            self.execution_worker.stop()
            self.execution_worker.wait(5000)  # Wait up to 5 seconds
        
        # Stop robot worker (for models)
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(5000)  # Wait up to 5 seconds
        
        # Reset UI
        self._reset_ui_after_run()
    
    def _parse_run_selection(self, selected: str) -> tuple:
        """Parse run selection into (type, name)

        Returns:
            ("model", "GrabBlock") or ("recording", "Grab Cup v1") or ("sequence", "Production Run")
        """
        if selected.startswith("🤖 Model:"):
            return ("model", selected.replace("🤖 Model: ", ""))
        elif selected.startswith("🔗 Sequence:"):
            return ("sequence", selected.replace("🔗 Sequence: ", ""))
        elif selected.startswith("🎬 Action:"):
            # Note: "Action" in UI = "recording" in code
            return ("recording", selected.replace("🎬 Action: ", ""))
        else:
            return (None, None)

    def _set_action_label_style(self, background: str):
        self.action_label.setStyleSheet(self._action_label_style_template.format(bg=background))

    def record_vision_status(self, state: str, detail: str, payload: Optional[dict] = None):
        payload = payload or {}
        countdown = payload.get("countdown")
        metric = payload.get("metric")
        zones_raw = payload.get("zones") or []
        zones = [z if isinstance(z, str) else str(z) for z in zones_raw]

        color_map = {
            "triggered": "#4CAF50",
            "idle": "#FFB300",
            "watching": "#383838",
            "complete": "#4CAF50",
            "error": "#b71c1c",
            "clear": "#383838",
        }

        bg = color_map.get(state, "#383838")
        self._set_action_label_style(bg)

        message = detail
        if countdown is not None:
            message = f"{detail} • {countdown}s"
        if metric is not None and state == "triggered":
            message = f"{detail} • metric={metric:.3f}"

        if state in {"idle", "watching", "triggered"}:
            self._vision_state_active = True
        elif state in {"complete", "clear", "error"}:
            self._vision_state_active = False

        if not self._vision_state_active and state in {"complete", "clear"}:
            self._set_action_label_style("#383838")

        self.action_label.setText(message)

        if state in {"idle", "watching"}:
            signature = (state, tuple(zones))
        elif state == "triggered":
            metric_key = round(metric or 0, 2) if metric is not None else None
            signature = (state, metric_key, tuple(zones))
        else:
            signature = (state, tuple(zones))

        if signature != self._last_vision_signature:
            zone_text = ", ".join(zones)
            level = "vision"

            if state == "idle":
                log_message = "Vision armed."
                if zone_text:
                    log_message += f" Watching {zone_text}."
                if countdown:
                    log_message += f" Next check in {countdown}s."
            elif state == "watching":
                log_message = "Vision is watching for movement."
                if zone_text:
                    log_message += f" Focus: {zone_text}."
            elif state == "triggered":
                level = "success"
                location = zone_text or "the workspace"
                log_message = f"Vision trigger detected in {location}."
                if metric is not None:
                    log_message += f" Confidence {metric:.2f}."
            elif state == "complete":
                level = "success"
                log_message = "Vision check complete."
            elif state == "clear":
                log_message = "Vision cleared."
            elif state == "error":
                level = "error"
                detail_text = payload.get("error") or detail or "Vision error detected."
                log_message = f"Vision error: {detail_text}. Check the camera setup and zones."
            else:
                log_message = detail

            self._append_log(log_message, level=level)
            self._last_vision_signature = signature

    def _on_status_update(self, status: str):
        """Handle status update from worker"""
        if self._vision_state_active:
            return
        self._set_action_label_style("#383838")
        self.action_label.setText(status)

    def _on_log_message(self, level: str, message: str):
        """Handle log message from worker"""
        translated = self._translate_worker_log(level, message)
        if not translated:
            return

        friendly_level, friendly_message = translated
        self._append_log(friendly_message, level=friendly_level)
    
    def _on_progress_update(self, current: int, total: int):
        """Handle progress update from worker"""
        if total > 0:
            progress = int((current / total) * 100)
            # Could update a progress bar here if we add one

    def _on_sequence_step_started(self, index: int, total: int, step: dict):
        seq_tab = self._get_sequence_tab()
        if seq_tab:
            seq_tab.highlight_running_step(index, step)

    def _on_sequence_step_completed(self, index: int, total: int, step: dict):
        # Placeholder for future use (e.g., marking completed)
        pass

    def _on_vision_state_update(self, state: str, payload: dict):
        message = payload.get("message", state.title())
        camera_name = payload.get("camera_name")
        zone_payload = payload.get("zone_polygons") or []

        if camera_name:
            if state in {"idle", "watching", "triggered"} and zone_payload:
                self.active_vision_zones[camera_name] = zone_payload
            elif state in {"complete", "clear", "error"}:
                self.active_vision_zones.pop(camera_name, None)

        self.record_vision_status(state, message, payload)
        if camera_name and self.camera_view_active and camera_name == self.active_camera_name:
            self.update_camera_previews(force=True)
    
    def _on_execution_completed(self, success: bool, summary: str):
        """Handle execution completion (for recordings/sequences)"""
        level = "success" if success else "error"
        status_text = "Completed" if success else "Failed"
        self._append_log(f"{status_text}: {summary}", level=level)

        if success:
            self.action_label.setText("✓ Completed")
        else:
            self.action_label.setText("✗ Failed")
        seq_tab = self._get_sequence_tab()
        if seq_tab:
            seq_tab.clear_running_highlight()
        
        # Reset UI
        self._reset_ui_after_run()
    
    def _on_model_completed(self, success: bool, summary: str):
        """Handle model execution completion"""
        try:
            level = "success" if success else "error"
            status_text = "Completed" if success else "Failed"
            self._append_log(f"{status_text}: {summary}", level=level)

            if success:
                self.action_label.setText("✓ Model completed")
            else:
                self.action_label.setText("✗ Model failed")
                # Show user-friendly message
                self._append_log(
                    "Check the robot connection and confirm the model path in Settings.",
                    level="warning",
                )
        except Exception as e:
            self._append_log(
                "Problem updating the completion status. See terminal for details.",
                level="error",
            )
            print("[DASHBOARD] Error handling completion:", e)
        finally:
            # Always reset UI, even if there's an error
            self._reset_ui_after_run()

    def _get_sequence_tab(self):
        parent = self.parent()
        while parent:
            if hasattr(parent, "sequence_tab"):
                return getattr(parent, "sequence_tab")
            parent = parent.parent()
        return None

    def _on_worker_thread_finished(self):
        """Handle worker thread finished (cleanup)"""
        try:
            # Give worker time to clean up
            if self.worker:
                self.worker.deleteLater()
        except Exception as e:
            self._append_log(
                "Cleanup issue detected. Restart the app if problems continue.",
                level="warning",
            )
            print("[DASHBOARD] Error in thread cleanup:", e)
    
    def _reset_ui_after_run(self):
        """Reset UI state after run completes or stops"""
        try:
            self.is_running = False
            self.start_stop_btn.setChecked(False)
            self.start_stop_btn.setText("START")
            self.timer.stop()
            self._vision_state_active = False
            self._last_vision_signature = None
            self.active_vision_zones.clear()
            self._set_action_label_style("#383838")
            seq_tab = self._get_sequence_tab()
            if seq_tab:
                seq_tab.clear_running_highlight()
            
            # Clean up execution worker (recordings/sequences)
            if self.execution_worker:
                try:
                    if self.execution_worker.isRunning():
                        self.execution_worker.quit()
                        self.execution_worker.wait(1000)
                except:
                    pass
                self.execution_worker = None
            
            # Clean up robot worker (models) - be very careful here
            if self.worker:
                try:
                    if self.worker.isRunning():
                        self.worker.quit()
                        self.worker.wait(2000)
                    # Mark for deletion but don't set to None yet
                    # Let Qt handle the cleanup
                    self.worker.deleteLater()
                except Exception as e:
                    self._append_log(
                        "Problem shutting down the previous run cleanly. Restart if issues persist.",
                        level="warning",
                    )
                    print("[DASHBOARD] Worker cleanup warning:", e)
                finally:
                    self.worker = None
        except Exception as e:
            self._append_log(
                "Could not reset the controls. Restart the app if controls look stuck.",
                level="error",
            )
            print("[DASHBOARD] Error resetting UI:", e)

    def go_home(self):
        """Go to home position"""
        self.action_label.setText("Moving to home...")
        self._append_log("Moving the robot to the home position...", level="action")
        self._append_log(f"Speed set to {int(self.master_speed * 100)}%.")

        try:
            env = os.environ.copy()
            env["LEROBOT_SPEED_MULTIPLIER"] = f"{self.master_speed:.2f}"
            result = subprocess.run(
                [sys.executable, str(ROOT / "HomePos.py"), "--go"],
                capture_output=True,
                text=True,
                timeout=30,
                env=env
            )

            if result.returncode == 0:
                self.action_label.setText("✓ At home position")
                self._append_log("Home position reached.", level="success")
            else:
                self.action_label.setText("⚠️ Home failed")
                self._append_log(
                    "Home move failed. See the terminal for details and check for obstacles.",
                    level="error",
                )
                print("[DASHBOARD] Home command error:", result.stderr)
        except Exception as e:
            self.action_label.setText("⚠️ Home error")
            self._append_log(
                "Could not move to home. Check the robot connection and try again.",
                level="error",
            )
            print("[DASHBOARD] Home error:", e)
    
    def run_from_dashboard(self):
        """Execute the selected RUN item (same as pressing START)"""
        if not self.is_running:
            self.start_stop_btn.setChecked(True)
            self.start_run()
    
    
    def update_elapsed_time(self):
        """Update elapsed time"""
        if self.start_time:
            self.elapsed_seconds = int((datetime.now() - self.start_time).total_seconds())
            minutes = self.elapsed_seconds // 60
            seconds = self.elapsed_seconds % 60
            self.time_label.setText(f"Time: {minutes:02d}:{seconds:02d}")
    
    # ========== DEVICE MANAGER SIGNAL HANDLERS ==========
    
    def on_robot_status_changed(self, status: str):
        """Handle robot status change from device manager
        
        Args:
            status: "empty", "online", or "offline"
        """
        if self.robot_indicator1:
            if status == "empty":
                self.robot_indicator1.set_null()
                if self.robot_indicator2:
                    self.robot_indicator2.set_null()
            elif status == "online":
                self.robot_indicator1.set_connected(True)
            else:
                self.robot_indicator1.set_connected(False)
        self._robot_status = status
        self._update_status_summaries()
    
    def on_camera_status_changed(self, camera_name: str, status: str):
        """Handle camera status change from device manager
        
        Args:
            camera_name: "front" or "wrist"
            status: "empty", "online", or "offline"
        """
        if camera_name == "front" and self.camera_front_circle:
            if status == "empty":
                self.camera_front_circle.set_null()
            elif status == "online":
                self.camera_front_circle.set_connected(True)
            else:
                self.camera_front_circle.set_connected(False)
        elif camera_name == "wrist" and self.camera_wrist_circle:
            if status == "empty":
                self.camera_wrist_circle.set_null()
            elif status == "online":
                self.camera_wrist_circle.set_connected(True)
            else:
                self.camera_wrist_circle.set_connected(False)
        elif self.camera_indicator3 and camera_name not in {"front", "wrist"}:
            if status == "empty":
                self.camera_indicator3.set_null()
            elif status == "online":
                self.camera_indicator3.set_connected(True)
            else:
                self.camera_indicator3.set_connected(False)

        self._camera_status[camera_name] = status
        self._update_status_summaries()

        if self.camera_view_active and camera_name == self.active_camera_name:
            self.update_camera_previews(force=True)

    def _update_status_summaries(self):
        """Update compact status summary labels."""
        if not hasattr(self, "robot_summary_label") or not hasattr(self, "camera_summary_label"):
            return

        robot_online = 1 if self._robot_status == "online" else 0
        self.robot_summary_label.setText(f"R:{robot_online}/{self._robot_total}")

        camera_total = len(self._camera_status)
        camera_online = sum(1 for state in self._camera_status.values() if state == "online")
        self.camera_summary_label.setText(f"C:{camera_online}/{camera_total}")
    
    def on_discovery_log(self, message: str):
        """Handle discovery log messages from device manager

        Args:
            message: Log message to display
        """
        level = "info"
        cleaned = message.strip()
        if cleaned.upper().startswith("ERROR:"):
            level = "error"
            cleaned = cleaned.split(":", 1)[-1].strip()
        elif cleaned.upper().startswith("WARN:"):
            level = "warning"
            cleaned = cleaned.split(":", 1)[-1].strip()

        self._append_log(cleaned, level=level)
