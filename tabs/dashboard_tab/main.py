"""
Dashboard Tab - Main robot control interface
This is the existing UI refactored as a tab
"""

import sys
from pathlib import Path
from typing import Optional, Dict, List, Tuple
try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    cv2 = None
    np = None

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTextEdit, QComboBox, QSizePolicy, QSpinBox, QSlider,
    QStackedWidget
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor, QImage, QPixmap

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.camera_hub import CameraStreamHub
from .widgets import CameraDetailDialog, CameraPreviewWidget, CircularProgress, StatusIndicator
from .state import DashboardStateMixin
from .camera import DashboardCameraMixin
from .execution import DashboardExecutionMixin
from .home import DashboardHomeMixin


class DashboardTab(QWidget, DashboardStateMixin, DashboardCameraMixin, DashboardExecutionMixin, DashboardHomeMixin):
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
        self._home_sequence_runner = None
        self._fatal_error_active = False
        self._last_log_code: Optional[str] = None
        self._last_log_message: Optional[str] = None
        self._stopping_run = False

        control_cfg = self.config.setdefault("control", {})
        self.master_speed = float(control_cfg.get("speed_multiplier", 1.0))
        if not 0.1 <= self.master_speed <= 1.2:
            self.master_speed = 1.0

        self.loop_enabled = control_cfg.get("loop_enabled", True)

        self._restoring_run_selection = False
        self._initial_run_selection: str = ""
        self._apply_saved_dashboard_state()

        self._speed_initialized = False

        self.camera_view_active = False
        self.camera_order: List[str] = list(self.config.get("cameras", {}).keys())
        self.vision_zones = self._load_vision_zones()
        self._robot_status = "empty"
        self._camera_status: Dict[str, str] = {
            name: "empty" for name in self.camera_order
        }
        self.robot_indicator1: Optional[StatusIndicator] = None
        self.robot_indicator2: Optional[StatusIndicator] = None
        self._robot_indicator_map: Dict[str, StatusIndicator] = {}
        self.robot_arm_order: List[str] = self._build_robot_arm_order()
        self._robot_status_map: Dict[str, str] = {name: "empty" for name in self.robot_arm_order}
        self._robot_total = len(self.robot_arm_order)
        if not self.robot_arm_order and self.config.get("robot"):
            self.robot_arm_order = ["robot"]
            self._robot_status_map["robot"] = "empty"
            self._robot_total = 1
        self.camera_indicator1: Optional[StatusIndicator] = None
        self.camera_indicator2: Optional[StatusIndicator] = None
        self.camera_indicator3: Optional[StatusIndicator] = None
        self.camera_indicator_map: Dict[str, StatusIndicator] = {}
        self.camera_front_circle: Optional[StatusIndicator] = None
        self.camera_wrist_circle: Optional[StatusIndicator] = None
        self.camera_wrist_right_circle: Optional[StatusIndicator] = None
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
        self._assign_robot_indicator_targets()
        self._update_status_summaries()
        self.validate_config()
        
        # Connect device manager signals if available
        if self.device_manager:
            self.device_manager.robot_status_changed.connect(self.on_robot_status_changed)
            if hasattr(self.device_manager, "robot_arm_status_changed"):
                self.device_manager.robot_arm_status_changed.connect(self.on_robot_arm_status_changed)
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

        self.connection_check_timer = QTimer()
        self.connection_check_timer.timeout.connect(self.check_connections_background)
        self.connection_check_timer.start(10000)
    
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

        self._rebuild_camera_indicator_map()

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
        # Set font with emoji support
        log_font = QFont("DejaVu Sans Mono, Noto Color Emoji, monospace", 13)
        self.log_text.setFont(log_font)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #404040;
                border-radius: 4px;
            }
        """)
        controls_column.addWidget(self.log_text, stretch=1)

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
        self._append_log_entry("welcome", "Welcome to NiceBot!", code="welcome_message")
        self._append_log_entry(
            "info",
            "Pick a Model, Action, or Sequence to begin, or visit Record to capture a new one.",
            code="welcome_instruction",
        )

        # Populate run selector
        self.refresh_run_selector()

        initial_speed = int(round(self.master_speed * 100))
        self.speed_slider.blockSignals(True)
        self.speed_slider.setValue(initial_speed)
        self.speed_slider.blockSignals(False)
        self.on_speed_slider_changed(initial_speed)

    # ------------------------------------------------------------------
    # Status indicator helpers

    def _apply_status_to_indicator(self, indicator: StatusIndicator, status: str) -> None:
        if status == "empty":
            indicator.set_null()
        elif status == "online":
            indicator.set_connected(True)
        elif status == "warning":
            indicator.set_warning()
        else:
            indicator.set_connected(False)

    def _rebuild_camera_indicator_map(self) -> None:
        indicators = [self.camera_indicator1, self.camera_indicator2, self.camera_indicator3]
        self.camera_indicator_map.clear()

        for indicator in indicators:
            if indicator:
                indicator.hide()
                indicator.set_null()

        for idx, camera_name in enumerate(self.camera_order[: len(indicators)]):
            indicator = indicators[idx]
            if indicator is None:
                continue
            indicator.show()
            indicator.setToolTip(self._camera_display_name(camera_name))
            indicator.setAccessibleName(f"camera_indicator_{camera_name}")
            self._apply_status_to_indicator(indicator, self._camera_status.get(camera_name, "empty"))
            self.camera_indicator_map[camera_name] = indicator

        self.camera_front_circle = self.camera_indicator_map.get("front")
        self.camera_wrist_circle = self.camera_indicator_map.get("wrist")
        self.camera_wrist_right_circle = self.camera_indicator_map.get("wrist_right")

        for idx in range(len(self.camera_order), len(indicators)):
            indicator = indicators[idx]
            if indicator:
                indicator.set_null()

    def _ensure_camera_known(self, camera_name: str) -> None:
        added = False
        if camera_name not in self.camera_order:
            self.camera_order.append(camera_name)
            added = True
        if camera_name not in self._camera_status:
            self._camera_status[camera_name] = "empty"
            added = True
        if added or camera_name not in self.camera_indicator_map:
            self._rebuild_camera_indicator_map()

    # ------------------------------------------------------------------
    # Robot indicator helpers

    def _build_robot_arm_order(self) -> List[str]:
        robot_cfg = self.config.get("robot", {}) or {}
        arms = robot_cfg.get("arms", []) or []
        names: List[str] = []
        for idx, arm in enumerate(arms):
            names.append(arm.get("id") or arm.get("name") or f"arm_{idx + 1}")
        return names

    def _rebuild_robot_arm_order(self) -> None:
        names = self._build_robot_arm_order()
        if not names and self.config.get("robot"):
            names = ["robot"]
        previous_statuses = getattr(self, "_robot_status_map", {})
        self.robot_arm_order = names
        self._robot_total = len(names)
        self._robot_status_map = {name: previous_statuses.get(name, "empty") for name in names}
        if hasattr(self, "_assign_robot_indicator_targets"):
            self._assign_robot_indicator_targets()
        self._update_status_summaries()

    def _assign_robot_indicator_targets(self) -> None:
        indicators = [self.robot_indicator1, self.robot_indicator2]
        self._robot_indicator_map.clear()

        for indicator in indicators:
            if indicator:
                indicator.set_null()

        for idx, name in enumerate(self.robot_arm_order[: len(indicators)]):
            indicator = indicators[idx]
            if indicator is None:
                continue
            indicator.show()
            indicator.setToolTip(name.title())
            indicator.setAccessibleName(f"robot_indicator_{name}")
            status = self._robot_status_map.get(name, "empty")
            self._apply_status_to_indicator(indicator, status)
            self._robot_indicator_map[name] = indicator

        for idx in range(len(self.robot_arm_order), len(indicators)):
            indicator = indicators[idx]
            if indicator:
                indicator.set_null()
