"""
Record Tab - Action Recorder
Allows recording sequences of motor positions for playback
"""

import time
from functools import partial
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QInputDialog, QMessageBox, QLineEdit, QSlider,
    QGridLayout, QFrame, QComboBox, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont

import contextlib

from widgets.action_table import ActionTableWidget
from utils.actions_manager import ActionsManager
from utils.config_compat import (
    get_active_arm_index,
    set_active_arm_index,
)
from utils.motor_controller import MotorController
from utils.app_state import AppStateStore
from utils.logging_utils import log_exception
from utils.teleop_controller import TeleopController, TeleopMode

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
        self.state_store = AppStateStore.instance()
        self.active_arm_index = get_active_arm_index(self.config, arm_type="robot")
        self.motor_controller = MotorController(config, arm_index=self.active_arm_index)
        self.teleop_controller = TeleopController(config)
        self.teleop_mode = TeleopMode.instance()
        self._robot_capable = True
        self._robot_available = True
        self._teleop_capable = False
        self.teleop_target = "both"
        self._teleop_log: list[str] = []
        
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
        self._live_record_arm_index = self.active_arm_index

        # Touch teleop state
        self.teleop_step = 10
        self.teleop_active_joint = None
        self.teleop_direction = 0
        self.teleop_multiplier = 1
        self.teleop_torque_enabled = False
        self.teleop_hold_timer = QTimer()
        self.teleop_hold_timer.setInterval(180)
        self.teleop_hold_timer.timeout.connect(self._apply_active_teleop_step)
        self.teleop_controller.status_changed.connect(self._on_teleop_status_message)
        self.teleop_controller.log_message.connect(self._append_teleop_log)
        self.teleop_controller.running_changed.connect(self._on_teleop_running_changed)
        self.teleop_controller.error_occurred.connect(self._on_teleop_error)
        self.teleop_mode.changed.connect(self._on_teleop_mode_changed)

        self.init_ui()
        self.refresh_action_list()
        self._apply_app_state_snapshot()
        self.state_store.state_changed.connect(self._on_app_state_changed)
    
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
        self._sync_active_arm_to_target()

    def _apply_arm_selection(self, arm_index: int) -> None:
        resolved = set_active_arm_index(self.config, arm_index, arm_type="robot")
        if resolved == self.active_arm_index:
            return
        self.active_arm_index = resolved
        self._rebuild_motor_controller()
        if hasattr(self, "status_label"):
            tag = self._arm_tag_for_index(resolved)
            self.status_label.setText(f"🎯 Recording arm set to {tag}")
            self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")
        self._notify_arm_change()

    def _rebuild_motor_controller(self) -> None:
        existing = getattr(self, "motor_controller", None)
        if existing:
            try:
                existing.disconnect()
            except Exception as exc:
                log_exception("RecordTab: failed to disconnect previous motor controller", exc, level="warning")
        try:
            self.motor_controller = MotorController(self.config, arm_index=self.active_arm_index)
        except Exception as exc:
            log_exception(f"RecordTab: motor controller init failed for arm {self.active_arm_index}", exc, level="error")
            if hasattr(self, "status_label"):
                self.status_label.setText(f"❌ Failed to initialize arm {self.active_arm_index + 1}: {exc}")
            self.motor_controller = None

    def _notify_arm_change(self) -> None:
        window = self.window()
        if hasattr(window, "dashboard_tab") and hasattr(window.dashboard_tab, "handle_external_arm_change"):
            try:
                window.dashboard_tab.handle_external_arm_change(self.active_arm_index)
            except Exception as exc:
                log_exception("RecordTab: dashboard arm change notification failed", exc, level="warning")
        if hasattr(window, "save_config"):
            try:
                window.save_config()
            except Exception as exc:
                log_exception("RecordTab: save_config after arm change failed", exc, level="warning")

    # ------------------------------------------------------------------
    # Capability-aware degradation

    def _apply_app_state_snapshot(self) -> None:
        snapshot = self.state_store.snapshot()
        if "capabilities.robot.followers" in snapshot:
            self._robot_capable = bool(snapshot["capabilities.robot.followers"])
        if "capabilities.teleop.available" in snapshot:
            self._teleop_capable = bool(snapshot["capabilities.teleop.available"])
        robot_status = snapshot.get("robot.status")
        if robot_status is not None:
            self._robot_available = robot_status != "empty"
        self._update_robot_capability_ui()

    def _on_app_state_changed(self, key: str, value) -> None:
        if key == "capabilities.robot.followers":
            self._robot_capable = bool(value)
            self._update_robot_capability_ui()
        elif key == "capabilities.teleop.available":
            self._teleop_capable = bool(value)
            self._update_robot_capability_ui()
        elif key == "robot.status":
            self._robot_available = value != "empty"
            self._update_robot_capability_ui()

    def _update_robot_capability_ui(self) -> None:
        can_use = self._robot_capable and self._robot_available

        if hasattr(self, "play_btn") and self.play_btn:
            self.play_btn.setEnabled(can_use or self.is_playing)
        if hasattr(self, "live_record_btn") and self.live_record_btn:
            self.live_record_btn.setEnabled(can_use and not self.is_live_recording)
        if hasattr(self, "set_btn") and self.set_btn:
            self.set_btn.setEnabled(can_use)
        if hasattr(self, "save_btn") and self.save_btn:
            self.save_btn.setEnabled(can_use)
        teleop_running = self.teleop_controller.is_running()
        teleop_ready = can_use and self._teleop_capable
        if hasattr(self, "teleop_launch_btn") and self.teleop_launch_btn:
            self.teleop_launch_btn.setEnabled(teleop_ready or teleop_running)
        teleop_panel = getattr(self, "teleop_panel", None)
        if teleop_panel is not None:
            teleop_panel.setEnabled(can_use or teleop_running)
        capability_label = getattr(self, "teleop_capability_label", None)
        if capability_label:
            if teleop_ready or teleop_running:
                capability_label.hide()
            else:
                capability_label.setText("⚠️ Connect leader controllers to enable Teleop.")
                capability_label.show()

        if not can_use and not self.is_playing and not self.is_live_recording:
            self.status_label.setText("⚠️ Robot unavailable — connect hardware to record or play actions.")

    # ------------------------------------------------------------------
    # Arm selection helpers

    def _robot_arms(self) -> list:
        return (self.config.get("robot", {}) or {}).get("arms", []) or []

    def _arm_tag_for_index(self, arm_index: int) -> str:
        arms = self._robot_arms()
        if arm_index < len(arms):
            name = (arms[arm_index].get("name") or arms[arm_index].get("id") or "").lower()
            if "left" in name:
                return "L"
            if "right" in name:
                return "R"
        if arm_index == 0:
            return "L"
        if arm_index == 1:
            return "R"
        return f"A{arm_index + 1}"

    def _target_arm_indices(self) -> list[int]:
        count = len(self._robot_arms())
        if count == 0:
            return []
        if self.teleop_target == "left":
            return [0]
        if self.teleop_target == "right" and count > 1:
            return [1]
        if self.teleop_target == "both" and count > 1:
            return [0, 1]
        return [0]

    def _primary_arm_index(self) -> int:
        indices = self._target_arm_indices()
        return indices[0] if indices else 0

    def _sync_active_arm_to_target(self) -> None:
        primary = self._primary_arm_index()
        if primary != self.active_arm_index:
            self._apply_arm_selection(primary)

    def _handle_teleop_button(self) -> None:
        if self.teleop_controller.is_running():
            self.teleop_controller.stop()
            return

        if not self._teleop_capable:
            self.status_label.setText("⚠️ Teleop leaders unavailable — connect controllers to start teleop.")
            return

        self._enter_teleop_mode()
        if not self.teleop_controller.start(self.teleop_target):
            self._handle_teleop_mode_exit(update_button=False)
            return

        self.status_label.setText("🚀 Teleop launching…")

    def _enter_teleop_mode(self) -> None:
        if self.teleop_mode.active:
            return
        self.teleop_mode.enter(self.motor_controller.speed_multiplier)
        self.teleop_status_label.setText("⚠️ Teleop mode active - speed limiters disabled")

    def _handle_teleop_mode_exit(self, *, update_button: bool = True) -> None:
        restored = self.teleop_mode.exit()
        if restored is not None:
            self._restore_speed_multiplier(restored)
        self.teleop_status_label.clear()

    def _teleop_target_display(self, short: bool = False) -> str:
        mapping = {
            "both": ("Both Arms", "Both"),
            "left": ("Left Arm", "Left"),
            "right": ("Right Arm", "Right"),
        }
        long_label, short_label = mapping.get(self.teleop_target, ("Both Arms", "Both"))
        return short_label if short else long_label

    def _cycle_teleop_target(self, delta: int) -> None:
        options = ["both", "left", "right"]
        idx = options.index(self.teleop_target)
        self.teleop_target = options[(idx + delta) % len(options)]
        self._update_teleop_target_label()
        self._sync_active_arm_to_target()

    def _update_teleop_target_label(self) -> None:
        if hasattr(self, "teleop_target_label"):
            self.teleop_target_label.setText(self._teleop_target_display())
        if hasattr(self, "teleop_launch_btn") and not self.teleop_controller.is_running():
            self.teleop_launch_btn.setText(f"Start Teleop ({self._teleop_target_display(short=True)})")

    def _is_teleop_active(self) -> bool:
        return self.teleop_controller.is_running()

    def _read_motor_positions_safe(self, *, prefer_bus: bool = True) -> list[int]:
        """Best-effort motor position read that plays nicely with teleop sessions."""

        # During teleop, still attempt to read positions but avoid blocking on bus
        prefer_bus = prefer_bus and not self._is_teleop_active()
        positions = self._read_positions_for_arm(self.active_arm_index, prefer_bus=prefer_bus)
        return positions or []

    def _build_teleop_metadata(self) -> Optional[dict]:
        """Describe the current teleop session / arm selection for recordings."""

        teleop_cfg = self.config.get("teleop", {}) or {}
        arms = teleop_cfg.get("arms", []) or []
        mode = teleop_cfg.get("mode") or ("bimanual" if len(arms) > 1 else "solo")
        fps = teleop_cfg.get("fps", 50)
        metadata = {
            "teleop": {
                "active": self._is_teleop_active(),
                "mode": mode,
                "fps": fps,
                "timestamp": time.time(),
            },
            "arm_selection": self.teleop_target,
        }
        return metadata

    def _restore_speed_multiplier(self, multiplier: float) -> None:
        control_cfg = self.config.setdefault("control", {})
        control_cfg["speed_multiplier"] = multiplier
        self.motor_controller.speed_multiplier = multiplier

    def _read_positions_for_arm(self, arm_index: int, *, prefer_bus: bool = True) -> list[int] | None:
        controller = None
        temporary = False
        if self.motor_controller and arm_index == self.active_arm_index:
            controller = self.motor_controller
        else:
            try:
                controller = MotorController(self.config, arm_index=arm_index)
                temporary = True
            except Exception as exc:
                log_exception(f"RecordTab: failed to init motor controller for arm {arm_index}", exc, level="warning")
                return None

        try:
            if prefer_bus and controller.bus:
                positions = controller.read_positions_from_bus()
                if positions:
                    return positions
            return controller.read_positions()
        finally:
            if temporary and controller:
                with contextlib.suppress(Exception):
                    controller.disconnect()

    def _capture_positions_for_target(self) -> list[tuple[int, list[int]]]:
        results: list[tuple[int, list[int]]] = []
        for arm_index in self._target_arm_indices():
            positions = self._read_positions_for_arm(arm_index, prefer_bus=False)
            if positions and len(positions) == 6:
                results.append((arm_index, positions))
        return results

    def _on_teleop_status_message(self, message: str) -> None:
        if message:
            self.status_label.setText(message)

    def _append_teleop_log(self, message: str) -> None:
        if not message:
            return
        self._teleop_log.append(message)
        if len(self._teleop_log) > 10:
            self._teleop_log.pop(0)
        if hasattr(self, "teleop_log_label"):
            self.teleop_log_label.setText(self._teleop_log[-1])

    def _on_teleop_running_changed(self, running: bool) -> None:
        if running:
            self.teleop_launch_btn.setText("Stop Teleop")
        else:
            self.teleop_launch_btn.setText(f"Start Teleop ({self._teleop_target_display(short=True)})")
        self.teleop_launch_btn.setEnabled(self._robot_capable or running)
        if not running:
            self._handle_teleop_mode_exit()
            self.status_label.setText("✅ Teleop session finished.")
        self._update_robot_capability_ui()

    def _on_teleop_error(self, message: str) -> None:
        if message:
            self.status_label.setText(f"❌ {message}")

    def _on_teleop_mode_changed(self, active: bool) -> None:
        if not active and hasattr(self, "teleop_status_label"):
            self.teleop_status_label.clear()

    def _create_teleop_panel(self) -> QWidget:
        """Create keypad teleoperation panel - 5 row layout for 600px height."""

        teleop_panel = QFrame()
        self.teleop_panel = teleop_panel
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
        self.hold_btn = QPushButton("HOLD")
        self.hold_btn.setCheckable(True)
        self.hold_btn.setMinimumHeight(64)  # doubled height
        self.hold_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.hold_btn.setStyleSheet("""
            QPushButton {
                background-color: #424242;
                color: white;
                border: 1px solid #616161;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
                padding: 8px 12px;
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

        # Torque toggle (full width)
        self.torque_toggle_btn = QPushButton()
        self.torque_toggle_btn.setCheckable(True)
        self.torque_toggle_btn.setMinimumHeight(42)
        self.torque_toggle_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.torque_toggle_btn.toggled.connect(self._on_torque_toggled)
        panel_layout.addWidget(self.torque_toggle_btn)
        self._update_torque_label(locked=False)

        panel_layout.addStretch()

        # Teleop target selector
        selector_layout = QHBoxLayout()
        selector_layout.setSpacing(6)
        self.teleop_target_prev = QPushButton("◀")
        self.teleop_target_prev.setFixedWidth(32)
        self.teleop_target_prev.clicked.connect(lambda: self._cycle_teleop_target(-1))
        selector_layout.addWidget(self.teleop_target_prev)

        self.teleop_target_label = QLabel("Both Arms")
        self.teleop_target_label.setAlignment(Qt.AlignCenter)
        self.teleop_target_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 4px 8px;
            }
        """)
        selector_layout.addWidget(self.teleop_target_label, 1)

        self.teleop_target_next = QPushButton("▶")
        self.teleop_target_next.setFixedWidth(32)
        self.teleop_target_next.clicked.connect(lambda: self._cycle_teleop_target(1))
        selector_layout.addWidget(self.teleop_target_next)
        panel_layout.addLayout(selector_layout)
        self._update_teleop_target_label()

        self.teleop_status_label = QLabel("")
        self.teleop_status_label.setStyleSheet("color: #FFB300; font-size: 11px; padding: 2px;")
        panel_layout.addWidget(self.teleop_status_label)

        self.teleop_capability_label = QLabel("")
        self.teleop_capability_label.setStyleSheet("color: #FF7043; font-size: 10px; padding: 2px;")
        self.teleop_capability_label.setWordWrap(True)
        self.teleop_capability_label.hide()
        panel_layout.addWidget(self.teleop_capability_label)

        teleop_btn = QPushButton("Start Teleop")
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
        teleop_btn.clicked.connect(self._handle_teleop_button)
        panel_layout.addWidget(teleop_btn)
        self.teleop_launch_btn = teleop_btn

        self.teleop_log_label = QLabel("No teleop output yet.")
        self.teleop_log_label.setWordWrap(True)
        self.teleop_log_label.setStyleSheet("""
            QLabel {
                color: #B0BEC5;
                background-color: #1f1f1f;
                border: 1px solid #2c2c2c;
                border-radius: 4px;
                font-size: 10px;
                padding: 6px;
            }
        """)
        panel_layout.addWidget(self.teleop_log_label)

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
            log_exception("RecordTab: teleop motor connect failed", exc, level="error")
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
                if hasattr(self, "torque_toggle_btn"):
                    self.torque_toggle_btn.blockSignals(True)
                    self.torque_toggle_btn.setChecked(True)
                    self.torque_toggle_btn.blockSignals(False)
            except Exception as exc:
                log_exception("RecordTab: teleop enable torque failed", exc, level="error")
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
            if hasattr(self, "torque_toggle_btn"):
                self.torque_toggle_btn.blockSignals(True)
                self.torque_toggle_btn.setChecked(False)
                self.torque_toggle_btn.blockSignals(False)
            self.status_label.setText("Torque released - manually move the arm, then press SET")
        except Exception as exc:
            log_exception("RecordTab: teleop release torque failed", exc, level="error")
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
        text = "Torque: LOCKED" if locked else "Torque: RELEASED"
        bg = "#2E7D32" if locked else "#8E3B2E"
        border = "#43A047" if locked else "#FFAB91"
        self.torque_toggle_btn.setText(text)
        self.torque_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                color: #ffffff;
                border: 1px solid {border};
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
                padding: 8px 10px;
            }}
            QPushButton:checked {{
                background: #2E7D32;
                border-color: #43A047;
            }}
        """)

    def _on_torque_toggled(self, checked: bool) -> None:
        """Toggle torque lock on demand."""
        # Prevent re-entrancy from programmatic sync
        if checked:
            if not self.ensure_teleop_connection():
                self.torque_toggle_btn.blockSignals(True)
                self.torque_toggle_btn.setChecked(False)
                self.torque_toggle_btn.blockSignals(False)
                return
            try:
                for name in self.motor_controller.motor_names:
                    self.motor_controller.bus.write("Torque_Enable", name, 1, normalize=False)
                self.teleop_torque_enabled = True
                self._update_torque_label(locked=True)
                self.status_label.setText("Torque locked - keypad active")
            except Exception as exc:
                log_exception("RecordTab: torque enable toggle failed", exc, level="error")
                self.status_label.setText("❌ Failed to enable torque")
                self.torque_toggle_btn.blockSignals(True)
                self.torque_toggle_btn.setChecked(False)
                self.torque_toggle_btn.blockSignals(False)
        else:
            if not self.ensure_teleop_connection():
                self.torque_toggle_btn.blockSignals(True)
                self.torque_toggle_btn.setChecked(True)
                self.torque_toggle_btn.blockSignals(False)
                return
            try:
                for name in self.motor_controller.motor_names:
                    self.motor_controller.bus.write("Torque_Enable", name, 0, normalize=False)
                self.teleop_torque_enabled = False
                self._update_torque_label(locked=False)
                self.status_label.setText("Torque released - manually move the arm")
            except Exception as exc:
                log_exception("RecordTab: torque release toggle failed", exc, level="error")
                self.status_label.setText("❌ Failed to release torque")
                self.torque_toggle_btn.blockSignals(True)
                self.torque_toggle_btn.setChecked(True)
                self.torque_toggle_btn.blockSignals(False)
    
