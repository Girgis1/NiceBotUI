from __future__ import annotations

import time
from copy import deepcopy
from typing import List, Optional

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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from utils.config_compat import format_arm_label, iter_arm_configs
from utils.motor_controller import MotorController
from utils.palletizer import (
    build_cycle,
    clone_pallet_config,
    compute_cell_positions,
    create_default_pallet_config as _create_default_config,
    ensure_corner_structure,
    have_all_corners,
    normalize_down_adjust,
    normalize_velocities,
    update_arm_metadata,
)


def create_default_pallet_config(config: dict | None = None, *, arm_index: int | None = None) -> dict:
    """Expose helper so SequenceTab can import from palletize_ui."""

    return _create_default_config(config, arm_index=arm_index)


class PalletizeConfigDialog(QDialog):
    """Guided setup dialog for palletization steps."""

    def __init__(self, parent: Optional[QWidget], step: Optional[dict], config: dict):
        super().__init__(parent)
        self.setWindowTitle("Palletisation Setup")
        self.resize(760, 620)
        self._app_config = config or {}
        defaults = create_default_pallet_config(self._app_config)
        ensure_corner_structure(defaults)
        self.step_data = clone_pallet_config(step or defaults, defaults=defaults)
        ensure_corner_structure(self.step_data)
        self._test_index = 0
        self._motor_controller: Optional[MotorController] = None
        self._controller_arm_index: Optional[int] = None

        self._build_ui()
        self._refresh_corner_labels()
        self._update_test_state()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Step name
        name_row = QHBoxLayout()
        name_label = QLabel("Step Name:")
        name_label.setStyleSheet("color: #ddd;")
        name_row.addWidget(name_label)
        self.name_edit = QLineEdit(self.step_data.get("name", "Palletise"))
        self.name_edit.textChanged.connect(self._handle_name_changed)
        name_row.addWidget(self.name_edit)
        layout.addLayout(name_row)

        # Arm selection
        arm_row = QHBoxLayout()
        arm_label = QLabel("Robot Arm:")
        arm_label.setStyleSheet("color: #ddd;")
        arm_row.addWidget(arm_label)
        self.arm_combo = QComboBox()
        self._arm_options: List[tuple[int, str]] = []
        current_index = int(self.step_data.get("arm_index", 0))
        for idx, arm_cfg in iter_arm_configs(self._app_config, arm_type="robot"):
            label = format_arm_label(idx, arm_cfg)
            self.arm_combo.addItem(label, idx)
            self._arm_options.append((idx, label))
        if not self._arm_options:
            self.arm_combo.addItem("Arm 1", 0)
            self._arm_options.append((0, "Arm 1"))
        combo_index = max(0, self.arm_combo.findData(current_index))
        self.arm_combo.setCurrentIndex(combo_index)
        self.arm_combo.currentIndexChanged.connect(self._handle_arm_changed)
        arm_row.addWidget(self.arm_combo)
        layout.addLayout(arm_row)

        # Grid configuration
        grid_group = QGroupBox("Grid")
        grid_group.setStyleSheet("QGroupBox { color: #fff; font-weight: bold; }")
        grid_layout = QHBoxLayout(grid_group)
        self.columns_spin = QSpinBox()
        self.columns_spin.setRange(1, 20)
        self.columns_spin.setValue(int(self.step_data.get("grid", {}).get("columns", 3)))
        self.columns_spin.setPrefix("Columns: ")
        self.columns_spin.valueChanged.connect(self._handle_grid_changed)
        grid_layout.addWidget(self.columns_spin)
        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(1, 20)
        self.rows_spin.setValue(int(self.step_data.get("grid", {}).get("rows", 3)))
        self.rows_spin.setPrefix("Rows: ")
        self.rows_spin.valueChanged.connect(self._handle_grid_changed)
        grid_layout.addWidget(self.rows_spin)
        layout.addWidget(grid_group)

        # Corner capture
        corner_group = QGroupBox("Corners")
        corner_group.setStyleSheet("QGroupBox { color: #fff; font-weight: bold; }")
        corner_layout = QGridLayout(corner_group)
        corner_layout.setContentsMargins(12, 12, 12, 12)
        corner_layout.setSpacing(8)
        self.corner_status: List[QLabel] = []
        for idx in range(4):
            frame = QFrame()
            frame.setFrameShape(QFrame.StyledPanel)
            frame_layout = QVBoxLayout(frame)
            header = QLabel(f"Corner {idx + 1}")
            header.setStyleSheet("color: #ffd54f; font-weight: bold;")
            frame_layout.addWidget(header)
            status = QLabel("Not set")
            status.setStyleSheet("color: #ccc;")
            frame_layout.addWidget(status)
            self.corner_status.append(status)
            btn_row = QHBoxLayout()
            capture_btn = QPushButton("Capture current")
            capture_btn.clicked.connect(lambda _=False, i=idx: self._capture_corner(i))
            btn_row.addWidget(capture_btn)
            clear_btn = QPushButton("Clear")
            clear_btn.clicked.connect(lambda _=False, i=idx: self._clear_corner(i))
            btn_row.addWidget(clear_btn)
            frame_layout.addLayout(btn_row)
            corner_layout.addWidget(frame, idx // 2, idx % 2)
        layout.addWidget(corner_group)

        # Down and release adjustments
        adjust_group = QGroupBox("Down & Release")
        adjust_group.setStyleSheet("QGroupBox { color: #fff; font-weight: bold; }")
        adjust_layout = QGridLayout(adjust_group)
        adjust_layout.setSpacing(6)
        down_values = normalize_down_adjust(self.step_data.get("down_adjust"))
        self.down_spins: List[QSpinBox] = []
        for offset, motor_id in enumerate(range(2, 6)):
            spin = QSpinBox()
            spin.setRange(-1200, 1200)
            spin.setValue(down_values[motor_id - 1])
            spin.setPrefix(f"Motor {motor_id}: ")
            spin.valueChanged.connect(lambda value, i=motor_id - 1: self._handle_down_adjust(i, value))
            self.down_spins.append(spin)
            adjust_layout.addWidget(spin, offset // 2, offset % 2)
        self.release_spin = QSpinBox()
        self.release_spin.setRange(-1200, 1200)
        self.release_spin.setPrefix("Motor 6 release: ")
        self.release_spin.setValue(int(self.step_data.get("release_adjust", 0)))
        self.release_spin.valueChanged.connect(self._handle_release_adjust)
        adjust_layout.addWidget(self.release_spin, 2, 0, 1, 2)
        self.release_hold_spin = QDoubleSpinBox()
        self.release_hold_spin.setRange(0.0, 5.0)
        self.release_hold_spin.setSingleStep(0.1)
        self.release_hold_spin.setPrefix("Release pause (s): ")
        self.release_hold_spin.setValue(float(self.step_data.get("release_hold", 0.3)))
        self.release_hold_spin.valueChanged.connect(self._handle_release_hold)
        adjust_layout.addWidget(self.release_hold_spin, 3, 0, 1, 2)
        layout.addWidget(adjust_group)

        # Velocity settings
        velocity_group = QGroupBox("Velocities")
        velocity_group.setStyleSheet("QGroupBox { color: #fff; font-weight: bold; }")
        velocity_layout = QHBoxLayout(velocity_group)
        velocities = normalize_velocities(self.step_data)
        self.travel_spin = self._build_velocity_spin("Travel", velocities["travel"], self._handle_travel_velocity)
        self.down_spin = self._build_velocity_spin("Down", velocities["down"], self._handle_down_velocity)
        self.release_velocity_spin = self._build_velocity_spin("Release", velocities["release"], self._handle_release_velocity)
        velocity_layout.addWidget(self.travel_spin)
        velocity_layout.addWidget(self.down_spin)
        velocity_layout.addWidget(self.release_velocity_spin)
        layout.addWidget(velocity_group)

        # Test controls
        test_row = QHBoxLayout()
        self.test_button = QPushButton("Test Next Cell")
        self.test_button.clicked.connect(self._run_test_cycle)
        test_row.addWidget(self.test_button)
        self.test_status = QLabel("Set four corners to enable testing.")
        self.test_status.setStyleSheet("color: #ccc;")
        test_row.addWidget(self.test_status)
        test_row.addStretch()
        layout.addLayout(test_row)

        # Dialog buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._handle_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_velocity_spin(self, label: str, value: int, handler) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(1, 4000)
        spin.setValue(int(value))
        spin.setPrefix(f"{label}: ")
        spin.valueChanged.connect(handler)
        return spin

    # ------------------------------------------------------------------ data helpers

    def _handle_name_changed(self, text: str) -> None:
        clean = text.strip() or "Palletise"
        self.step_data["name"] = clean

    def _handle_arm_changed(self) -> None:
        data = self.arm_combo.currentData()
        arm_index = int(data) if data is not None else 0
        update_arm_metadata(self.step_data, self._app_config, arm_index)
        self._disconnect_motor_controller()

    def _handle_grid_changed(self) -> None:
        grid = self.step_data.setdefault("grid", {})
        grid["columns"] = int(self.columns_spin.value())
        grid["rows"] = int(self.rows_spin.value())
        self._update_test_state()

    def _handle_down_adjust(self, motor_index: int, value: int) -> None:
        adjust = normalize_down_adjust(self.step_data.get("down_adjust"))
        adjust[motor_index] = int(value)
        self.step_data["down_adjust"] = adjust

    def _handle_release_adjust(self, value: int) -> None:
        self.step_data["release_adjust"] = int(value)

    def _handle_release_hold(self, value: float) -> None:
        self.step_data["release_hold"] = float(value)

    def _handle_travel_velocity(self, value: int) -> None:
        velocities = normalize_velocities(self.step_data)
        velocities["travel"] = int(value)
        self.step_data["velocities"] = velocities

    def _handle_down_velocity(self, value: int) -> None:
        velocities = normalize_velocities(self.step_data)
        velocities["down"] = int(value)
        self.step_data["velocities"] = velocities

    def _handle_release_velocity(self, value: int) -> None:
        velocities = normalize_velocities(self.step_data)
        velocities["release"] = int(value)
        self.step_data["velocities"] = velocities

    # ------------------------------------------------------------------ corners

    def _capture_corner(self, index: int) -> None:
        controller = self._ensure_motor_controller()
        if not controller:
            return
        if not controller.bus and not controller.connect():
            QMessageBox.warning(self, "Motor Connection", "Failed to connect to motors. Check power and USB.")
            return
        try:
            positions = controller.read_positions_from_bus()
        except Exception as exc:  # pragma: no cover - hardware
            QMessageBox.warning(self, "Motor Read", f"Could not read positions: {exc}")
            return
        if not positions:
            QMessageBox.warning(self, "Motor Read", "Motor positions are unavailable.")
            return
        self.step_data["corners"][index]["motor_positions"] = [int(p) for p in positions]
        self.step_data["corners"][index]["timestamp"] = time.time()
        self._refresh_corner_labels(index)
        self._update_test_state()

    def _clear_corner(self, index: int) -> None:
        self.step_data["corners"][index]["motor_positions"] = None
        self.step_data["corners"][index]["timestamp"] = None
        self._refresh_corner_labels(index)
        self._update_test_state()

    def _refresh_corner_labels(self, only_index: Optional[int] = None) -> None:
        targets = [only_index] if only_index is not None else range(len(self.corner_status))
        for idx in targets:
            corner = self.step_data["corners"][idx]
            label = self.corner_status[idx]
            positions = corner.get("motor_positions")
            if positions and len(positions) == 6:
                preview = ", ".join(str(int(p)) for p in positions[:2])
                label.setText(f"Set ({preview} …)")
                label.setStyleSheet("color: #a5d6a7;")
            else:
                label.setText("Not set")
                label.setStyleSheet("color: #ccc;")

    # ------------------------------------------------------------------ motor helpers

    def _ensure_motor_controller(self) -> Optional[MotorController]:
        arm_index = int(self.step_data.get("arm_index", 0))
        if self._motor_controller and self._controller_arm_index == arm_index:
            return self._motor_controller
        self._disconnect_motor_controller()
        try:
            controller = MotorController(self._app_config, arm_index=arm_index)
        except Exception as exc:  # pragma: no cover - defensive
            QMessageBox.warning(self, "Motor Controller", f"Could not create controller: {exc}")
            return None
        controller.speed_multiplier = 1.0
        self._motor_controller = controller
        self._controller_arm_index = arm_index
        return controller

    def _disconnect_motor_controller(self) -> None:
        if self._motor_controller:
            try:
                self._motor_controller.disconnect()
            except Exception:
                pass
        self._motor_controller = None
        self._controller_arm_index = None

    # ------------------------------------------------------------------ testing

    def _run_test_cycle(self) -> None:
        if not have_all_corners(self.step_data):
            QMessageBox.information(self, "Corners", "Set all four corners before testing.")
            return
        controller = self._ensure_motor_controller()
        if not controller:
            return
        if not controller.bus and not controller.connect():
            QMessageBox.warning(self, "Motor Connection", "Failed to connect to motors.")
            return
        cells = compute_cell_positions(self.step_data)
        if not cells:
            QMessageBox.warning(self, "Grid", "Could not compute pallet cells. Check the corners.")
            return
        index = self._test_index % len(cells)
        self._test_index += 1
        cycle = build_cycle(self.step_data, index)
        if not cycle:
            QMessageBox.warning(self, "Cycle", "Unable to build motion for this cell.")
            return
        velocities = normalize_velocities(self.step_data)
        self.test_status.setText(f"Testing cell {index + 1}/{len(cells)}…")
        self._send_pose(controller, cycle.approach, velocities["travel"], keep_connection=True)
        self._send_pose(controller, cycle.down, velocities["down"], keep_connection=True)
        self._send_pose(controller, cycle.release, velocities["release"], keep_connection=True)
        hold = max(0.0, float(self.step_data.get("release_hold", 0.0)))
        if hold > 0:
            time.sleep(hold)
        self._send_pose(controller, cycle.retreat, velocities["travel"], keep_connection=True)
        self.test_status.setText(f"✓ Completed cell {index + 1}")

    def _send_pose(self, controller: MotorController, positions: List[int], velocity: int, *, keep_connection: bool) -> None:
        try:
            controller.set_positions(positions, velocity=velocity, wait=True, keep_connection=keep_connection)
        except Exception as exc:  # pragma: no cover - hardware
            QMessageBox.warning(self, "Motor Move", f"Movement failed: {exc}")

    def _update_test_state(self) -> None:
        ready = have_all_corners(self.step_data)
        self.test_button.setEnabled(ready)
        if ready:
            cols = int(self.step_data.get("grid", {}).get("columns", 1))
            rows = int(self.step_data.get("grid", {}).get("rows", 1))
            self.test_status.setText(f"Ready • {cols * rows} cells configured")
        else:
            self.test_status.setText("Set four corners to enable testing.")

    # ------------------------------------------------------------------ dialog API

    def _handle_accept(self) -> None:
        self.accept()

    def get_step_data(self) -> dict:
        data = deepcopy(self.step_data)
        data["type"] = "palletize"
        ensure_corner_structure(data)
        return data

    def closeEvent(self, event) -> None:  # pragma: no cover - Qt
        self._disconnect_motor_controller()
        super().closeEvent(event)
