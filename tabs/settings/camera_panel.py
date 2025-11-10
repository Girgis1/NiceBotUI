"""Camera panel helpers for the Settings tab."""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Optional
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

try:  # Optional dependency used for live previews
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    cv2 = None

from utils.camera_hub import temporarily_release_camera_hub


class CameraPanelMixin:
    """Encapsulates camera UI wiring and discovery helpers."""

    camera_front_circle: Optional[QLabel]  # Provided at runtime
    camera_wrist_circle: Optional[QLabel]
    camera_wrist_right_circle: Optional[QLabel]

    def create_camera_tab(self) -> QWidget:
        """Create camera settings tab - optimized for 1024x600 touchscreen."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        detect_section = QLabel("🎥 Camera Configuration")
        detect_section.setStyleSheet("color: #4CAF50; font-size: 14px; font-weight: bold; margin-bottom: 2px;")
        layout.addWidget(detect_section)

        front_row = QHBoxLayout()
        front_row.setSpacing(6)
        self.camera_front_circle = self.create_status_circle("empty")
        front_row.addWidget(self.camera_front_circle)

        front_label = QLabel("Front:")
        front_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        front_label.setFixedWidth(55)
        front_row.addWidget(front_label)

        self.cam_front_edit = QLineEdit("/dev/video1")
        self.cam_front_edit.setFixedHeight(45)
        self.cam_front_edit.setStyleSheet(self._camera_lineedit_style())
        front_row.addWidget(self.cam_front_edit)
        self.cam_front_edit.editingFinished.connect(
            partial(self._commit_camera_field, "front", self.cam_front_edit)
        )
        front_row.addStretch()
        layout.addLayout(front_row)

        wrist_row = QHBoxLayout()
        wrist_row.setSpacing(6)
        self.camera_wrist_circle = self.create_status_circle("empty")
        wrist_row.addWidget(self.camera_wrist_circle)

        wrist_label = QLabel("Wrist L:")
        wrist_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        wrist_label.setFixedWidth(55)
        wrist_row.addWidget(wrist_label)

        self.cam_wrist_edit = QLineEdit("/dev/video3")
        self.cam_wrist_edit.setFixedHeight(45)
        self.cam_wrist_edit.setStyleSheet(self._camera_lineedit_style())
        wrist_row.addWidget(self.cam_wrist_edit)
        self.cam_wrist_edit.editingFinished.connect(
            partial(self._commit_camera_field, "wrist", self.cam_wrist_edit)
        )
        wrist_row.addSpacing(12)
        wrist_row.addStretch()
        layout.addLayout(wrist_row)

        wrist_r_row = QHBoxLayout()
        wrist_r_row.setSpacing(6)
        self.camera_wrist_right_circle = self.create_status_circle("empty")
        wrist_r_row.addWidget(self.camera_wrist_right_circle)

        wrist_r_label = QLabel("Wrist R:")
        wrist_r_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        wrist_r_label.setFixedWidth(55)
        wrist_r_row.addWidget(wrist_r_label)

        self.cam_wrist_right_edit = QLineEdit("/dev/video5")
        self.cam_wrist_right_edit.setFixedHeight(45)
        self.cam_wrist_right_edit.setStyleSheet(self._camera_lineedit_style())
        wrist_r_row.addWidget(self.cam_wrist_right_edit)
        self.cam_wrist_right_edit.editingFinished.connect(
            partial(self._commit_camera_field, "wrist_right", self.cam_wrist_right_edit)
        )
        wrist_r_row.addSpacing(12)
        wrist_r_row.addStretch()
        layout.addLayout(wrist_r_row)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.find_cameras_btn = QPushButton("🔍 Find Cameras")
        self.find_cameras_btn.setFixedHeight(45)
        self.find_cameras_btn.setFixedWidth(160)
        self.find_cameras_btn.setStyleSheet(self.get_button_style("#FF9800", "#F57C00"))
        self.find_cameras_btn.clicked.connect(self.find_cameras)
        button_row.addWidget(self.find_cameras_btn)
        layout.addLayout(button_row)

        layout.addSpacing(8)

        settings_section = QLabel("⚙️ Camera Properties")
        settings_section.setStyleSheet("color: #4CAF50; font-size: 14px; font-weight: bold; margin-bottom: 2px;")
        layout.addWidget(settings_section)

        self.cam_width_spin = self.add_spinbox_row(layout, "Width:", 320, 1920, 640)
        self.cam_height_spin = self.add_spinbox_row(layout, "Height:", 240, 1080, 480)
        self.cam_fps_spin = self.add_spinbox_row(layout, "Camera FPS:", 1, 60, 30)

        layout.addStretch()
        return widget

    def _camera_lineedit_style(self) -> str:
        return (
            """
            QLineEdit {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #4CAF50;
                background-color: #555555;
            }
            """
        )

    def find_cameras(self):
        """Scan for available cameras and allow the user to assign them."""
        if cv2 is None:
            self.status_label.setText("❌ OpenCV is required for camera discovery")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
            return

        try:
            self.status_label.setText("⏳ Scanning for cameras...")
            self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")

            with temporarily_release_camera_hub():
                found_cameras = []
                preview_timer: Optional[QTimer] = None
                found_cameras = self._discover_cameras_for_dialog()

                if not found_cameras:
                    self.status_label.setText("❌ No cameras found")
                    self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
                    return

                dialog = QDialog(self)
                dialog.setWindowTitle("Found Cameras")
                dialog.setMinimumWidth(600)
                dialog.setMinimumHeight(500)
                dialog.setStyleSheet("QDialog { background-color: #2a2a2a; }")

                layout = QVBoxLayout(dialog)
                title = QLabel(f"✓ Found {len(found_cameras)} camera(s):")
                title.setStyleSheet("color: #4CAF50; font-size: 16px; font-weight: bold; padding: 10px;")
                layout.addWidget(title)

                camera_list = QComboBox()
                camera_list.setStyleSheet(
                    """
                    QComboBox {
                        background-color: #505050;
                        color: #ffffff;
                        border: 2px solid #707070;
                        border-radius: 8px;
                        padding: 10px;
                        font-size: 15px;
                    }
                    """
                )
                for cam in found_cameras:
                    camera_list.addItem(f"{cam['path']} - {cam['resolution']}", cam["id"])
                layout.addWidget(camera_list)

                preview_label = QLabel("Camera Preview")
                preview_label.setStyleSheet("background-color: #000000; min-height: 300px;")
                preview_label.setAlignment(Qt.AlignCenter)
                layout.addWidget(preview_label)

                assign_section = QLabel("Assign to:")
                assign_section.setStyleSheet("color: #e0e0e0; font-size: 14px; padding: 10px;")
                layout.addWidget(assign_section)

                assign_group = QButtonGroup(dialog)
                front_radio = QRadioButton("Front Camera")
                front_radio.setStyleSheet("QRadioButton { color: #e0e0e0; font-size: 14px; padding: 5px; }")
                front_radio.setChecked(True)
                assign_group.addButton(front_radio, 0)
                layout.addWidget(front_radio)

                wrist_radio = QRadioButton("Wrist L Camera")
                wrist_radio.setStyleSheet("QRadioButton { color: #e0e0e0; font-size: 14px; padding: 5px; }")
                assign_group.addButton(wrist_radio, 1)
                layout.addWidget(wrist_radio)

                wrist_r_radio = QRadioButton("Wrist R Camera")
                wrist_r_radio.setStyleSheet("QRadioButton { color: #e0e0e0; font-size: 14px; padding: 5px; }")
                assign_group.addButton(wrist_r_radio, 2)
                layout.addWidget(wrist_r_radio)

                def update_preview():
                    try:
                        selected_id = camera_list.currentData()
                        for cam in found_cameras:
                            if cam["id"] == selected_id:
                                ret, frame = cam["capture"].read()
                                if ret:
                                    frame = cv2.resize(frame, (480, 360))
                                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                                    h, w, ch = rgb_frame.shape
                                    bytes_per_line = ch * w
                                    qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
                                    preview_label.setPixmap(QPixmap.fromImage(qt_image))
                                break
                    except Exception:
                        pass

                preview_timer = QTimer(dialog)
                preview_timer.timeout.connect(update_preview)
                preview_timer.start(120)

                btn_layout = QHBoxLayout()
                btn_layout.addStretch()

                cancel_btn = QPushButton("Cancel")
                cancel_btn.setStyleSheet(self.get_button_style("#909090", "#707070"))
                cancel_btn.clicked.connect(dialog.reject)
                btn_layout.addWidget(cancel_btn)

                select_btn = QPushButton("Assign Camera")
                select_btn.setStyleSheet(self.get_button_style("#4CAF50", "#388E3C"))
                select_btn.clicked.connect(dialog.accept)
                btn_layout.addWidget(select_btn)
                layout.addLayout(btn_layout)

                try:
                    if dialog.exec() == QDialog.Accepted:
                        selected_id = camera_list.currentData()
                        selected_cam = next((cam for cam in found_cameras if cam["id"] == selected_id), None)
                        if selected_cam:
                            camera_path = selected_cam["path"]
                            target = assign_group.checkedId()
                            if target == 0:
                                self.cam_front_edit.setText(camera_path)
                                self._apply_camera_assignment_to_config("front", camera_path)
                                self.camera_front_status = "online"
                                if self.camera_front_circle:
                                    self.update_status_circle(self.camera_front_circle, "online")
                                if self.device_manager:
                                    self.device_manager.update_camera_status("front", "online")
                                self.status_label.setText(f"✓ Assigned {camera_path} to Front Camera")
                            elif target == 1:
                                self.cam_wrist_edit.setText(camera_path)
                                self._apply_camera_assignment_to_config("wrist", camera_path)
                                self.camera_wrist_status = "online"
                                if self.camera_wrist_circle:
                                    self.update_status_circle(self.camera_wrist_circle, "online")
                                if self.device_manager:
                                    self.device_manager.update_camera_status("wrist", "online")
                                self.status_label.setText(f"✓ Assigned {camera_path} to Wrist L Camera")
                            else:
                                self.cam_wrist_right_edit.setText(camera_path)
                                self._apply_camera_assignment_to_config("wrist_right", camera_path)
                                self.camera_wrist_right_status = "online"
                                if self.camera_wrist_right_circle:
                                    self.update_status_circle(self.camera_wrist_right_circle, "online")
                                if self.device_manager:
                                    self.device_manager.update_camera_status("wrist_right", "online")
                                self.status_label.setText(f"✓ Assigned {camera_path} to Wrist R Camera")
                            self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")
                finally:
                    if preview_timer is not None:
                        preview_timer.stop()
                    for cam in found_cameras:
                        capture = cam.get("capture")
                        try:
                            if capture:
                                capture.release()
                        except Exception:
                            pass
        except Exception as exc:
            self.status_label.setText(f"❌ Error: {exc}")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")

    def _commit_camera_field(self, camera_name: str, widget: QLineEdit) -> None:
        self._apply_camera_assignment_to_config(camera_name, widget.text().strip())

    def _apply_camera_assignment_to_config(self, camera_name: str, index_or_path: str) -> None:
        if not hasattr(self, "_ensure_schema"):
            return
        config = self._ensure_schema()
        cameras = config.setdefault("cameras", {})
        camera_cfg = cameras.setdefault(camera_name, {})
        camera_cfg["index_or_path"] = index_or_path
        camera_cfg["width"] = self.cam_width_spin.value()
        camera_cfg["height"] = self.cam_height_spin.value()
        camera_cfg["fps"] = self.cam_fps_spin.value()

        if getattr(self, "device_manager", None):
            self.device_manager.config = config

    def _candidate_camera_sources(self):
        candidates = []
        if self.device_manager and hasattr(self.device_manager, "scan_available_cameras"):
            try:
                for info in self.device_manager.scan_available_cameras():
                    index = info.get("index")
                    path = info.get("path") or (f"/dev/video{index}" if index is not None else "")
                    candidates.append((index, path))
            except Exception:
                candidates = []
        if not candidates:
            is_linux = sys.platform.startswith("linux")
            for i in range(10):
                path = f"/dev/video{i}"
                if is_linux and not Path(path).exists():
                    continue
                candidates.append((i, path))
        return candidates

    def _discover_cameras_for_dialog(self):
        if cv2 is None:
            return []

        backend_flag = getattr(cv2, "CAP_V4L2", None)
        found = []
        seen_ids = set()
        for index, path in self._candidate_camera_sources():
            cam_id = index if index is not None else path
            if cam_id in seen_ids:
                continue
            seen_ids.add(cam_id)
            source = index if index is not None else path
            if source in (None, ""):
                continue
            try:
                cap = cv2.VideoCapture(source, backend_flag) if backend_flag is not None else cv2.VideoCapture(source)
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret:
                        height, width = frame.shape[:2]
                        found.append(
                            {
                                "id": cam_id,
                                "index": index,
                                "path": path or str(source),
                                "resolution": f"{width}x{height}",
                                "capture": cap,
                            }
                        )
                        continue
                cap.release()
            except Exception:
                pass
        return found
