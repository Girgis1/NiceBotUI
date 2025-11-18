"""Palletize configuration dialog."""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from utils.config_compat import format_arm_label, get_active_arm_index, iter_arm_configs
from utils.logging_utils import log_exception
from utils.motor_controller import MOTOR_CONTROL_AVAILABLE, MotorController
from utils.palletize_planner import PalletizePlanner

try:  # Lazy import to avoid circular dependency at import time
    from HomePos import read_config as _read_hw_config
except Exception:  # pragma: no cover - fallback for tests
    def _read_hw_config() -> Dict:
        return {}


def _default_corners() -> List[Dict[str, Optional[List[int]]]]:
    return [
        {"name": f"Corner {idx}", "positions": None}
        for idx in range(1, 5)
    ]


def create_default_palletize_config(config: Optional[Dict] = None) -> Dict:
    cfg = config or _read_hw_config() or {}
    arm_index = get_active_arm_index(cfg, arm_type="robot")
    return {
        "type": "palletize",
        "name": "Palletize Items",
        "palletize_id": str(uuid.uuid4()),
        "arm_index": arm_index,
        "corners": _default_corners(),
        "grid": {
            "corner12_divisions": 3,
            "corner23_divisions": 3,
        },
        "velocities": {
            "travel": 900,
            "down": 400,
            "release": 300,
            "retreat": 900,
        },
        "down_adjustments": {str(motor): 0 for motor in range(2, 6)},
        "release_adjustment": 0,
    }


