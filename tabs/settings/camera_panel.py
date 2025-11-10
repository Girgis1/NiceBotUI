"""Camera panel helpers for the Settings tab."""

from __future__ import annotations

from typing import Optional

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


class CameraPanelMixin:
    """Encapsulates camera UI wiring and discovery helpers."""

    camera_front_circle: Optional[QLabel]  # Provided at runtime
    camera_wrist_circle: Optional[QLabel]
    camera_extra_circle: Optional[QLabel]
    extra_camera_label: Optional[QLabel]

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

        self.find_cameras_btn = QPushButton("🔍 Find Cameras")
        self.find_cameras_btn.setFixedHeight(45)
        self.find_cameras_btn.setFixedWidth(140)
        self.find_cameras_btn.setStyleSheet(self.get_button_style("#FF9800", "#F57C00"))
        self.find_cameras_btn.clicked.connect(self.find_cameras)
        front_row.addWidget(self.find_cameras_btn)
        front_row.addStretch()
        layout.addLayout(front_row)

        wrist_row = QHBoxLayout()
        wrist_row.setSpacing(6)
        self.camera_wrist_circle = self.create_status_circle("empty")
        wrist_row.addWidget(self.camera_wrist_circle)

        wrist_label = QLabel("Wrist:")
        wrist_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        wrist_label.setFixedWidth(55)
        wrist_row.addWidget(wrist_label)

        self.cam_wrist_edit = QLineEdit("/dev/video3")
        self.cam_wrist_edit.setFixedHeight(45)
        self.cam_wrist_edit.setStyleSheet(self._camera_lineedit_style())
        wrist_row.addWidget(self.cam_wrist_edit)
        wrist_row.addSpacing(12)
        wrist_row.addStretch()
        layout.addLayout(wrist_row)

        extra_row = QHBoxLayout()
        extra_row.setSpacing(6)
        self.camera_extra_circle = self.create_status_circle("empty")
        extra_row.addWidget(self.camera_extra_circle)

        self.extra_camera_label = QLabel("Aux:")
        self.extra_camera_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        self.extra_camera_label.setFixedWidth(55)
        extra_row.addWidget(self.extra_camera_label)

        self.cam_extra_edit = QLineEdit("")
        self.cam_extra_edit.setFixedHeight(45)
        self.cam_extra_edit.setStyleSheet(self._camera_lineedit_style())
        self.cam_extra_edit.setPlaceholderText("Optional camera path")
        extra_row.addWidget(self.cam_extra_edit)
        extra_row.addSpacing(12)
        extra_row.addStretch()
        layout.addLayout(extra_row)

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

    def _format_camera_label(self, name: Optional[str]) -> str:
        if not name:
            return "Aux"
        return name.replace("_", " ").title()

    def find_cameras(self):
        """Scan for available cameras and allow the user to assign them."""
        if cv2 is None:
            self.status_label.setText("❌ OpenCV is required for camera discovery")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
            return

        try:
            self.status_label.setText("⏳ Scanning for cameras...")
            self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")

            found_cameras = []
            for i in range(10):
                try:
                    cap = cv2.VideoCapture(i)
                    if cap.isOpened():
                        ret, frame = cap.read()
                        if ret:
                            height, width = frame.shape[:2]
                            found_cameras.append({
                                "index": i,
                                "path": f"/dev/video{i}",
                                "resolution": f"{width}x{height}",
                                "capture": cap,
                            })
                        else:
                            cap.release()
                    else:
                        cap.release()
                except Exception:
                    pass

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
                camera_list.addItem(f"{cam['path']} - {cam['resolution']}", cam["index"])
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

            wrist_radio = QRadioButton("Wrist Camera")
            wrist_radio.setStyleSheet("QRadioButton { color: #e0e0e0; font-size: 14px; padding: 5px; }")
            assign_group.addButton(wrist_radio, 1)
            layout.addWidget(wrist_radio)

            extra_label = self._format_camera_label(getattr(self, "extra_camera_key", "aux"))
            extra_radio = QRadioButton(f"{extra_label} Camera")
            extra_radio.setStyleSheet("QRadioButton { color: #e0e0e0; font-size: 14px; padding: 5px; }")
            assign_group.addButton(extra_radio, 2)
            layout.addWidget(extra_radio)

            def update_preview():
                try:
                    selected_idx = camera_list.currentData()
                    for cam in found_cameras:
                        if cam["index"] == selected_idx:
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
            preview_timer.start(100)

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

            if dialog.exec() == QDialog.Accepted:
                selected_idx = camera_list.currentData()
                selected_cam = next((cam for cam in found_cameras if cam["index"] == selected_idx), None)
                if selected_cam:
                    camera_path = selected_cam["path"]
                    target = assign_group.checkedId()
                    if target == 0:
                        self.cam_front_edit.setText(camera_path)
                        self.camera_front_status = "online"
                        if self.camera_front_circle:
                            self.update_status_circle(self.camera_front_circle, "online")
                        if self.device_manager:
                            self.device_manager.update_camera_status("front", "online")
                        self.status_label.setText(f"✓ Assigned {camera_path} to Front Camera")
                    elif target == 1:
                        self.cam_wrist_edit.setText(camera_path)
                        self.camera_wrist_status = "online"
                        if self.camera_wrist_circle:
                            self.update_status_circle(self.camera_wrist_circle, "online")
                        if self.device_manager:
                            self.device_manager.update_camera_status("wrist", "online")
                        self.status_label.setText(f"✓ Assigned {camera_path} to Wrist Camera")
                    else:
                        self.cam_extra_edit.setText(camera_path)
                        self.camera_extra_status = "online"
                        if self.camera_extra_circle:
                            self.update_status_circle(self.camera_extra_circle, "online")
                        extra_key = getattr(self, "extra_camera_key", "aux") or "aux"
                        if self.device_manager:
                            self.device_manager.update_camera_status(extra_key, "online")
                        label = self._format_camera_label(extra_key)
                        self.status_label.setText(f"✓ Assigned {camera_path} to {label} Camera")
                    self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")

            preview_timer.stop()
            for cam in found_cameras:
                cam["capture"].release()
        except Exception as exc:
            self.status_label.setText(f"❌ Error: {exc}")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
