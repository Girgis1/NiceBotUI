"""UI widgets for configuring and exercising IK-based teleoperation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional, Sequence

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .solver import IKSolver
from utils.motor_controller import MotorController  # type: ignore

MOTOR_RESOLUTION = 4095.0
DEFAULT_OFFSETS = np.full(6, 2048.0)
DEFAULT_SIGNS = np.array([-1.0, 1.0, 1.0, 1.0, 1.0, 1.0])


@dataclass
class IKPreset:
    name: str
    parameters: Dict[str, float]


class IKToolWidget(QWidget):
    """Embeddable widget exposing preset tuning and IK keypad control."""

    def __init__(self, config: Dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.config = config
        self.solver = IKSolver()
        self.motor_controller: Optional[MotorController] = None

        self._loading = False
        self.parameter_spins: Dict[str, QDoubleSpinBox] = {}
        self.target_position = np.array([0.20, 0.0, 0.18])  # metres
        self.current_solution: Optional[np.ndarray] = None

        self.servo_offsets = DEFAULT_OFFSETS.copy()
        self.servo_signs = DEFAULT_SIGNS.copy()

        self.presets: Dict[str, IKPreset] = {
            "SO-100": IKPreset(
                name="SO-100 Arm",
                parameters={
                    "base_height_mm": 105.0,
                    "shoulder_offset_mm": 32.0,
                    "upper_arm_length_mm": 185.0,
                    "forearm_length_mm": 210.0,
                    "wrist_offset_mm": 95.0,
                    "tool_length_mm": 60.0,
                    "elbow_offset_mm": 0.0,
                },
            ),
            "SO-101": IKPreset(
                name="SO-101 Arm",
                parameters={
                    "base_height_mm": 110.0,
                    "shoulder_offset_mm": 28.0,
                    "upper_arm_length_mm": 200.0,
                    "forearm_length_mm": 230.0,
                    "wrist_offset_mm": 105.0,
                    "tool_length_mm": 70.0,
                    "elbow_offset_mm": 5.0,
                },
            ),
        }

        self._build_ui()
        self._load_from_config()
        self._recompute_solution()

    # ------------------------------------------------------------------ UI helpers
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        header = QLabel("SO-Series IK Toolkit")
        header.setStyleSheet("QLabel { color: #4CAF50; font-size: 18px; font-weight: bold; }")
        layout.addWidget(header)

        description = QLabel(
            "Tune the IK model for SO-100 / SO-101, compute joint solutions using the bundled URDF, "
            "and jog the end-effector in Cartesian space."
        )
        description.setWordWrap(True)
        description.setStyleSheet("QLabel { color: #d0d0d0; font-size: 13px; }")
        layout.addWidget(description)

        layout.addLayout(self._build_preset_controls())
        layout.addLayout(self._build_parameter_grid())
        layout.addWidget(self._build_calibration_panel())
        layout.addWidget(self._build_keypad())

        self.output_box = QTextEdit()
        self.output_box.setReadOnly(True)
        self.output_box.setMinimumHeight(150)
        self.output_box.setStyleSheet(
            "QTextEdit { background-color: #2f2f2f; color: #f0f0f0; border: 1px solid #555; border-radius: 6px; }"
        )
        layout.addWidget(self.output_box)

        footer = QHBoxLayout()
        footer.addStretch()

        self.apply_btn = QPushButton("Save Parameters")
        self.apply_btn.clicked.connect(self._apply_to_config)
        footer.addWidget(self.apply_btn)

        recompute_btn = QPushButton("Recompute IK")
        recompute_btn.clicked.connect(self._recompute_solution)
        footer.addWidget(recompute_btn)

        layout.addLayout(footer)

    def _build_preset_controls(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        label = QLabel("Arm preset:")
        label.setStyleSheet("QLabel { color: #e0e0e0; font-size: 14px; min-width: 120px; }")
        row.addWidget(label)

        self.arm_combo = QComboBox()
        for key, preset in self.presets.items():
            self.arm_combo.addItem(preset.name, key)
        self.arm_combo.currentIndexChanged.connect(self._on_preset_changed)
        row.addWidget(self.arm_combo, stretch=1)

        self.load_preset_btn = QPushButton("Load Preset")
        self.load_preset_btn.clicked.connect(self._load_selected_preset)
        row.addWidget(self.load_preset_btn)

        row.addStretch()
        return row

    def _build_parameter_grid(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)

        param_specs = [
            ("Base Height (mm)", "base_height_mm", 0.0, 400.0),
            ("Shoulder Offset (mm)", "shoulder_offset_mm", 0.0, 200.0),
            ("Upper Arm Length (mm)", "upper_arm_length_mm", 50.0, 400.0),
            ("Forearm Length (mm)", "forearm_length_mm", 50.0, 400.0),
            ("Wrist Offset (mm)", "wrist_offset_mm", 0.0, 200.0),
            ("Tool Length (mm)", "tool_length_mm", 0.0, 200.0),
            ("Elbow Offset (mm)", "elbow_offset_mm", -50.0, 50.0),
        ]

        for row, (label_text, key, minimum, maximum) in enumerate(param_specs):
            label = QLabel(label_text)
            label.setStyleSheet("QLabel { color: #e0e0e0; font-size: 13px; }")
            grid.addWidget(label, row, 0)

            spin = QDoubleSpinBox()
            spin.setRange(minimum, maximum)
            spin.setSingleStep(1.0)
            spin.setDecimals(2)
            spin.setMinimumHeight(36)
            spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
            spin.setStyleSheet(
                "QDoubleSpinBox { background-color: #505050; color: #ffffff; border: 2px solid #707070;"
                " border-radius: 6px; padding: 6px; font-size: 13px; }"
                "QDoubleSpinBox:focus { border-color: #4CAF50; background-color: #555555; }"
            )
            spin.valueChanged.connect(self._update_summary)
            grid.addWidget(spin, row, 1)
            self.parameter_spins[key] = spin

        self.prefer_elbow_up_check = QCheckBox("Prefer elbow-up posture when feasible")
        self.prefer_elbow_up_check.setStyleSheet("QCheckBox { color: #e0e0e0; font-size: 13px; padding: 4px; }")
        grid.addWidget(self.prefer_elbow_up_check, len(param_specs), 0, 1, 2)

        return grid

    def _build_calibration_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(6)
        layout.setContentsMargins(0, 12, 0, 12)

        title = QLabel("Calibration & Mapping")
        title.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; font-weight: bold; }")
        layout.addWidget(title)

        explainer = QLabel(
            "Servo offsets/signs convert IK joint angles into motor units. Capture offsets after aligning the arm to your zero pose."
        )
        explainer.setWordWrap(True)
        explainer.setStyleSheet("QLabel { color: #aaaaaa; font-size: 12px; }")
        layout.addWidget(explainer)

        self.offset_label = QLabel("")
        self.offset_label.setStyleSheet(
            "QLabel { color: #e0e0e0; font-size: 12px; padding: 4px; border: 1px solid #555555; border-radius: 6px; }"
        )
        layout.addWidget(self.offset_label)

        button_row = QHBoxLayout()
        capture_btn = QPushButton("Capture Offsets from Robot")
        capture_btn.clicked.connect(self._capture_offsets_from_robot)
        button_row.addWidget(capture_btn)

        defaults_btn = QPushButton("Reset Defaults")
        defaults_btn.clicked.connect(self._reset_offsets_to_defaults)
        button_row.addWidget(defaults_btn)
        button_row.addStretch()
        layout.addLayout(button_row)

        sign_row = QHBoxLayout()
        sign_row.setSpacing(6)
        sign_row.addWidget(QLabel("Servo signs:"))
        self.sign_combos: list[QComboBox] = []
        for idx in range(6):
            combo = QComboBox()
            combo.addItems(["+1", "-1"])
            combo.setFixedWidth(60)
            combo.currentIndexChanged.connect(self._update_signs_from_ui)
            self.sign_combos.append(combo)
            sign_row.addWidget(QLabel(f"J{idx + 1}"))
            sign_row.addWidget(combo)
        sign_row.addStretch()
        layout.addLayout(sign_row)

        self.hold_connection_check = QCheckBox("Keep bus connection open")
        self.hold_connection_check.setChecked(True)
        self.hold_connection_check.setStyleSheet("QCheckBox { color: #e0e0e0; font-size: 12px; padding: 4px; }")
        layout.addWidget(self.hold_connection_check)

        return container

    def _build_keypad(self) -> QWidget:
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setSpacing(8)
        vbox.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Cartesian Jog Controls")
        title.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; font-weight: bold; }")
        vbox.addWidget(title)

        info = QLabel(
            "Adjust target position in millimetre steps and solve IK. Enable Auto send to push set-points to the robot."
        )
        info.setWordWrap(True)
        info.setStyleSheet("QLabel { color: #aaaaaa; font-size: 12px; }")
        vbox.addWidget(info)

        step_row = QHBoxLayout()
        step_row.addWidget(QLabel("Step (mm):"))
        self.step_spin = QDoubleSpinBox()
        self.step_spin.setRange(1.0, 50.0)
        self.step_spin.setSingleStep(1.0)
        self.step_spin.setValue(10.0)
        self.step_spin.setDecimals(1)
        self.step_spin.setMinimumHeight(32)
        self.step_spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.step_spin.setStyleSheet(
            "QDoubleSpinBox { background-color: #505050; color: #ffffff; border: 2px solid #707070;"
            " border-radius: 6px; padding: 4px; font-size: 12px; }"
        )
        step_row.addWidget(self.step_spin)
        step_row.addStretch()
        vbox.addLayout(step_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)

        def add_button(text: str, callback) -> QPushButton:
            btn = QPushButton(text)
            btn.setMinimumHeight(36)
            btn.clicked.connect(callback)
            return btn

        grid.addWidget(add_button("↑", lambda: self._nudge(dy=self._step_m())), 0, 1)
        grid.addWidget(add_button("↓", lambda: self._nudge(dy=-self._step_m())), 2, 1)
        grid.addWidget(add_button("←", lambda: self._nudge(dx=-self._step_m())), 1, 0)
        grid.addWidget(add_button("→", lambda: self._nudge(dx=self._step_m())), 1, 2)
        grid.addWidget(add_button("⬆ Z", lambda: self._nudge(dz=self._step_m())), 0, 2)
        grid.addWidget(add_button("⬇ Z", lambda: self._nudge(dz=-self._step_m())), 2, 2)

        vbox.addLayout(grid)

        options_row = QHBoxLayout()
        self.reset_btn = QPushButton("🏠 Reset Target")
        self.reset_btn.setMinimumHeight(32)
        self.reset_btn.clicked.connect(self._reset_position)
        options_row.addWidget(self.reset_btn)

        self.auto_send_check = QCheckBox("Auto send to robot")
        self.auto_send_check.setStyleSheet("QCheckBox { color: #e0e0e0; font-size: 12px; padding: 4px; }")
        options_row.addWidget(self.auto_send_check)
        options_row.addStretch()
        vbox.addLayout(options_row)

        velocity_row = QHBoxLayout()
        velocity_row.addWidget(QLabel("Velocity:"))
        self.velocity_spin = QDoubleSpinBox()
        self.velocity_spin.setRange(50, 2000)
        self.velocity_spin.setSingleStep(25)
        self.velocity_spin.setValue(600)
        self.velocity_spin.setDecimals(0)
        self.velocity_spin.setMinimumHeight(32)
        self.velocity_spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.velocity_spin.setStyleSheet(
            "QDoubleSpinBox { background-color: #505050; color: #ffffff; border: 2px solid #707070;"
            " border-radius: 6px; padding: 4px; font-size: 12px; }"
        )
        velocity_row.addWidget(self.velocity_spin)
        velocity_row.addStretch()
        vbox.addLayout(velocity_row)

        self.position_label = QLabel("")
        self.position_label.setStyleSheet(
            "QLabel { color: #e0e0e0; font-size: 13px; padding: 4px; border: 1px solid #555555; border-radius: 6px; }"
        )
        vbox.addWidget(self.position_label)

        self.solution_label = QLabel("")
        self.solution_label.setWordWrap(True)
        self.solution_label.setStyleSheet(
            "QLabel { color: #cfcfcf; font-size: 12px; padding: 4px; border: 1px dashed #555555; border-radius: 6px; }"
        )
        vbox.addWidget(self.solution_label)

        self.send_now_btn = QPushButton("Send to Robot")
        self.send_now_btn.setMinimumHeight(36)
        self.send_now_btn.clicked.connect(self._send_to_robot)
        vbox.addWidget(self.send_now_btn)

        return container

    # ------------------------------------------------------------------ data loading
    def _load_selected_preset(self) -> None:
        preset_key = self.arm_combo.currentData()
        if isinstance(preset_key, str):
            self._apply_preset(self.presets[preset_key])

    def _on_preset_changed(self) -> None:
        if self._loading:
            return
        self._load_selected_preset()

    def _apply_preset(self, preset: IKPreset) -> None:
        self._loading = True
        for key, value in preset.parameters.items():
            spin = self.parameter_spins.get(key)
            if spin:
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
        self._loading = False
        self._update_summary()
        self._append_output(f"Loaded preset: {preset.name}")

    def _load_from_config(self) -> None:
        ik_section = self.config.get("ik", {})
        active = ik_section.get("active_preset")
        if active and active in self.presets:
            index = self.arm_combo.findData(active)
            if index >= 0:
                self.arm_combo.setCurrentIndex(index)
        else:
            self._load_selected_preset()

        params = ik_section.get("parameters")
        if isinstance(params, dict):
            for key, spin in self.parameter_spins.items():
                if key in params:
                    spin.blockSignals(True)
                    spin.setValue(float(params[key]))
                    spin.blockSignals(False)

        if "prefer_elbow_up" in ik_section:
            self.prefer_elbow_up_check.setChecked(bool(ik_section["prefer_elbow_up"]))

        offsets = ik_section.get("servo_offsets")
        if isinstance(offsets, Sequence) and len(offsets) == 6:
            self.servo_offsets = np.array([float(v) for v in offsets])

        signs = ik_section.get("servo_signs")
        if isinstance(signs, Sequence) and len(signs) == 6:
            self.servo_signs = np.array([float(v) for v in signs])

        step_mm = ik_section.get("step_mm")
        if isinstance(step_mm, (int, float)):
            self.step_spin.setValue(float(step_mm))

        velocity = ik_section.get("velocity")
        if isinstance(velocity, (int, float)):
            self.velocity_spin.setValue(float(velocity))

        last_target = ik_section.get("last_target")
        if isinstance(last_target, Sequence) and len(last_target) == 3:
            self.target_position = np.array([float(v) for v in last_target])

        self.auto_send_check.setChecked(bool(ik_section.get("auto_send", False)))
        self.hold_connection_check.setChecked(bool(ik_section.get("keep_connection", True)))

        self._refresh_offset_display()
        self._set_signs_ui()

    # ------------------------------------------------------------------ calculations & UI updates
    def _step_m(self) -> float:
        return self.step_spin.value() / 1000.0

    def _nudge(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> None:
        self.target_position = self.target_position + np.array([dx, dy, dz])
        self._recompute_solution()

    def _reset_position(self) -> None:
        self.target_position = np.zeros(3)
        self._recompute_solution()

    def _refresh_offset_display(self) -> None:
        values = ", ".join(f"{int(v)}" for v in self.servo_offsets)
        self.offset_label.setText(f"Offsets (units): [{values}]")

    def _set_signs_ui(self) -> None:
        for idx, combo in enumerate(self.sign_combos):
            sign = self.servo_signs[idx]
            combo.blockSignals(True)
            combo.setCurrentIndex(0 if sign >= 0 else 1)
            combo.blockSignals(False)

    def _update_signs_from_ui(self) -> None:
        for idx, combo in enumerate(self.sign_combos):
            self.servo_signs[idx] = 1.0 if combo.currentIndex() == 0 else -1.0

    def _update_summary(self) -> None:
        if self._loading:
            return
        up = self.parameter_spins["upper_arm_length_mm"].value()
        forearm = self.parameter_spins["forearm_length_mm"].value()
        wrist = self.parameter_spins["wrist_offset_mm"].value()
        reach = up + forearm + wrist
        summary = (
            f"Approx. reach: {reach:.1f} mm\n"
            f"Tool length: {self.parameter_spins['tool_length_mm'].value():.1f} mm"
        )
        self.prefer_elbow_up_check.setToolTip(
            "When enabled, prefer elbow-up configurations if multiple IK solutions exist."
        )
        self.solution_label.setToolTip("Joint angles produced by the latest IK solve.")
        self.offset_label.setToolTip(
            "Motor units captured from the robot representing the joint zero (rest) offsets."
        )
        # summary label sits above keypad
        # (Wider display updates so no direct set here)

    def _recompute_solution(self) -> None:
        self.position_label.setText(
            f"Target: x={self.target_position[0]:.3f} m, y={self.target_position[1]:.3f} m, z={self.target_position[2]:.3f} m"
        )
        try:
            joints = self.solver.solve(self.target_position)
            self.current_solution = joints
            degrees = np.degrees(joints)
            text = ", ".join(f"J{i + 1}:{deg:.1f}°" for i, deg in enumerate(degrees))
            self.solution_label.setText(f"Solution (rad): {joints.round(4)}\nAngles: {text}")
            self._append_output("Computed IK solution successfully. Adjust offsets before applying to real hardware.")
        except Exception as exc:
            self.current_solution = None
            self.solution_label.setText(f"IK failed: {exc}")
            self._append_output(f"IK failure: {exc}")
            return

        if self.auto_send_check.isChecked():
            self._send_to_robot()

    # ------------------------------------------------------------------ calibration helpers
    def _capture_offsets_from_robot(self) -> None:
        try:
            controller = self._get_motor_controller()
            positions = controller.read_positions()
            if not positions:
                raise RuntimeError("Failed to read motor positions. Ensure torque is enabled and the robot is connected.")
            self.servo_offsets = np.array([float(v) for v in positions])
            self._refresh_offset_display()
            self._append_output("Captured servo offsets from current robot pose.")
            self._maybe_release_connection()
        except Exception as exc:
            self._append_output(f"Offset capture failed: {exc}")

    def _reset_offsets_to_defaults(self) -> None:
        self.servo_offsets = DEFAULT_OFFSETS.copy()
        self.servo_signs = DEFAULT_SIGNS.copy()
        self._refresh_offset_display()
        self._set_signs_ui()
        self._append_output("Offsets reset to factory defaults (2048, default signs).")

    # ------------------------------------------------------------------ hardware interface
    def _get_motor_controller(self) -> MotorController:
        if self.motor_controller is None:
            self.motor_controller = MotorController(self.config)
        if not self.motor_controller.bus and not self.motor_controller.connect():
            raise RuntimeError("Unable to connect to motor bus. Check robot power and USB connection.")
        return self.motor_controller

    def _maybe_release_connection(self) -> None:
        if not self.hold_connection_check.isChecked() and self.motor_controller:
            self.motor_controller.disconnect()
            self.motor_controller = None

    def _radians_to_units(self, radians: np.ndarray) -> np.ndarray:
        scale = MOTOR_RESOLUTION / (2 * math.pi)
        units = self.servo_offsets + self.servo_signs * radians * scale
        return np.clip(np.round(units), 0, MOTOR_RESOLUTION)

    def _send_to_robot(self) -> None:
        if self.current_solution is None:
            self._append_output("Cannot send to robot: No IK solution available.")
            return
        try:
            controller = self._get_motor_controller()
            units = self._radians_to_units(self.current_solution).astype(int).tolist()
            velocity = int(self.velocity_spin.value())
            controller.set_positions(units, velocity=velocity, wait=True, keep_connection=True)
            self._append_output(f"Sent to robot (velocity={velocity}) → {units}")
            self._maybe_release_connection()
        except Exception as exc:
            self._append_output(f"Send failed: {exc}")

    # ------------------------------------------------------------------ config persistence
    def _apply_to_config(self) -> None:
        section = self.config.setdefault("ik", {})
        section["active_preset"] = self.arm_combo.currentData()
        section["parameters"] = {k: spin.value() for k, spin in self.parameter_spins.items()}
        section["prefer_elbow_up"] = self.prefer_elbow_up_check.isChecked()
        section["last_target"] = self.target_position.tolist()
        if self.current_solution is not None:
            section["last_solution_rad"] = self.current_solution.tolist()
        section["servo_offsets"] = self.servo_offsets.tolist()
        section["servo_signs"] = self.servo_signs.tolist()
        section["step_mm"] = self.step_spin.value()
        section["velocity"] = self.velocity_spin.value()
        section["auto_send"] = self.auto_send_check.isChecked()
        section["keep_connection"] = self.hold_connection_check.isChecked()
        self._append_output("Stored IK parameters in memory. Click the main Save button to persist to disk.")

    def _append_output(self, text: str) -> None:
        self.output_box.append(text)

    def closeEvent(self, event) -> None:  # pragma: no cover - Qt hook
        if self.motor_controller is not None:
            try:
                self.motor_controller.disconnect()
            except Exception:
                pass
        self.solver.disconnect()
        super().closeEvent(event)


class IKToolDialog(QDialog):
    """Convenience dialog that embeds :class:`IKToolWidget`."""

    def __init__(self, config: Dict, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("IK Tools")
        self.resize(560, 720)
        layout = QVBoxLayout(self)
        self.widget = IKToolWidget(config, self)
        layout.addWidget(self.widget)
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)
