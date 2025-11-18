"""Qt dialog for configuring palletization steps."""

from __future__ import annotations

import copy
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from utils.config_compat import format_arm_label, iter_arm_configs
from utils.palletize_runtime import (
    PalletizeRuntime,
    compute_pallet_cells,
    create_default_palletize_config,
)


class CornerEditor(QFrame):
    """Small widget that holds a single corner configuration."""

    changed = Signal()

    def __init__(self, index: int, label: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.index = index
        self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("cornerEditor")
        layout = QVBoxLayout(self)
        title = QLabel(label)
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText("2048, 2048, 2048, 2048, 2048, 2048")
        self.line_edit.textChanged.connect(self.changed)
        layout.addWidget(self.line_edit)

        btn_row = QHBoxLayout()
        self.capture_btn = QPushButton("Capture")
        btn_row.addWidget(self.capture_btn)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear)
        btn_row.addWidget(clear_btn)
        layout.addLayout(btn_row)

    def set_positions(self, positions: List[int]):
        if positions:
            text = ", ".join(str(int(p)) for p in positions[:6])
            self.line_edit.setText(text)
        else:
            self.line_edit.clear()

    def get_positions(self) -> List[int]:
        raw = self.line_edit.text().strip()
        if not raw:
            return []
        cleaned = raw.replace("[", "").replace("]", "")
        parts = [p.strip() for p in cleaned.split(",") if p.strip()]
        values: List[int] = []
        for part in parts[:6]:
            try:
                values.append(int(float(part)))
            except ValueError:
                raise ValueError("Corner values must be numeric")
        if len(values) != 6:
            raise ValueError("Each corner must provide exactly 6 joint values")
        return values

    def clear(self):
        self.line_edit.clear()
        self.changed.emit()


class PalletizeTestWorker(QThread):
    status = Signal(str)
    failed = Signal(str)
    completed = Signal()

    def __init__(self, config: dict, step_data: Dict):
        super().__init__()
        self.config = config
        self.step_data = copy.deepcopy(step_data)
        self._stop_requested = False
        self.runtime = PalletizeRuntime(config)

    def stop(self):
        self._stop_requested = True

    def run(self):
        try:
            cells = self.runtime.compute_cells(self.step_data)
            if not cells:
                raise ValueError("Please set all four corners before testing.")
            total = len(cells)
            for idx in range(total):
                if self._stop_requested:
                    break
                self.status.emit(f"Moving to cell {idx + 1} of {total}")
                self.runtime.execute(
                    self.step_data,
                    cell_index=idx,
                    logger=lambda level, msg: self.status.emit(msg),
                    stop_cb=lambda: self._stop_requested,
                )
            self.completed.emit()
        except Exception as exc:  # pragma: no cover - hardware interaction
            self.failed.emit(str(exc))


