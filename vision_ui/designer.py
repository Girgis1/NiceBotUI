"""
Modern vision trigger designer UI.

Provides a reusable widget/dialog for configuring camera-trigger pairs with
touch-friendly polygon editing and live preview feedback.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import platform
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Helpers and defaults


def create_default_vision_config() -> Dict:
    """Create a fresh default vision step configuration."""
    return {
        "type": "vision",
        "name": "Detection Zone",
        "camera": {
            "index": 0,
            "label": "Unassigned Camera",
            "resolution": [640, 480],
            "source_id": "camera:0",
            "config_key": None,
            "index_or_path": 0,
        },
        "trigger": {
            "display_name": "Detection Zone",
            "mode": "presence",
            "vision_type": "basic_detection",
            "settings": {
                "metric": "intensity",
                "threshold": 0.55,
                "invert": False,
                "hold_time": 0.0,
                "sensitivity": 0.6,
            },
            "zones": [],
            "idle_mode": {
                "enabled": False,
                "interval_seconds": 2.0,
            },
        },
    }


def _load_system_config() -> Dict:
    """Load the kiosk config (if available) to expose camera names."""
    root = Path(__file__).resolve().parent.parent
    config_path = root / "config.json"
    try:
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
    except Exception as exc:
        print(f"[VISION][WARN] Unable to load kiosk config: {exc}")
    return {}


def _generate_zone_name(existing: List[str]) -> str:
    base = "Zone"
    counter = 1
    while f"{base} {counter}" in existing:
        counter += 1
    return f"{base} {counter}"


def _normalize_color(color: str) -> str:
    if isinstance(color, str) and len(color) == 7 and color.startswith("#"):
        return color.upper()
    return "#33FF99"


def _uuid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _to_qimage(frame: np.ndarray) -> QImage:
    """Convert BGR OpenCV frame to QImage."""
    if frame is None:
        return QImage()
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    bytes_per_line = ch * w
    return QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()


def _normalized_polygon_to_pixels(polygon: List[Tuple[float, float]], width: int, height: int) -> np.ndarray:
    """Convert a normalized polygon to integer pixel coordinates."""
    if not polygon:
        return np.zeros((0, 2), dtype=np.int32)
    pts = []
    for x, y in polygon:
        px = int(_clamp(x) * width)
        py = int(_clamp(y) * height)
        pts.append([px, py])
    return np.array(pts, dtype=np.int32)


def _pixels_to_normalized(polygon: List[Tuple[int, int]], width: int, height: int) -> List[Tuple[float, float]]:
    if width <= 0 or height <= 0:
        return []
    return [(_clamp(x / width), _clamp(y / height)) for x, y in polygon]


# ---------------------------------------------------------------------------
# Camera handling


@dataclass
class CameraSource:
    source_id: str
    label: str
    kind: str  # "camera" | "virtual" | "system"
    index: Optional[int] = None
    available: bool = True
    config_key: Optional[str] = None
    path: Optional[str] = None


class CameraStream:
    """Manage a camera or virtual feed."""

    def __init__(self, system_cameras: Optional[Dict[str, Dict]] = None):
        self.cap: Optional[cv2.VideoCapture] = None
        self.active_source: Optional[CameraSource] = None
        self._virtual_tick = 0
        self.system_cameras = system_cameras or {}

    def list_sources(self, max_devices: int = 5) -> List[CameraSource]:
        sources: List[CameraSource] = []

        # First, prefer cameras that were configured in kiosk settings.
        for key, cam_cfg in self.system_cameras.items():
            label = cam_cfg.get("label") or cam_cfg.get("name") or key.replace("_", " ").title()
            index_or_path = cam_cfg.get("index_or_path", cam_cfg.get("index", 0))
            index: Optional[int] = None
            path: Optional[str] = None
            capture: Optional[cv2.VideoCapture] = None
            available = False

            try:
                if isinstance(index_or_path, int):
                    index = index_or_path
                    capture = cv2.VideoCapture(index)
                else:
                    path = str(index_or_path)
                    capture = cv2.VideoCapture(path)
                available = bool(capture and capture.isOpened())
            except Exception:
                available = False
            finally:
                if capture:
                    capture.release()

            if not available:
                offline_label = f"{label} (offline)"
            else:
                offline_label = label

            sources.append(
                CameraSource(
                    source_id=f"system:{key}",
                    label=offline_label,
                    kind="system",
                    index=index,
                    available=available,
                    config_key=key,
                    path=path,
                )
            )

        # Also include a small set of direct device indices for ad-hoc testing.
        system_name = platform.system()
        for idx in range(max_devices):
            source_id = f"camera:{idx}"
            if any(src.source_id == source_id for src in sources):
                continue

            label = f"Camera {idx}"
            available = False
            capture = None

            try:
                if system_name == "Windows":
                    capture = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                    if not capture or not capture.isOpened():
                        if capture:
                            capture.release()
                        capture = cv2.VideoCapture(idx)
                else:
                    capture = cv2.VideoCapture(idx)

                available = bool(capture and capture.isOpened())
            except Exception:
                available = False
            finally:
                if capture:
                    capture.release()

            if not available:
                label = f"{label} (offline)"

            sources.append(CameraSource(source_id, label, "camera", index=idx, available=available))

        # Add demo virtual feed
        sources.append(CameraSource("virtual:demo", "Demo Feed", "virtual", index=-1, available=True))
        return sources

    def open(self, source: CameraSource):
        if self.cap:
            self.cap.release()
            self.cap = None

        self.active_source = source
        self._virtual_tick = 0

        if source.kind in ("camera", "system"):
            if not source.available:
                self.cap = None
                self.active_source = CameraSource("virtual:demo", "Demo Feed", "virtual", index=-1, available=True)
                return

            capture_target = source.path if source.path is not None else source.index
            cap = cv2.VideoCapture(capture_target)
            if not cap or not cap.isOpened():
                self.cap = None
                print("[VISION][WARN] Camera %s unavailable. Falling back to demo feed." % (capture_target,))
                self.active_source = CameraSource("virtual:demo", "Demo Feed", "virtual", index=-1, available=True)
            else:
                self.cap = cap

    def read(self) -> Optional[np.ndarray]:
        if not self.active_source:
            return None

        if self.active_source.kind == "virtual":
            return self._generate_virtual_frame()

        if not self.cap:
            return None

        ok, frame = self.cap.read()
        if not ok:
            return None
        return frame

    def close(self):
        if self.cap:
            self.cap.release()
        self.cap = None
        self.active_source = None

    # ------------------------------------------------------------------
    # Virtual feed
    def _generate_virtual_frame(self) -> np.ndarray:
        """Create a simple animated gradient frame for testing UI."""
        width, height = 960, 540
        frame = np.zeros((height, width, 3), dtype=np.uint8)

        x = (self._virtual_tick % width)
        cv2.rectangle(frame, (x, 120), (x + 160, 360), (0, 220, 120), -1)

        # Add moving circle
        cx = int((np.sin(self._virtual_tick / 40.0) * 0.4 + 0.5) * width)
        cy = int((np.cos(self._virtual_tick / 30.0) * 0.3 + 0.5) * height)
        cv2.circle(frame, (cx, cy), 70, (120, 0, 220), -1)

        self._virtual_tick += 5
        return frame


# ---------------------------------------------------------------------------
# Camera canvas with touch-friendly polygon editing


class CameraCanvas(QWidget):
    """Display camera frames and handle polygon drawing/editing."""

    polygonFinished = Signal(str, list)  # zone_id, normalized points
    polygonUpdated = Signal(str, list)
    zoneTapped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(700, 460)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._frame_image: Optional[QImage] = None
        self._frame_rect = QRectF()
        self._frame_size = (640, 480)

        self._zones: Dict[str, Dict] = {}
        self._active_zone_id: Optional[str] = None

        self._mode = "idle"  # idle | drawing | editing
        self._current_points: List[Tuple[float, float]] = []
        self._drag_vertex_index: Optional[int] = None
        self._was_dragging = False

    # Public API -------------------------------------------------------
    def set_frame(self, frame_image: QImage, frame_size: Tuple[int, int]):
        self._frame_image = frame_image
        self._frame_size = frame_size
        self.update()

    def set_zones(self, zones: List[Dict], active_zone_id: Optional[str]):
        self._zones = {zone["zone_id"]: zone for zone in zones}
        self._active_zone_id = active_zone_id
        self.update()

    def start_drawing(self, zone_id: str):
        self._mode = "drawing"
        self._active_zone_id = zone_id
        self._current_points = []
        self._drag_vertex_index = None
        self._was_dragging = False
        self.update()

    def edit_zone(self, zone_id: str):
        zone = self._zones.get(zone_id)
        if not zone:
            return
        self._mode = "editing"
        self._active_zone_id = zone_id
        self._current_points = list(zone.get("polygon", []))
        self._drag_vertex_index = None
        self._was_dragging = False
        self.update()

    def cancel_temporary_edit(self):
        self._mode = "idle"
        self._current_points = []
        self._drag_vertex_index = None
        self._was_dragging = False
        self.update()

    # Coordinate helpers ----------------------------------------------
    def _frame_to_widget(self, norm_point: Tuple[float, float]) -> QPointF:
        if not self._frame_rect.width() or not self._frame_rect.height():
            return QPointF()
        x = self._frame_rect.left() + norm_point[0] * self._frame_rect.width()
        y = self._frame_rect.top() + norm_point[1] * self._frame_rect.height()
        return QPointF(x, y)

    def _widget_to_normalized(self, pos: QPointF) -> Tuple[float, float]:
        if not self._frame_rect.width() or not self._frame_rect.height():
            return 0.0, 0.0
        nx = _clamp((pos.x() - self._frame_rect.left()) / self._frame_rect.width())
        ny = _clamp((pos.y() - self._frame_rect.top()) / self._frame_rect.height())
        return nx, ny

    def _nearest_vertex(self, pos: QPointF) -> Optional[int]:
        points = self._current_points if self._current_points else []
        if not points:
            return None
        widget_points = [self._frame_to_widget(pt) for pt in points]
        for idx, wpt in enumerate(widget_points):
            if (wpt - pos).manhattanLength() < 24:  # generous radius for touch
                return idx
        return None

    def _is_near_first_point(self, pos: QPointF) -> bool:
        if len(self._current_points) < 3:
            return False
        first_point_widget = self._frame_to_widget(self._current_points[0])
        return (first_point_widget - pos).manhattanLength() < 28

    # Painting ---------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111111"))

        if self._frame_image is None or self._frame_image.isNull():
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#333333"))
            painter.drawRoundedRect(self.rect().adjusted(10, 10, -10, -10), 12, 12)
            painter.setPen(QColor("#888888"))
            painter.setFont(QFont("Noto Sans", 24, QFont.Bold))
            painter.drawText(self.rect(), Qt.AlignCenter, "Camera feed unavailable")
            return

        # Preserve aspect ratio when drawing frame
        frame_size = self._frame_image.size()
        frame_rect = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        frame_rect = self._scaled_rect(frame_size.width(), frame_size.height(), frame_rect)
        self._frame_rect = frame_rect

        painter.drawImage(frame_rect, self._frame_image)

        # Draw zones
        for zone_id, zone in self._zones.items():
            polygon = zone.get("polygon", [])
            if not polygon:
                continue
            widget_points = [self._frame_to_widget(pt) for pt in polygon]
            poly = QPolygonF(widget_points)

            is_active = zone_id == self._active_zone_id
            is_triggered = zone.get("detection", {}).get("triggered", False)

            if is_triggered:
                base_color = QColor("#2ECC71")  # Green when active
            else:
                base_color = QColor("#F44336")  # Red when inactive

            fill_color = QColor(base_color)
            fill_color.setAlpha(80 if is_active else 45)
            border_color = QColor(base_color)
            border_color.setAlpha(255 if is_active else 180)

            painter.setBrush(fill_color)
            painter.setPen(QPen(border_color, 3 if is_active else 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPolygon(poly)

            # Draw vertices for active zone
            if is_active:
                painter.setBrush(QColor("#FFFFFF"))
                painter.setPen(QPen(border_color, 2))
                for wpt in widget_points:
                    painter.drawEllipse(wpt, 6, 6)

            # Label
            painter.setPen(QPen(border_color))
            painter.setFont(QFont("Noto Sans", 14, QFont.Medium))
            center = poly.boundingRect().center()
            painter.drawText(center, zone.get("name", "Zone"))

        # Draw in-progress polygon (drawing mode)
        if self._mode == "drawing" and self._current_points:
            widget_points = [self._frame_to_widget(pt) for pt in self._current_points]
            painter.setPen(QPen(QColor("#FFFFFF"), 2, Qt.DashLine))
            for pt in widget_points:
                painter.drawEllipse(pt, 5, 5)
            for idx in range(len(widget_points) - 1):
                painter.drawLine(widget_points[idx], widget_points[idx + 1])

    def _scaled_rect(self, width: int, height: int, bounds: QRectF) -> QRectF:
        if width <= 0 or height <= 0:
            return QRectF(bounds)
        aspect = width / height
        if bounds.width() / bounds.height() > aspect:
            new_height = bounds.height()
            new_width = new_height * aspect
        else:
            new_width = bounds.width()
            new_height = new_width / aspect
        x = bounds.center().x() - new_width / 2
        y = bounds.center().y() - new_height / 2
        return QRectF(x, y, new_width, new_height)

    # Interaction ------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        pos = event.position()
        if not self._frame_rect.contains(pos):
            return

        if self._mode == "drawing":
            if len(self._current_points) >= 3 and self._is_near_first_point(pos):
                # Complete polygon
                self.polygonFinished.emit(self._active_zone_id, list(self._current_points))
                self._mode = "idle"
                self._current_points = []
                self.update()
                return

            new_point = self._widget_to_normalized(pos)
            self._current_points.append(new_point)
            self.polygonUpdated.emit(self._active_zone_id, list(self._current_points))
            self.update()
            return

        if self._mode == "editing":
            vertex_idx = self._nearest_vertex(pos)
            if vertex_idx is not None:
                self._drag_vertex_index = vertex_idx
                self._was_dragging = False
                return

        # Tap selection in idle mode
        tapped_zone = self._hit_test_zone(pos)
        if tapped_zone:
            self.zoneTapped.emit(tapped_zone)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return

        if self._mode != "editing" or self._drag_vertex_index is None:
            return

        pos = event.position()
        if not self._frame_rect.contains(pos):
            return

        self._was_dragging = True
        new_point = self._widget_to_normalized(pos)
        if 0 <= self._drag_vertex_index < len(self._current_points):
            self._current_points[self._drag_vertex_index] = new_point
            self.polygonUpdated.emit(self._active_zone_id, list(self._current_points))
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        if self._mode == "editing" and self._drag_vertex_index is not None:
            if not self._was_dragging:
                # Treat as tap to close editor
                pass
            self._drag_vertex_index = None
            self._was_dragging = False

    def _hit_test_zone(self, pos: QPointF) -> Optional[str]:
        for zone_id, zone in self._zones.items():
            polygon = zone.get("polygon", [])
            if not polygon:
                continue
            widget_points = [self._frame_to_widget(pt) for pt in polygon]
            poly = QPolygonF(widget_points)
            if poly.containsPoint(pos, Qt.OddEvenFill):
                return zone_id
        return None


# ---------------------------------------------------------------------------
# Vision designer widget (main content)


class VisionDesignerWidget(QWidget):
    """Composable widget with camera preview and configuration controls."""

    state_changed = Signal(str, dict)

    def __init__(
        self,
        parent=None,
        config: Optional[Dict] = None,
        system_config: Optional[Dict] = None,
    ):
        super().__init__(parent)
        self.setMinimumSize(960, 540)

        self._config = config if config else create_default_vision_config()
        self._config = deepcopy(self._config)
        trigger_cfg = self._config.setdefault("trigger", {})
        trigger_cfg.setdefault("idle_mode", {"enabled": False, "interval_seconds": 2.0})
        trigger_cfg.setdefault("vision_type", "basic_detection")

        self.system_config = deepcopy(system_config) if system_config else {}
        self.system_cameras = deepcopy(self.system_config.get("cameras", {}))

        self.camera_stream = CameraStream(self.system_cameras)
        self.available_sources = self.camera_stream.list_sources()

        self.active_zone_id: Optional[str] = None
        self._current_detection_summary: Dict[str, bool] = {}
        self._last_frame: Optional[np.ndarray] = None
        self._current_state = "watching"
        self._last_state_signature: Optional[Tuple[str, str]] = None
        self.controls_scroll: Optional[QScrollArea] = None
        self.scroll_up_btn: Optional[QPushButton] = None
        self.scroll_down_btn: Optional[QPushButton] = None

        self._normal_interval_ms = 1000 // 30
        self._idle_min_interval_ms = 1000  # 1 FPS baseline for idle preview
        self._current_timer_interval_ms = self._normal_interval_ms
        self._last_detection_check = 0.0

        self._build_ui()
        self._update_state("watching", {"message": "Watching for triggers"})

        # Camera update timer
        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self._update_frame)
        self.frame_timer.start(self._normal_interval_ms)

        # Kick off with initial camera
        self._sync_camera_selection(initial=True)

    # ------------------------------------------------------------------
    # Timing helpers
    def _set_timer_interval(self, interval_ms: int):
        interval_ms = max(25, int(interval_ms))
        if interval_ms == self._current_timer_interval_ms:
            return
        if self.frame_timer.isActive():
            self.frame_timer.stop()
        self.frame_timer.start(interval_ms)
        self._current_timer_interval_ms = interval_ms

    def _adjust_frame_timer(self, state: str, idle_interval: float):
        if state == "idle":
            interval_ms = max(int(idle_interval * 1000), self._idle_min_interval_ms)
        else:
            interval_ms = self._normal_interval_ms
        self._set_timer_interval(interval_ms)

    # ------------------------------------------------------------------
    # UI construction
    def _build_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(12)

        # Left: camera canvas sized for 1024x600 layouts
        self.canvas = CameraCanvas(self)
        self.canvas.polygonFinished.connect(self._on_polygon_finished)
        self.canvas.polygonUpdated.connect(self._on_polygon_updated)
        self.canvas.zoneTapped.connect(self._on_zone_tapped)
        self.canvas.setMinimumSize(640, 480)
        main_layout.addWidget(self.canvas, stretch=3)

        # Right: scrollable control stack with touch arrows
        controls_stack = QVBoxLayout()
        controls_stack.setContentsMargins(0, 0, 0, 0)
        controls_stack.setSpacing(6)

        self.scroll_up_btn = QPushButton("▲")
        self.scroll_up_btn.setMinimumHeight(44)
        self.scroll_up_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.scroll_up_btn.setStyleSheet("""
            QPushButton {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 10px;
                font-size: 22px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
        """)
        controls_stack.addWidget(self.scroll_up_btn)

        self.controls_scroll = QScrollArea()
        self.controls_scroll.setWidgetResizable(True)
        self.controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.controls_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.controls_scroll.setFrameShape(QFrame.NoFrame)
        self.controls_scroll.setMinimumWidth(352)
        self.controls_scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
            }
            QScrollBar:vertical {
                width: 32px;
                background: #2a2a2a;
                margin: 6px 0 6px 6px;
                border-radius: 12px;
            }
            QScrollBar::handle:vertical {
                background: #505050;
                min-height: 40px;
                border-radius: 12px;
            }
            QScrollBar::handle:vertical:hover {
                background: #6b6b6b;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        controls_panel = QWidget()
        controls_panel.setMinimumWidth(352)
        controls_layout = QVBoxLayout(controls_panel)
        controls_layout.setContentsMargins(12, 8, 24, 8)
        controls_layout.setSpacing(12)

        controls_layout.addWidget(self._build_state_card())
        controls_layout.addWidget(self._build_camera_step())
        controls_layout.addWidget(self._build_idle_step())
        controls_layout.addWidget(self._build_vision_type_step())
        controls_layout.addWidget(self._build_zone_step())
        controls_layout.addWidget(self._build_settings_step())
        controls_layout.addStretch()

        self.controls_scroll.setWidget(controls_panel)
        controls_stack.addWidget(self.controls_scroll, stretch=1)

        self.scroll_down_btn = QPushButton("▼")
        self.scroll_down_btn.setMinimumHeight(44)
        self.scroll_down_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.scroll_down_btn.setStyleSheet("""
            QPushButton {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 10px;
                font-size: 22px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
        """)
        controls_stack.addWidget(self.scroll_down_btn)

        main_layout.addLayout(controls_stack, stretch=1)
        self._configure_scroll_buttons()

        self._refresh_zone_table()

    def _configure_scroll_buttons(self):
        """Configure scroll controls for touch interaction."""
        for btn, direction in ((self.scroll_up_btn, -1), (self.scroll_down_btn, 1)):
            btn.setAutoRepeat(True)
            btn.setAutoRepeatDelay(300)
            btn.setAutoRepeatInterval(120)
            btn.clicked.connect(lambda _, d=direction: self._scroll_controls(d * 160))
        if self.controls_scroll:
            bar = self.controls_scroll.verticalScrollBar()
            bar.setSingleStep(60)
            bar.setPageStep(220)

    def _scroll_controls(self, delta: int):
        if not self.controls_scroll:
            return
        bar = self.controls_scroll.verticalScrollBar()
        bar.setValue(bar.value() + delta)

    def _create_step_container(self, number: int, title: str, description: str) -> Tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setStyleSheet(
            """
            QFrame {
                background-color: #2b2b2b;
                border-radius: 12px;
                border: 1px solid #3d3d3d;
            }
            """
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        header = QLabel(f"{number}. {title}")
        header.setStyleSheet("color: #ffffff; font-size: 16px; font-weight: bold;")
        layout.addWidget(header)

        desc_label = QLabel(description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #bbbbbb; font-size: 12px;")
        layout.addWidget(desc_label)

        return frame, layout

    def _build_state_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            """
            QFrame {
                background-color: #252525;
                border-radius: 14px;
                border: 1px solid #333333;
            }
            """
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title = QLabel("Vision Status")
        title.setStyleSheet("color: #f0f0f0; font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        self.state_chip = QLabel("FALSE")
        self.state_chip.setAlignment(Qt.AlignCenter)
        self.state_chip.setMinimumHeight(38)
        self.state_chip.setStyleSheet("border-radius: 10px; font-size: 16px; font-weight: bold;")
        layout.addWidget(self.state_chip)

        self.detection_status = QLabel("Watching for triggers")
        self.detection_status.setWordWrap(True)
        self.detection_status.setStyleSheet("color: #cccccc; font-size: 13px;")
        layout.addWidget(self.detection_status)

        self.metric_label = QLabel("Metric: N/A")
        self.metric_label.setStyleSheet("color: #999999; font-size: 12px;")
        layout.addWidget(self.metric_label)

        self._apply_state_chip("false")
        return card

    def _build_camera_step(self) -> QFrame:
        frame, layout = self._create_step_container(
            1,
            "Select Camera",
            "Choose which named camera from Settings should power this vision step.",
        )

        self.camera_combo = QComboBox()
        self.camera_combo.setMinimumHeight(48)
        self.camera_combo.setStyleSheet(
            """
            QComboBox {
                background-color: #404040;
                color: white;
                border: 2px solid #505050;
                border-radius: 6px;
                padding: 12px;
                font-size: 15px;
            }
            """
        )
        self._populate_camera_combo()
        self.camera_combo.currentIndexChanged.connect(self._on_camera_changed)
        layout.addWidget(self.camera_combo)

        row = QHBoxLayout()
        self.camera_status = QLabel("Status: Not connected")
        self.camera_status.setStyleSheet("color: #bbbbbb; font-size: 12px;")
        row.addWidget(self.camera_status)

        self.rescan_btn = QPushButton("Rescan")
        self.rescan_btn.setMinimumHeight(36)
        self.rescan_btn.setMaximumWidth(120)
        self.rescan_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #505050;
                color: #ffffff;
                border-radius: 8px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #5e5e5e; }
            """
        )
        self.rescan_btn.clicked.connect(self._rescan_cameras)
        row.addWidget(self.rescan_btn, alignment=Qt.AlignRight)
        layout.addLayout(row)

        return frame

    def _build_idle_step(self) -> QFrame:
        frame, layout = self._create_step_container(
            2,
            "Idle Mode",
            "Pause the camera between checks to save power. Idle keeps watching every few seconds until a detection flips the state to True.",
        )

        controls = QHBoxLayout()
        controls.setSpacing(10)

        self.idle_toggle = QPushButton("Idle Off")
        self.idle_toggle.setCheckable(True)
        self.idle_toggle.setMinimumHeight(44)
        self.idle_toggle.setStyleSheet("border-radius: 10px; font-size: 14px; font-weight: bold;")
        self.idle_toggle.toggled.connect(self._on_idle_toggle_changed)
        controls.addWidget(self.idle_toggle)

        spin_container = QHBoxLayout()
        spin_container.setSpacing(6)
        seconds_label = QLabel("Seconds:")
        seconds_label.setStyleSheet("color: #dddddd; font-size: 13px;")
        spin_container.addWidget(seconds_label)

        self.idle_interval_spin = QDoubleSpinBox()
        self.idle_interval_spin.setRange(0.5, 60.0)
        self.idle_interval_spin.setSingleStep(0.5)
        self.idle_interval_spin.setDecimals(2)
        self.idle_interval_spin.setValue(self._config["trigger"].get("idle_mode", {}).get("interval_seconds", 2.0))
        self.idle_interval_spin.valueChanged.connect(self._on_idle_interval_changed)
        self.idle_interval_spin.setEnabled(False)
        spin_container.addWidget(self.idle_interval_spin)
        spin_container.addStretch()

        controls.addLayout(spin_container)
        layout.addLayout(controls)

        self._apply_idle_toggle_style(self._config["trigger"].get("idle_mode", {}).get("enabled", False))

        return frame

    def _build_vision_type_step(self) -> QFrame:
        frame, layout = self._create_step_container(
            3,
            "Vision Type",
            "Pick the detection model to run. More options will appear here as we add advanced vision modes.",
        )

        self.vision_type_combo = QComboBox()
        self.vision_type_combo.setMinimumHeight(44)
        self.vision_type_combo.setStyleSheet(
            """
            QComboBox {
                background-color: #404040;
                color: white;
                border: 2px solid #505050;
                border-radius: 6px;
                padding: 10px;
                font-size: 15px;
            }
            """
        )
        self.vision_type_combo.addItem("Basic Vision Detection", "basic_detection")
        current_type = self._config["trigger"].get("vision_type", "basic_detection")
        idx = self.vision_type_combo.findData(current_type)
        if idx >= 0:
            self.vision_type_combo.setCurrentIndex(idx)
        self.vision_type_combo.currentIndexChanged.connect(self._on_vision_type_changed)
        layout.addWidget(self.vision_type_combo)

        return frame

    def _build_zone_step(self) -> QFrame:
        frame, layout = self._create_step_container(
            4,
            "Draw Area",
            "Trace the detection zone on the preview. We'll store a single polygon now and expand to multiples later.",
        )

        self.zones_table = QTableWidget(0, 3)
        self.zones_table.setHorizontalHeaderLabels(["Area", "Points", "Actions"])
        self.zones_table.horizontalHeader().setStretchLastSection(True)
        self.zones_table.horizontalHeader().setStyleSheet("color: #dddddd; font-size: 12px;")
        self.zones_table.verticalHeader().setVisible(False)
        self.zones_table.setShowGrid(False)
        self.zones_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.zones_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.zones_table.setFocusPolicy(Qt.NoFocus)
        self.zones_table.setStyleSheet(
            """
            QTableWidget {
                background-color: #2f2f2f;
                border: 1px solid #3e3e3e;
                border-radius: 10px;
            }
            QTableWidget::item {
                color: #f0f0f0;
                font-size: 13px;
                padding: 8px;
            }
            """
        )
        layout.addWidget(self.zones_table)

        self.add_zone_btn = QPushButton("➕ Add Area")
        self.add_zone_btn.setMinimumHeight(40)
        self.add_zone_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border-radius: 10px;
                font-weight: bold;
            }
            QPushButton:disabled { background-color: #2f5f33; color: #aaaaaa; }
            """
        )
        self.add_zone_btn.clicked.connect(self._create_zone)
        layout.addWidget(self.add_zone_btn, alignment=Qt.AlignRight)

        self._zone_action_buttons: Dict[str, QPushButton] = {}
        self._editing_zone_id: Optional[str] = None

        return frame

    def _build_settings_step(self) -> QFrame:
        frame, layout = self._create_step_container(
            5,
            "Detection Settings",
            "Tune how the basic detector behaves. Adjust the display name, metric, and threshold to set when the state flips to True (green).",
        )

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        self.trigger_name_edit = QLineEdit(self._config["trigger"].get("display_name", "Detection Zone"))
        self.trigger_name_edit.setClearButtonEnabled(True)
        self.trigger_name_edit.textChanged.connect(self._on_trigger_name_changed)
        self.trigger_name_edit.setMinimumHeight(38)
        form.addRow("Display Name", self.trigger_name_edit)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["presence", "absence", "edge", "custom"])
        current_mode = self._config["trigger"].get("mode", "presence")
        idx = self.mode_combo.findText(current_mode)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        form.addRow("Trigger Mode", self.mode_combo)

        self.metric_combo = QComboBox()
        self.metric_combo.addItems(["intensity", "green_channel", "edge_density"])
        current_metric = self._config["trigger"]["settings"].get("metric", "intensity")
        metric_idx = self.metric_combo.findText(current_metric)
        if metric_idx >= 0:
            self.metric_combo.setCurrentIndex(metric_idx)
        self.metric_combo.currentTextChanged.connect(self._on_metric_changed)
        form.addRow("Detection Metric", self.metric_combo)

        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setRange(0, 100)
        self.threshold_slider.setValue(int(self._config["trigger"]["settings"].get("threshold", 0.55) * 100))
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)
        form.addRow("Threshold", self.threshold_slider)

        self.sensitivity_spin = QDoubleSpinBox()
        self.sensitivity_spin.setRange(0.1, 1.0)
        self.sensitivity_spin.setSingleStep(0.05)
        self.sensitivity_spin.setValue(self._config["trigger"]["settings"].get("sensitivity", 0.6))
        self.sensitivity_spin.valueChanged.connect(self._on_sensitivity_changed)
        form.addRow("Sensitivity", self.sensitivity_spin)

        self.invert_checkbox = QCheckBox("Invert trigger (detect when metric below threshold)")
        self.invert_checkbox.setChecked(self._config["trigger"]["settings"].get("invert", False))
        self.invert_checkbox.toggled.connect(self._on_invert_toggled)
        form.addRow(self.invert_checkbox)

        self.hold_spin = QDoubleSpinBox()
        self.hold_spin.setRange(0.0, 5.0)
        self.hold_spin.setSingleStep(0.1)
        self.hold_spin.setValue(self._config["trigger"]["settings"].get("hold_time", 0.0))
        self.hold_spin.valueChanged.connect(self._on_hold_changed)
        form.addRow("Hold Time (s)", self.hold_spin)

        layout.addLayout(form)

        debug_row = QVBoxLayout()
        debug_row.setSpacing(6)
        self.debug_toggle = QCheckBox("Show debug preview (camera + metrics overlay)")
        self.debug_toggle.setStyleSheet("color: #dddddd; font-size: 12px;")
        self.debug_toggle.toggled.connect(self._on_debug_toggled)
        debug_row.addWidget(self.debug_toggle)

        self.debug_preview_label = QLabel("Enable debug preview to visualize threshold checks.")
        self.debug_preview_label.setAlignment(Qt.AlignCenter)
        self.debug_preview_label.setMinimumHeight(120)
        self.debug_preview_label.setStyleSheet(
            "color: #aaaaaa; font-size: 12px; border: 1px dashed #444444; border-radius: 10px; padding: 6px;"
        )
        debug_row.addWidget(self.debug_preview_label)

        layout.addLayout(debug_row)

        return frame

    def _populate_camera_combo(self):
        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()
        for source in self.available_sources:
            self.camera_combo.addItem(source.label, source.source_id)
        self.camera_combo.blockSignals(False)

    def _set_camera_combo(self, source_id: str):
        idx = self.camera_combo.findData(source_id)
        if idx >= 0:
            self.camera_combo.blockSignals(True)
            self.camera_combo.setCurrentIndex(idx)
            self.camera_combo.blockSignals(False)

    def _use_virtual_feed(self, status_message: str):
        virtual_source = next((s for s in self.available_sources if s.source_id == "virtual:demo"), None)
        if virtual_source is None:
            virtual_source = CameraSource("virtual:demo", "Demo Feed", "virtual", index=-1, available=True)
            self.available_sources.append(virtual_source)
            self.camera_combo.addItem(virtual_source.label, virtual_source.source_id)
        self.camera_stream.open(virtual_source)
        self._set_camera_combo(virtual_source.source_id)
        self.camera_status.setText(status_message)
        camera_cfg = self._config.setdefault("camera", {})
        camera_cfg.update(
            {
                "index": virtual_source.index,
                "label": virtual_source.label,
                "source_id": virtual_source.source_id,
                "config_key": None,
                "index_or_path": virtual_source.index,
            }
        )
        if self._current_state != "triggered":
            self._update_state("watching", {"message": "Using demo feed"})

    def _apply_state_chip(self, state: str):
        palette = {
            "true": ("#2e7d32", "TRUE"),
            "false": ("#c62828", "FALSE"),
            "idle": ("#ff9800", "IDLE"),
        }
        background, label = palette.get(state, palette["false"])
        self.state_chip.setText(label)
        self.state_chip.setStyleSheet(
            f"""
            QLabel {{
                background-color: {background};
                color: #ffffff;
                border-radius: 10px;
                font-weight: bold;
            }}
            """
        )

    def _apply_idle_toggle_style(self, enabled: bool):
        if enabled:
            self.idle_toggle.setText("Idle On")
            self.idle_toggle.setChecked(True)
            self.idle_toggle.setStyleSheet(
                """
                QPushButton {
                    background-color: #ff9800;
                    color: #1e1e1e;
                    border-radius: 10px;
                    font-weight: bold;
                }
                QPushButton:checked {
                    background-color: #ffb74d;
                    color: #1e1e1e;
                }
                """
            )
            self.idle_interval_spin.setEnabled(True)
        else:
            self.idle_toggle.blockSignals(True)
            self.idle_toggle.setChecked(False)
            self.idle_toggle.blockSignals(False)
            self.idle_toggle.setText("Idle Off")
            self.idle_toggle.setStyleSheet(
                """
                QPushButton {
                    background-color: #424242;
                    color: #f5f5f5;
                    border-radius: 10px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #4c4c4c; }
                """
            )
            self.idle_interval_spin.setEnabled(False)

    def _refresh_zone_table(self):
        zones = self._config["trigger"].get("zones", [])
        self.zones_table.blockSignals(True)
        self.zones_table.setRowCount(len(zones))
        self._zone_action_buttons.clear()

        for row, zone in enumerate(zones):
            zone_id = zone.get("zone_id")
            name = zone.get("name", f"Zone {row + 1}")
            points_count = len(zone.get("polygon", []))

            name_item = QTableWidgetItem(name)
            name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            points_item = QTableWidgetItem(f"{points_count} pts")
            points_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

            self.zones_table.setItem(row, 0, name_item)
            self.zones_table.setItem(row, 1, points_item)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(0, 0, 0, 0)
            action_layout.setSpacing(6)

            edit_btn = QPushButton("Edit")
            edit_btn.setMinimumHeight(32)
            edit_btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #4a90e2;
                    color: white;
                    border-radius: 8px;
                    font-weight: bold;
                    padding: 4px 10px;
                }
                QPushButton:hover { background-color: #5aa0f0; }
                """
            )
            edit_btn.clicked.connect(lambda _, zid=zone_id: self._toggle_zone_edit(zid))

            delete_btn = QPushButton("Delete")
            delete_btn.setMinimumHeight(32)
            delete_btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #c62828;
                    color: white;
                    border-radius: 8px;
                    font-weight: bold;
                    padding: 4px 10px;
                }
                QPushButton:hover { background-color: #d84343; }
                """
            )
            delete_btn.clicked.connect(lambda _, zid=zone_id: self._delete_zone(zid))

            if self._editing_zone_id == zone_id:
                edit_btn.setText("Done")
                edit_btn.setStyleSheet(
                    """
                    QPushButton {
                        background-color: #43a047;
                        color: white;
                        border-radius: 8px;
                        font-weight: bold;
                        padding: 4px 10px;
                    }
                    QPushButton:hover { background-color: #4caf50; }
                    """
                )

            action_layout.addWidget(edit_btn)
            action_layout.addWidget(delete_btn)
            action_layout.addStretch()
            self.zones_table.setCellWidget(row, 2, action_widget)
            if zone_id:
                self._zone_action_buttons[zone_id] = edit_btn

        self.zones_table.blockSignals(False)
        self.add_zone_btn.setEnabled(len(zones) < 1)
        self.canvas.set_zones(zones, self.active_zone_id)
        self._highlight_zone_row(self.active_zone_id)

    def _highlight_zone_row(self, zone_id: Optional[str]):
        if zone_id is None:
            self.zones_table.clearSelection()
            return
        zones = self._config["trigger"].get("zones", [])
        for row, zone in enumerate(zones):
            if zone.get("zone_id") == zone_id:
                self.zones_table.selectRow(row)
                break

    def _create_zone(self):
        zones = self._config["trigger"].setdefault("zones", [])
        if len(zones) >= 1:
            QMessageBox.information(self, "Draw Area", "Only one area is supported right now.")
            return

        existing_names = [zone.get("name", "") for zone in zones]
        zone_name = _generate_zone_name(existing_names)
        zone_id = _uuid("zone")
        new_zone = {
            "zone_id": zone_id,
            "name": zone_name,
            "polygon": [],
            "enabled": True,
            "color": "#33FF99",
        }
        zones.append(new_zone)
        self.active_zone_id = zone_id
        self._editing_zone_id = zone_id
        self.canvas.start_drawing(zone_id)
        self._refresh_zone_table()

    def _toggle_zone_edit(self, zone_id: Optional[str]):
        if zone_id is None:
            return
        if self._editing_zone_id == zone_id:
            self._editing_zone_id = None
            self.canvas.cancel_temporary_edit()
        else:
            self._editing_zone_id = zone_id
            self.active_zone_id = zone_id
            zone = self._zone_by_id(zone_id)
            if zone and zone.get("polygon"):
                self.canvas.edit_zone(zone_id)
            else:
                self.canvas.start_drawing(zone_id)
        self._refresh_zone_table()

    def _delete_zone(self, zone_id: Optional[str]):
        if not zone_id:
            return
        zones = self._config["trigger"].get("zones", [])
        self._config["trigger"]["zones"] = [zone for zone in zones if zone.get("zone_id") != zone_id]
        if self.active_zone_id == zone_id:
            self.active_zone_id = None
        if self._editing_zone_id == zone_id:
            self._editing_zone_id = None
            self.canvas.cancel_temporary_edit()
        self._refresh_zone_table()

    def _on_zone_tapped(self, zone_id: str):
        self.active_zone_id = zone_id
        self._highlight_zone_row(zone_id)
        self.canvas.set_zones(self._config["trigger"].get("zones", []), self.active_zone_id)

    def _on_polygon_updated(self, zone_id: str, points: List[Tuple[float, float]]):
        zone = self._zone_by_id(zone_id)
        if not zone:
            return
        zone["polygon"] = points
        self._refresh_zone_table()

    def _on_polygon_finished(self, zone_id: str, points: List[Tuple[float, float]]):
        zone = self._zone_by_id(zone_id)
        if not zone:
            return
        zone["polygon"] = points
        self.canvas.cancel_temporary_edit()
        if self._editing_zone_id == zone_id:
            self._editing_zone_id = None
        self._refresh_zone_table()

    def _zone_by_id(self, zone_id: str) -> Optional[Dict]:
        for zone in self._config.get("trigger", {}).get("zones", []):
            if zone.get("zone_id") == zone_id:
                return zone
        return None

    def _update_state(self, state: str, payload: Optional[Dict] = None):
        payload = payload or {}
        message = payload.get("message", "Watching for triggers")
        signature = (state, message)
        self._current_state = state

        idle_interval = self._config["trigger"].get("idle_mode", {}).get("interval_seconds", 2.0)
        self._adjust_frame_timer(state, idle_interval)

        if state == "triggered":
            self._apply_state_chip("true")
            self.detection_status.setText(message)
            self.detection_status.setStyleSheet("color: #4CAF50; font-size: 13px;")
        elif state == "idle":
            self._apply_state_chip("idle")
            self.detection_status.setText(message)
            self.detection_status.setStyleSheet("color: #FFB300; font-size: 13px;")
        else:
            self._apply_state_chip("false")
            self.detection_status.setText(message)
            self.detection_status.setStyleSheet("color: #e57373; font-size: 13px;")

        if signature != self._last_state_signature:
            self._last_state_signature = signature
            self.state_changed.emit(state, payload)

    # ------------------------------------------------------------------
    # Configuration management
    def get_config(self) -> Dict:
        return deepcopy(self._config)

    def set_config(self, config: Dict):
        self._config = deepcopy(config)
        self.trigger_name_edit.setText(self._config["trigger"].get("display_name", "Detection Zone"))
        mode = self._config["trigger"].get("mode", "presence")
        idx = self.mode_combo.findText(mode)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)
        metric = self._config["trigger"]["settings"].get("metric", "intensity")
        idx = self.metric_combo.findText(metric)
        if idx >= 0:
            self.metric_combo.setCurrentIndex(idx)
        self.threshold_slider.setValue(int(self._config["trigger"]["settings"].get("threshold", 0.55) * 100))
        self.invert_checkbox.setChecked(self._config["trigger"]["settings"].get("invert", False))
        self.hold_spin.setValue(self._config["trigger"]["settings"].get("hold_time", 0.0))
        self.sensitivity_spin.setValue(self._config["trigger"]["settings"].get("sensitivity", 0.6))
        idle_cfg = self._config["trigger"].setdefault("idle_mode", {"enabled": False, "interval_seconds": 2.0})
        enabled = idle_cfg.get("enabled", False)
        interval = idle_cfg.get("interval_seconds", 2.0)
        self.idle_toggle.blockSignals(True)
        self.idle_toggle.setChecked(enabled)
        self.idle_toggle.blockSignals(False)
        self._apply_idle_toggle_style(enabled)
        self.idle_interval_spin.setValue(interval)
        self.idle_interval_spin.setEnabled(enabled)
        vision_type = self._config["trigger"].get("vision_type", "basic_detection")
        idx = self.vision_type_combo.findData(vision_type)
        if idx >= 0:
            self.vision_type_combo.setCurrentIndex(idx)
        if not self._config.get("name"):
            self._config["name"] = self._config["trigger"].get("display_name", "Vision Trigger")
        self._refresh_zone_table()
        current_source_id = self._config.get("camera", {}).get("source_id")
        self.available_sources = self.camera_stream.list_sources()
        self._populate_camera_combo()
        if current_source_id:
            self._set_camera_combo(current_source_id)
        self._sync_camera_selection()

    # ------------------------------------------------------------------
    # Camera handling
    def _sync_camera_selection(self, initial: bool = False):
        source_id = self._config["camera"].get("source_id", "camera:0")
        source = self._source_by_id(source_id)

        if source and source.kind in {"camera", "system"} and source.available:
            self._set_camera_combo(source.source_id)
            self.camera_stream.open(source)
            camera_cfg = self._config.setdefault("camera", {})
            camera_cfg.update(
                {
                    "index": source.index if source.index is not None else 0,
                    "label": source.label,
                    "source_id": source.source_id,
                    "config_key": source.config_key,
                    "index_or_path": source.path if source.path is not None else source.index,
                }
            )
            self.camera_status.setText("Status: Connected")
            if self._current_state != "triggered":
                self._update_state("watching", {"message": "Watching for triggers"})
            return

        if source and source.kind == "virtual":
            self._set_camera_combo(source.source_id)
            self.camera_stream.open(source)
            self.camera_status.setText("Status: Demo feed")
            if self._current_state != "triggered":
                self._update_state("watching", {"message": "Using demo feed"})
            return

        available_camera = next(
            (s for s in self.available_sources if s.kind in {"camera", "system"} and s.available),
            None,
        )

        if available_camera:
            self._set_camera_combo(available_camera.source_id)
            self.camera_stream.open(available_camera)
            camera_cfg = self._config.setdefault("camera", {})
            camera_cfg.update(
                {
                    "index": available_camera.index if available_camera.index is not None else 0,
                    "label": available_camera.label,
                    "source_id": available_camera.source_id,
                    "config_key": available_camera.config_key,
                    "index_or_path": available_camera.path
                    if available_camera.path is not None
                    else available_camera.index,
                }
            )
            self.camera_status.setText("Status: Connected")
            if self._current_state != "triggered":
                self._update_state("watching", {"message": "Watching for triggers"})
        else:
            self._use_virtual_feed("Status: Demo feed (no camera detected)")

    def _source_by_id(self, source_id: str) -> Optional[CameraSource]:
        for source in self.available_sources:
            if source.source_id == source_id:
                return source
        return None

    def _on_camera_changed(self, index: int):
        source_id = self.camera_combo.itemData(index)
        source = self._source_by_id(source_id)
        if not source:
            return
        if source.kind == "virtual":
            self.camera_stream.open(source)
            camera_cfg = self._config.setdefault("camera", {})
            camera_cfg.update(
                {
                    "index": source.index if source.index is not None else 0,
                    "label": source.label,
                    "source_id": source.source_id,
                    "config_key": None,
                    "index_or_path": source.index,
                }
            )
            self.camera_status.setText("Status: Demo feed")
            if self._current_state != "triggered":
                self._update_state("watching", {"message": "Using demo feed"})
            return

        if not source.available:
            self.camera_status.setText(f"Status: {source.label}")
            self._use_virtual_feed("Status: Demo feed (camera unavailable)")
            return

        self.camera_stream.open(source)
        camera_cfg = self._config.setdefault("camera", {})
        camera_cfg.update(
            {
                "index": source.index if source.index is not None else 0,
                "label": source.label,
                "source_id": source.source_id,
                "config_key": source.config_key,
                "index_or_path": source.path if source.path is not None else source.index,
            }
        )
        self.camera_status.setText("Status: Connected")
        if self._current_state != "triggered":
            self._update_state("watching", {"message": "Watching for triggers"})

    def _rescan_cameras(self):
        self.available_sources = self.camera_stream.list_sources()
        current_source = self._config["camera"].get("source_id", "camera:0")

        self._populate_camera_combo()

        if current_source:
            self._set_camera_combo(current_source)

        self._sync_camera_selection()

    def _update_frame(self):
        frame = self.camera_stream.read()
        if frame is None:
            self._last_frame = None
            self.canvas.set_frame(QImage(), (0, 0))
            self.detection_status.setText("Waiting for camera...")
            self.metric_label.setText("Metric: N/A")
            self._update_debug_preview(None, {})
            self._update_state("watching", {"message": "Waiting for camera feed"})
            return

        height, width = frame.shape[:2]
        self._config["camera"]["resolution"] = [width, height]
        self._last_frame = frame.copy()

        now = time.monotonic()

        idle_cfg = self._config["trigger"].get("idle_mode", {})
        interval = max(float(idle_cfg.get("interval_seconds", 2.0)), 0.0)
        idle_enabled = idle_cfg.get("enabled", False)
        effective_interval = (
            max(interval, self._idle_min_interval_ms / 1000.0) if idle_enabled else interval
        )

        should_sample = True
        if idle_enabled and self._current_state != "triggered":
            if effective_interval > 0 and self._last_detection_check:
                should_sample = (now - self._last_detection_check) >= effective_interval
        if not self._current_detection_summary:
            should_sample = True

        if should_sample:
            detection_summary = self._evaluate_detection(frame)
            self._current_detection_summary = detection_summary
            self._last_detection_check = now
        else:
            detection_summary = self._current_detection_summary

        triggered_zones = []
        zones = deepcopy(self._config["trigger"]["zones"])
        for zone in zones:
            zone_id = zone["zone_id"]
            triggered = detection_summary.get(zone_id, False)
            if triggered:
                triggered_zones.append(zone.get("name", zone_id))
            zone["detection"] = {
                "triggered": triggered,
                "metric": detection_summary.get(f"{zone_id}_metric"),
            }

        time_since_last = now - self._last_detection_check if self._last_detection_check else 0.0
        time_until_next = max(0.0, effective_interval - time_since_last) if idle_enabled else 0.0

        if triggered_zones:
            message = "Triggered • " + ", ".join(triggered_zones)
            state = "triggered"
        elif idle_cfg.get("enabled", False):
            message = (
                f"Idle mode • next check in {time_until_next:.1f}s "
                f"(every {effective_interval:.1f}s)"
            )
            state = "idle"
        else:
            message = "Watching for triggers"
            state = "watching"

        metric_value = self._latest_metric_value(detection_summary)
        if metric_value is not None:
            self.metric_label.setText(f"Metric: {metric_value:.3f}")
        else:
            self.metric_label.setText("Metric: N/A")

        self.canvas.set_frame(_to_qimage(frame), (width, height))
        self.canvas.set_zones(zones, self.active_zone_id)
        self._update_debug_preview(self._last_frame, detection_summary)
        self.detection_status.setText(message)

        payload = {
            "message": message,
            "zones": triggered_zones,
            "interval_seconds": effective_interval,
            "configured_interval_seconds": interval,
            "metric": metric_value,
            "next_check_seconds": time_until_next,
        }
        self._update_state(state, payload)

    def _evaluate_detection(self, frame: np.ndarray) -> Dict[str, float]:
        """Compute detection metric for each zone."""
        zones = self._config["trigger"]["zones"]
        if not zones:
            return {}

        height, width = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        detection_summary: Dict[str, float] = {}

        metric_type = self._config["trigger"]["settings"].get("metric", "intensity")

        for zone in zones:
            polygon = zone.get("polygon", [])
            if len(polygon) < 3:
                continue

            pts = _normalized_polygon_to_pixels(polygon, width, height)
            if pts.size == 0:
                continue

            mask = np.zeros((height, width), dtype=np.uint8)
            cv2.fillPoly(mask, [pts], 255)

            if metric_type == "intensity":
                metric = cv2.mean(gray, mask=mask)[0] / 255.0
            elif metric_type == "green_channel":
                metric = cv2.mean(frame[:, :, 1], mask=mask)[0] / 255.0
            elif metric_type == "edge_density":
                edges = cv2.Canny(gray, 50, 150)
                masked_edges = cv2.bitwise_and(edges, edges, mask=mask)
                edge_pixels = np.count_nonzero(masked_edges)
                total_pixels = np.count_nonzero(mask)
                metric = edge_pixels / total_pixels if total_pixels else 0.0
            else:
                metric = cv2.mean(gray, mask=mask)[0] / 255.0

            detection_summary[f"{zone['zone_id']}_metric"] = metric

            threshold = _clamp(self._config["trigger"]["settings"].get("threshold", 0.55))
            invert = self._config["trigger"]["settings"].get("invert", False)

            triggered = metric <= threshold if invert else metric >= threshold
            detection_summary[zone["zone_id"]] = triggered

        return detection_summary

    def _latest_metric_value(self, detection_summary: Dict[str, float]) -> Optional[float]:
        for key in detection_summary:
            if key.endswith("_metric"):
                return detection_summary[key]
        return None

    # ------------------------------------------------------------------
    # Trigger settings callbacks
    def _on_trigger_name_changed(self, value: str):
        display_name = value.strip() or "Detection Zone"
        self._config["trigger"]["display_name"] = display_name
        self._config["name"] = display_name

    def _on_mode_changed(self, mode: str):
        self._config["trigger"]["mode"] = mode

    def _on_metric_changed(self, metric: str):
        self._config["trigger"]["settings"]["metric"] = metric

    def _on_vision_type_changed(self, index: int):
        value = self.vision_type_combo.itemData(index)
        if value is None:
            value = "basic_detection"
        self._config["trigger"]["vision_type"] = value

    def _on_threshold_changed(self, value: int):
        self._config["trigger"]["settings"]["threshold"] = value / 100.0

    def _on_sensitivity_changed(self, value: float):
        self._config["trigger"]["settings"]["sensitivity"] = value

    def _on_invert_toggled(self, checked: bool):
        self._config["trigger"]["settings"]["invert"] = checked

    def _on_hold_changed(self, value: float):
        self._config["trigger"]["settings"]["hold_time"] = value

    def _on_idle_toggle_changed(self, checked: bool):
        idle_cfg = self._config["trigger"].setdefault("idle_mode", {})
        idle_cfg["enabled"] = checked
        if not idle_cfg.get("interval_seconds"):
            idle_cfg["interval_seconds"] = 2.0
        self.idle_interval_spin.setEnabled(checked)
        self._apply_idle_toggle_style(checked)
        if checked:
            self._last_detection_check = 0.0
        interval = idle_cfg.get("interval_seconds", 2.0)
        message = "Idle mode" if checked else "Watching for triggers"
        if self._current_state != "triggered":
            self._update_state("idle" if checked else "watching", {
                "message": message,
                "interval_seconds": interval,
            })

    def _on_idle_interval_changed(self, value: float):
        idle_cfg = self._config["trigger"].setdefault("idle_mode", {})
        idle_cfg["interval_seconds"] = value
        if idle_cfg.get("enabled", False):
            self._last_detection_check = 0.0
            if self._current_state != "triggered":
                self._update_state("idle", {
                    "message": f"Idle mode • next check in {value:.1f}s (every {value:.1f}s)",
                    "interval_seconds": value,
                })
            else:
                self._adjust_frame_timer(self._current_state, value)

    def _on_debug_toggled(self, checked: bool):
        if not checked:
            self.debug_preview_label.setPixmap(QPixmap())
            self.debug_preview_label.setText("Enable debug preview to visualize threshold checks.")
            return
        self._update_debug_preview(self._last_frame, self._current_detection_summary)

    def _update_debug_preview(self, frame: Optional[np.ndarray], detection_summary: Dict[str, float]):
        if not self.debug_toggle.isChecked():
            return
        if frame is None:
            self.debug_preview_label.setPixmap(QPixmap())
            self.debug_preview_label.setText("Waiting for camera frame...")
            return
        zones = self._config["trigger"].get("zones", [])
        if not zones:
            self.debug_preview_label.setPixmap(QPixmap())
            self.debug_preview_label.setText("Add a draw area to view debug preview.")
            return

        overlay = frame.copy()
        height, width = overlay.shape[:2]
        threshold = _clamp(self._config["trigger"]["settings"].get("threshold", 0.55))

        for zone in zones:
            polygon = zone.get("polygon", [])
            if len(polygon) < 3:
                continue
            pts = _normalized_polygon_to_pixels(polygon, width, height)
            if pts.size == 0:
                continue
            triggered = detection_summary.get(zone.get("zone_id", ""), False)
            metric = detection_summary.get(f"{zone.get('zone_id')}_metric")
            color = (67, 160, 71) if triggered else (198, 40, 40)

            mask = np.zeros_like(overlay)
            cv2.fillPoly(mask, [pts], color)
            overlay = cv2.addWeighted(overlay, 1.0, mask, 0.32, 0)
            cv2.polylines(overlay, [pts], True, color, 2)

            if metric is not None:
                comparator = "≥" if triggered else "<"
                text = f"{metric:.2f} {comparator} {threshold:.2f}"
            else:
                text = f"Threshold {threshold:.2f}"
            text_start = (max(0, pts[0][0] + 6), max(22, pts[0][1] + 18))
            cv2.putText(overlay, text, text_start, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)

        pixmap = QPixmap.fromImage(_to_qimage(overlay))
        target_width = max(20, self.debug_preview_label.width() - 12)
        target_height = max(20, self.debug_preview_label.height() - 12)
        pixmap = pixmap.scaled(target_width, target_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.debug_preview_label.setPixmap(pixmap)
        self.debug_preview_label.setText("")

    # ------------------------------------------------------------------
    # Zone management

    # ------------------------------------------------------------------
    # Lifecycle helpers
    def shutdown(self):
        if self.frame_timer.isActive():
            self.frame_timer.stop()
        self.camera_stream.close()

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Dialog and standalone window


class VisionConfigDialog(QDialog):
    """Modal dialog wrapping the designer widget."""

    state_changed = Signal(str, dict)

    def __init__(
        self,
        parent=None,
        step_data: Optional[Dict] = None,
        system_config: Optional[Dict] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Configure Vision Trigger")
        self.setModal(True)
        self.setFixedSize(1024, 600)

        config_source = system_config if system_config is not None else _load_system_config()
        self.designer = VisionDesignerWidget(
            self,
            step_data or create_default_vision_config(),
            config_source,
        )
        self.designer.state_changed.connect(self.state_changed)

        layout = QVBoxLayout(self)
        layout.addWidget(self.designer)

        button_row = QHBoxLayout()
        button_row.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(42)
        self.cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save Vision Step")
        self.save_btn.setMinimumHeight(42)
        self.save_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; }")
        self.save_btn.clicked.connect(self.accept)
        button_row.addWidget(self.save_btn)

        layout.addLayout(button_row)

    def get_step_data(self) -> Dict:
        return self.designer.get_config()

    def accept(self):
        self.designer.shutdown()
        super().accept()

    def reject(self):
        self.designer.shutdown()
        super().reject()


class VisionDesignerWindow(QWidget):
    """Standalone window to test the designer without loading full app."""

    def __init__(
        self,
        step_data: Optional[Dict] = None,
        system_config: Optional[Dict] = None,
    ):
        super().__init__()
        self.setWindowTitle("Vision Trigger Designer")
        self.setFixedSize(1024, 600)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.header = QLabel("Vision Trigger Designer")
        self.header.setAlignment(Qt.AlignCenter)
        self.header.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff; padding: 4px;")
        layout.addWidget(self.header)

        config_source = system_config if system_config is not None else _load_system_config()
        self.designer = VisionDesignerWidget(self, step_data or create_default_vision_config(), config_source)
        self.designer.setMinimumHeight(520)
        layout.addWidget(self.designer, stretch=1)

        info_bar = QHBoxLayout()
        info_bar.addStretch()
        export_btn = QPushButton("Export to Console")
        export_btn.clicked.connect(self._print_config)
        export_btn.setMaximumHeight(32)
        info_bar.addWidget(export_btn)
        layout.addLayout(info_bar)

        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                color: #f5f5f5;
            }
            QGroupBox {
                border: 2px solid #3a3a3a;
                border-radius: 8px;
                margin-top: 12px;
                padding: 12px;
            }
        """)

    def _print_config(self):
        config = self.designer.get_config()
        import json

        print("[VISION] Current configuration:")
        print(json.dumps(config, indent=2))

    def closeEvent(self, event):
        self.designer.shutdown()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Standalone execution helper


def run_standalone():
    """Allow running `python -m vision_ui.designer` for quick testing."""
    app = QApplication.instance() or QApplication(sys.argv)
    window = VisionDesignerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_standalone()
