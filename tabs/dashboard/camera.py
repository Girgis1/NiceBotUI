"""Camera handling utilities and mixins for the dashboard tab."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

try:  # pragma: no cover - optional dependency
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    cv2 = None  # type: ignore
    np = None  # type: ignore

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QVBoxLayout

from utils.camera_hub import CameraStreamHub

ROOT = Path(__file__).resolve().parents[2]


class CameraPreviewWidget(QFrame):
    """Single camera preview with overlay-ready QLabel."""

    clicked = Signal()

    def __init__(self, parent=None):
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

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
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
        parent=None,
    ):
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

        from PySide6.QtCore import QTimer  # Imported lazily to avoid circular import

        self.timer = QTimer(self)
        self.timer.setInterval(70)
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

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.timer.stop()
        super().closeEvent(event)


class DashboardCameraMixin:
    """Mixin encapsulating camera preview logic."""

    def _camera_display_name(self, camera_name: str) -> str:
        return camera_name.replace("_", " ").title()

    def _refresh_active_camera_label(self) -> None:
        if not self.single_camera_preview:
            return

        if not self.camera_order:
            self.active_camera_name = None
            self.single_camera_preview.set_camera_name("No cameras")
            self.single_camera_preview.update_preview(None, "Configure cameras in Settings.")
            self.camera_cycle_btn.setEnabled(False)
            return

        if self.active_camera_name not in self.camera_order:
            self.active_camera_index = 0
            self.active_camera_name = self.camera_order[0]
            self._last_preview_timestamp = 0.0

        display = self._camera_display_name(self.active_camera_name)
        self.single_camera_preview.set_camera_name(display)
        self.camera_cycle_btn.setEnabled(len(self.camera_order) > 1)

    def cycle_active_camera(self) -> None:
        if not self.camera_order:
            return
        self.active_camera_index = (self.active_camera_index + 1) % len(self.camera_order)
        self.active_camera_name = self.camera_order[self.active_camera_index]
        self._last_preview_timestamp = 0.0
        self._refresh_active_camera_label()
        self.update_camera_previews(force=True)

    def on_camera_toggle(self, checked: bool) -> None:
        self.camera_toggle_btn.setText("✕" if checked else "Cameras")
        if checked:
            self.camera_toggle_btn.setMinimumWidth(85)
            self.camera_toggle_btn.setMaximumWidth(85)
        else:
            self.camera_toggle_btn.setMinimumWidth(self._camera_toggle_default_width)
            self.camera_toggle_btn.setMaximumWidth(self._camera_toggle_default_width)
        if checked:
            self.enter_camera_mode()
        else:
            self.exit_camera_mode()

    def enter_camera_mode(self) -> None:
        if self.camera_view_active:
            return
        if cv2 is None:
            self._append_log_entry(
                "warning",
                "Camera preview is unavailable on this station. Install the camera viewer add-on to enable live video.",
                code="camera_preview_unavailable",
            )
            self.camera_toggle_btn.blockSignals(True)
            self.camera_toggle_btn.setChecked(False)
            self.camera_toggle_btn.blockSignals(False)
            self.camera_toggle_btn.setMinimumWidth(self._camera_toggle_default_width)
            self.camera_toggle_btn.setMaximumWidth(self._camera_toggle_default_width)
            return

        self.normal_status_container.hide()
        self.status_summary_container.show()
        self.time_label.hide()
        self.run_label.hide()

        self._refresh_active_camera_label()
        self.camera_panel.setVisible(True)
        if not self.camera_order or not self.active_camera_name:
            self.camera_view_active = False
            self.single_camera_preview.update_preview(None, "No camera configured.")
            return

        self.camera_view_active = True
        self.camera_preview_timer.start(300)
        self.update_camera_previews(force=True)

    def exit_camera_mode(self) -> None:
        if not self.camera_view_active:
            return

        self.status_summary_container.hide()
        self.normal_status_container.show()
        self.time_label.show()
        self.run_label.show()
        self.camera_toggle_btn.setMinimumWidth(self._camera_toggle_default_width)
        self.camera_toggle_btn.setMaximumWidth(self._camera_toggle_default_width)

        self.camera_view_active = False
        self.camera_preview_timer.stop()
        self.camera_panel.setVisible(False)
        self.single_camera_preview.update_preview(None, "Preview closed.")

    def close_camera_panel(self) -> None:
        if self.camera_toggle_btn.isChecked():
            self.camera_toggle_btn.setChecked(False)
        elif self.camera_view_active:
            self.exit_camera_mode()

    def _load_vision_zones(self) -> Dict[str, List[dict]]:
        zones_map: Dict[str, List[dict]] = {}
        sequences_dir = ROOT / "data" / "sequences"
        if not sequences_dir.exists():
            return zones_map

        for manifest_path in sequences_dir.glob("*/manifest.json"):
            try:
                with open(manifest_path, "r", encoding="utf-8") as handle:
                    manifest = json.load(handle)
            except Exception:
                continue

            for step in manifest.get("steps", []):
                if step.get("step_type") != "vision":
                    continue

                camera_name = self._match_camera_name(step.get("camera", {}))
                if not camera_name:
                    continue

                zones_map.setdefault(camera_name, []).append(step)
        return zones_map

    def _normalize_camera_identifier(self, identifier) -> str:
        if isinstance(identifier, str):
            return identifier.lower()
        if isinstance(identifier, dict):
            return identifier.get("name", "").lower()
        return ""

    def _match_camera_name(self, camera_info: dict) -> Optional[str]:
        target = self._normalize_camera_identifier(camera_info)
        for name in self.camera_order:
            if self._normalize_camera_identifier(name) == target:
                return name
        return None

    def _polygon_to_pixels(self, polygon: List[List[float]], width: int, height: int):
        if cv2 is None or np is None:
            return np.array([], dtype=np.int32) if np is not None else []
        pts = []
        for point in polygon or []:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                continue
            px = int(float(point[0]) * width)
            py = int(float(point[1]) * height)
            pts.append((px, py))
        if not pts:
            return np.array([], dtype=np.int32)
        return np.array(pts, dtype=np.int32)

    def _evaluate_metric(self, frame, gray, mask, metric_type: str) -> float:
        if cv2 is None or np is None:
            return 0.0
        metric_type = (metric_type or "intensity").lower()
        if metric_type == "green_channel":
            return cv2.mean(frame[:, :, 1], mask=mask)[0] / 255.0
        if metric_type == "edge_density":
            edges = cv2.Canny(gray, 50, 150)
            masked_edges = cv2.bitwise_and(edges, edges, mask=mask)
            edge_pixels = np.count_nonzero(masked_edges)
            total_pixels = np.count_nonzero(mask)
            return edge_pixels / total_pixels if total_pixels else 0.0
        return cv2.mean(gray, mask=mask)[0] / 255.0

    def _render_camera_frame(self, camera_name: str, frame, zones: Optional[List[dict]] = None):
        if cv2 is None or np is None:
            return frame, "nominal"

        zones = zones if zones is not None else self.vision_zones.get(camera_name, [])
        if not zones:
            return frame, "nominal"

        height, width = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        triggered_any = False
        valid_zone = False

        for zone in zones:
            polygon = zone.get("polygon", [])
            pts = self._polygon_to_pixels(polygon, width, height)
            if pts is None or (hasattr(pts, "size") and pts.size == 0):
                continue
            valid_zone = True

            mask = np.zeros((height, width), dtype=np.uint8)
            cv2.fillPoly(mask, [pts], 255)

            metric = self._evaluate_metric(frame, gray, mask, zone.get("metric", "intensity"))
            threshold = float(zone.get("threshold", 0.5))
            invert = bool(zone.get("invert", False))
            triggered = metric <= threshold if invert else metric >= threshold
            if triggered:
                triggered_any = True

            color = (76, 175, 80) if triggered else (244, 67, 54)
            overlay = np.zeros_like(frame)
            cv2.fillPoly(overlay, [pts], color)
            frame = cv2.addWeighted(frame, 1.0, overlay, 0.28, 0)
            cv2.polylines(frame, [pts], True, color, 2, cv2.LINE_AA)

        if not valid_zone:
            return frame, "nominal"
        return frame, "triggered" if triggered_any else "idle"

    def _frame_to_pixmap(self, frame: "np.ndarray") -> QPixmap:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channel = rgb.shape
        image = QImage(rgb.data, width, height, channel * width, QImage.Format_RGB888)
        return QPixmap.fromImage(image)

    def _get_preview_zones(self, camera_name: str) -> List[dict]:
        zones = self.active_vision_zones.get(camera_name)
        if zones:
            return zones
        return []

    def update_camera_previews(self, force: bool = False) -> None:
        if not self.camera_view_active or cv2 is None or np is None:
            return

        if not self.active_camera_name:
            self.single_camera_preview.update_preview(None, "No camera configured.")
            return

        if not self.camera_hub:
            self.single_camera_preview.update_preview(None, "Camera hub unavailable.", status="Offline")
            return

        frame, timestamp = self.camera_hub.get_frame_with_timestamp(self.active_camera_name, preview=True)
        if frame is None:
            self.single_camera_preview.update_preview(None, "Camera offline.", status="Offline")
            return

        if not force and timestamp <= self._last_preview_timestamp:
            return

        zones = self._get_preview_zones(self.active_camera_name)
        render_frame, status = self._render_camera_frame(self.active_camera_name, frame.copy(), zones)
        pixmap = self._frame_to_pixmap(render_frame)
        status_text = {
            "triggered": "Triggered",
            "idle": "Watching",
            "nominal": "Live",
            "offline": "Offline",
            "no_vision": "No vision",
        }.get(status, "")
        self.single_camera_preview.update_preview(pixmap, status=status_text)
        self._last_preview_timestamp = timestamp

    def open_camera_detail(self, camera_name: str) -> None:
        camera_cfg = self.config.get("cameras", {}).get(camera_name)
        if not camera_cfg:
            return
        zones = self.active_vision_zones.get(camera_name) or self.vision_zones.get(camera_name, [])
        dialog = CameraDetailDialog(
            camera_name, camera_cfg, zones, self._render_camera_frame, self.camera_hub, self
        )
        dialog.exec()

    def on_camera_status_changed(self, camera_name: str, status: str) -> None:
        if camera_name == "front" and self.camera_front_circle:
            if status == "empty":
                self.camera_front_circle.set_null()
            elif status == "online":
                self.camera_front_circle.set_connected(True)
            else:
                self.camera_front_circle.set_connected(False)
        elif camera_name == "wrist" and self.camera_wrist_circle:
            if status == "empty":
                self.camera_wrist_circle.set_null()
            elif status == "online":
                self.camera_wrist_circle.set_connected(True)
            else:
                self.camera_wrist_circle.set_connected(False)
        elif self.camera_indicator3 and camera_name not in {"front", "wrist"}:
            if status == "empty":
                self.camera_indicator3.set_null()
            elif status == "online":
                self.camera_indicator3.set_connected(True)
            else:
                self.camera_indicator3.set_connected(False)

        self._camera_status[camera_name] = status
        self._update_status_summaries()

        if self.camera_view_active and camera_name == self.active_camera_name:
            self.update_camera_previews(force=True)


__all__ = [
    "CameraPreviewWidget",
    "CameraDetailDialog",
    "DashboardCameraMixin",
]
