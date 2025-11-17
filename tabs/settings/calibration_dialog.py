"""Touch-friendly SO101 calibration dialog with command runner."""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from PySide6.QtCore import Qt, QProcess, QTimer, Signal
from PySide6.QtGui import QFont, QGuiApplication, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CENTER_IMAGE = ROOT_DIR / "assets" / "calibration" / "so101_center.png"
CENTER_PROMPT_TRIGGERS = (
    "center position",
    "move the arm to center",
    "move the arm to the center",
    "set the arm in center",
)

JOINT_PROMPT_TRIGGERS = (
    "move each joint",
    "joint positions",
    "min and max",
    "record min/max",
    "move to min",
    "move to max",
)


def _normalize_port(port: str) -> str:
    port = (port or "").strip()
    if not port:
        return port
    if not port.startswith("/dev/"):
        if not port.startswith("tty"):
            port = f"tty{port}"
        port = f"/dev/{port}"
    return port


class SO101CalibrationDialog(QDialog):
    """Wizard-like dialog that wraps the lerobot-calibrate workflow."""

    calibration_finished = Signal(dict)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        default_robot_type: str = "so101",
        default_arm_role: str = "follower",
        default_port: str = "",
        default_robot_id: str = "",
        available_ports: Optional[Iterable[str]] = None,
        calibration_image_path: Path = DEFAULT_CENTER_IMAGE,
    ) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlag(Qt.FramelessWindowHint, True)  # Match vision window: no native title bar/close button
        self.setWindowTitle("SO101 Calibration")
        self.resize(1024, 600)

        self._stage = "config"
        self._awaiting_center = False
        self._active_process: Optional[QProcess] = None
        self._process_kind: Optional[str] = None
        self._latest_aux_output = ""
        self._max_output_size = 1024 * 1024  # 1MB cap on aux output
        self._result_payload: Optional[Dict[str, str]] = None
        self._manual_id_override = False
        self._id_variants: List[str] = []
        self._id_variant_index = 0
        self._initial_robot_id = default_robot_id or ""
        self.calibration_image_path = calibration_image_path
        self._motor_snapshot_mode = False
        self._motor_lines: Dict[str, str] = {}
        self._log_fullscreen = False

        self._build_ui(
            default_robot_type,
            default_arm_role,
            default_port,
            default_robot_id,
            available_ports or [],
        )
        self._update_command_preview()
        QTimer.singleShot(0, self._focus_default)
        QTimer.singleShot(0, self._load_center_image)

    # ------------------------------------------------------------------ UI
    def _build_ui(
        self,
        default_robot_type: str,
        default_arm_role: str,
        default_port: str,
        default_robot_id: str,
        available_ports: Iterable[str],
    ) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 2)
        layout.setSpacing(2)

        header = QLabel("SO101 Calibration")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet(
            "font-size: 18px; font-weight: 600; color: #f5f5f5; padding: 2px;"
        )
        layout.addWidget(header)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, stretch=1)

        self.form_widget = self._build_form(default_robot_type, default_arm_role, default_port, default_robot_id, available_ports)
        self.stack.addWidget(self.form_widget)

        self.center_widget = self._build_center_prompt()
        self.stack.addWidget(self.center_widget)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(100)
        self.log_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        log_font = QFont("DejaVu Sans Mono, Noto Color Emoji, monospace", 11)
        self.log_output.setFont(log_font)
        self.log_output.setStyleSheet(
            """
            QPlainTextEdit {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #404040;
                border-radius: 4px;
                padding: 8px;
            }
            """
        )
        layout.addWidget(self.log_output, stretch=0)

        button_row = QHBoxLayout()
        button_row.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(40)
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        button_row.addWidget(self.cancel_btn)

        self.primary_btn = QPushButton("Next")
        self.primary_btn.setMinimumHeight(40)
        self.primary_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; font-size: 16px; font-weight: bold; padding: 8px 20px; border-radius: 8px; }"
        )
        self.primary_btn.clicked.connect(self._on_primary_clicked)
        button_row.addWidget(self.primary_btn)

        layout.addLayout(button_row)

    def _build_form(
        self,
        default_robot_type: str,
        default_arm_role: str,
        default_port: str,
        default_robot_id: str,
        available_ports: Iterable[str],
    ) -> QWidget:
        container = QFrame()
        container.setFrameShape(QFrame.NoFrame)
        container.setStyleSheet("QFrame { background-color: #303030; border: 2px solid #4a4a4a; border-radius: 8px; }")

        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        table = QGridLayout()
        table.setVerticalSpacing(4)
        table.setHorizontalSpacing(8)

        label_style = "color: #dcdcdc; font-size: 16px; font-weight: 600;"

        # Robot Type
        robot_label = QLabel("Robot Type")
        robot_label.setStyleSheet(label_style)
        table.addWidget(robot_label, 0, 0)

        self.robot_type_combo = QComboBox()
        self.robot_type_combo.addItems(["so101", "so100"])
        self.robot_type_combo.setCurrentText(default_robot_type or "so101")
        self.robot_type_combo.setMinimumHeight(36)
        self.robot_type_combo.setStyleSheet(self._combo_style())
        self.robot_type_combo.currentTextChanged.connect(self._on_schema_changed)
        table.addWidget(self.robot_type_combo, 0, 1)

        # Arm type
        arm_label = QLabel("Arm Type")
        arm_label.setStyleSheet(label_style)
        table.addWidget(arm_label, 1, 0)

        self.arm_role_combo = QComboBox()
        self.arm_role_combo.addItems(["Follower", "Leader"])
        self.arm_role_combo.setCurrentText((default_arm_role or "follower").title())
        self.arm_role_combo.setMinimumHeight(36)
        self.arm_role_combo.setStyleSheet(self._combo_style())
        self.arm_role_combo.currentTextChanged.connect(self._on_schema_changed)
        table.addWidget(self.arm_role_combo, 1, 1)

        # Robot port row with find button
        port_label = QLabel("Robot Port")
        port_label.setStyleSheet(label_style)
        table.addWidget(port_label, 2, 0)

        port_row = QHBoxLayout()
        port_row.setSpacing(6)
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setMinimumHeight(36)
        self.port_combo.setStyleSheet(self._combo_style())
        ports = list(dict.fromkeys([_normalize_port(p) for p in available_ports if p]))
        if default_port and default_port not in ports:
            ports.insert(0, default_port)
        if ports:
            self.port_combo.addItems(ports)
        if default_port:
            self.port_combo.setCurrentText(default_port)
        self.port_combo.currentTextChanged.connect(self._update_command_preview)
        port_row.addWidget(self.port_combo, stretch=1)

        self.find_ports_btn = QPushButton("lerobot-find-port")
        self.find_ports_btn.setMinimumHeight(36)
        self.find_ports_btn.setStyleSheet(
            "QPushButton { background-color: #1976D2; color: white; font-weight: bold; padding: 0 12px; border-radius: 8px; }"
        )
        self.find_ports_btn.clicked.connect(self._run_port_discovery)
        port_row.addWidget(self.find_ports_btn)
        table.addLayout(port_row, 2, 1)

        # Robot ID row with arrows
        id_label = QLabel("Robot ID (Name)")
        id_label.setStyleSheet(label_style)
        table.addWidget(id_label, 3, 0)

        id_row = QHBoxLayout()
        id_row.setSpacing(4)
        self.robot_id_edit = QLineEdit(default_robot_id)
        self.robot_id_edit.setMinimumHeight(36)
        self.robot_id_edit.setStyleSheet(
            "QLineEdit { background-color: #2a2a2a; color: #f5f5f5; border: 2px solid #5a5a5a; border-radius: 8px; padding: 0 8px; font-size: 14px; }"
        )
        self.robot_id_edit.textEdited.connect(self._on_name_edited)
        id_row.addWidget(self.robot_id_edit, stretch=1)

        self.id_prev_btn = QPushButton("◀")
        self.id_prev_btn.setFixedSize(36, 36)
        self.id_prev_btn.clicked.connect(lambda: self._cycle_id(-1))
        id_row.addWidget(self.id_prev_btn)

        self.id_next_btn = QPushButton("▶")
        self.id_next_btn.setFixedSize(36, 36)
        self.id_next_btn.clicked.connect(lambda: self._cycle_id(1))
        id_row.addWidget(self.id_next_btn)
        table.addLayout(id_row, 3, 1)

        layout.addLayout(table)

        self.command_preview = QLabel()
        self.command_preview.setWordWrap(True)
        self.command_preview.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.command_preview.setStyleSheet(
            "color: #9ee5ff; font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 12px;"
        )
        self.command_preview.setFixedHeight(24)  # Compact single-row footprint
        self.command_preview.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.command_preview)

        self._refresh_id_suggestions(default_robot_id)
        return container

    def _build_center_prompt(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self.center_image_label = QLabel()
        self.center_image_label.setAlignment(Qt.AlignCenter)
        self.center_image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.center_image_label.setMaximumSize(800, 400)  # Limit size to prevent huge gray box
        self.center_image_label.setStyleSheet(
            "QLabel { background-color: #1f1f1f; border: 2px solid #3a3a3a; border-radius: 12px; }"
        )
        layout.addWidget(self.center_image_label, stretch=1)

        self.center_pixmap = QPixmap()
        self.center_image_label.setText("Loading calibration reference…")

        return container

    def _update_center_pixmap(self) -> None:
        if self.center_pixmap.isNull():
            return
        available = self.center_image_label.size()
        scaled = self.center_pixmap.scaled(
            available,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.center_image_label.setPixmap(scaled)

    def resizeEvent(self, event):  # type: ignore[override]
        super().resizeEvent(event)
        self._update_center_pixmap()

    def _load_center_image(self) -> None:
        """Load center image safely once the dialog is visible."""
        try:
            if self.calibration_image_path.exists():
                pixmap = QPixmap(str(self.calibration_image_path))
                if not pixmap.isNull():
                    self.center_pixmap = pixmap
                    self.center_image_label.clear()
                    self._update_center_pixmap()
                    return
            self.center_image_label.setText("Calibration reference image missing. Add one under assets/calibration/so101_center.png.")
        except Exception as exc:
            self.center_image_label.setText(f"Image load error: {exc}")

    # ---------------------------------------------------------------- Schema / command helpers
    def _combo_style(self) -> str:
        return (
            "QComboBox { background-color: #2a2a2a; color: #f5f5f5; border: 2px solid #5a5a5a; border-radius: 10px; padding: 0 12px; font-size: 16px; }"
            "QComboBox::drop-down { width: 32px; border: none; }"
            "QComboBox QAbstractItemView { background-color: #2f2f2f; color: #fff; selection-background-color: #4CAF50; }"
        )

    def _focus_default(self):
        self.robot_type_combo.setFocus()

    def _refresh_id_suggestions(self, default_robot_id: str = ""):
        robot = (self.robot_type_combo.currentText() or "so101").lower()
        role = (self.arm_role_combo.currentText() or "Follower").lower()
        base = f"R_{robot}_{role.capitalize()}"
        variants = [base, f"{base}_01", f"{base}_02", f"{base}_backup"]
        preferred_id = default_robot_id or self.robot_id_edit.text().strip() or self._initial_robot_id
        if preferred_id and preferred_id not in variants:
            variants.insert(0, preferred_id)
        self._id_variants = variants
        self._id_variant_index = 0
        if not self._manual_id_override:
            self.robot_id_edit.setText(self._id_variants[0])
        self._update_command_preview()

    def _cycle_id(self, step: int):
        if not self._id_variants:
            return
        self._manual_id_override = False
        self._id_variant_index = (self._id_variant_index + step) % len(self._id_variants)
        self.robot_id_edit.setText(self._id_variants[self._id_variant_index])
        self._update_command_preview()

    def _on_schema_changed(self):
        # Keep the user-provided ID when toggling schema; only refresh variants
        self._refresh_id_suggestions(self.robot_id_edit.text().strip())

    def _on_name_edited(self):
        self._manual_id_override = True
        self._update_command_preview()

    def _build_command(self) -> str:
        robot_slug = (self.robot_type_combo.currentText() or "so101").lower()
        arm_role = (self.arm_role_combo.currentText() or "Follower").lower()
        robot_type = f"{robot_slug}_{arm_role}"
        port_value = _normalize_port(self.port_combo.currentText())
        robot_id = self.robot_id_edit.text().strip() or f"R_{robot_slug}_{arm_role.title()}"
        section = "teleop" if arm_role == "leader" else "robot"
        args = [
            "lerobot-calibrate",
            f"--{section}.type={robot_type}",
            f"--{section}.port={port_value}",
            f"--{section}.id={robot_id}",
        ]
        return " ".join(shlex.quote(arg) for arg in args)

    def _update_command_preview(self):
        command = self._build_command()
        self.command_preview.setText(f"$ {command}")

    # ----------------------------------------------------------------- Actions
    def _on_primary_clicked(self):
        if self._active_process:
            awaiting_center = self._awaiting_center
            action_label = "confirm center position" if awaiting_center else "advance calibration"
            self._append_log(f"[UI] Sending ENTER to {action_label}...\n")
            try:
                self._active_process.write(b"\n")
                self._active_process.waitForBytesWritten(50)
            except Exception as exc:
                self._append_log(f"[UI] Failed to send ENTER: {exc}\n")
                return
            if awaiting_center:
                self._awaiting_center = False
                self.primary_btn.setText("Next")
            return

        if self._stage == "config":
            self._begin_calibration()
        elif self._stage == "complete":
            self.accept()

    def _on_cancel_clicked(self):
        if self._active_process:
            self._append_log("[UI] Stopping active command...\n")
            self._active_process.kill()
            self._active_process = None
        self.reject()

    def _begin_calibration(self):
        command = self._build_command()
        if not _normalize_port(self.port_combo.currentText()):
            self._append_log("❌ Select a valid robot port before continuing.\n")
            return
        if not self._can_start_process():
            self._append_log("[UI] Calibration already in progress.\n")
            return

        self._stage = "running"
        self._disable_motor_snapshot_mode()
        self.primary_btn.setEnabled(False)  # Disable button during calibration process
        self.cancel_btn.setText("Stop")
        self.robot_type_combo.setEnabled(False)
        self.arm_role_combo.setEnabled(False)
        self.port_combo.setEnabled(False)
        self.find_ports_btn.setEnabled(False)
        self.robot_id_edit.setEnabled(False)
        self.id_next_btn.setEnabled(False)
        self.id_prev_btn.setEnabled(False)
        self._remove_existing_calibration()
        self._prepare_output()
        self._show_center_prompt()
        self._start_process(command, "calibrate")

    def _prepare_output(self):
        self.log_output.appendPlainText("—" * 60)
        self.log_output.appendPlainText("Starting lerobot-calibrate...\n")

    def _run_port_discovery(self):
        if not self._can_start_process():
            self._append_log("[UI] Cannot start port discovery - process already running.\n")
            return
        self.find_ports_btn.setEnabled(False)
        self._latest_aux_output = ""
        self._start_process("lerobot-find-port", "find-port")

    def _start_process(self, command: str, kind: str):
        process = QProcess(self)
        process.setProgram("bash")
        process.setArguments(["-lc", command])
        process.readyReadStandardOutput.connect(lambda: self._on_process_output(process, False))
        process.readyReadStandardError.connect(lambda: self._on_process_output(process, True))
        process.errorOccurred.connect(lambda err: self._on_process_error(process, kind, err))
        process.finished.connect(lambda code, status: self._on_process_finished(process, kind, code))
        self._active_process = process
        self._process_kind = kind
        self._append_log(f"$ {command}\n")
        process.start()
        if process.error() != QProcess.UnknownError and process.state() == QProcess.NotRunning:
            self._append_log(f"[UI] Failed to start process: {process.errorString()}\n")
            self._active_process = None
            self._process_kind = None
            self._stage = "config"

    def _on_process_output(self, process: QProcess, is_stderr: bool):
        data = bytes(process.readAllStandardError() if is_stderr else process.readAllStandardOutput())
        if not data:
            return
        text = data.decode("utf-8", errors="ignore").replace("\r", "\n")
        if text:
            self._append_log(text)
        if self._process_kind == "calibrate":
            lowered = text.lower()
            if not self._awaiting_center and any(trigger in lowered for trigger in CENTER_PROMPT_TRIGGERS):
                self._show_center_prompt()
            elif not self._motor_snapshot_mode and any(trigger in lowered for trigger in JOINT_PROMPT_TRIGGERS):
                self._enable_motor_snapshot_mode()
        elif self._process_kind == "find-port":
            self._latest_aux_output += text
            if len(self._latest_aux_output) > self._max_output_size:
                self._latest_aux_output = self._latest_aux_output[-self._max_output_size // 2 :]
                self._append_log("[UI] Warning: Port discovery output truncated\n")

    def _show_center_prompt(self):
        if self._awaiting_center:
            return
        self._awaiting_center = True
        self.primary_btn.setEnabled(True)
        self.primary_btn.setText("Set")
        self._set_log_fullscreen(False)
        self.stack.setCurrentWidget(self.center_widget)
        self._append_log("[UI] Awaiting center position confirmation...\n")

    def _can_start_process(self) -> bool:
        """Return True when no active process is running and stage is valid."""
        if self._active_process and self._active_process.state() != QProcess.NotRunning:
            return False
        return self._stage in ("config", "running")

    def _on_process_finished(self, process: QProcess, kind: str, exit_code: int):
        if self._active_process is not process:
            return
        success = exit_code == 0
        if kind == "find-port":
            self.find_ports_btn.setEnabled(True)
            new_ports = self._extract_ports(self._latest_aux_output)
            for port in new_ports:
                if self.port_combo.findText(port) == -1:
                    self.port_combo.addItem(port)
            self._append_log(f"[lerobot-find-port] exit code {exit_code}\n")
        elif kind == "calibrate":
            self._finalize_calibration(success)
        self._active_process = None
        self._process_kind = None
        self._stage = "config" if kind == "find-port" else self._stage

    def _on_process_error(self, process: QProcess, kind: str, error):
        if self._active_process is not process:
            return
        self._append_log(f"[UI] Process error ({kind}): {process.errorString()}\n")
        self.find_ports_btn.setEnabled(True)
        self._active_process = None
        self._process_kind = None
        self._stage = "config"

    def _finalize_calibration(self, success: bool):
        self.primary_btn.setEnabled(True)
        self.cancel_btn.setText("Close")
        self.find_ports_btn.setEnabled(True)
        self.robot_type_combo.setEnabled(True)
        self.arm_role_combo.setEnabled(True)
        self.port_combo.setEnabled(True)
        self.robot_id_edit.setEnabled(True)
        self.id_next_btn.setEnabled(True)
        self.id_prev_btn.setEnabled(True)
        self.stack.setCurrentWidget(self.form_widget)
        self._awaiting_center = False
        self._disable_motor_snapshot_mode()
        if success:
            payload = self._build_result_payload()
            self._result_payload = payload
            self._append_log("✅ Calibration finished successfully.\n")
            self.calibration_finished.emit(payload)
            self.primary_btn.setText("Close")
            self._stage = "complete"
        else:
            self._append_log("❌ Calibration failed. Check the logs above.\n")
            self.primary_btn.setText("Close")
            self._stage = "complete"

    def _build_result_payload(self) -> Dict[str, str]:
        robot_slug = (self.robot_type_combo.currentText() or "so101").lower()
        arm_role = (self.arm_role_combo.currentText() or "Follower").lower()
        return {
            "robot_type": robot_slug,
            "arm_role": arm_role,
            "robot_type_slug": f"{robot_slug}_{arm_role}",
            "port": _normalize_port(self.port_combo.currentText()),
            "robot_id": self.robot_id_edit.text().strip(),
        }

    def result_payload(self) -> Optional[Dict[str, str]]:
        return self._result_payload

    def _calibration_file_path(self, robot_type_slug: str, arm_role: str, robot_id: str) -> Path:
        base = Path.home() / ".cache" / "huggingface" / "lerobot" / "calibration"
        category = "robots" if arm_role == "follower" else "teleoperators"
        return base / category / robot_type_slug / f"{robot_id}.json"

    def _remove_existing_calibration(self):
        payload = self._build_result_payload()
        file_path = self._calibration_file_path(payload["robot_type_slug"], payload["arm_role"], payload["robot_id"])
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if file_path.exists():
                file_path.unlink()
                self._append_log(f"[UI] Removed existing calibration: {file_path.name}\n")
        except OSError as exc:
            self._append_log(f"[UI] Warning: could not remove {file_path.name}: {exc}\n")

    def _extract_ports(self, text: str) -> List[str]:
        pattern = re.compile(r"/dev/tty[\w\d._-]+")
        return sorted(set(pattern.findall(text)))

    def _enable_motor_snapshot_mode(self):
        if self._motor_snapshot_mode:
            return
        self._motor_snapshot_mode = True
        self._motor_lines.clear()
        self._set_log_fullscreen(True)
        if not self._awaiting_center and self._stage == "running":
            self.primary_btn.setEnabled(True)
            self.primary_btn.setText("Save")
        self._render_motor_snapshot()

    def _disable_motor_snapshot_mode(self):
        if not self._motor_snapshot_mode:
            return
        self._motor_snapshot_mode = False
        self._motor_lines.clear()
        self._set_log_fullscreen(False)

    def _ingest_motor_snapshot_text(self, text: str):
        updated = False
        for raw in text.splitlines():
            stripped = raw.strip()
            if not stripped:
                continue
            label = self._motor_label_from_line(stripped)
            if not label:
                continue
            self._motor_lines[str(label)] = stripped
            updated = True
        if updated:
            self._render_motor_snapshot()

    def _render_motor_snapshot(self):
        header = "Live Motor Positions"
        lines = [header, "-" * len(header)]
        if self._motor_lines:
            for label in sorted(self._motor_lines.keys(), key=self._motor_sort_key):
                lines.append(self._motor_lines[label])
        else:
            lines.append("Move each joint to record min/max positions…")
        self.log_output.setPlainText("\n".join(lines))
        self.log_output.moveCursor(QTextCursor.Start)

    def _motor_label_from_line(self, line: str) -> Optional[str]:
        if ":" in line:
            return line.split(":", 1)[0].strip()
        if "=" in line:
            return line.split("=", 1)[0].strip()
        parts = line.split()
        if parts:
            return parts[0]
        return None

    def _motor_sort_key(self, label: str):
        label_str = str(label)
        match = re.search(r"(\d+)", label_str)
        if match:
            return (0, int(match.group(1)), label_str.lower())
        return (1, 0, label_str.lower())

    def _set_log_fullscreen(self, fullscreen: bool):
        if fullscreen == self._log_fullscreen:
            return
        self._log_fullscreen = fullscreen
        if fullscreen:
            self.stack.hide()
            self.log_output.setMinimumHeight(0)
            self.log_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        else:
            self.stack.show()
            self.log_output.setMinimumHeight(100)
            self.log_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self.stack.setCurrentWidget(self.center_widget if self._awaiting_center else self.form_widget)

    def _append_log(self, text: str):
        if not text:
            return
        if self._motor_snapshot_mode:
            self._ingest_motor_snapshot_text(text)
            return
        scrollbar = self.log_output.verticalScrollBar()
        at_bottom = scrollbar.value() == scrollbar.maximum()
        self.log_output.moveCursor(QTextCursor.End)
        self.log_output.insertPlainText(text)
        if at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def showEvent(self, event):  # type: ignore[override]
        super().showEvent(event)
        self._match_host_window()
        self._set_log_fullscreen(False)

    def _match_host_window(self):
        target_rect = None
        parent = self.parentWidget()
        if parent is not None:
            target_rect = (parent.window() or parent).geometry()
        if target_rect is None:
            screen = (self.windowHandle().screen() if self.windowHandle() else None) or QGuiApplication.primaryScreen()
            if screen is not None:
                target_rect = screen.availableGeometry()
        if target_rect is None:
            return
        # For 1024x600 touchscreen, ensure we fit perfectly
        width = min(target_rect.width(), 1024)
        height = min(target_rect.height(), 600)
        self.resize(width, height)
        self.move(
            target_rect.center().x() - self.width() // 2,
            target_rect.center().y() - self.height() // 2,
        )

    def reject(self) -> None:  # type: ignore[override]
        if self._active_process:
            self._active_process.kill()
            self._active_process = None
            self._process_kind = None
            self._stage = "config"
        super().reject()

    def accept(self) -> None:  # type: ignore[override]
        super().accept()
