"""UI widgets for configuring and previewing IK behaviour."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional

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


@dataclass
class IKPreset:
    name: str
    parameters: Dict[str, float]


class IKToolWidget(QWidget):
    """Embeddable widget exposing IK presets, tuning and a simple teleop keypad."""

    def __init__(self, config: Dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.config = config
        self.solver = IKSolver()

        self._loading = False
        self.parameter_spins: Dict[str, QDoubleSpinBox] = {}
        self.target_position = np.array([0.20, 0.0, 0.18])  # metres
        self.current_solution: Optional[np.ndarray] = None

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
            "Adjust geometric parameters, compute inverse kinematics using the phosphobot URDF, "
            "and experiment with incremental Cartesian moves before wiring this into other systems."
        )
        description.setWordWrap(True)
        description.setStyleSheet("QLabel { color: #d0d0d0; font-size: 13px; }")
        layout.addWidget(description)

        # Preset selection
        preset_row = QHBoxLayout()
        preset_row.setSpacing(8)

        preset_label = QLabel("Arm preset:")
        preset_label.setStyleSheet("QLabel { color: #e0e0e0; font-size: 14px; min-width: 120px; }")
        preset_row.addWidget(preset_label)

        self.arm_combo = QComboBox()
        for key, preset in self.presets.items():
            self.arm_combo.addItem(preset.name, key)
        self.arm_combo.currentIndexChanged.connect(self._on_preset_changed)
        preset_row.addWidget(self.arm_combo, stretch=1)

        self.load_preset_btn = QPushButton("Load Preset")
        self.load_preset_btn.clicked.connect(self._load_selected_preset)
        preset_row.addWidget(self.load_preset_btn)

        preset_row.addStretch()
        layout.addLayout(preset_row)

        # Parameter grid
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

        layout.addLayout(grid)

        self.prefer_elbow_up_check = QCheckBox("Prefer elbow-up posture when feasible")
        self.prefer_elbow_up_check.setStyleSheet("QCheckBox { color: #e0e0e0; font-size: 13px; padding: 4px; }")
        layout.addWidget(self.prefer_elbow_up_check)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            "QLabel { color: #d0d0d0; font-size: 13px; padding: 8px; border-radius: 6px; border: 1px solid #555555; }"
        )
        layout.addWidget(self.summary_label)

        # Teleop keypad
        layout.addWidget(self._build_keypad())

        # Output console
        self.output_box = QTextEdit()
        self.output_box.setReadOnly(True)
        self.output_box.setMinimumHeight(140)
        self.output_box.setStyleSheet(
            "QTextEdit { background-color: #2f2f2f; color: #f0f0f0; border: 1px solid #555555; border-radius: 6px; }"
        )
        layout.addWidget(self.output_box)

        # Footer buttons
        footer = QHBoxLayout()
        footer.addStretch()

        self.apply_btn = QPushButton("Save Parameters")
        self.apply_btn.clicked.connect(self._apply_to_config)
        footer.addWidget(self.apply_btn)

        close_btn = QPushButton("Recompute IK")
        close_btn.clicked.connect(self._recompute_solution)
        footer.addWidget(close_btn)

        layout.addLayout(footer)

    def _build_keypad(self) -> QWidget:
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setSpacing(8)
        vbox.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Cartesian Test Controls")
        title.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; font-weight: bold; }")
        vbox.addWidget(title)

        info = QLabel(
            "Adjust target position in 10mm steps (configurable) and compute IK. "
            "Values are relative to the robot base in metres."
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

        grid.addWidget(add_button("↑", lambda: self._nudge(dx=0.0, dy=self._step_m())), 0, 1)
        grid.addWidget(add_button("↓", lambda: self._nudge(dx=0.0, dy=-self._step_m())), 2, 1)
        grid.addWidget(add_button("←", lambda: self._nudge(dx=-self._step_m(), dy=0.0)), 1, 0)
        grid.addWidget(add_button("→", lambda: self._nudge(dx=self._step_m(), dy=0.0)), 1, 2)
        grid.addWidget(add_button("⬆ Z", lambda: self._nudge(dz=self._step_m())), 0, 2)
        grid.addWidget(add_button("⬇ Z", lambda: self._nudge(dz=-self._step_m())), 2, 2)

        vbox.addLayout(grid)

        home_row = QHBoxLayout()
        self.reset_btn = QPushButton("🏠 To (0,0,0)")
        self.reset_btn.setMinimumHeight(32)
        self.reset_btn.clicked.connect(self._reset_position)
        home_row.addWidget(self.reset_btn)
        home_row.addStretch()
        vbox.addLayout(home_row)

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

    # ------------------------------------------------------------------ calculations
    def _step_m(self) -> float:
        return self.step_spin.value() / 1000.0

    def _nudge(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> None:
        self.target_position = self.target_position + np.array([dx, dy, dz])
        self._recompute_solution()

    def _reset_position(self) -> None:
        self.target_position = np.zeros(3)
        self._recompute_solution()

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
        self.summary_label.setText(summary)

    def _recompute_solution(self) -> None:
        self.position_label.setText(
            f"Target position: x={self.target_position[0]:.3f} m, y={self.target_position[1]:.3f} m, z={self.target_position[2]:.3f} m"
        )
        try:
            joints = self.solver.solve(self.target_position)
            self.current_solution = joints
            degrees = np.degrees(joints)
            text = ", ".join(f"J{i+1}:{deg:.1f}°" for i, deg in enumerate(degrees))
            self.solution_label.setText(f"Solution (rad): {joints.round(4)}\nAngles: {text}")
            self._append_output(
                "Computed IK solution successfully. Adjust offsets before applying to real hardware."
            )
        except Exception as exc:  # pragma: no cover - pybullet exceptions
            self.current_solution = None
            self.solution_label.setText(f"IK failed: {exc}")
            self._append_output(f"IK failure: {exc}")

    def _apply_to_config(self) -> None:
        section = self.config.setdefault("ik", {})
        section["active_preset"] = self.arm_combo.currentData()
        section["parameters"] = {k: spin.value() for k, spin in self.parameter_spins.items()}
        section["prefer_elbow_up"] = self.prefer_elbow_up_check.isChecked()
        section["last_target"] = self.target_position.tolist()
        if self.current_solution is not None:
            section["last_solution_rad"] = self.current_solution.tolist()
        self._append_output("Stored IK parameters in session config (remember to Save).")

    def _append_output(self, text: str) -> None:
        self.output_box.append(text)

    def closeEvent(self, event) -> None:  # pragma: no cover - Qt hook
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
