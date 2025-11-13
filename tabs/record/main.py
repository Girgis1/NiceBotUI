"""
Record Tab - Action Recorder
Allows recording sequences of motor positions for playback
"""

import sys
import shutil
from pathlib import Path
from functools import partial
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QInputDialog, QMessageBox, QLineEdit, QSlider,
    QGridLayout, QFrame
)
from PySide6.QtCore import Qt, QTimer, Signal, QProcess
from PySide6.QtGui import QFont

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from widgets.action_table import ActionTableWidget
from utils.actions_manager import ActionsManager
from utils.config_compat import (
    format_arm_label,
    get_active_arm_index,
    iter_arm_configs,
    set_active_arm_index,
)
from utils.motor_controller import MotorController

from .record_store import RecordStoreMixin
from .transport_controls import TransportControlsMixin
from .tab_bridge import TabBridgeMixin


class RecordTab(
    QWidget,
    RecordStoreMixin,
    TransportControlsMixin,
    TabBridgeMixin,
):
    """Action recorder tab - record and playback motor position sequences"""
    
    # Signal when playback status changes
    playback_status = Signal(str)  # "playing", "stopped", "idle"
    
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.actions_manager = ActionsManager()
        self.active_arm_index = get_active_arm_index(self.config, arm_type="robot")
        self.arm_selector: Optional[QComboBox] = None
        self.motor_controller = MotorController(config, arm_index=self.active_arm_index)
        
        self.current_action_name = "NewAction01"
        self.is_playing = False
        self.play_loop = False
        self.position_counter = 1
        self.default_velocity = 600  # Default velocity
        
        # Live recording state
        self.is_live_recording = False
        self.live_record_timer = QTimer()
        self.live_record_timer.timeout.connect(self.capture_live_position)
        self.live_record_rate = 20  # Hz - INDUSTRIAL: 20Hz for high precision
        self.last_recorded_position = None
        self.live_position_threshold = 3  # INDUSTRIAL: 3 units for tighter precision
        self.live_recorded_data = []  # Store {positions, timestamp, velocity}
        self.live_record_start_time = None
        self._live_record_connected_locally = False

        # Touch teleop state
        self.teleop_step = 10
        self.teleop_active_joint = None
        self.teleop_direction = 0
        self.teleop_multiplier = 1
        self.teleop_torque_enabled = False
        self.teleop_hold_timer = QTimer()
        self.teleop_hold_timer.setInterval(180)
        self.teleop_hold_timer.timeout.connect(self._apply_active_teleop_step)
        self.teleop_process: QProcess | None = None

        self.init_ui()
        self.refresh_action_list()
    
    def init_ui(self):
        """Initialize UI with teleop panel on right side (1/4 width)"""
        # Main horizontal layout: content (3/4) | teleop panel (1/4)
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Left side: Original record content (3/4 width)
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(10)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Top bar: Action selector and Save button
        top_bar = QHBoxLayout()
        
        action_label = QLabel("ACTION:")
        action_label.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        top_bar.addWidget(action_label)
        
        self.action_combo = QComboBox()
        self.action_combo.setEditable(True)
        self.action_combo.setMinimumHeight(60)
        self.action_combo.setStyleSheet("""
            QComboBox {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 16px;
                font-weight: bold;
            }
            QComboBox:hover {
                border-color: #2196F3;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 30px;
                border: none;
            }
            QComboBox::down-arrow {
                width: 0;
                height: 0;
                border-style: solid;
                border-width: 6px 4px 0 4px;
                border-color: #ffffff transparent transparent transparent;
            }
            QComboBox QAbstractItemView {
                background-color: #404040;
                color: #ffffff;
                selection-background-color: #2196F3;
                border: 1px solid #505050;
                font-size: 15px;
            }
        """)
        self.action_combo.currentTextChanged.connect(self.on_action_changed)
        top_bar.addWidget(self.action_combo, stretch=3)

        self.arm_selector_label = QLabel("ARM:")
        self.arm_selector_label.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: bold; padding-left: 8px;")
        top_bar.addWidget(self.arm_selector_label)

        self.arm_selector = QComboBox()
        self.arm_selector.setMinimumHeight(50)
        self.arm_selector.setStyleSheet("""
            QComboBox {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 6px;
                padding: 4px 28px 4px 10px;
                font-size: 14px;
                min-width: 140px;
            }
            QComboBox:hover {
                border-color: #4CAF50;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 26px;
                border: none;
                padding-right: 4px;
            }
            QComboBox::down-arrow {
                width: 0;
                height: 0;
                border-style: solid;
                border-width: 7px 5px 0 5px;
                border-color: #ffffff transparent transparent transparent;
            }
            QComboBox QAbstractItemView {
                background-color: #404040;
                color: #ffffff;
                selection-background-color: #4CAF50;
                font-size: 13px;
            }
        """)
        self.arm_selector.currentIndexChanged.connect(self._on_arm_selector_changed)
        top_bar.addWidget(self.arm_selector, stretch=1)
        
        # New action button
        self.new_action_btn = QPushButton("➕")
        self.new_action_btn.setMinimumHeight(45)
        self.new_action_btn.setMinimumWidth(50)
        self.new_action_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
        """)
        self.new_action_btn.clicked.connect(self.create_new_action)
        top_bar.addWidget(self.new_action_btn)
        
        self.save_btn = QPushButton("💾 SAVE")
        self.save_btn.setMinimumHeight(45)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
            QPushButton:pressed {
                background-color: #2E7D32;
            }
        """)
        self.save_btn.clicked.connect(self.save_action)
        top_bar.addWidget(self.save_btn)
        
        layout.addLayout(top_bar)
        self._refresh_arm_selector()
        
        # Control bar: SET, PLAY/STOP, Loop, Delay buttons
        control_bar = QHBoxLayout()
        control_bar.setSpacing(10)
        
        self.set_btn = QPushButton("📍 SET")
        self.set_btn.setMinimumHeight(50)
        self.set_btn.setMinimumWidth(120)
        self.set_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #1565C0;
            }
        """)
        self.set_btn.clicked.connect(self.record_position)
        control_bar.addWidget(self.set_btn)
        
        self.play_btn = QPushButton("▶ PLAY")
        self.play_btn.setMinimumHeight(50)
        self.play_btn.setMinimumWidth(150)
        self.play_btn.setCheckable(True)
        self.play_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
            QPushButton:checked {
                background-color: #f44336;
            }
            QPushButton:checked:hover {
                background-color: #c62828;
            }
        """)
        self.play_btn.clicked.connect(self.toggle_playback)
        control_bar.addWidget(self.play_btn)
        
        self.loop_btn = QPushButton("🔁 Loop")
        self.loop_btn.setMinimumHeight(50)
        self.loop_btn.setCheckable(True)
        self.loop_btn.setStyleSheet("""
            QPushButton {
                background-color: #909090;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #616161;
            }
            QPushButton:checked {
                background-color: #FF9800;
            }
        """)
        self.loop_btn.toggled.connect(self.toggle_loop)
        control_bar.addWidget(self.loop_btn)
        
        # Delay button removed - delays now handled per-step in composite manifest
        # Users can edit delays in the future step editor UI
        
        control_bar.addStretch()
        
        # Live recording button - far right
        self.live_record_btn = QPushButton("🔴 LIVE RECORD")
        self.live_record_btn.setMinimumHeight(50)
        self.live_record_btn.setMinimumWidth(140)
        self.live_record_btn.setCheckable(True)
        self.live_record_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e57373;
            }
            QPushButton:checked {
                background-color: #4CAF50;
                border: 2px solid #81C784;
            }
            QPushButton:checked:hover {
                background-color: #66BB6A;
            }
        """)
        self.live_record_btn.clicked.connect(self.toggle_live_recording)
        control_bar.addWidget(self.live_record_btn)
        
        # Speed controls - Velocity and Playback Speed Scale
        velocity_frame = QHBoxLayout()
        velocity_frame.setSpacing(15)
        
        # Recording velocity
        velocity_label = QLabel("Record Speed:")
        velocity_label.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        velocity_frame.addWidget(velocity_label)
        
        self.velocity_slider = QSlider(Qt.Horizontal)
        self.velocity_slider.setMinimum(10)
        self.velocity_slider.setMaximum(1000)
        self.velocity_slider.setValue(600)
        self.velocity_slider.setSingleStep(10)
        self.velocity_slider.setPageStep(100)
        self.velocity_slider.setTickPosition(QSlider.TicksBelow)
        self.velocity_slider.setTickInterval(100)
        self.velocity_slider.setMinimumWidth(300)
        self.velocity_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #404040;
                height: 8px;
                background: #2d2d2d;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #2196F3;
                border: 2px solid #1976D2;
                width: 20px;
                margin: -6px 0;
                border-radius: 10px;
            }
            QSlider::handle:horizontal:hover {
                background: #1E88E5;
            }
            QSlider::sub-page:horizontal {
                background: #2196F3;
                border-radius: 4px;
            }
        """)
        self.velocity_slider.valueChanged.connect(self.on_velocity_changed)
        velocity_frame.addWidget(self.velocity_slider)
        
        self.velocity_display = QLabel("600")
        self.velocity_display.setStyleSheet("""
            color: #ffffff;
            background-color: #404040;
            border: 2px solid #505050;
            border-radius: 4px;
            font-size: 16px;
            font-weight: bold;
            padding: 5px 10px;
            min-width: 50px;
        """)
        self.velocity_display.setAlignment(Qt.AlignCenter)
        velocity_frame.addWidget(self.velocity_display)
        
        velocity_frame.addStretch()
        
        # Add control sections to content layout
        layout.addLayout(control_bar)
        layout.addLayout(velocity_frame)

        # Table for recorded positions
        self.table = ActionTableWidget()
        self.table.delete_clicked.connect(self.delete_position)
        self.table.itemChanged.connect(self.on_table_item_changed)
        layout.addWidget(self.table, stretch=1)
        
        # Mode indicator
        from utils.mode_utils import get_mode_display_name, get_current_robot_mode
        current_mode = get_current_robot_mode(self.config)
        self.mode_label = QLabel(f"Recording Mode: {get_mode_display_name(current_mode)}")
        self.mode_label.setStyleSheet("""
            QLabel {
                color: #4CAF50;
                background-color: #2d2d2d;
                border: 2px solid #4CAF50;
                border-radius: 4px;
                padding: 6px;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        self.mode_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.mode_label)
        
        # Status label
        self.status_label = QLabel("Ready to record. Move robot to desired position and press SET.")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                background-color: #2d2d2d;
                border: 1px solid #404040;
                border-radius: 4px;
                padding: 10px;
                font-size: 13px;
            }
        """)
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Add content widget to main layout (left side, 3/4 width)
        main_layout.addWidget(content_widget, stretch=3)
        
        # Right side: Teleop control panel (1/4 width)
        teleop_panel = self._create_teleop_panel()
        teleop_panel.setMaximumWidth(256)
        teleop_panel.setMinimumWidth(220)
        main_layout.addWidget(teleop_panel, stretch=1)

    def _refresh_arm_selector(self) -> None:
        if not self.arm_selector:
            return

        options = [
            (idx, format_arm_label(idx, arm))
            for idx, arm in iter_arm_configs(self.config, arm_type="robot", enabled_only=True)
        ]
        self.arm_selector.blockSignals(True)
        self.arm_selector.clear()
        for idx, label in options:
            self.arm_selector.addItem(label, idx)

        if options:
            active = get_active_arm_index(self.config, preferred=self.active_arm_index, arm_type="robot")
            self.active_arm_index = active
            combo_index = next((i for i, option in enumerate(options) if option[0] == active), 0)
            self.arm_selector.setCurrentIndex(combo_index)

        self.arm_selector.blockSignals(False)
        visible = bool(options)
        self.arm_selector.setVisible(visible)
        if hasattr(self, "arm_selector_label"):
            self.arm_selector_label.setVisible(visible)
        self.arm_selector.setEnabled(visible and len(options) > 1)

    def _on_arm_selector_changed(self, combo_index: int) -> None:
        if not self.arm_selector or combo_index < 0:
            return
        arm_index = self.arm_selector.itemData(combo_index)
        if arm_index is None:
            return
        self._apply_arm_selection(int(arm_index))

    def _apply_arm_selection(self, arm_index: int) -> None:
        resolved = set_active_arm_index(self.config, arm_index, arm_type="robot")
        if resolved == self.active_arm_index:
            return
        self.active_arm_index = resolved
        self._rebuild_motor_controller()
        if hasattr(self, "status_label"):
            label = self.arm_selector.currentText() if self.arm_selector else f"Arm {resolved + 1}"
            self.status_label.setText(f"🎯 Recording arm set to {label}")
            self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")
        self._notify_arm_change()

    def _rebuild_motor_controller(self) -> None:
        existing = getattr(self, "motor_controller", None)
        if existing:
            try:
                existing.disconnect()
            except Exception:
                pass
        try:
            self.motor_controller = MotorController(self.config, arm_index=self.active_arm_index)
        except Exception as exc:
            print(f"[RECORD] ⚠️ Motor controller init failed for arm {self.active_arm_index}: {exc}")

    def _notify_arm_change(self) -> None:
        window = self.window()
        if hasattr(window, "dashboard_tab") and hasattr(window.dashboard_tab, "handle_external_arm_change"):
            try:
                window.dashboard_tab.handle_external_arm_change(self.active_arm_index)
            except Exception:
                pass
        if hasattr(window, "save_config"):
            try:
                window.save_config()
            except Exception:
                pass

    def _launch_bimanual_teleop(self) -> None:
        if self.teleop_process and self.teleop_process.state() != QProcess.NotRunning:
            self.status_label.setText("⏳ Teleop already running…")
            return

        script_path = Path(__file__).resolve().parents[2] / "run_bimanual_teleop.sh"
        if not script_path.exists():
            self.status_label.setText(f"❌ Teleop script missing: {script_path}")
            return

        if not Path("/etc/nv_tegra_release").exists():
            self.status_label.setText("⚠️ Teleop available only on the Jetson device.")
            return

        terminal = shutil.which("gnome-terminal") or shutil.which("xterm")
        if terminal:
            if "gnome-terminal" in terminal:
                args = ["--", "bash", "-lc", "./run_bimanual_teleop.sh; read -p 'Press Enter to close…'"]
            else:
                args = ["-hold", "-e", "./run_bimanual_teleop.sh"]
            started = QProcess.startDetached(terminal, args, str(script_path.parent))
            if started:
                self.status_label.setText("🟠 Teleop launching in external terminal…")
            else:
                self.status_label.setText("❌ Failed to launch teleop terminal.")
            return

        self.status_label.setText("🚀 Launching bimanual teleop…")
        self.teleop_launch_btn.setEnabled(False)

        process = QProcess(self)
        process.setProgram("bash")
        process.setArguments(["-lc", "./run_bimanual_teleop.sh"])
        process.setWorkingDirectory(str(script_path.parent))
        process.readyReadStandardOutput.connect(lambda: self._handle_teleop_output(process.readAllStandardOutput(), False))
        process.readyReadStandardError.connect(lambda: self._handle_teleop_output(process.readAllStandardError(), True))
        process.finished.connect(self._handle_teleop_finished)
        process.start()
        self.teleop_process = process

    def _handle_teleop_output(self, data, is_error: bool) -> None:
        try:
            text = bytes(data).decode("utf-8", errors="ignore").strip()
        except Exception:
            text = ""
        if not text:
            return
        prefix = "⚠️" if is_error else "🟠"
        self.status_label.setText(f"{prefix} {text}")

    def _handle_teleop_finished(self, exit_code: int, status: QProcess.ExitStatus) -> None:
        if exit_code == 0 and status == QProcess.NormalExit:
            self.status_label.setText("✅ Teleop session finished.")
        else:
            self.status_label.setText("⚠️ Teleop script exited unexpectedly.")
        self.teleop_launch_btn.setEnabled(True)
        self.teleop_process = None

    def _create_teleop_panel(self) -> QWidget:
        """Create keypad teleoperation panel - 5 row layout for 600px height."""

        teleop_panel = QFrame()
        teleop_panel.setStyleSheet("""
            QFrame {
                background-color: #1f1f1f;
                border: 1px solid #363636;
                border-radius: 8px;
            }
        """)

        panel_layout = QVBoxLayout(teleop_panel)
        panel_layout.setContentsMargins(8, 8, 8, 8)
        panel_layout.setSpacing(4)

        # Header with HOLD button
        header_row = QHBoxLayout()
        header_label = QLabel("TELEOP")
        header_label.setStyleSheet("color: #90CAF9; font-size: 12px; font-weight: bold;")
        header_row.addWidget(header_label)
        header_row.addStretch()

        self.hold_btn = QPushButton("HOLD")
        self.hold_btn.setCheckable(True)
        self.hold_btn.setFixedHeight(32)
        self.hold_btn.setStyleSheet("""
            QPushButton {
                background-color: #424242;
                color: white;
                border: 1px solid #616161;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 12px;
            }
            QPushButton:pressed, QPushButton:checked {
                background-color: #f44336;
                border-color: #ef9a9a;
            }
        """)
        self.hold_btn.pressed.connect(self.on_hold_pressed)
        self.hold_btn.released.connect(self.on_hold_released)
        header_row.addWidget(self.hold_btn)

        panel_layout.addLayout(header_row)

        # Main grid layout (5 rows x 3 columns)
        grid = QGridLayout()
        grid.setHorizontalSpacing(3)
        grid.setVerticalSpacing(3)

        # Helper to create compact buttons
        def create_btn(text, color):
            btn = QPushButton(text)
            btn.setFixedHeight(48)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 10px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {self._adjust_color(color, 1.1)};
                }}
                QPushButton:pressed {{
                    background-color: {self._adjust_color(color, 0.9)};
                }}
            """)
            return btn

        # ROW 0: J3 Elbow + J2 Shoulder
        btn_j3_up = create_btn("▲\nJ3", "#10B981")
        btn_j3_up.pressed.connect(partial(self.start_teleop_move, 2, 1))
        btn_j3_up.released.connect(self.stop_teleop_move)
        grid.addWidget(btn_j3_up, 0, 0)

        btn_j2_up = create_btn("↑\nJ2", "#1976D2")
        btn_j2_up.pressed.connect(partial(self.start_teleop_move, 1, 1))
        btn_j2_up.released.connect(self.stop_teleop_move)
        grid.addWidget(btn_j2_up, 0, 1)

        btn_j3_down = create_btn("▼\nJ3", "#10B981")
        btn_j3_down.pressed.connect(partial(self.start_teleop_move, 2, -1))
        btn_j3_down.released.connect(self.stop_teleop_move)
        grid.addWidget(btn_j3_down, 0, 2)

        # ROW 1: J1 Base (with center spacer)
        btn_j1_left = create_btn("←\nJ1", "#1976D2")
        btn_j1_left.pressed.connect(partial(self.start_teleop_move, 0, -1))
        btn_j1_left.released.connect(self.stop_teleop_move)
        grid.addWidget(btn_j1_left, 1, 0)

        spacer = QLabel()
        spacer.setStyleSheet("background: #2d2d2d; border-radius: 4px;")
        grid.addWidget(spacer, 1, 1)

        btn_j1_right = create_btn("→\nJ1", "#1976D2")
        btn_j1_right.pressed.connect(partial(self.start_teleop_move, 0, 1))
        btn_j1_right.released.connect(self.stop_teleop_move)
        grid.addWidget(btn_j1_right, 1, 2)

        # ROW 2: J4 Wrist Pitch + J2 Shoulder
        btn_j4_up = create_btn("↑\nJ4", "#F59E0B")
        btn_j4_up.pressed.connect(partial(self.start_teleop_move, 3, 1))
        btn_j4_up.released.connect(self.stop_teleop_move)
        grid.addWidget(btn_j4_up, 2, 0)

        btn_j2_down = create_btn("↓\nJ2", "#1976D2")
        btn_j2_down.pressed.connect(partial(self.start_teleop_move, 1, -1))
        btn_j2_down.released.connect(self.stop_teleop_move)
        grid.addWidget(btn_j2_down, 2, 1)

        btn_j4_down = create_btn("↓\nJ4", "#F59E0B")
        btn_j4_down.pressed.connect(partial(self.start_teleop_move, 3, -1))
        btn_j4_down.released.connect(self.stop_teleop_move)
        grid.addWidget(btn_j4_down, 2, 2)

        # ROW 3: J5 Wrist Roll (2 wide buttons)
        btn_j5_left = create_btn("◀ J5", "#F59E0B")
        btn_j5_left.setFixedHeight(38)
        btn_j5_left.pressed.connect(partial(self.start_teleop_move, 4, -1))
        btn_j5_left.released.connect(self.stop_teleop_move)
        grid.addWidget(btn_j5_left, 3, 0, 1, 2)  # Span 2 columns

        btn_j5_right = create_btn("▶ J5", "#F59E0B")
        btn_j5_right.setFixedHeight(38)
        btn_j5_right.pressed.connect(partial(self.start_teleop_move, 4, 1))
        btn_j5_right.released.connect(self.stop_teleop_move)
        grid.addWidget(btn_j5_right, 3, 2)

        # ROW 4: J6 Gripper (2 wide buttons)
        btn_gripper_close = create_btn("CLOSE J6", "#9333EA")
        btn_gripper_close.setFixedHeight(38)
        btn_gripper_close.clicked.connect(partial(self._apply_teleop_step, 5, -1, 4))
        grid.addWidget(btn_gripper_close, 4, 0, 1, 2)  # Span 2 columns

        btn_gripper_open = create_btn("OPEN J6", "#9333EA")
        btn_gripper_open.setFixedHeight(38)
        btn_gripper_open.clicked.connect(partial(self._apply_teleop_step, 5, 1, 4))
        grid.addWidget(btn_gripper_open, 4, 2)

        panel_layout.addLayout(grid)

        # Step control with up/down arrows
        step_row = QHBoxLayout()
        step_row.setSpacing(4)

        step_label = QLabel("Step:")
        step_label.setStyleSheet("color: #fff; font-size: 9px; font-weight: bold;")
        step_row.addWidget(step_label)

        btn_step_down = QPushButton("▼")
        btn_step_down.setFixedSize(24, 24)
        btn_step_down.clicked.connect(lambda: self.adjust_step(-5))
        btn_step_down.setStyleSheet("""
            QPushButton {
                background: #424242;
                color: white;
                border: none;
                border-radius: 3px;
                font-size: 12px;
            }
            QPushButton:hover { background: #616161; }
        """)
        step_row.addWidget(btn_step_down)

        self.teleop_step_value = QLabel(f"{self.teleop_step}")
        self.teleop_step_value.setFixedWidth(40)
        self.teleop_step_value.setAlignment(Qt.AlignCenter)
        self.teleop_step_value.setStyleSheet("""
            background: #2d2d2d;
            color: #10B981;
            border: 1px solid #404040;
            border-radius: 3px;
            font-size: 11px;
            font-weight: bold;
            padding: 2px;
        """)
        step_row.addWidget(self.teleop_step_value)

        btn_step_up = QPushButton("▲")
        btn_step_up.setFixedSize(24, 24)
        btn_step_up.clicked.connect(lambda: self.adjust_step(5))
        btn_step_up.setStyleSheet("""
            QPushButton {
                background: #424242;
                color: white;
                border: none;
                border-radius: 3px;
                font-size: 12px;
            }
            QPushButton:hover { background: #616161; }
        """)
        step_row.addWidget(btn_step_up)

        step_row.addStretch()
        panel_layout.addLayout(step_row)

        # Torque status
        self.torque_status_label = QLabel()
        self.torque_status_label.setStyleSheet("font-size: 9px;")
        self._update_torque_label(locked=False)
        panel_layout.addWidget(self.torque_status_label)

        panel_layout.addStretch()

        teleop_btn = QPushButton("Teleop")
        teleop_btn.setMinimumHeight(64)
        teleop_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
                font-size: 20px;
                font-weight: bold;
                padding: 12px;
            }
            QPushButton:hover {
                background-color: #FB8C00;
            }
            QPushButton:pressed {
                background-color: #EF6C00;
            }
            QPushButton:disabled {
                background-color: #BDBDBD;
                color: #424242;
            }
        """)
        teleop_btn.clicked.connect(self._launch_bimanual_teleop)
        panel_layout.addWidget(teleop_btn)
        self.teleop_launch_btn = teleop_btn

        return teleop_panel

    def _teleop_button_style(self) -> str:
        return """
            QPushButton {
                background-color: #1976D2;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                min-height: 48px;
            }
            QPushButton:hover {
                background-color: #1565C0;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
        """

    def _teleop_secondary_button_style(self, color: str) -> str:
        hover = self._adjust_color(color, 1.1)
        pressed = self._adjust_color(color, 0.9)
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
                padding: 10px;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:pressed {{
                background-color: {pressed};
            }}
        """

    def _create_teleop_button(self, label: str, joint_index: int, direction: int) -> QPushButton:
        button = QPushButton(label)
        button.setMinimumHeight(48)
        button.setStyleSheet(self._teleop_button_style())
        button.pressed.connect(partial(self.start_teleop_move, joint_index, direction))
        button.released.connect(self.stop_teleop_move)
        return button

    @staticmethod
    def _adjust_color(color: str, factor: float) -> str:
        """Lighten or darken a hex color string."""
        color = color.lstrip('#')
        if len(color) != 6:
            return f"#{color}"

        r = int(color[0:2], 16)
        g = int(color[2:4], 16)
        b = int(color[4:6], 16)

        r = max(0, min(255, int(r * factor)))
        g = max(0, min(255, int(g * factor)))
        b = max(0, min(255, int(b * factor)))

        return f"#{r:02X}{g:02X}{b:02X}"

    def adjust_step(self, delta: int):
        """Adjust step size by delta amount."""
        self.teleop_step = max(1, min(200, self.teleop_step + delta))
        self.teleop_step_value.setText(f"{self.teleop_step}")
    
    def on_teleop_step_changed(self, value: int):
        """Update teleop step size display."""
        self.teleop_step = value
        self.teleop_step_value.setText(f"{value}")

    def ensure_teleop_connection(self) -> bool:
        """Ensure bus connection is available for teleop operations."""
        try:
            if not self.motor_controller.bus:
                if not self.motor_controller.connect():
                    self.status_label.setText("❌ Failed to connect to motors")
                    return False
        except Exception as exc:
            print(f"[TELEOP] ❌ Failed to connect: {exc}")
            self.status_label.setText("❌ Failed to connect to motors")
            return False
        return bool(self.motor_controller.bus)

    def ensure_teleop_ready(self) -> bool:
        """Ensure teleop connection and torque lock are active."""
        if not self.ensure_teleop_connection():
            return False

        if not self.teleop_torque_enabled:
            try:
                for name in self.motor_controller.motor_names:
                    self.motor_controller.bus.write("Torque_Enable", name, 1, normalize=False)
                self.teleop_torque_enabled = True
                self._update_torque_label(locked=True)
            except Exception as exc:
                print(f"[TELEOP] ❌ Failed to enable torque: {exc}")
                self.status_label.setText("❌ Failed to enable torque")
                return False

        return True

    def on_hold_pressed(self):
        """Hold button pressed - release torque for manual positioning."""
        self.stop_teleop_move()
        if not self.ensure_teleop_connection():
            return

        try:
            for name in self.motor_controller.motor_names:
                self.motor_controller.bus.write("Torque_Enable", name, 0, normalize=False)
            self.teleop_torque_enabled = False
            self._update_torque_label(locked=False)
            self.status_label.setText("Torque released - manually move the arm, then press SET")
        except Exception as exc:
            print(f"[TELEOP] ❌ Failed to release torque: {exc}")
            self.status_label.setText("❌ Failed to release torque")

    def on_hold_released(self):
        """Hold released - re-enable torque lock."""
        self.hold_btn.setChecked(False)
        if self.ensure_teleop_ready():
            self.status_label.setText("Torque locked - use keypad for fine adjustments")

    def start_teleop_move(self, joint_index: int, direction: int):
        """Start continuous teleop adjustments for a joint."""
        if not self.ensure_teleop_ready():
            return

        self.teleop_active_joint = joint_index
        self.teleop_direction = direction
        self.teleop_multiplier = 1
        self._apply_active_teleop_step()
        self.teleop_hold_timer.start()

    def stop_teleop_move(self):
        """Stop continuous teleop adjustments."""
        if self.teleop_hold_timer.isActive():
            self.teleop_hold_timer.stop()
        self.teleop_active_joint = None
        self.teleop_direction = 0
        self.teleop_multiplier = 1

    def _apply_active_teleop_step(self):
        """Apply a step for the active joint during continuous teleop."""
        if self.teleop_active_joint is None or self.teleop_direction == 0:
            return

        self._apply_teleop_step(
            self.teleop_active_joint,
            self.teleop_direction,
            self.teleop_multiplier,
        )

    def _apply_teleop_step(self, joint_index: int, direction: int, multiplier: int = 1):
        """Apply a teleop step to the given joint."""
        if not self.ensure_teleop_ready():
            return

        try:
            positions = self.motor_controller.read_positions_from_bus()
            if not positions:
                positions = self.motor_controller.read_positions()
            if not positions or joint_index >= len(positions):
                return

            step = self.teleop_step * multiplier
            target_positions = positions[:]
            target_positions[joint_index] = max(0, min(4095, positions[joint_index] + direction * step))

            motor_name = self.motor_controller.motor_names[joint_index]
            velocity = max(120, min(1200, self.default_velocity))
            self.motor_controller.bus.write("Goal_Velocity", motor_name, velocity, normalize=False)
            self.motor_controller.bus.write("Goal_Position", motor_name, target_positions[joint_index], normalize=False)

            print(
                f"[TELEOP] Joint {motor_name}: {positions[joint_index]} -> {target_positions[joint_index]}"
            )

        except Exception as exc:
            print(f"[TELEOP] ❌ Failed to move joint: {exc}")
            self.status_label.setText("❌ Teleop move failed")

    def _update_torque_label(self, locked: bool):
        if locked:
            self.torque_status_label.setText("Torque: LOCKED")
            self.torque_status_label.setStyleSheet("color: #A5D6A7; font-size: 12px; font-weight: bold;")
        else:
            self.torque_status_label.setText("Torque: RELEASED")
            self.torque_status_label.setStyleSheet("color: #FFAB91; font-size: 12px; font-weight: bold;")
    
