"""Reusable status header with robot/camera indicators and preview."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tabs.dashboard_tab.widgets import CircularProgress, StatusIndicator, CameraPreviewWidget


class CameraPopup(QDialog):
    """Simple camera popup with a preview placeholder and close button."""

    def __init__(self, parent: Optional[QWidget] = None, preview: Optional[CameraPreviewWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Cameras")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        if preview:
            layout.addWidget(preview)
        else:
            lbl = QLabel("Camera preview unavailable.")
            lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(lbl)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class StatusHeader(QWidget):
    """Status header widget reusable across tabs."""

    def __init__(self, model_name: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._model_name = model_name
        self._build_ui()

    def _build_ui(self):
        bar = QHBoxLayout(self)
        bar.setSpacing(12)
        bar.setContentsMargins(0, 0, 0, 0)

        self.throbber = CircularProgress()
        bar.addWidget(self.throbber)

        robot_group = QHBoxLayout()
        robot_group.setSpacing(6)
        robot_label = QLabel("Robot")
        robot_label.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        robot_group.addWidget(robot_label)
        self.robot_indicator1 = StatusIndicator()
        self.robot_indicator2 = StatusIndicator()
        for ind in (self.robot_indicator1, self.robot_indicator2):
            ind.set_null()
            robot_group.addWidget(ind)
        bar.addLayout(robot_group)

        cam_group = QHBoxLayout()
        cam_group.setSpacing(6)
        cam_label = QLabel("Cameras")
        cam_label.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        cam_group.addWidget(cam_label)
        self.camera_indicator1 = StatusIndicator()
        self.camera_indicator2 = StatusIndicator()
        self.camera_indicator3 = StatusIndicator()
        for ind in (self.camera_indicator1, self.camera_indicator2, self.camera_indicator3):
            ind.set_null()
            cam_group.addWidget(ind)
        bar.addLayout(cam_group)

        model_label = QLabel("Model:")
        model_label.setStyleSheet("color: #a0a0a0; font-size: 12px; font-weight: bold;")
        bar.addWidget(model_label)
        self.model_value = QLabel(self._model_name)
        self.model_value.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: bold;")
        bar.addWidget(self.model_value)

        bar.addStretch(1)

        # Camera preview frame with button
        cam_frame = QFrame()
        cam_frame.setStyleSheet("QFrame { border: 1px solid #404040; border-radius: 8px; background-color: #1a1a1a; }")
        cam_layout = QVBoxLayout(cam_frame)
        cam_layout.setContentsMargins(8, 8, 8, 8)
        cam_layout.setSpacing(6)

        header_row = QHBoxLayout()
        cam_title = QLabel("Camera Preview")
        cam_title.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: bold;")
        header_row.addWidget(cam_title)
        header_row.addStretch()
        self.camera_popup_btn = QPushButton("Cameras")
        self.camera_popup_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #2f2f2f;
                color: #ffffff;
                border: 1px solid #505050;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #3a3a3a; }
            """
        )
        self.camera_popup_btn.clicked.connect(self._open_camera_popup)
        header_row.addWidget(self.camera_popup_btn)
        cam_layout.addLayout(header_row)

        self.camera_preview = CameraPreviewWidget()
        self.camera_preview.setFixedSize(200, 140)
        self.camera_preview.update_preview(None, "Preview unavailable")
        cam_layout.addWidget(self.camera_preview)

        bar.addWidget(cam_frame)

    # ------------------------------------------------------------------ Public API
    def set_model_name(self, name: str):
        self._model_name = name
        self.model_value.setText(name)

    def set_robot_status(self, statuses: List[bool]):
        inds = [self.robot_indicator1, self.robot_indicator2]
        for idx, ind in enumerate(inds):
            if ind is None:
                continue
            if idx < len(statuses) and statuses[idx]:
                ind.set_connected(True)
            else:
                ind.set_null()

    def set_camera_status(self, statuses: List[bool]):
        inds = [self.camera_indicator1, self.camera_indicator2, self.camera_indicator3]
        for idx, ind in enumerate(inds):
            if ind is None:
                continue
            if idx < len(statuses) and statuses[idx]:
                ind.set_connected(True)
            else:
                ind.set_null()

    def set_status_text(self, text: str):
        # Caller can add their own status label below; provided for completeness.
        pass

    def set_camera_preview_message(self, message: str):
        self.camera_preview.update_preview(None, message)

    # ------------------------------------------------------------------ Internals
    def _open_camera_popup(self):
        # Reuse the existing preview for consistency
        popup_preview = CameraPreviewWidget()
        popup_preview.setFixedSize(320, 240)
        popup_preview.update_preview(None, "Camera preview unavailable")
        dialog = CameraPopup(self, popup_preview)
        dialog.exec()
