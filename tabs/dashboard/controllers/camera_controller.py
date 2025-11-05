"""
Camera Controller - Manages camera operations and vision processing

Handles camera cycling, preview management, vision zone processing,
and camera hub interactions for the dashboard.
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import json

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtGui import QPixmap

try:
    from utils.camera_hub import CameraStreamHub
except ImportError:
    CameraStreamHub = None

try:
    from vision_ui.designer import _normalized_polygon_to_pixels, _pixels_to_normalized
except ImportError:
    _normalized_polygon_to_pixels = None
    _pixels_to_normalized = None

# Import from our new modules
try:
    from ..widgets.camera_preview import CameraDetailDialog
except ImportError:
    CameraDetailDialog = None


class CameraController(QObject):
    """Manages camera operations and vision processing"""

    # Signals for UI updates
    camera_mode_changed = Signal(bool)  # (active)
    active_camera_changed = Signal(str)  # camera_name
    camera_preview_updated = Signal(str, QPixmap, str)  # (camera_name, pixmap, status)
    camera_detail_requested = Signal(str)  # camera_name
    log_entry_needed = Signal(str, str, dict)  # (level, message, metadata)

    def __init__(self, config: Dict[str, Any], camera_hub: Optional[CameraStreamHub] = None):
        super().__init__()
        self.config = config
        self.camera_hub = camera_hub

        # Camera state
        self.camera_order: List[str] = []
        self.active_camera_index = 0
        self.active_camera_name: Optional[str] = None
        self.camera_view_active = False
        self._last_preview_timestamp = 0.0

        # Vision data
        self.vision_zones: Dict[str, List[dict]] = {}
        self.active_vision_zones: Dict[str, List[dict]] = {}

        # Camera preview timer
        self.camera_preview_timer = QTimer(self)
        self.camera_preview_timer.timeout.connect(self.update_camera_previews)
        self.camera_preview_timer.setInterval(300)  # ~3 FPS for preview

    def initialize_cameras(self, camera_order: List[str]):
        """Initialize camera configuration"""
        self.camera_order = camera_order or []
        if self.camera_order:
            self.active_camera_name = self.camera_order[0]
            self.active_camera_index = 0

        # Load vision zones
        self._load_vision_zones()

    def cycle_active_camera(self):
        """Cycle to the next camera in the order"""
        if not self.camera_order:
            return

        self.active_camera_index = (self.active_camera_index + 1) % len(self.camera_order)
        self.active_camera_name = self.camera_order[self.active_camera_index]
        self._last_preview_timestamp = 0.0
        self.active_camera_changed.emit(self.active_camera_name)
        self.update_camera_previews(force=True)

    def enter_camera_mode(self) -> bool:
        """Enter camera preview mode"""
        if self.camera_view_active:
            return True

        if cv2 is None:
            self._log("warning", "Camera preview is unavailable on this station. Install the camera viewer add-on to enable live video.", code="camera_preview_unavailable")
            return False

        self.camera_view_active = True
        self.camera_preview_timer.start(300)
        self.update_camera_previews(force=True)
        self.camera_mode_changed.emit(True)
        return True

    def exit_camera_mode(self):
        """Exit camera preview mode"""
        if not self.camera_view_active:
            return

        self.camera_view_active = False
        self.camera_preview_timer.stop()
        self.camera_mode_changed.emit(False)

    def close_camera_panel(self):
        """Close camera panel and reset state"""
        self.exit_camera_mode()

    def update_camera_previews(self, force: bool = False):
        """Update camera previews for active camera"""
        if not self.camera_view_active or cv2 is None or np is None:
            return

        if not self.active_camera_name:
            self.camera_preview_updated.emit("", QPixmap(), "No camera configured.")
            return

        if not self.camera_hub:
            self.camera_preview_updated.emit(self.active_camera_name, QPixmap(), "Camera hub unavailable.")
            return

        frame, timestamp = self.camera_hub.get_frame_with_timestamp(self.active_camera_name, preview=True)
        if frame is None:
            self.camera_preview_updated.emit(self.active_camera_name, QPixmap(), "Camera offline.")
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

        self.camera_preview_updated.emit(self.active_camera_name, pixmap, status_text)
        self._last_preview_timestamp = timestamp

    def open_camera_detail(self, camera_name: str):
        """Open detailed camera preview dialog"""
        camera_cfg = self.config.get("cameras", {}).get(camera_name)
        if not camera_cfg or not CameraDetailDialog:
            return

        zones = self.active_vision_zones.get(camera_name) or self.vision_zones.get(camera_name, [])
        dialog = CameraDetailDialog(
            camera_name, camera_cfg, zones, self._render_camera_frame, self.camera_hub
        )
        dialog.exec()

    def _load_vision_zones(self) -> Dict[str, List[dict]]:
        """Load vision zones from sequence configurations"""
        zones_map: Dict[str, List[dict]] = {}
        sequences_dir = Path(__file__).parent.parent.parent / "data" / "sequences"
        if not sequences_dir.exists():
            return zones_map

        for manifest_path in sequences_dir.glob("*/manifest.json"):
            try:
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
                    zones_map.setdefault(camera_name, []).append({
                        "polygon": polygon,
                        "threshold": threshold,
                        "invert": invert,
                        "metric": metric
                    })

        self.vision_zones = zones_map
        return zones_map

    def _normalize_camera_identifier(self, identifier) -> str:
        """Normalize camera identifier to string"""
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
        """Match camera info to configured camera name"""
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
        """Convert normalized polygon to pixel coordinates"""
        if np is None or _normalized_polygon_to_pixels is None:
            return np.zeros((0, 2), dtype=np.int32) if np else None

        return _normalized_polygon_to_pixels(polygon, width, height)

    def _evaluate_metric(self, frame, gray, mask, metric_type: str) -> float:
        """Evaluate vision metric for a masked region"""
        if cv2 is None or np is None:
            return 0.0

        try:
            if metric_type == "intensity":
                mean_val = cv2.mean(gray, mask=mask)[0]
                return mean_val / 255.0
            elif metric_type == "edges":
                edges = cv2.Canny(gray, 100, 200)
                edge_pixels = cv2.bitwise_and(edges, edges, mask=mask)
                return np.sum(edge_pixels > 0) / np.sum(mask > 0) if np.sum(mask > 0) > 0 else 0.0
            else:
                return cv2.mean(gray, mask=mask)[0] / 255.0
        except:
            return 0.0

    def _render_camera_frame(self, camera_name: str, frame, zones: Optional[List[dict]] = None):
        """Render camera frame with vision zones overlay"""
        if cv2 is None or np is None:
            return frame, "offline"

        height, width = frame.shape[:2]
        render_frame = frame.copy()

        if not zones:
            return render_frame, "nominal"

        triggered = False
        for zone in zones:
            polygon = zone.get("polygon", [])
            if not polygon:
                continue

            # Convert to pixels
            pixel_polygon = self._polygon_to_pixels(polygon, width, height)
            if pixel_polygon is None or len(pixel_polygon) == 0:
                continue

            # Create mask
            mask = np.zeros((height, width), dtype=np.uint8)
            cv2.fillPoly(mask, [pixel_polygon.astype(np.int32)], 255)

            # Evaluate metric
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) > 2 else frame
            metric_value = self._evaluate_metric(frame, gray, mask, zone.get("metric", "intensity"))

            threshold = zone.get("threshold", 0.5)
            invert = zone.get("invert", False)

            condition_met = (metric_value > threshold) if not invert else (metric_value < threshold)
            if condition_met:
                triggered = True
                color = (0, 0, 255)  # Red for triggered
            else:
                color = (0, 255, 0)  # Green for monitoring

            # Draw zone outline
            cv2.polylines(render_frame, [pixel_polygon.astype(np.int32)], True, color, 2)

        status = "triggered" if triggered else "idle"
        return render_frame, status

    def _frame_to_pixmap(self, frame: "np.ndarray") -> QPixmap:
        """Convert frame to QPixmap for display"""
        if frame is None or cv2 is None:
            return QPixmap()

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channel = rgb.shape
        image = QPixmap.fromImage(
            QImage(rgb.data, width, height, channel * width, QImage.Format_RGB888)
        )
        return image

    def _get_preview_zones(self, camera_name: str) -> List[dict]:
        """Get zones for camera preview"""
        return self.active_vision_zones.get(camera_name) or self.vision_zones.get(camera_name, [])

    def _camera_display_name(self, camera_name: str) -> str:
        """Get display name for camera"""
        display_names = {
            "front": "Front Camera",
            "wrist": "Wrist Camera",
        }
        return display_names.get(camera_name, f"Camera {camera_name}")

    def _refresh_active_camera_label(self):
        """Refresh the active camera display label"""
        if self.active_camera_name:
            display_name = self._camera_display_name(self.active_camera_name)
            self.active_camera_changed.emit(display_name)

    def _log(self, level: str, message: str, action: str = "", code: str = "") -> None:
        """Emit log entry signal"""
        metadata = {}
        if action:
            metadata["action"] = action
        if code:
            metadata["code"] = code
        self.log_entry_needed.emit(level, message, metadata)
