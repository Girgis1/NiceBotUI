"""Multi-arm configuration helpers for the Settings tab."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from utils.home_move_worker import HomeMoveRequest, HomeMoveWorker
from utils.mode_widgets import ModeSelector, SingleArmConfig
from utils.config_compat import (
    get_enabled_arms,
    get_home_positions,
)
from utils.home_service import save_home_positions
from utils.port_tester import PortTestRequest, PortTestWorker
from .calibration_dialog import SO101CalibrationDialog


class MultiArmMixin:
    """Encapsulates robot/teleop configuration UI and helpers."""

    def create_robot_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        rest_section = QLabel("🏠 Home Position")
        rest_section.setStyleSheet(
            "color: #4CAF50; font-size: 14px; font-weight: bold; margin-bottom: 2px;"
        )
        layout.addWidget(rest_section)

        rest_row = QHBoxLayout()
        rest_row.setSpacing(6)

        self.home_btn = QPushButton("🏠 Home All Arms")
        self.home_btn.setFixedHeight(45)
        self.home_btn.setStyleSheet(self.get_button_style("#2196F3", "#1976D2"))
        self.home_btn.clicked.connect(self.home_all_arms)
        rest_row.addWidget(self.home_btn)

        velocity_label = QLabel("Master Velocity:")
        velocity_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        velocity_label.setFixedWidth(110)
        rest_row.addWidget(velocity_label)

        self.rest_velocity_spin = QSpinBox()
        self.rest_velocity_spin.setMinimum(50)
        self.rest_velocity_spin.setMaximum(2000)
        self.rest_velocity_spin.setValue(600)
        self.rest_velocity_spin.setFixedHeight(45)
        self.rest_velocity_spin.setFixedWidth(80)
        self.rest_velocity_spin.setButtonSymbols(QSpinBox.NoButtons)
        self.rest_velocity_spin.setStyleSheet(
            """
            QSpinBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
            }
            QSpinBox:focus {
                border-color: #4CAF50;
                background-color: #555555;
            }
            """
        )
        rest_row.addWidget(self.rest_velocity_spin)

        self.test_ports_btn = QPushButton("🧪 Test Ports")
        self.test_ports_btn.setFixedHeight(45)
        self.test_ports_btn.setStyleSheet(self.get_button_style("#FF9800", "#F57C00"))
        self.test_ports_btn.clicked.connect(self.test_all_robot_ports)
        rest_row.addWidget(self.test_ports_btn)
        rest_row.addStretch()

        layout.addLayout(rest_row)
        layout.addSpacing(8)

        config_section = QLabel("🤖 Robot Arms (Followers)")
        config_section.setStyleSheet("color: #4CAF50; font-size: 15px; font-weight: bold;")
        layout.addWidget(config_section)

        self.robot_mode_selector = ModeSelector()
        self.robot_mode_selector.mode_changed.connect(self.on_robot_mode_changed)
        layout.addWidget(self.robot_mode_selector)

        self.solo_container = QWidget()
        solo_layout = QVBoxLayout(self.solo_container)
        solo_layout.setContentsMargins(0, 0, 0, 0)

        arm_select_row = QHBoxLayout()
        arm_select_label = QLabel("Select Arm:")
        arm_select_label.setStyleSheet("color: #e0e0e0; font-size: 14px;")
        arm_select_row.addWidget(arm_select_label)

        self.solo_arm_selector = QComboBox()
        self.solo_arm_selector.addItems(["Arm 1", "Arm 2"])
        self.solo_arm_selector.setStyleSheet(self._selector_style())
        self.solo_arm_selector.currentIndexChanged.connect(self.on_solo_arm_changed)
        arm_select_row.addWidget(self.solo_arm_selector)
        arm_select_row.addStretch()
        solo_layout.addLayout(arm_select_row)

        self.solo_arm_config = SingleArmConfig("Arm 1")
        self.solo_arm_config.home_clicked.connect(lambda: self.home_arm(self.solo_arm_selector.currentIndex()))
        self.solo_arm_config.set_home_clicked.connect(
            lambda: self.set_home_arm(self.solo_arm_selector.currentIndex())
        )
        self.solo_arm_config.calibrate_clicked.connect(
            lambda: self.calibrate_arm_at_index(self.solo_arm_selector.currentIndex())
        )
        self.solo_arm_config.test_clicked.connect(
            lambda: self.test_robot_arm(self.solo_arm_selector.currentIndex(), source_widget=self.solo_arm_config)
        )
        solo_layout.addWidget(self.solo_arm_config)
        layout.addWidget(self.solo_container)

        self.bimanual_container = QWidget()
        bimanual_layout = QVBoxLayout(self.bimanual_container)
        bimanual_layout.setContentsMargins(0, 0, 0, 0)

        arms_row = QHBoxLayout()
        self.robot_arm1_config = SingleArmConfig("Left Arm (Arm 1)")
        self.robot_arm1_config.home_clicked.connect(lambda: self.home_arm(0))
        self.robot_arm1_config.set_home_clicked.connect(lambda: self.set_home_arm(0))
        self.robot_arm1_config.calibrate_clicked.connect(lambda: self.calibrate_arm_at_index(0))
        self.robot_arm1_config.test_clicked.connect(
            lambda: self.test_robot_arm(0, source_widget=self.robot_arm1_config)
        )
        arms_row.addWidget(self.robot_arm1_config)

        self.robot_arm2_config = SingleArmConfig("Right Arm (Arm 2)")
        self.robot_arm2_config.home_clicked.connect(lambda: self.home_arm(1))
        self.robot_arm2_config.set_home_clicked.connect(lambda: self.set_home_arm(1))
        self.robot_arm2_config.calibrate_clicked.connect(lambda: self.calibrate_arm_at_index(1))
        self.robot_arm2_config.test_clicked.connect(
            lambda: self.test_robot_arm(1, source_widget=self.robot_arm2_config)
        )
        arms_row.addWidget(self.robot_arm2_config)
        bimanual_layout.addLayout(arms_row)
        layout.addWidget(self.bimanual_container)

        layout.addSpacing(8)

        teleop_section = QLabel("🎮 Teleoperation (Leaders)")
        teleop_section.setStyleSheet("color: #4CAF50; font-size: 15px; font-weight: bold;")
        layout.addWidget(teleop_section)

        self.teleop_mode_selector = ModeSelector()
        self.teleop_mode_selector.mode_changed.connect(self.on_teleop_mode_changed)
        layout.addWidget(self.teleop_mode_selector)

        self.teleop_solo_container = QWidget()
        teleop_solo_layout = QVBoxLayout(self.teleop_solo_container)
        teleop_solo_layout.setContentsMargins(0, 0, 0, 0)

        teleop_arm_select_row = QHBoxLayout()
        teleop_arm_select_label = QLabel("Select Arm:")
        teleop_arm_select_label.setStyleSheet("color: #e0e0e0; font-size: 14px;")
        teleop_arm_select_row.addWidget(teleop_arm_select_label)

        self.teleop_solo_arm_selector = QComboBox()
        self.teleop_solo_arm_selector.addItems(["Arm 1", "Arm 2"])
        self.teleop_solo_arm_selector.setStyleSheet(self._selector_style())
        self.teleop_solo_arm_selector.currentIndexChanged.connect(self.on_teleop_solo_arm_changed)
        teleop_arm_select_row.addWidget(self.teleop_solo_arm_selector)
        teleop_arm_select_row.addStretch()
        teleop_solo_layout.addLayout(teleop_arm_select_row)

        self.teleop_solo_arm_config = SingleArmConfig("Leader Arm 1", show_home_controls=False)
        self.teleop_solo_arm_config.test_clicked.connect(
            lambda: self.test_teleop_arm(self.teleop_solo_arm_selector.currentIndex(), self.teleop_solo_arm_config)
        )
        teleop_solo_layout.addWidget(self.teleop_solo_arm_config)
        layout.addWidget(self.teleop_solo_container)

        self.teleop_bimanual_container = QWidget()
        teleop_bimanual_layout = QVBoxLayout(self.teleop_bimanual_container)
        teleop_bimanual_layout.setContentsMargins(0, 0, 0, 0)

        teleop_arms_row = QHBoxLayout()
        self.teleop_arm1_config = SingleArmConfig("Left Leader (Arm 1)", show_home_controls=False)
        self.teleop_arm1_config.test_clicked.connect(
            lambda: self.test_teleop_arm(0, self.teleop_arm1_config)
        )
        teleop_arms_row.addWidget(self.teleop_arm1_config)
        self.teleop_arm2_config = SingleArmConfig("Right Leader (Arm 2)", show_home_controls=False)
        self.teleop_arm2_config.test_clicked.connect(
            lambda: self.test_teleop_arm(1, self.teleop_arm2_config)
        )
        teleop_arms_row.addWidget(self.teleop_arm2_config)
        teleop_bimanual_layout.addLayout(teleop_arms_row)
        layout.addWidget(self.teleop_bimanual_container)

        layout.addStretch()
        return widget

    def _selector_style(self) -> str:
        return (
            """
            QComboBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
            }
            """
        )

    def on_robot_mode_changed(self, mode: str):
        if mode == "solo":
            self.solo_container.show()
            self.bimanual_container.hide()
        else:
            self.solo_container.hide()
            self.bimanual_container.show()

    def on_solo_arm_changed(self, index: int):
        arms = self.config.get("robot", {}).get("arms", [])
        if index < len(arms) and self.solo_arm_config:
            arm = arms[index]
            self.solo_arm_config.set_port(arm.get("port", ""))
            self.solo_arm_config.set_id(arm.get("id", ""))
            self.solo_arm_config.set_home_positions(arm.get("home_positions", []))

    def on_teleop_mode_changed(self, mode: str):
        if mode == "solo":
            self.teleop_solo_container.show()
            self.teleop_bimanual_container.hide()
        else:
            self.teleop_solo_container.hide()
            self.teleop_bimanual_container.show()

    def on_teleop_solo_arm_changed(self, index: int):
        arms = self.config.get("teleop", {}).get("arms", [])
        if index < len(arms) and self.teleop_solo_arm_config:
            arm = arms[index]
            self.teleop_solo_arm_config.set_port(arm.get("port", ""))
            self.teleop_solo_arm_config.set_id(arm.get("id", ""))

    def home_arm(self, arm_index: int):
        if self._home_thread and self._home_thread.isRunning():
            self.status_label.setText("⏳ Already moving...")
            return

        home_pos = get_home_positions(self.config, arm_index)
        if not home_pos:
            self.status_label.setText(f"❌ No home position for Arm {arm_index + 1}. Set home first.")
            return

        velocity = self.rest_velocity_spin.value() if self.rest_velocity_spin else 600
        self.status_label.setText(f"🏠 Moving Arm {arm_index + 1} to home...")
        self.home_btn.setEnabled(False)

        request = HomeMoveRequest(config=self.config, velocity_override=velocity, arm_index=arm_index)
        worker = HomeMoveWorker(request)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_home_progress)
        worker.finished.connect(self._on_home_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_home_thread_finished)

        self._home_worker = worker
        self._home_thread = thread
        self._pending_home_velocity = velocity
        thread.start()

    def set_home_arm(self, arm_index: int):
        try:
            from utils.motor_controller import MotorController

            self.status_label.setText(f"⏳ Reading positions from Arm {arm_index + 1}...")
            motor_controller = MotorController(self.config, arm_index=arm_index)

            if not motor_controller.connect():
                self.status_label.setText(f"❌ Failed to connect to Arm {arm_index + 1}")
                return

            positions = motor_controller.read_positions()
            motor_controller.disconnect()

            if positions is None:
                self.status_label.setText(f"❌ Failed to read positions from Arm {arm_index + 1}")
                return

            self.config = save_home_positions(
                positions,
                arm_index,
                home_velocity=self.rest_velocity_spin.value() if self.rest_velocity_spin else None,
                config_path=self.config_path,
            )

            self._update_home_widgets(arm_index, positions)
            self.status_label.setText(f"✓ Home position saved for Arm {arm_index + 1}: {positions}")
            self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")
            self.config_changed.emit()
        except Exception as exc:
            self.status_label.setText(f"❌ Error setting home for Arm {arm_index + 1}: {exc}")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")

    def calibrate_arm_at_index(self, arm_index: int):
        """Launch the touch calibration dialog for the requested arm."""
        arms = self.config.setdefault("robot", {}).setdefault("arms", [])
        while len(arms) <= arm_index:
            arms.append({})
        arm_cfg = arms[arm_index]

        default_robot_type = arm_cfg.get("robot_type", "so101")
        default_arm_role = arm_cfg.get("arm_role", "follower")
        default_port = arm_cfg.get("port") or self._get_arm_port_from_ui(arm_index)
        default_robot_id = arm_cfg.get("id") or self._suggest_robot_id(default_robot_type, default_arm_role)
        available_ports = self._collect_known_ports()

        dialog = SO101CalibrationDialog(
            parent=self.window() or self,
            default_robot_type=default_robot_type,
            default_arm_role=default_arm_role,
            default_port=default_port,
            default_robot_id=default_robot_id,
            available_ports=available_ports,
        )
        dialog.calibration_finished.connect(
            lambda payload, idx=arm_index: self._apply_calibration_result(idx, payload)
        )
        dialog.exec()

    # ------------------------------------------------------------------ Calibration helpers
    def _suggest_robot_id(self, robot_type: str, arm_role: str) -> str:
        return f"R_{(robot_type or 'so101').lower()}_{(arm_role or 'follower').title()}"

    def _collect_known_ports(self) -> List[str]:
        ports: List[str] = []

        def add_port(value: Optional[str]):
            if not value:
                return
            normalized = value.strip()
            if normalized and normalized not in ports:
                ports.append(normalized)

        for arm in self.config.get("robot", {}).get("arms", []):
            add_port(arm.get("port"))

        widgets = [
            self.robot_arm1_config,
            self.robot_arm2_config,
            self.solo_arm_config,
        ]
        for widget in widgets:
            if widget:
                try:
                    add_port(widget.get_port())
                except Exception:
                    continue
        return ports

    def _get_arm_port_from_ui(self, arm_index: int) -> str:
        widget = None
        if arm_index == 0 and self.robot_arm1_config:
            widget = self.robot_arm1_config
        elif arm_index == 1 and self.robot_arm2_config:
            widget = self.robot_arm2_config

        if self.solo_arm_config and self.solo_arm_selector and self.solo_arm_selector.currentIndex() == arm_index:
            widget = self.solo_arm_config

        return widget.get_port() if widget else ""

    def _apply_calibration_result(self, arm_index: int, payload: Dict[str, str]):
        try:
            arms = self.config.setdefault("robot", {}).setdefault("arms", [])
            while len(arms) <= arm_index:
                arms.append({})
            arm_cfg = arms[arm_index]
            arm_cfg["port"] = payload["port"]
            arm_cfg["id"] = payload["robot_id"]
            arm_cfg["robot_type"] = payload["robot_type"]
            arm_cfg["arm_role"] = payload["arm_role"]
            Path(self.config_path).write_text(json.dumps(self.config, indent=2))
            self._sync_ui_arm_fields(arm_index, payload)
            self.status_label.setText(
                f"✓ Calibration saved for Arm {arm_index + 1}: {payload['robot_id']} on {payload['port']}"
            )
            self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")
            self.config_changed.emit()
        except Exception as exc:
            self.status_label.setText(f"❌ Failed to store calibration: {exc}")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")

    def _sync_ui_arm_fields(self, arm_index: int, payload: Dict[str, str]):
        if arm_index == 0 and self.robot_arm1_config:
            self.robot_arm1_config.set_port(payload["port"])
            self.robot_arm1_config.set_id(payload["robot_id"])
        if arm_index == 1 and self.robot_arm2_config:
            self.robot_arm2_config.set_port(payload["port"])
            self.robot_arm2_config.set_id(payload["robot_id"])
        if self.solo_arm_config and self.solo_arm_selector and self.solo_arm_selector.currentIndex() == arm_index:
            self.solo_arm_config.set_port(payload["port"])
            self.solo_arm_config.set_id(payload["robot_id"])

    def home_all_arms(self):
        enabled_arms = get_enabled_arms(self.config, "robot")
        if not enabled_arms:
            self.status_label.setText("❌ No enabled arms to home")
            return
        self.status_label.setText(f"🏠 Homing {len(enabled_arms)} enabled arm(s)...")
        self.home_arm(0)

    def set_rest_position(self):
        try:
            from utils.motor_controller import MotorController

            self.status_label.setText("⏳ Reading motor positions from Arm 1...")
            self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")

            motor_controller = MotorController(self.config, arm_index=0)
            if not motor_controller.connect():
                self.status_label.setText("❌ Failed to connect to motors")
                self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
                return

            positions = motor_controller.read_positions()
            motor_controller.disconnect()

            if positions is None:
                self.status_label.setText("❌ Failed to read motor positions")
                self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
                return

            self.config = save_home_positions(
                positions,
                arm_index=0,
                home_velocity=self.rest_velocity_spin.value() if self.rest_velocity_spin else None,
                config_path=self.config_path,
            )
            self._update_home_widgets(0, positions)
            self.status_label.setText(f"✓ Home saved for Arm 1: {positions}")
            self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")
            self.config_changed.emit()
        except Exception as exc:
            self.status_label.setText(f"❌ Error: {exc}")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")

    def go_home(self):
        if self._home_thread and self._home_thread.isRunning():
            self.status_label.setText("⏳ Already moving to home...")
            self.status_label.setStyleSheet("QLabel { color: #FFB74D; font-size: 15px; padding: 8px; }")
            return

        home_pos = get_home_positions(self.config, arm_index=0)
        if not home_pos:
            self.status_label.setText("❌ No home position saved for Arm 1. Click 'Set Home' first.")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
            return

        velocity = self.rest_velocity_spin.value()
        self._pending_home_velocity = velocity

        self.status_label.setText("🏠 Moving Arm 1 to home position...")
        self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")
        self.home_btn.setEnabled(False)

        request = HomeMoveRequest(config=self.config, velocity_override=velocity, arm_index=0)
        worker = HomeMoveWorker(request)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_home_progress)
        worker.finished.connect(self._on_home_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_home_thread_finished)

        self._home_thread = thread
        self._home_worker = worker
        thread.start()

    def calibrate_arm(self):
        try:
            from PySide6.QtWidgets import QMessageBox
            from utils.motor_controller import MotorController

            reply = QMessageBox.warning(
                self,
                "Calibration Warning",
                "⚠️ This will move the arm through its full range of motion.\n\n"
                "Please ensure:\n"
                "• Workspace is clear\n"
                "• Arm can move freely\n"
                "• Emergency stop is accessible\n\n"
                "Continue with calibration?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )

            if reply != QMessageBox.Yes:
                return

            self.status_label.setText("⏳ Starting calibration...")
            self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")

            motor_config = self.config.get("robot", {})
            motor_controller = MotorController(motor_config)

            if not motor_controller.connect():
                self.status_label.setText("❌ Failed to connect to motors")
                self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
                return

            self.status_label.setText("⏳ Step 1/3: Reading current positions...")
            current_positions = motor_controller.read_positions()
            if not current_positions:
                self.status_label.setText("❌ Failed to read positions")
                self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
                motor_controller.disconnect()
                return

            self.status_label.setText("⏳ Step 2/3: Moving to home position...")
            home_positions = [2048] * len(current_positions)
            motor_controller.set_positions(home_positions, velocity=400, wait=True, keep_connection=True)

            self.status_label.setText("⏳ Step 3/3: Testing joint range...")
            for i in range(len(current_positions)):
                test_positions = home_positions.copy()
                test_positions[i] = 2248
                motor_controller.set_positions(test_positions, velocity=300, wait=True, keep_connection=True)
                time.sleep(0.5)
                test_positions[i] = 1848
                motor_controller.set_positions(test_positions, velocity=300, wait=True, keep_connection=True)
                time.sleep(0.5)
                motor_controller.set_positions(home_positions, velocity=300, wait=True, keep_connection=True)

            calib_cfg = self.config.setdefault("calibration", {})
            calib_cfg["home_positions"] = home_positions
            calib_cfg["calibrated"] = True
            calib_cfg["date"] = str(Path(__file__).stat().st_mtime)

            Path(self.config_path).write_text(json.dumps(self.config, indent=2))
            motor_controller.disconnect()

            self.status_label.setText("✓ Calibration complete!")
            self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")
            self.config_changed.emit()
        except Exception as exc:
            self.status_label.setText(f"❌ Error: {exc}")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")

    def _on_home_progress(self, message: str) -> None:
        self.status_label.setText(message)
        self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")

    def _on_home_finished(self, success: bool, message: str) -> None:
        self.home_btn.setEnabled(True)
        if success:
            detail = message or f"✓ Moved to home position at velocity {self._pending_home_velocity or 0}"
            color = "#4CAF50"
        else:
            detail = message or "Unknown error"
            if not detail.startswith("❌"):
                detail = f"❌ Error: {detail}"
            color = "#f44336"
        self.status_label.setText(detail)
        self.status_label.setStyleSheet(f"QLabel {{ color: {color}; font-size: 15px; padding: 8px; }}")
        self._pending_home_velocity = None

    def _on_home_thread_finished(self) -> None:
        if self._home_thread:
            self._home_thread.deleteLater()
        self._home_thread = None
        self._home_worker = None
        self._pending_home_velocity = None

    # ------------------------------------------------------------------ Port testing
    def test_robot_arm(self, arm_index: int, source_widget: SingleArmConfig | None = None):
        request = self._build_port_test_request(
            arm_index,
            section="robot",
            source_widget=source_widget or self._get_robot_arm_widget(arm_index),
            label_prefix="Follower",
        )
        if not request:
            self.status_label.setText(f"❌ No port configured for Arm {arm_index + 1}")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
            return
        self._start_port_test([request])

    def test_teleop_arm(self, arm_index: int, source_widget: SingleArmConfig | None = None):
        request = self._build_port_test_request(
            arm_index,
            section="teleop",
            source_widget=source_widget or self._get_teleop_arm_widget(arm_index),
            label_prefix="Leader",
        )
        if not request:
            self.status_label.setText(f"❌ No port configured for Leader {arm_index + 1}")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
            return
        self._start_port_test([request])

    def test_all_robot_ports(self):
        arms = self.config.get("robot", {}).get("arms", [])
        ports = self._list_serial_ports()
        if not ports:
            return

        requests: list[PortTestRequest] = []
        seen_ports: set[str] = set()
        for port in ports:
            if port in seen_ports:
                continue
            label = self._describe_port_assignment(port)
            if label:
                label = f"{label} – {port}"
            else:
                label = f"Port {port}"
            requests.append(PortTestRequest(port=port, label=label))
            seen_ports.add(port)

        if not requests:
            self.status_label.setText("❌ No robot ports detected")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
            return

        summary = f"⏳ Testing {len(requests)} robot port(s)..."
        self.status_label.setText(summary)
        self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")
        self._start_port_test(requests)

    def _start_port_test(self, requests: list[PortTestRequest]):
        if not requests:
            return

        worker_running = getattr(self, "_port_test_worker", None)
        if worker_running and worker_running.isRunning():
            self.status_label.setText("⏳ Already testing ports...")
            self.status_label.setStyleSheet("QLabel { color: #FFB74D; font-size: 15px; padding: 8px; }")
            return

        self._port_test_worker = PortTestWorker(requests)
        self._port_test_worker.progress.connect(self._on_port_test_progress)
        self._port_test_worker.completed.connect(self._on_port_test_completed)
        self._port_test_worker.finished.connect(self._on_port_test_finished)
        self._port_test_worker.start()

    def _on_port_test_progress(self, message: str):
        self.status_label.setText(message)
        self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")

    def _on_port_test_completed(self, success: bool, message: str):
        color = "#4CAF50" if success else "#FFB74D"
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"QLabel {{ color: {color}; font-size: 15px; padding: 8px; }}")

    def _on_port_test_finished(self):
        if self._port_test_worker:
            self._port_test_worker.deleteLater()
        self._port_test_worker = None

    def _build_port_test_request(
        self,
        arm_index: int,
        section: str,
        source_widget: SingleArmConfig | None,
        label_prefix: str,
    ) -> PortTestRequest | None:
        section_cfg = self.config.get(section, {})
        arms = section_cfg.get("arms", [])
        arm_cfg = arms[arm_index] if arm_index < len(arms) else {}

        port = arm_cfg.get("port", "")
        if (not port) and source_widget:
            try:
                port = source_widget.get_port()
            except Exception:
                port = ""

        if not port:
            return None

        arm_id = arm_cfg.get("id", "")
        if (not arm_id) and source_widget:
            try:
                arm_id = source_widget.get_id()
            except Exception:
                arm_id = ""

        label = f"{label_prefix} Arm {arm_index + 1}"
        if arm_id:
            label += f" ({arm_id})"
        label += f" – {port}"
        return PortTestRequest(port=port, label=label)

    def _get_robot_arm_widget(self, arm_index: int) -> SingleArmConfig | None:
        widgets: list[SingleArmConfig | None] = []
        if self.solo_arm_config and self.solo_arm_selector and self.solo_arm_selector.currentIndex() == arm_index:
            widgets.append(self.solo_arm_config)
        if arm_index == 0 and self.robot_arm1_config:
            widgets.append(self.robot_arm1_config)
        if arm_index == 1 and self.robot_arm2_config:
            widgets.append(self.robot_arm2_config)
        return next((widget for widget in widgets if widget is not None), None)

    def _get_teleop_arm_widget(self, arm_index: int) -> SingleArmConfig | None:
        widgets: list[SingleArmConfig | None] = []
        if (
            self.teleop_solo_arm_config
            and self.teleop_solo_arm_selector
            and self.teleop_solo_arm_selector.currentIndex() == arm_index
        ):
            widgets.append(self.teleop_solo_arm_config)
        if arm_index == 0 and self.teleop_arm1_config:
            widgets.append(self.teleop_arm1_config)
        if arm_index == 1 and self.teleop_arm2_config:
            widgets.append(self.teleop_arm2_config)
        return next((widget for widget in widgets if widget is not None), None)

    def _update_home_widgets(self, arm_index: int, positions: list[int]) -> None:
        if arm_index == 0 and self.robot_arm1_config:
            self.robot_arm1_config.set_home_positions(positions)
        if arm_index == 1 and self.robot_arm2_config:
            self.robot_arm2_config.set_home_positions(positions)

        if self.solo_arm_config and self.solo_arm_selector:
            # Update solo view if it is currently looking at the same arm
            if self.solo_arm_selector.currentIndex() == arm_index:
                self.solo_arm_config.set_home_positions(positions)

    def _list_serial_ports(self) -> List[str]:
        try:
            import serial.tools.list_ports
        except ImportError:
            self.status_label.setText("❌ pyserial is required for port testing")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
            return []

        devices = []
        for info in serial.tools.list_ports.comports():
            device = info.device
            if "ttyACM" in device or "ttyUSB" in device:
                devices.append(device)
        devices = sorted(set(devices))
        if not devices:
            self.status_label.setText("❌ No serial ports detected")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
        return devices

    def _describe_port_assignment(self, port: str) -> str:
        robot_arms = self.config.get("robot", {}).get("arms", [])
        for idx, arm in enumerate(robot_arms):
            if arm.get("port") == port:
                desc = f"Follower Arm {idx + 1}"
                arm_id = arm.get("id")
                if arm_id:
                    desc += f" ({arm_id})"
                return desc

        teleop_arms = self.config.get("teleop", {}).get("arms", [])
        for idx, arm in enumerate(teleop_arms):
            if arm.get("port") == port:
                desc = f"Leader Arm {idx + 1}"
                arm_id = arm.get("id")
                if arm_id:
                    desc += f" ({arm_id})"
                return desc
        return ""

    def find_robot_ports(self):
        try:
            import serial.tools.list_ports
            from utils.motor_controller import MotorController

            self.status_label.setText("⏳ Scanning serial ports...")
            self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")

            ports = serial.tools.list_ports.comports()
            found_robots = []
            for port in ports:
                port_name = port.device
                if not ("ttyACM" in port_name or "ttyUSB" in port_name):
                    continue
                try:
                    test_config = self.config.get("robot", {}).copy()
                    test_config["port"] = port_name
                    motor_controller = MotorController(test_config)
                    if motor_controller.connect():
                        positions = motor_controller.read_positions()
                        motor_controller.disconnect()
                        if positions:
                            found_robots.append(
                                {
                                    "port": port_name,
                                    "motors": len(positions),
                                    "description": port.description,
                                }
                            )
                except Exception:
                    continue

            if not found_robots:
                self.status_label.setText("❌ No robot ports detected")
                self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
                return

            dialog = QDialog(self)
            dialog.setWindowTitle("Found Robot Ports")
            dialog.setMinimumWidth(500)
            dialog.setStyleSheet("QDialog { background-color: #2a2a2a; }")
            layout = QVBoxLayout(dialog)

            title = QLabel(f"✓ Found {len(found_robots)} robot(s):")
            title.setStyleSheet("color: #4CAF50; font-size: 16px; font-weight: bold; padding: 10px;")
            layout.addWidget(title)

            button_group = QButtonGroup(dialog)
            for robot in found_robots:
                radio = QRadioButton(
                    f"{robot['port']} - {robot['motors']} motors - {robot['description']}"
                )
                radio.setStyleSheet("QRadioButton { color: #e0e0e0; font-size: 14px; padding: 5px; }")
                radio.setProperty("port", robot["port"])
                button_group.addButton(radio)
                layout.addWidget(radio)

            if button_group.buttons():
                button_group.buttons()[0].setChecked(True)

            btn_layout = QHBoxLayout()
            btn_layout.addStretch()

            cancel_btn = QPushButton("Cancel")
            cancel_btn.setStyleSheet(self.get_button_style("#909090", "#707070"))
            cancel_btn.clicked.connect(dialog.reject)
            btn_layout.addWidget(cancel_btn)

            select_btn = QPushButton("Select")
            select_btn.setStyleSheet(self.get_button_style("#4CAF50", "#388E3C"))
            select_btn.clicked.connect(dialog.accept)
            btn_layout.addWidget(select_btn)
            layout.addLayout(btn_layout)

            if dialog.exec() == QDialog.Accepted:
                for btn in button_group.buttons():
                    if btn.isChecked():
                        selected_port = btn.property("port")
                        if self.solo_arm_config and self.solo_arm_selector.currentIndex() == 0:
                            self.solo_arm_config.set_port(selected_port)
                        elif self.robot_arm1_config:
                            self.robot_arm1_config.set_port(selected_port)
                        self.status_label.setText(f"✓ Selected port {selected_port}")
                        self.status_label.setStyleSheet(
                            "QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }"
                        )
                        break
        except Exception as exc:
            self.status_label.setText(f"❌ Error: {exc}")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")

    def _populate_calibration_ids(self, combo: QComboBox):
        from pathlib import Path

        calib_base = Path.home() / ".cache" / "huggingface" / "lerobot" / "calibration"
        calibration_ids = []
        for category in ["robots", "teleoperators"]:
            category_dir = calib_base / category
            if category_dir.exists() and category_dir.is_dir():
                for type_dir in category_dir.iterdir():
                    if type_dir.is_dir():
                        for json_file in sorted(type_dir.glob("*.json")):
                            calib_id = json_file.stem
                            if calib_id not in calibration_ids:
                                calibration_ids.append(calib_id)
        calibration_ids.sort()
        combo.clear()
        if calibration_ids:
            combo.addItems(calibration_ids)
        else:
            combo.addItem("(no calibrations found)")