class PalletizeConfigDialog(QDialog):
    """Dialog that captures pallet corners, grid density, and motion offsets."""

    def __init__(self, parent=None, step_data: Optional[Dict] = None, config: Optional[Dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Configure Palletize Step")
        self.setModal(True)
        self.config = config or {}
        base = create_default_palletize_config(self.config)
        if step_data:
            merged = base
            merged.update({k: v for k, v in step_data.items() if v is not None})
            base = merged
        if not base.get("palletize_id"):
            base["palletize_id"] = str(uuid.uuid4())
        base.setdefault("corners", _default_corners())
        base.setdefault("grid", {})
        base.setdefault("velocities", {})
        base.setdefault("down_adjustments", {str(motor): 0 for motor in range(2, 6)})
        base.setdefault("release_adjustment", 0)
        base["type"] = "palletize"
        self.step = base
        self._test_cell_index = 0
        self._controller: Optional[MotorController] = None
        self._last_arm_index = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("Configure pallet grid and release behaviour")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        self.name_edit = QLineEdit(self.step.get("name", "Palletize Items"))
        self.name_edit.setPlaceholderText("Step name")
        layout.addWidget(self._wrap_with_label("Step Name", self.name_edit))

        self.arm_combo = QComboBox()
        self._populate_arm_combo()
        layout.addWidget(self._wrap_with_label("Robot Arm", self.arm_combo))

        grid_box = QGroupBox("Grid Setup")
        grid_layout = QGridLayout(grid_box)
        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(1, 20)
        self.cols_spin.setValue(int(self.step.get("grid", {}).get("corner12_divisions", 3)))
        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(1, 20)
        self.rows_spin.setValue(int(self.step.get("grid", {}).get("corner23_divisions", 3)))
        grid_layout.addWidget(QLabel("Corner 1→2 divisions"), 0, 0)
        grid_layout.addWidget(self.cols_spin, 0, 1)
        grid_layout.addWidget(QLabel("Corner 2→3 divisions"), 1, 0)
        grid_layout.addWidget(self.rows_spin, 1, 1)
        layout.addWidget(grid_box)

        corners_box = QGroupBox("Corner Poses")
        corners_layout = QGridLayout(corners_box)
        self.corner_labels: List[QLabel] = []
        for idx in range(4):
            name = QLabel(f"Corner {idx + 1}")
            summary = QLabel("Not set")
            summary.setStyleSheet("color: #cccccc")
            capture = QPushButton("Capture")
            capture.setEnabled(MOTOR_CONTROL_AVAILABLE)
            capture.clicked.connect(lambda _=False, i=idx: self.capture_corner(i))
            clear = QPushButton("Clear")
            clear.clicked.connect(lambda _=False, i=idx: self.clear_corner(i))
            row = idx
            corners_layout.addWidget(name, row, 0)
            corners_layout.addWidget(summary, row, 1)
            corners_layout.addWidget(capture, row, 2)
            corners_layout.addWidget(clear, row, 3)
            self.corner_labels.append(summary)
        layout.addWidget(corners_box)

        offsets_box = QGroupBox("Down & Release")
        offsets_layout = QGridLayout(offsets_box)
        self.down_spins: Dict[str, QSpinBox] = {}
        for offset_idx, motor in enumerate(range(2, 6)):
            spin = QSpinBox()
            spin.setRange(-2000, 2000)
            spin.setValue(int(self.step.get("down_adjustments", {}).get(str(motor), 0)))
            offsets_layout.addWidget(QLabel(f"Motor {motor} Δ"), offset_idx, 0)
            offsets_layout.addWidget(spin, offset_idx, 1)
            self.down_spins[str(motor)] = spin
        self.release_spin = QSpinBox()
        self.release_spin.setRange(-2000, 2000)
        self.release_spin.setValue(int(self.step.get("release_adjustment", 0)))
        offsets_layout.addWidget(QLabel("Motor 6 (release) Δ"), 4, 0)
        offsets_layout.addWidget(self.release_spin, 4, 1)
        layout.addWidget(offsets_box)

        velocity_box = QGroupBox("Velocities")
        velocity_layout = QGridLayout(velocity_box)
        self.velocity_spins: Dict[str, QSpinBox] = {}
        labels = [
            ("travel", "Approach"),
            ("down", "Down"),
            ("release", "Release"),
            ("retreat", "Retreat"),
        ]
        for row, (key, label_text) in enumerate(labels):
            spin = QSpinBox()
            spin.setRange(50, 4000)
            spin.setSingleStep(50)
            spin.setValue(int(self.step.get("velocities", {}).get(key, 800 if key != "down" else 400)))
            velocity_layout.addWidget(QLabel(f"{label_text} velocity"), row, 0)
            velocity_layout.addWidget(spin, row, 1)
            self.velocity_spins[key] = spin
        layout.addWidget(velocity_box)

        self.status_label = QLabel("Capture corners to enable testing.")
        self.status_label.setStyleSheet("color: #cccccc")
        layout.addWidget(self.status_label)

        button_bar = QHBoxLayout()
        self.test_btn = QPushButton("Test next cell")
        self.test_btn.setEnabled(MOTOR_CONTROL_AVAILABLE)
        self.test_btn.clicked.connect(self.run_test_cycle)
        button_bar.addWidget(self.test_btn)

        button_box = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save)
        button_box.rejected.connect(self.reject)
        button_box.accepted.connect(self.accept)
        button_bar.addWidget(button_box)

        layout.addLayout(button_bar)
        self.resize(520, 640)

        self._refresh_corner_labels()

    # ------------------------------------------------------------------
    # UI helpers

    def _wrap_with_label(self, label: str, widget) -> QGroupBox:
        box = QGroupBox(label)
        lay = QVBoxLayout(box)
        lay.addWidget(widget)
        return box

    def _populate_arm_combo(self):
        self.arm_combo.clear()
        arms = list(iter_arm_configs(self.config, arm_type="robot", enabled_only=True))
        if not arms:
            arms = [(0, {})]
        selected = self.step.get("arm_index", get_active_arm_index(self.config, arm_type="robot"))
        for idx, arm_cfg in arms:
            label = format_arm_label(idx + 1, arm_cfg or {"name": f"Arm {idx + 1}"})
            self.arm_combo.addItem(label, idx)
            if idx == selected:
                self.arm_combo.setCurrentIndex(self.arm_combo.count() - 1)
        if selected >= len(arms):
            self.arm_combo.setCurrentIndex(0)

    def _refresh_corner_labels(self):
        corners = self.step.get("corners", [])
        for idx, label in enumerate(self.corner_labels):
            if idx < len(corners) and corners[idx].get("positions"):
                pose = corners[idx]["positions"]
                label.setText(
                    f"Set • [{pose[0]}, {pose[1]}, {pose[2]}, {pose[3]}, {pose[4]}, {pose[5]}]"
                )
                label.setStyleSheet("color: #00e676")
            else:
                label.setText("Not set")
                label.setStyleSheet("color: #cccccc")

    def _set_status(self, message: str, *, error: bool = False):
        color = "#ff6e40" if error else "#cccccc"
        self.status_label.setStyleSheet(f"color: {color}")
        self.status_label.setText(message)

    # ------------------------------------------------------------------
    # Corner capture

    def capture_corner(self, index: int):
        if not MOTOR_CONTROL_AVAILABLE:
            self._set_status("Motor control not available on this system.", error=True)
            return
        controller = self._ensure_controller()
        if not controller:
            return
        try:
            positions = controller.read_positions_from_bus()
            if not positions:
                positions = controller.read_positions()
            if not positions:
                self._set_status("Failed to read motor positions.", error=True)
                return
            corners = self.step.setdefault("corners", _default_corners())
            corners[index]["positions"] = positions[:6]
            self._refresh_corner_labels()
            self._set_status(f"Corner {index + 1} captured.")
        except Exception as exc:  # pragma: no cover - hardware interaction
            log_exception("PalletizeConfigDialog: capture failed", exc, level="warning")
            self._set_status(f"Capture failed: {exc}", error=True)

    def clear_corner(self, index: int):
        corners = self.step.setdefault("corners", _default_corners())
        corners[index]["positions"] = None
        self._refresh_corner_labels()
        self._set_status(f"Corner {index + 1} cleared.")

    def _ensure_controller(self) -> Optional[MotorController]:
        target_arm = int(self.arm_combo.currentData()) if self.arm_combo.count() else 0
        if self._controller and self._last_arm_index != target_arm:
            self._controller.disconnect()
            self._controller = None
        if not self._controller:
            try:
                controller = MotorController(self.config, arm_index=target_arm)
            except Exception as exc:  # pragma: no cover - config error
                log_exception("PalletizeConfigDialog: failed to build motor controller", exc, level="warning")
                self._set_status("Could not build motor controller.", error=True)
                return None
            controller.speed_multiplier = self.config.get("control", {}).get("speed_multiplier", 1.0)
            self._controller = controller
            self._last_arm_index = target_arm
        if not self._controller.bus:
            if not self._controller.connect():
                self._set_status("Failed to connect to motors.", error=True)
                return None
        return self._controller

    # ------------------------------------------------------------------
    # Testing

    def run_test_cycle(self):
        data = self.get_step_data()
        planner = PalletizePlanner(data)
        validation = planner.validate()
        if not validation.valid:
            self._set_status(validation.message, error=True)
            return
        controller = self._ensure_controller()
        if not controller:
            return
        try:
            motion_plan = planner.build_motion_plan(self._test_cell_index)
            description = planner.describe_cell(self._test_cell_index)
            for stage_name, target, velocity in motion_plan:
                controller.set_positions(target, velocity=velocity, wait=True, keep_connection=True)
            self._set_status(f"Tested {description}.")
            self._test_cell_index = (self._test_cell_index + 1) % planner.total_cells()
        except Exception as exc:  # pragma: no cover - hardware interaction
            log_exception("PalletizeConfigDialog: test failed", exc, level="warning")
            self._set_status(f"Test failed: {exc}", error=True)

    # ------------------------------------------------------------------
    # Dialog plumbing

    def get_step_data(self) -> Dict:
        data = dict(self.step)
        data["name"] = self.name_edit.text().strip() or "Palletize Items"
        data["arm_index"] = int(self.arm_combo.currentData()) if self.arm_combo.count() else 0
        data.setdefault("corners", _default_corners())
        data.setdefault("grid", {})
        data["grid"]["corner12_divisions"] = int(self.cols_spin.value())
        data["grid"]["corner23_divisions"] = int(self.rows_spin.value())
        data.setdefault("down_adjustments", {})
        for key, spin in self.down_spins.items():
            data["down_adjustments"][key] = int(spin.value())
        data["release_adjustment"] = int(self.release_spin.value())
        data.setdefault("velocities", {})
        for key, spin in self.velocity_spins.items():
            data["velocities"][key] = int(spin.value())
        data["type"] = "palletize"
        return data

    def accept(self):
        data = self.get_step_data()
        planner = PalletizePlanner(data)
        validation = planner.validate()
        if not validation.valid:
            QMessageBox.warning(self, "Invalid palletize setup", validation.message)
            return
        self.step = data
        super().accept()

    def closeEvent(self, event):  # pragma: no cover - Qt hook
        if self._controller:
            try:
                self._controller.disconnect()
            except Exception:
                pass
        super().closeEvent(event)
