"""Camera preview helpers for the dashboard tab."""

from __future__ import annotations

from typing import Dict, List, Optional

try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    cv2 = None
    np = None

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from .constants import ROOT
from .widgets import CameraDetailDialog

CAMERA_DISPLAY_OVERRIDES = {
    "wrist": "Wrist L",
    "wrist_l": "Wrist L",
    "wrist_left": "Wrist L",
    "wrist_right": "Wrist R",
    "wrist_r": "Wrist R",
}


class DashboardCameraMixin:
    """Mixin containing camera preview utilities for :class:`DashboardTab`."""

    def _camera_display_name(self, camera_name: str) -> str:
        key = (camera_name or "").lower()
        if key in CAMERA_DISPLAY_OVERRIDES:
            return CAMERA_DISPLAY_OVERRIDES[key]
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
                import json

                with open(manifest_path, "r") as handle:
                    manifest = json.load(handle)
            except Exception:
                continue

            for step in manifest.get("steps", []):
                if step.get("step_type") != "vision":
                    continue

                camera_name = self._match_camera_name(step.get("camera", {}))
                if not camera_name:
                    continue

                trigger = step.get("trigger", {})
                settings = trigger.get("settings", {})
                threshold = float(settings.get("threshold", 0.55))
                invert = bool(settings.get("invert", False))
                metric = settings.get("metric", "intensity")

                for zone in trigger.get("zones", []):
                    polygon = zone.get("polygon", [])
                    if not polygon:
                        continue
                    zones_map.setdefault(camera_name, []).append(
                        {
                            "polygon": polygon,
                            "threshold": threshold,
                            "invert": invert,
                            "metric": metric,
                        }
                    )
        return zones_map

    def _normalize_camera_identifier(self, identifier) -> str:
        if isinstance(identifier, int):
            return str(identifier)
        if isinstance(identifier, str):
            stripped = identifier.strip()
            if stripped.startswith("/dev/video") and stripped[10:].isdigit():
                return stripped[10:]
            if stripped.startswith("camera:"):
                return stripped.split(":", 1)[-1]
            if stripped.isdigit():
                return stripped
            return stripped
        return str(identifier)

    def _match_camera_name(self, camera_info: dict) -> Optional[str]:
        if not camera_info:
            return None

        source_id = str(camera_info.get("source_id", ""))
        index = camera_info.get("index")
        normalized_source = self._normalize_camera_identifier(source_id) if source_id else None
        normalized_index = str(index) if index is not None else None

        for name, cfg in self.config.get("cameras", {}).items():
            identifier = cfg.get("index_or_path", 0)
            norm_identifier = self._normalize_camera_identifier(identifier)
            if normalized_source and norm_identifier == normalized_source:
                return name
            if normalized_index and norm_identifier == normalized_index:
                return name
            if source_id and str(identifier) == source_id:
                return name
        return None

    def _polygon_to_pixels(self, polygon: List[List[float]], width: int, height: int) -> "np.ndarray":
        if np is None:
            return np.zeros((0, 2), dtype=np.int32)

        pts = []
        for point in polygon:
            if len(point) != 2:
                continue
            x, y = point
            if isinstance(x, float) and isinstance(y, float) and 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
                px = int(round(x * (width - 1)))
                py = int(round(y * (height - 1)))
            else:
                px = int(round(float(x)))
                py = int(round(float(y)))
            pts.append([px, py])
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
            if pts.size == 0:
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

        if not force and timestamp <= getattr(self, "_last_preview_timestamp", 0.0):
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
        if cv2 is None:
            self._append_log_entry(
                "warning",
                "Camera preview is unavailable on this station. Install the camera viewer add-on to enable live video.",
                code="camera_preview_unavailable",
            )
            return

        camera_cfg = self.config.get("cameras", {}).get(camera_name)
        if not camera_cfg:
            return
        zones = self.active_vision_zones.get(camera_name) or self.vision_zones.get(camera_name, [])

        dialog = CameraDetailDialog(
            camera_name,
            camera_cfg,
            zones,
            self._render_camera_frame,
            self.camera_hub,
            parent=self,
        )
        dialog.exec()
