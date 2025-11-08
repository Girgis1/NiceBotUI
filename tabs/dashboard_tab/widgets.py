"""Reusable widgets for the dashboard tab."""

from __future__ import annotations

from typing import List, Optional

try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    cv2 = None
    np = None

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from utils.camera_hub import CameraStreamHub


class CircularProgress(QWidget):
    """Circular progress indicator."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.progress = 0
        self.setFixedSize(24, 24)
        self.setVisible(True)  # Always visible

    def set_progress(self, value: int) -> None:
        self.progress = value
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        pen = QPen(QColor("#555555"), 2)
        painter.setPen(pen)
        painter.setBrush(QColor("#2d2d2d"))
        painter.drawEllipse(2, 2, 20, 20)

        if self.progress > 0:
            pen = QPen(QColor("#4CAF50"), 3)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)

            start_angle = -90 * 16
            span_angle = -(self.progress * 360 // 100) * 16

            painter.drawArc(3, 3, 18, 18, start_angle, span_angle)


class StatusIndicator(QLabel):
    """Colored dot indicator."""

    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.connected = False
        self.warning = False
        self.null = False  # Initialize null attribute
        self.update_style()

    def set_connected(self, connected: bool) -> None:
        self.connected = connected
        self.warning = False
        self.null = False  # Clear null state when setting connected
        self.update_style()

    def set_warning(self) -> None:
        self.connected = False
        self.warning = True
        self.null = False  # Clear null state when setting warning
        self.update_style()

    def set_null(self) -> None:
        """Set as null/empty indicator."""

        self.connected = False
        self.warning = False
        self.null = True
        self.update_style()

    def update_style(self) -> None:
        if getattr(self, "null", False):
            # Null indicator - unfilled black circle
            self.setFixedSize(20, 20)
            self.setStyleSheet(
                """
                QLabel {
                    background-color: transparent;
                    border: 2px solid #606060;
                    border-radius: 10px;
                }
                """
            )
        elif self.warning:
            color = "#FF9800"
            self.setFixedSize(20, 20)
            self.setStyleSheet(
                f"""
                QLabel {{
                    background-color: {color};
                    border-radius: 10px;
                }}
                """
            )
        elif self.connected:
            color = "#2e7d32"
            self.setFixedSize(20, 20)
            self.setStyleSheet(
                f"""
                QLabel {{
                    background-color: {color};
                    border-radius: 10px;
                }}
                """
            )
        else:
            self.setFixedSize(20, 20)
            self.setStyleSheet(
                """
                QLabel {
                    background-color: #404040;
                    border-radius: 10px;
                }
                """
            )


class CameraPreviewWidget(QFrame):
    """Single camera preview with overlay-ready QLabel."""

    clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("singleCameraPreview")
        self.setStyleSheet(
            """
            #singleCameraPreview {
                border: 1px solid #404040;
                border-radius: 8px;
                background-color: #151515;
            }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.header_row = QHBoxLayout()
        self.header_row.setContentsMargins(0, 0, 0, 0)
        self.header_row.setSpacing(8)

        self.camera_label = QLabel("Camera")
        self.camera_label.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: bold;")
        self.header_row.addWidget(self.camera_label)
        self.header_row.addStretch()

        self.status_chip = QLabel("")
        self.status_chip.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status_chip.setStyleSheet(
            "color: #a0a0a0; font-size: 11px; padding: 2px 6px; border-radius: 4px; background-color: #2b2b2b;"
        )
        self.status_chip.hide()
        self.header_row.addWidget(self.status_chip)

        layout.addLayout(self.header_row)

        self.preview_label = QLabel("Camera preview disabled")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("color: #777777; font-size: 12px;")
        self.preview_label.setScaledContents(True)
        self.preview_label.setMinimumSize(320, 200)
        layout.addWidget(self.preview_label, stretch=1)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def update_preview(
        self, pixmap: Optional[QPixmap], message: Optional[str] = None, status: Optional[str] = None
    ) -> None:
        if status:
            self.status_chip.setText(status)
            self.status_chip.show()
        else:
            self.status_chip.hide()

        if pixmap is None:
            if message:
                self.preview_label.setText(message)
            else:
                self.preview_label.setText("No camera feed")
            self.preview_label.setPixmap(QPixmap())
        else:
            self.preview_label.setPixmap(pixmap)
            self.preview_label.setText("")

    def set_camera_name(self, name: str) -> None:
        self.camera_label.setText(name)


class CameraDetailDialog(QDialog):
    """Large detailed camera preview in a dialog powered by the camera hub."""

    def __init__(
        self,
        camera_name: str,
        camera_config: dict,
        vision_zones: List[dict],
        render_callback,
        camera_hub: Optional[CameraStreamHub],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.camera_name = camera_name
        self.camera_config = camera_config
        self.vision_zones = vision_zones
        self.render_callback = render_callback
        self.camera_hub = camera_hub

        self.setWindowTitle(f"Camera Preview - {camera_name}")
        self.setModal(True)
        self.resize(900, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        self.preview_label = QLabel("Initializing camera…")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("color: #f0f0f0; font-size: 14px;")
        self.preview_label.setMinimumSize(640, 360)
        self.preview_label.setScaledContents(True)
        layout.addWidget(self.preview_label, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #f0f0f0; font-size: 12px;")
        layout.addWidget(self.status_label)

        self.timer = QTimer(self)
        self.timer.setInterval(70)  # ~14 FPS
        self.timer.timeout.connect(self._update_frame)
        self.timer.start()

    def _update_frame(self) -> None:
        if cv2 is None or np is None:
            self.status_label.setText("OpenCV/NumPy missing. Install dependencies.")
            return
        if not self.camera_hub:
            self.status_label.setText("Camera hub unavailable.")
            self.preview_label.setText("No shared camera stream.")
            return

        frame = self.camera_hub.get_frame(self.camera_name, preview=False)
        if frame is None:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("Camera offline.")
            self.status_label.setText("No frames available.")
            return

        render_frame, status = self.render_callback(self.camera_name, frame.copy(), self.vision_zones)
        rgb = cv2.cvtColor(render_frame, cv2.COLOR_BGR2RGB)
        height, width, channel = rgb.shape
        image = QImage(rgb.data, width, height, channel * width, QImage.Format_RGB888)
        self.preview_label.setPixmap(QPixmap.fromImage(image))
        status_text = {
            "triggered": "Active detection",
            "idle": "Monitoring",
            "nominal": "Live preview",
            "offline": "Offline",
            "no_vision": "No vision zones configured",
        }
        self.status_label.setText(status_text.get(status, ""))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.timer.stop()
        super().closeEvent(event)
