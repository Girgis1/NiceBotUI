"""Qt dialog for configuring palletization steps."""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from utils.config_compat import format_arm_label, iter_arm_configs
from utils.logging_utils import log_exception
from utils.motor_controller import MotorController
from utils.palletizer import (
    PalletizerStateStore,
    apply_down_offsets,
    apply_release_offset,
    build_cell_positions,
    create_default_palletizer_config,
    describe_cell,
    normalize_corner_positions,
    reorder_cells_for_snake,
)


class PalletizerConfigDialog(QDialog):
    """Guided setup dialog for palletize steps."""

    def __init__(self, parent: Optional[QWidget] = None, step_data: Optional[Dict] = None, config: Optional[Dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Palletize Setup")
        self.setModal(True)
        self.resize(720, 640)
        self.config = config or {}
        self.state_store = PalletizerStateStore()
        self.step_data = step_data or create_default_palletizer_config(config)
        self.corner_entries: List[Dict] = []
        self._test_index = 0

        grid_cfg = self.step_data.get("grid", {})
        existing_corners = grid_cfg.get("corners", [])
        for idx, normalized in enumerate(normalize_corner_positions(existing_corners)):
            captured = False
            if idx < len(existing_corners):
                captured = bool(existing_corners[idx].get("captured"))
            if not captured:
                captured = any(value != 0 for value in normalized)
            self.corner_entries.append({
                "label": f"Corner {idx + 1}",
                "positions": normalized,
                "captured": captured,
            })

        self._build_ui()
        self._apply_initial_values()

    # ------------------------------------------------------------------
    # UI construction

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        layout.addWidget(self._build_header_box())
        layout.addWidget(self._build_corner_box())
        layout.addWidget(self._build_division_box())
        layout.addWidget(self._build_motion_box())
        layout.addWidget(self._build_progress_box())
        layout.addLayout(self._build_buttons())

    def _build_header_box(self) -> QWidget:
        group = QGroupBox("General")
        form = QGridLayout(group)
        form.setSpacing(8)

        name_label = QLabel("Step Name:")
        name_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.name_edit = QLineEdit(self.step_data.get("name", "Palletize Grid"))
        self.name_edit.setPlaceholderText("Palletize Grid")
        form.addWidget(name_label, 0, 0)
        form.addWidget(self.name_edit, 0, 1)

        arm_label = QLabel("Arm:")
        arm_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.arm_combo = QComboBox()
        self.arm_combo.setMinimumHeight(36)
        self._populate_arm_combo()
        form.addWidget(arm_label, 1, 0)
        form.addWidget(self.arm_combo, 1, 1)

        return group

    def _populate_arm_combo(self):
        current = int(self.step_data.get("arm_index", 0))
        added = False
        for idx, arm_cfg in iter_arm_configs(self.config, arm_type="robot"):
            label = format_arm_label(idx, arm_cfg)
            self.arm_combo.addItem(label, idx)
            if idx == current:
                self.arm_combo.setCurrentIndex(self.arm_combo.count() - 1)
            added = True

        if not added:
            # Fallback if config missing
            self.arm_combo.addItem("Arm 1", 0)
            self.arm_combo.addItem("Arm 2", 1)
            self.arm_combo.setCurrentIndex(min(current, self.arm_combo.count() - 1))

    def _build_corner_box(self) -> QWidget:
        group = QGroupBox("Corners (record current joint positions)")
        layout = QGridLayout(group)
        layout.setSpacing(6)

        self.corner_labels: List[QLabel] = []
        for idx in range(4):
            label = QLabel(f"Corner {idx + 1}")
            label.setStyleSheet("font-weight: bold; color: #e0e0e0;")
            layout.addWidget(label, idx, 0)

            value_label = QLabel(self._format_corner_text(idx))
            value_label.setWordWrap(True)
            value_label.setStyleSheet("color: #bdbdbd;")
            layout.addWidget(value_label, idx, 1)
            self.corner_labels.append(value_label)

            capture_btn = QPushButton("Capture")
            capture_btn.setProperty("corner_index", idx)
            capture_btn.clicked.connect(lambda _, i=idx: self._capture_corner(i))
            layout.addWidget(capture_btn, idx, 2)

        return group

    def _build_division_box(self) -> QWidget:
        group = QGroupBox("Grid divisions")
        layout = QGridLayout(group)
        layout.setSpacing(6)

        self.columns_spin = QSpinBox()
        self.columns_spin.setRange(1, 12)
        self.columns_spin.setValue(self.step_data.get("grid", {}).get("columns", 2))
        self.columns_spin.valueChanged.connect(self._update_next_cell_label)

        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(1, 12)
        self.rows_spin.setValue(self.step_data.get("grid", {}).get("rows", 2))
        self.rows_spin.valueChanged.connect(self._update_next_cell_label)

        layout.addWidget(QLabel("Corner 1 → Corner 2 (columns):"), 0, 0)
        layout.addWidget(self.columns_spin, 0, 1)
        layout.addWidget(QLabel("Corner 2 → Corner 3 (rows):"), 1, 0)
        layout.addWidget(self.rows_spin, 1, 1)

        self.snake_check = QCheckBox("Snake fill rows")
        self.snake_check.setChecked(bool(self.step_data.get("grid", {}).get("snake", False)))
        layout.addWidget(self.snake_check, 2, 0, 1, 2)

        return group

    def _build_motion_box(self) -> QWidget:
        group = QGroupBox("Motion offsets and velocities")
        layout = QGridLayout(group)
        layout.setSpacing(6)

        motion = self.step_data.get("motion", {})

        self.travel_spin = self._build_velocity_spin(motion.get("travel_velocity", 650))
        self.down_spin = self._build_velocity_spin(motion.get("down_velocity", 450))
        self.release_spin = self._build_velocity_spin(motion.get("release_velocity", 250))
        self.retreat_spin = self._build_velocity_spin(motion.get("retreat_velocity", 650))

        layout.addWidget(QLabel("Travel velocity:"), 0, 0)
        layout.addWidget(self.travel_spin, 0, 1)
        layout.addWidget(QLabel("Down velocity:"), 1, 0)
        layout.addWidget(self.down_spin, 1, 1)
        layout.addWidget(QLabel("Release velocity:"), 2, 0)
        layout.addWidget(self.release_spin, 2, 1)
        layout.addWidget(QLabel("Retreat velocity:"), 3, 0)
        layout.addWidget(self.retreat_spin, 3, 1)

        offsets_frame = QFrame()
        offsets_layout = QGridLayout(offsets_frame)
        offsets_layout.setSpacing(4)

        labels = ["Motor 2", "Motor 3", "Motor 4", "Motor 5"]
        self.offset_spins: List[QSpinBox] = []
        down_offsets = motion.get("down_offsets", [0, 0, 0, 0, 0, 0])
        for idx, text in enumerate(labels, start=1):
            spin = QSpinBox()
            spin.setRange(-600, 600)
            spin.setValue(int(down_offsets[idx] if idx < len(down_offsets) else 0))
            offsets_layout.addWidget(QLabel(text), idx - 1, 0)
            offsets_layout.addWidget(spin, idx - 1, 1)
            self.offset_spins.append(spin)

        layout.addWidget(QLabel("Down offsets (added to approach pose):"), 4, 0)
        layout.addWidget(offsets_frame, 4, 1)

        self.release_offset_spin = QSpinBox()
        self.release_offset_spin.setRange(-800, 800)
        self.release_offset_spin.setValue(int(motion.get("release_offset", 180)))
        layout.addWidget(QLabel("Gripper release offset (motor 6):"), 5, 0)
        layout.addWidget(self.release_offset_spin, 5, 1)

        return group

    def _build_velocity_spin(self, value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(50, 4000)
        spin.setValue(int(value))
        spin.setSuffix(" units/s")
        return spin

    def _build_progress_box(self) -> QWidget:
        box = QGroupBox("Progress and testing")
        layout = QVBoxLayout(box)
        layout.setSpacing(6)

        self.next_cell_label = QLabel()
        layout.addWidget(self.next_cell_label)

        btn_row = QHBoxLayout()
        self.test_btn = QPushButton("Test next cell")
        self.test_btn.clicked.connect(self._run_test_cycle)
        btn_row.addWidget(self.test_btn)

        self.reset_btn = QPushButton("Reset order")
        self.reset_btn.clicked.connect(self._reset_progress)
        btn_row.addWidget(self.reset_btn)

        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        return box

    def _build_buttons(self):
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        save = QPushButton("Save")
        save.setDefault(True)
        save.clicked.connect(self.accept)
        row.addWidget(save)
        return row

    def _apply_initial_values(self):
        self._update_corner_labels()
        self._update_next_cell_label()

    # ------------------------------------------------------------------
    # Corner helpers

    def _selected_arm_index(self) -> int:
        data = self.arm_combo.currentData()
        try:
            return int(data)
        except (TypeError, ValueError):
            return 0

    def _format_corner_text(self, index: int) -> str:
        entry = self.corner_entries[index]
        positions = entry.get("positions", [0] * 6)
        if not entry.get("captured"):
            return "Not set"
        return " / ".join(str(val) for val in positions)

    def _update_corner_labels(self):
        for idx, label in enumerate(self.corner_labels):
            label.setText(self._format_corner_text(idx))

    def _capture_corner(self, index: int):
        try:
            controller = MotorController(self.config, arm_index=self._selected_arm_index())
            positions = controller.read_positions()
            if not positions:
                raise RuntimeError("Unable to read positions")
            self.corner_entries[index]["positions"] = positions[:6]
            self.corner_entries[index]["captured"] = True
            self._update_corner_labels()
        except Exception as exc:
            log_exception("Palletizer: capture failed", exc, level="warning")
            QMessageBox.warning(self, "Capture failed", f"Could not read joint positions: {exc}")

    # ------------------------------------------------------------------
    # Progress helpers

    def _update_next_cell_label(self):
        uid = self.step_data.get("palletizer_uid")
        columns = self.columns_spin.value()
        rows = self.rows_spin.value()
        total = columns * rows
        if uid:
            index = self.state_store.peek_next(uid, total)
        else:
            index = 0
        grid = self.step_data.get("grid", {})
        desc = describe_cell(index, columns, bool(grid.get("snake")))
        self.next_cell_label.setText(
            f"Next placement: cell {index + 1}/{total} (row {desc['row'] + 1}, column {desc['column'] + 1})"
        )

    def _reset_progress(self):
        uid = self.step_data.get("palletizer_uid")
        if not uid:
            return
        self.state_store.reset(uid)
        self._test_index = 0
        self._update_next_cell_label()

    # ------------------------------------------------------------------
    # Data export

    def _build_step_payload(self, *, validate: bool = True) -> Dict:
        payload = dict(self.step_data)
        payload["name"] = self.name_edit.text().strip() or "Palletize Grid"
        payload["arm_index"] = int(self.arm_combo.currentData())

        grid = dict(payload.get("grid", {}))
        grid["columns"] = self.columns_spin.value()
        grid["rows"] = self.rows_spin.value()
        grid["snake"] = self.snake_check.isChecked()
        grid["corners"] = []

        missing = []
        for entry in self.corner_entries:
            positions = entry.get("positions", [0] * 6)
            captured = bool(entry.get("captured"))
            grid["corners"].append({
                "positions": positions[:6],
                "captured": captured,
                "label": entry.get("label"),
            })
            if validate and not captured:
                missing.append(entry.get("label"))

        if validate and missing:
            raise ValueError(f"Missing corners: {', '.join(missing)}")

        payload["grid"] = grid

        motion = dict(payload.get("motion", {}))
        motion["travel_velocity"] = self.travel_spin.value()
        motion["down_velocity"] = self.down_spin.value()
        motion["release_velocity"] = self.release_spin.value()
        motion["retreat_velocity"] = self.retreat_spin.value()

        down_offsets = [0] * 6
        for offset_idx, spin in enumerate(self.offset_spins, start=1):
            down_offsets[offset_idx] = spin.value()
        motion["down_offsets"] = down_offsets
        motion["release_offset"] = self.release_offset_spin.value()
        payload["motion"] = motion

        if not payload.get("palletizer_uid"):
            payload["palletizer_uid"] = self.step_data.get("palletizer_uid")

        return payload

    def get_step_data(self) -> Optional[Dict]:
        try:
            return self._build_step_payload(validate=True)
        except ValueError as exc:
            QMessageBox.warning(self, "Missing data", str(exc))
            return None

    # ------------------------------------------------------------------
    # Dialog overrides

    def accept(self):
        payload = self.get_step_data()
        if payload is None:
            return
        self.step_data = payload
        super().accept()

    # ------------------------------------------------------------------
    # Testing helpers

    def _run_test_cycle(self):
        try:
            payload = self._build_step_payload(validate=True)
        except ValueError as exc:
            QMessageBox.warning(self, "Missing data", str(exc))
            return
        columns = payload["grid"]["columns"]
        rows = payload["grid"]["rows"]
        corners = [corner.get("positions", [0] * 6) for corner in payload["grid"]["corners"]]
        cells = build_cell_positions(corners, columns, rows)
        cells = reorder_cells_for_snake(cells, columns, bool(payload["grid"].get("snake")))
        if not cells:
            QMessageBox.warning(self, "No cells", "Please configure at least one placement cell.")
            return

        index = self._test_index % len(cells)
        target = cells[index]
        motion = payload["motion"]
        down = apply_down_offsets(target, motion.get("down_offsets", [0] * 6))
        release = apply_release_offset(down, motion.get("release_offset", 0))

        controller = None
        try:
            controller = MotorController(self.config, arm_index=int(payload.get("arm_index", 0)))
            if not controller.connect():
                raise RuntimeError("Failed to connect to motors")
            controller.set_positions(target, velocity=motion.get("travel_velocity", 600), wait=True, keep_connection=True)
            controller.set_positions(down, velocity=motion.get("down_velocity", 400), wait=True, keep_connection=True)
            controller.set_positions(release, velocity=motion.get("release_velocity", 250), wait=True, keep_connection=True)
            controller.set_positions(target, velocity=motion.get("retreat_velocity", 600), wait=True, keep_connection=False)
        except Exception as exc:
            log_exception("Palletizer: test failed", exc, level="error")
            QMessageBox.warning(self, "Test failed", f"Unable to execute preview: {exc}")
            return
        finally:
            if controller:
                try:
                    controller.disconnect()
                except Exception:
                    pass

        self._test_index += 1
        columns = payload["grid"]["columns"]
        desc = describe_cell(index, columns, bool(payload["grid"].get("snake")))
        QMessageBox.information(
            self,
            "Test completed",
            f"Moved through cell {index + 1} (row {desc['row'] + 1}, column {desc['column'] + 1}).",
        )