class PalletizeConfigWidget(QWidget):
    """Reusable widget that renders the palletization options."""

    def __init__(self, step_data: Dict, config: dict, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = config or {}
        self.step = copy.deepcopy(step_data)
        self._build_ui()
        self.load_from_step(self.step)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        self.summary_label = QLabel("Define four corners to generate the pallet grid.")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        arm_group = QGroupBox("Target Arm")
        arm_layout = QHBoxLayout(arm_group)
        self.arm_combo = QComboBox()
        self._arm_indexes: List[int] = []
        for idx, arm_cfg in iter_arm_configs(self.config, arm_type="robot", enabled_only=True):
            label = format_arm_label(idx, arm_cfg)
            self.arm_combo.addItem(label, idx)
            self._arm_indexes.append(idx)
        if not self._arm_indexes:
            self.arm_combo.addItem("Arm 1", 0)
        arm_layout.addWidget(self.arm_combo)
        layout.addWidget(arm_group)

        corners_group = QGroupBox("Corners")
        corners_layout = QGridLayout(corners_group)
        self.corner_widgets: List[CornerEditor] = []
        for i in range(4):
            editor = CornerEditor(i, f"Corner {i + 1}")
            editor.capture_btn.clicked.connect(lambda checked=False, idx=i: self.capture_corner(idx))
            editor.changed.connect(self._update_summary)
            self.corner_widgets.append(editor)
            corners_layout.addWidget(editor, i // 2, i % 2)
        layout.addWidget(corners_group)

        grid_group = QGroupBox("Grid Divisions")
        grid_layout = QGridLayout(grid_group)
        grid_layout.addWidget(QLabel("Corner 1 → Corner 2"), 0, 0)
        self.div_x_spin = QSpinBox()
        self.div_x_spin.setRange(1, 12)
        self.div_x_spin.valueChanged.connect(self._update_summary)
        grid_layout.addWidget(self.div_x_spin, 0, 1)
        grid_layout.addWidget(QLabel("Corner 2 → Corner 3"), 1, 0)
        self.div_y_spin = QSpinBox()
        self.div_y_spin.setRange(1, 12)
        self.div_y_spin.valueChanged.connect(self._update_summary)
        grid_layout.addWidget(self.div_y_spin, 1, 1)
        layout.addWidget(grid_group)

        down_group = QGroupBox("Down / Release Offsets")
        down_layout = QGridLayout(down_group)
        self.down_spins: Dict[int, QSpinBox] = {}
        for col, motor_id in enumerate((2, 3, 4)):
            label = QLabel(f"Motor {motor_id}")
            spin = QSpinBox()
            spin.setRange(-1000, 1000)
            spin.setSingleStep(10)
            self.down_spins[motor_id] = spin
            down_layout.addWidget(label, 0, col)
            down_layout.addWidget(spin, 1, col)
        down_layout.addWidget(QLabel("Motor 6 release delta"), 1, 0, 1, 2)
        self.release_spin = QSpinBox()
        self.release_spin.setRange(-1000, 1000)
        self.release_spin.setSingleStep(10)
        down_layout.addWidget(self.release_spin, 1, 2, 1, 2)
        layout.addWidget(down_group)

        velocity_group = QGroupBox("Motion Settings")
        velocity_layout = QGridLayout(velocity_group)
        self.approach_spin = self._make_velocity_spin()
        self.down_spin = self._make_velocity_spin()
        self.release_velocity_spin = self._make_velocity_spin()
        self.retract_spin = self._make_velocity_spin()
        velocity_layout.addWidget(QLabel("Approach velocity"), 0, 0)
        velocity_layout.addWidget(self.approach_spin, 0, 1)
        velocity_layout.addWidget(QLabel("Down velocity"), 0, 2)
        velocity_layout.addWidget(self.down_spin, 0, 3)
        velocity_layout.addWidget(QLabel("Release velocity"), 1, 0)
        velocity_layout.addWidget(self.release_velocity_spin, 1, 1)
        velocity_layout.addWidget(QLabel("Retract velocity"), 1, 2)
        velocity_layout.addWidget(self.retract_spin, 1, 3)

        velocity_layout.addWidget(QLabel("Settle time (s)"), 2, 0)
        self.settle_spin = QDoubleSpinBox()
        self.settle_spin.setRange(0.0, 2.0)
        self.settle_spin.setSingleStep(0.05)
        velocity_layout.addWidget(self.settle_spin, 2, 1)
        velocity_layout.addWidget(QLabel("Release hold (s)"), 2, 2)
        self.release_hold_spin = QDoubleSpinBox()
        self.release_hold_spin.setRange(0.0, 2.0)
        self.release_hold_spin.setSingleStep(0.05)
        velocity_layout.addWidget(self.release_hold_spin, 2, 3)
        layout.addWidget(velocity_group)

        layout.addStretch()

    def _make_velocity_spin(self) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(1, 4000)
        spin.setSingleStep(25)
        return spin

    def capture_corner(self, index: int):
        arm_index = int(self.arm_combo.currentData()) if self.arm_combo.count() else 0
        try:
            from utils.motor_controller import MotorController

            controller = MotorController(self.config, arm_index=arm_index)
            positions = controller.read_positions()
            if not positions:
                raise RuntimeError("Unable to read motor positions.")
            self.corner_widgets[index].set_positions(positions)
            self._update_summary()
        except Exception as exc:  # pragma: no cover - hardware interaction
            QMessageBox.warning(self, "Capture Failed", str(exc))

    def load_from_step(self, step: Dict):
        self.arm_combo.setCurrentIndex(max(0, self.arm_combo.findData(step.get("arm_index", 0))))
        corners = step.get("corners", [])
        for idx, editor in enumerate(self.corner_widgets):
            data = corners[idx] if idx < len(corners) else {}
            if isinstance(data, dict):
                editor.set_positions(data.get("positions") or [])
            elif isinstance(data, list):
                editor.set_positions(data)
            else:
                editor.set_positions([])
        div = step.get("divisions", {}) or {}
        self.div_x_spin.setValue(int(div.get("c1_c2", 1)))
        self.div_y_spin.setValue(int(div.get("c2_c3", 1)))
        for motor_id, spin in self.down_spins.items():
            spin.setValue(int(step.get("down_offsets", {}).get(str(motor_id), 0)))
        self.release_spin.setValue(int(step.get("release_offset", 0)))
        self.approach_spin.setValue(int(step.get("approach_velocity", 600)))
        self.down_spin.setValue(int(step.get("down_velocity", 400)))
        self.release_velocity_spin.setValue(int(step.get("release_velocity", 300)))
        self.retract_spin.setValue(int(step.get("retract_velocity", 600)))
        self.settle_spin.setValue(float(step.get("settle_time", 0.1)))
        self.release_hold_spin.setValue(float(step.get("release_hold", 0.2)))
        self._update_summary()

    def build_step_data(self) -> Dict:
        corners: List[Dict[str, List[int]]] = []
        for editor in self.corner_widgets:
            positions = editor.get_positions()
            if len(positions) != 6:
                raise ValueError("Each corner must have 6 joint values")
            corners.append({"label": f"Corner {editor.index + 1}", "positions": positions})
        step = create_default_palletize_config(self.config)
        step.update(
            {
                "arm_index": int(self.arm_combo.currentData()),
                "corners": corners,
                "divisions": {
                    "c1_c2": self.div_x_spin.value(),
                    "c2_c3": self.div_y_spin.value(),
                },
                "down_offsets": {str(mid): spin.value() for mid, spin in self.down_spins.items()},
                "release_offset": self.release_spin.value(),
                "approach_velocity": self.approach_spin.value(),
                "down_velocity": self.down_spin.value(),
                "release_velocity": self.release_velocity_spin.value(),
                "retract_velocity": self.retract_spin.value(),
                "settle_time": self.settle_spin.value(),
                "release_hold": self.release_hold_spin.value(),
            }
        )
        step["name"] = self.step.get("name", "Palletize Grid")
        return step

    def _update_summary(self):
        try:
            step = self.build_step_data()
            cell_count = len(compute_pallet_cells(step))
            self.summary_label.setText(f"Configured {cell_count} pallet cell(s).")
        except Exception:
            self.summary_label.setText("Define all four corners to preview the grid.")


class PalletizeConfigDialog(QDialog):
    """Dialog wrapper that adds buttons/test controls around the widget."""

    def __init__(self, parent: Optional[QWidget], step: Dict, config: dict):
        super().__init__(parent)
        self.setWindowTitle("Palletize Setup")
        # Target 1024x600 screens: keep dialog comfortably within 600px and make content scrollable.
        self.resize(720, 560)
        self._config = config
        self._result: Optional[Dict] = None
        self._test_worker: Optional[PalletizeTestWorker] = None
        self._test_requested_stop = False

        layout = QVBoxLayout(self)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        self.widget = PalletizeConfigWidget(step, config, self)
        scroll.setWidget(self.widget)
        layout.addWidget(scroll)

        test_bar = QHBoxLayout()
        self.test_btn = QPushButton("Test Cells")
        self.test_btn.clicked.connect(self.start_test)
        test_bar.addWidget(self.test_btn)
        self.stop_test_btn = QPushButton("Stop Test")
        self.stop_test_btn.setEnabled(False)
        self.stop_test_btn.clicked.connect(self.stop_test)
        test_bar.addWidget(self.stop_test_btn)
        self.test_status = QLabel("Idle")
        self.test_status.setStyleSheet("color: #bbbbbb;")
        test_bar.addWidget(self.test_status)
        test_bar.addStretch()
        layout.addLayout(test_bar)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def start_test(self):
        if self._test_worker and self._test_worker.isRunning():
            return
        try:
            step = self.widget.build_step_data()
        except Exception as exc:
            QMessageBox.warning(self, "Invalid Configuration", str(exc))
            return
        self._test_requested_stop = False
        self._test_worker = PalletizeTestWorker(self._config, step)
        self._test_worker.status.connect(self.test_status.setText)
        self._test_worker.completed.connect(self._handle_test_complete)
        self._test_worker.failed.connect(self._handle_test_failed)
        self._test_worker.start()
        self.test_btn.setEnabled(False)
        self.stop_test_btn.setEnabled(True)
        self.test_status.setText("Running test…")

    def stop_test(self):
        if self._test_worker and self._test_worker.isRunning():
            self._test_requested_stop = True
            self._test_worker.stop()
            self._test_worker.wait(2000)
            self._test_worker = None
        self.test_btn.setEnabled(True)
        self.stop_test_btn.setEnabled(False)
        self.test_status.setText("Test stopped")

    def _handle_test_complete(self):
        self.test_btn.setEnabled(True)
        self.stop_test_btn.setEnabled(False)
        if self._test_requested_stop:
            self.test_status.setText("Test stopped")
        else:
            self.test_status.setText("Test finished")
        self._test_worker = None
        self._test_requested_stop = False

    def _handle_test_failed(self, message: str):
        self.test_btn.setEnabled(True)
        self.stop_test_btn.setEnabled(False)
        self.test_status.setText("Test failed")
        QMessageBox.warning(self, "Test Failed", message)
        self._test_worker = None
        self._test_requested_stop = False

    def accept(self):
        try:
            self._result = self.widget.build_step_data()
        except Exception as exc:
            QMessageBox.warning(self, "Invalid Configuration", str(exc))
            return
        super().accept()

    def reject(self):
        self.stop_test()
        super().reject()

    def closeEvent(self, event):  # pragma: no cover - UI hook
        self.stop_test()
        super().closeEvent(event)

    def get_step_data(self) -> Optional[Dict]:
        return self._result
