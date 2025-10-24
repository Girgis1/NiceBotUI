"""
Self-contained IK configuration dialog for SO-series arms.

The goal is to keep inverse-kinematics tuning separate from the main
Settings tab so the UI can evolve without breaking core configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


try:  # Optional dependency
    from phosphobot.ik.so_series import build_solver  # type: ignore

    IK_AVAILABLE = True
except Exception:  # pragma: no cover - phosphobot is optional
    build_solver = None
    IK_AVAILABLE = False


@dataclass
class IKPreset:
    name: str
    base_height_mm: float
    shoulder_offset_mm: float
    upper_arm_length_mm: float
    forearm_length_mm: float
    wrist_offset_mm: float
    tool_length_mm: float
    elbow_offset_mm: float = 0.0

    def as_dict(self) -> Dict[str, float]:
        return {
            "base_height_mm": self.base_height_mm,
            "shoulder_offset_mm": self.shoulder_offset_mm,
            "upper_arm_length_mm": self.upper_arm_length_mm,
            "forearm_length_mm": self.forearm_length_mm,
            "wrist_offset_mm": self.wrist_offset_mm,
            "tool_length_mm": self.tool_length_mm,
            "elbow_offset_mm": self.elbow_offset_mm,
        }


class IKToolDialog(QDialog):
    """Standalone dialog for configuring IK parameters."""

    def __init__(self, config: Dict, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("SO-Series IK Tools")
        self.resize(520, 640)
        self.setModal(True)

        self.config = config
        self.applied_settings: Optional[Dict[str, float]] = None
        self._loading = False

        self.ik_presets: Dict[str, IKPreset] = {
            "SO-100": IKPreset(
                name="SO-100",
                base_height_mm=105.0,
                shoulder_offset_mm=32.0,
                upper_arm_length_mm=185.0,
                forearm_length_mm=210.0,
                wrist_offset_mm=95.0,
                tool_length_mm=60.0,
            ),
            "SO-101": IKPreset(
                name="SO-101",
                base_height_mm=110.0,
                shoulder_offset_mm=28.0,
                upper_arm_length_mm=200.0,
                forearm_length_mm=230.0,
                wrist_offset_mm=105.0,
                tool_length_mm=70.0,
                elbow_offset_mm=5.0,
            ),
        }

        self._build_ui()
        self._load_initial_values()

    # ------------------------------------------------------------------ UI creation
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("SO-Series IK Configuration")
        title.setStyleSheet("QLabel { color: #4CAF50; font-size: 18px; font-weight: bold; }")
        layout.addWidget(title)

        instructions = QLabel(
            "Adjust the geometric parameters used by the IK solver. "
            "Load a preset, tweak the dimensions, then run the debug check "
            "to verify the solver response. When you are happy, apply the "
            "values back to your session configuration."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("QLabel { color: #e0e0e0; font-size: 13px; }")
        layout.addWidget(instructions)

        model_row = QHBoxLayout()
        model_row.setSpacing(8)

        model_label = QLabel("Arm Model:")
        model_label.setStyleSheet("QLabel { color: #e0e0e0; font-size: 14px; min-width: 110px; }")
        model_row.addWidget(model_label)

        self.arm_combo = QComboBox()
        for preset in self.ik_presets.values():
            self.arm_combo.addItem(preset.name, preset.name)
        self.arm_combo.currentIndexChanged.connect(self._on_model_changed)
        model_row.addWidget(self.arm_combo, stretch=1)

        self.load_btn = QPushButton("Load Preset")
        self.load_btn.setMinimumWidth(120)
        self.load_btn.clicked.connect(self._on_load_pressed)
        model_row.addWidget(self.load_btn)

        layout.addLayout(model_row)

        self.parameter_spins: Dict[str, QDoubleSpinBox] = {}

        def add_param_row(label: str, key: str, minimum: float, maximum: float, step: float = 1.0):
            row = QHBoxLayout()
            row.setSpacing(6)
            lbl = QLabel(label)
            lbl.setStyleSheet("QLabel { color: #e0e0e0; font-size: 13px; min-width: 150px; }")
            row.addWidget(lbl)

            spin = QDoubleSpinBox()
            spin.setRange(minimum, maximum)
            spin.setSingleStep(step)
            spin.setDecimals(2)
            spin.setMinimumHeight(40)
            spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
            spin.setStyleSheet(
                "QDoubleSpinBox { background-color: #505050; color: #ffffff; "
                "border: 2px solid #707070; border-radius: 6px; padding: 6px; font-size: 13px; }"
                "QDoubleSpinBox:focus { border-color: #4CAF50; background-color: #555555; }"
            )
            spin.valueChanged.connect(self._update_summary)
            row.addWidget(spin)
            row.addStretch()
            layout.addLayout(row)
            self.parameter_spins[key] = spin

        add_param_row("Base Height (mm):", "base_height_mm", 0.0, 400.0)
        add_param_row("Shoulder Offset (mm):", "shoulder_offset_mm", 0.0, 200.0)
        add_param_row("Upper Arm Length (mm):", "upper_arm_length_mm", 50.0, 400.0)
        add_param_row("Forearm Length (mm):", "forearm_length_mm", 50.0, 400.0)
        add_param_row("Wrist Offset (mm):", "wrist_offset_mm", 0.0, 200.0)
        add_param_row("Tool Length (mm):", "tool_length_mm", 0.0, 200.0)
        add_param_row("Elbow Offset (mm):", "elbow_offset_mm", -50.0, 50.0, step=0.5)

        self.flip_elbow_check = QCheckBox("Prefer elbow-up solutions when reachability allows")
        self.flip_elbow_check.setStyleSheet("QCheckBox { color: #e0e0e0; font-size: 13px; padding: 4px; }")
        layout.addWidget(self.flip_elbow_check)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            "QLabel { color: #d0d0d0; font-size: 13px; padding: 8px; border: 1px solid #555; border-radius: 6px; }"
        )
        layout.addWidget(self.summary_label)

        debug_row = QHBoxLayout()
        debug_row.addStretch()

        self.debug_btn = QPushButton("Run IK Debug")
        self.debug_btn.setMinimumHeight(42)
        self.debug_btn.clicked.connect(self._run_debug)
        self.debug_btn.setEnabled(IK_AVAILABLE)
        debug_row.addWidget(self.debug_btn)

        self.apply_btn = QPushButton("Apply to Config")
        self.apply_btn.setMinimumHeight(42)
        self.apply_btn.clicked.connect(self._apply_to_config)
        debug_row.addWidget(self.apply_btn)

        layout.addLayout(debug_row)

        self.output_box = QTextEdit()
        self.output_box.setReadOnly(True)
        self.output_box.setMinimumHeight(160)
        self.output_box.setStyleSheet(
            "QTextEdit { background-color: #2f2f2f; color: #f0f0f0; border: 1px solid #555; border-radius: 6px; }"
        )
        layout.addWidget(self.output_box)

        footer = QHBoxLayout()
        footer.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        layout.addLayout(footer)

        if not IK_AVAILABLE:
            self._append_output(
                "IK debug functionality requires the phosphobot package. "
                "Install it from https://github.com/phospho-app/phosphobot."
            )

    # ------------------------------------------------------------------ Helpers
    def _load_initial_values(self) -> None:
        """Load initial values from configuration or presets."""
        active = self.config.get("ik", {}).get("active_preset", "SO-100")
        if active not in self.ik_presets:
            active = "SO-100"
        index = self.arm_combo.findData(active)
        if index >= 0:
            self.arm_combo.setCurrentIndex(index)
        self._apply_preset(active)

        stored = self.config.get("ik", {}).get("parameters")
        if isinstance(stored, dict):
            for key, spin in self.parameter_spins.items():
                if key in stored:
                    spin.blockSignals(True)
                    spin.setValue(float(stored[key]))
                    spin.blockSignals(False)
        self.flip_elbow_check.setChecked(bool(self.config.get("ik", {}).get("prefer_elbow_up", False)))
        self._update_summary()

    def _apply_preset(self, name: str) -> None:
        preset = self.ik_presets.get(name)
        if not preset:
            return
        self._loading = True
        for key, value in preset.as_dict().items():
            spin = self.parameter_spins.get(key)
            if spin:
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
        self._loading = False
        self._update_summary()
        self._append_output(f"Loaded preset '{name}'. Adjust parameters as needed.")

    def _on_model_changed(self) -> None:
        if self._loading:
            return
        data = self.arm_combo.currentData()
        if data:
            self._apply_preset(str(data))

    def _on_load_pressed(self) -> None:
        data = self.arm_combo.currentData()
        if data:
            self._apply_preset(str(data))

    def _update_summary(self) -> None:
        if self._loading:
            return
        up = self.parameter_spins["upper_arm_length_mm"].value()
        forearm = self.parameter_spins["forearm_length_mm"].value()
        wrist = self.parameter_spins["wrist_offset_mm"].value()
        reach = up + forearm + wrist
        summary = (
            f"Approximate straight-line reach: {reach:.1f} mm\n"
            f"Tool length: {self.parameter_spins['tool_length_mm'].value():.1f} mm\n"
            f"Prefer elbow-up: {'Yes' if self.flip_elbow_check.isChecked() else 'No'}"
        )
        self.summary_label.setText(summary)

    def _collect_parameters(self) -> Dict[str, float]:
        params = {key: spin.value() for key, spin in self.parameter_spins.items()}
        params["prefer_elbow_up"] = float(self.flip_elbow_check.isChecked())
        return params

    def _run_debug(self) -> None:
        if not IK_AVAILABLE or build_solver is None:
            QMessageBox.information(
                self,
                "IK Debug Unavailable",
                "Install the phosphobot package to enable IK debugging.",
            )
            return

        params = self._collect_parameters()
        try:
            solver = build_solver(
                upper_arm=params["upper_arm_length_mm"] / 1000.0,
                forearm=params["forearm_length_mm"] / 1000.0,
                tool=params["tool_length_mm"] / 1000.0,
                shoulder_offset=params["shoulder_offset_mm"] / 1000.0,
                wrist_offset=params["wrist_offset_mm"] / 1000.0,
                elbow_offset=params["elbow_offset_mm"] / 1000.0,
                base_height=params["base_height_mm"] / 1000.0,
            )
            reach = solver.max_reach_m * 1000.0
            self._append_output(
                f"Solver initialized successfully.\nEstimated reach (from solver): {reach:.1f} mm"
            )
        except Exception as exc:  # pragma: no cover - depends on external pkg
            self._append_output(f"Failed to build solver: {exc}")

    def _apply_to_config(self) -> None:
        params = self._collect_parameters()
        arm_name = self.arm_combo.currentData() or "SO-100"
        config_section = self.config.setdefault("ik", {})
        config_section["active_preset"] = arm_name
        config_section["parameters"] = params
        config_section["prefer_elbow_up"] = bool(self.flip_elbow_check.isChecked())
        self.applied_settings = params
        self._append_output(f"Applied parameters to config under 'ik' → active preset '{arm_name}'.")
        QMessageBox.information(self, "IK Settings Applied", "IK parameters stored in memory for this session.")

    def _append_output(self, text: str) -> None:
        self.output_box.append(text)
