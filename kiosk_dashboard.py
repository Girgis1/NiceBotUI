"""
Kiosk Dashboard - Main robot control interface
Safety-first design with always-responsive UI
"""

import sys
import os
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFrame, QTextEdit, QSlider, QStackedWidget, QDialog
)
from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QFont, QImage, QPixmap

try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    cv2 = None
    np = None

from kiosk_styles import Colors, Styles, StatusIndicator
from robot_worker import RobotWorker

# Paths
ROOT = Path(__file__).parent


class StatusDot(QLabel):
    """Status indicator dot"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.connected = False
        self.warning = False
        self.disabled = False
        self.setFixedSize(20, 20)
        self.update_style()
    
    def set_connected(self, connected: bool):
        """Set connected state"""
        self.connected = connected
        self.warning = False
        self.disabled = False
        self.update_style()
    
    def set_warning(self):
        """Set warning state"""
        self.connected = False
        self.warning = True
        self.disabled = False
        self.update_style()
    
    def set_disabled(self):
        """Set disabled state"""
        self.connected = False
        self.warning = False
        self.disabled = True
        self.update_style()
    
    def update_style(self):
        """Update visual style"""
        self.setStyleSheet(StatusIndicator.get_style(
            connected=self.connected,
            warning=self.warning,
            disabled=self.disabled
        ))


class CameraPreviewTile(QFrame):
    """Small camera preview tile shown in the status bar when camera mode is active."""

    clicked = Signal(str)

    def __init__(self, camera_name: str, display_name: str, parent=None):
        super().__init__(parent)
        self.camera_name = camera_name
        self.display_name = display_name
        self.setObjectName(f"camera_tile_{camera_name}")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(60)
        self.setMinimumWidth(150)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self.preview_label = QLabel("No Feed")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("color: #b0b0b0; font-size: 11px;")
        self.preview_label.setScaledContents(True)
        self.preview_label.setFixedHeight(36)
        layout.addWidget(self.preview_label, stretch=1)

        self.name_label = QLabel(display_name)
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: bold;")
        layout.addWidget(self.name_label)

        self.set_status("offline")

    def set_status(self, status: str):
        """Update border colour based on camera status."""
        colors = {
            "triggered": "#4CAF50",
            "idle": "#FF9800",
            "nominal": "#4FC3F7",
            "offline": "#F44336",
            "no_vision": "#9E9E9E"
        }
        color = colors.get(status, "#9E9E9E")
        self.setStyleSheet(f"""
            #{self.objectName()} {{
                border: 4px solid {color};
                border-radius: 14px;
                background-color: #1f1f1f;
            }}
        """)

    def update_pixmap(self, pixmap: Optional[QPixmap]):
        if pixmap is None:
            self.preview_label.setText("No Feed")
            self.preview_label.setPixmap(QPixmap())
        else:
            self.preview_label.setPixmap(pixmap)
            self.preview_label.setText("")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.camera_name)
        super().mousePressEvent(event)


class CameraDetailDialog(QDialog):
    """Full camera view dialog with live preview."""

    def __init__(self, camera_name: str, camera_config: dict, vision_zones: List[dict],
                 render_callback, parent=None):
        super().__init__(parent)
        self.camera_name = camera_name
        self.camera_config = camera_config
        self.vision_zones = vision_zones
        self.render_callback = render_callback

        self.setWindowTitle(f"Camera Preview - {camera_name}")
        self.setModal(True)
        self.resize(960, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
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
        self.timer.timeout.connect(self._update_frame)
        self.capture = None

        self._open_camera()

    def _open_camera(self):
        if cv2 is None:
            self.status_label.setText("OpenCV is not available. Install opencv-python to enable preview.")
            return

        identifier = self.camera_config.get("index_or_path", 0)
        self.capture = cv2.VideoCapture(identifier)
        if self.capture and self.capture.isOpened():
            width = self.camera_config.get("width", 640)
            height = self.camera_config.get("height", 480)
            fps = self.camera_config.get("fps", 30)
            self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self.capture.set(cv2.CAP_PROP_FPS, fps)
            self.status_label.setText("")
            self.timer.start(80)
        else:
            self.status_label.setText("Camera unavailable.")
            self.capture = None

    def _update_frame(self):
        if self.capture is None:
            return
        ret, frame = self.capture.read()
        if not ret or frame is None:
            self.status_label.setText("No frame data.")
            return

        render_frame, status = self.render_callback(self.camera_name, frame, self.vision_zones)
        rgb = cv2.cvtColor(render_frame, cv2.COLOR_BGR2RGB)
        height, width, channel = rgb.shape
        bytes_per_line = channel * width
        image = QImage(rgb.data, width, height, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(image)
        self.preview_label.setPixmap(pixmap)

        status_text = {
            "triggered": "Active detection",
            "idle": "Monitoring",
            "nominal": "Live preview",
            "offline": "Offline",
            "no_vision": "No vision zones configured"
        }
        self.status_label.setText(status_text.get(status, ""))

    def closeEvent(self, event):
        self.timer.stop()
        if self.capture:
            try:
                self.capture.release()
            except Exception:
                pass
            self.capture = None
        super().closeEvent(event)


class KioskDashboard(QWidget):
    """
    Main dashboard screen with safety-first design
    
    CRITICAL SAFETY FEATURES:
    - Robot operations run in separate QThread (RobotWorker)
    - STOP button always enabled and responsive (< 100ms)
    - UI thread never blocks
    - Proper emergency stop escalation
    """
    
    # Signals
    config_changed = Signal(dict)
    
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config

        # State
        control_cfg = self.config.setdefault("control", {})
        self.master_speed = float(control_cfg.get("speed_multiplier", 1.0))
        if not 0.1 <= self.master_speed <= 1.2:
            self.master_speed = 1.0
            control_cfg["speed_multiplier"] = self.master_speed
        self.loop_enabled = control_cfg.get("loop_enabled", True)
        control_cfg["loop_enabled"] = self.loop_enabled

        self.is_running = False
        self.worker = None
        self.start_time = None
        self.elapsed_seconds = 0
        self._camera_caps = {}
        self.preview_caps: Dict[str, Optional['cv2.VideoCapture']] = {}
        self.camera_view_active = False
        self.camera_tiles: Dict[str, CameraPreviewTile] = {}
        self.camera_order = list(self.config.get("cameras", {}).keys())
        self.vision_zones = self._load_vision_zones()

        self.camera_preview_timer = QTimer(self)
        self.camera_preview_timer.timeout.connect(self.update_camera_previews)
        
        # Initialize UI
        self.init_ui()
        
        # Start background timers
        self.setup_timers()
        
        # Initial connection check
        self.check_connections()
    
    def init_ui(self):
        """Initialize user interface"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # === TOP STATUS BAR (80px) ===
        status_bar = self.create_status_bar()
        layout.addWidget(status_bar)
        
        # === RUN SELECTOR (120px) ===
        run_selector = self.create_run_selector()
        layout.addWidget(run_selector)
        
        # === MAIN CONTROLS (180px) ===
        controls = self.create_main_controls()
        layout.addLayout(controls)
        
        # === BOTTOM AREA ===
        bottom = self.create_bottom_area()
        layout.addLayout(bottom)
    
    def create_status_bar(self):
        """Create top status bar with indicators, camera toggle, and status text."""
        bar = QFrame()
        bar.setFixedHeight(90)
        bar.setStyleSheet(Styles.get_status_panel_style())

        layout = QHBoxLayout(bar)
        layout.setSpacing(18)
        layout.setContentsMargins(20, 12, 20, 12)

        # Indicator widget (robot + cameras + runtime)
        indicators_widget = QWidget()
        indicators_layout = QHBoxLayout(indicators_widget)
        indicators_layout.setSpacing(18)
        indicators_layout.setContentsMargins(0, 0, 0, 0)

        robot_group = QHBoxLayout()
        robot_group.setSpacing(6)
        robot_label = QLabel("Robot")
        robot_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 12px;")
        robot_group.addWidget(robot_label)

        self.robot_dot1 = StatusDot()
        robot_group.addWidget(self.robot_dot1)
        self.robot_dot2 = StatusDot()
        self.robot_dot2.set_disabled()
        robot_group.addWidget(self.robot_dot2)

        indicators_layout.addLayout(robot_group)

        camera_group = QHBoxLayout()
        camera_group.setSpacing(6)
        camera_label = QLabel("Cameras")
        camera_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 12px;")
        camera_group.addWidget(camera_label)

        self.camera_dots = []
        for idx in range(3):
            dot = StatusDot()
            self.camera_dots.append(dot)
            camera_group.addWidget(dot)
            if idx == 0:
                self.camera_dot1 = dot
            elif idx == 1:
                self.camera_dot2 = dot
            elif idx == 2:
                self.camera_dot3 = dot

        indicators_layout.addLayout(camera_group)

        self.time_label = QLabel("00:00")
        self.time_label.setStyleSheet(f"""
            color: {Colors.SUCCESS};
            font-size: 16px;
            font-weight: bold;
            font-family: monospace;
        """)
        indicators_layout.addWidget(self.time_label)

        # Camera preview stack (indicators vs thumbnails)
        self.camera_preview_widget = self.create_camera_preview_widget()
        self.status_stack = QStackedWidget()
        self.status_stack.addWidget(indicators_widget)
        self.status_stack.addWidget(self.camera_preview_widget)
        self.status_stack.setCurrentIndex(0)

        layout.addWidget(self.status_stack, stretch=4)

        # Camera toggle button
        self.camera_toggle_btn = QPushButton("📷 Cameras")
        self.camera_toggle_btn.setCheckable(True)
        self.camera_toggle_btn.setMinimumHeight(56)
        self.camera_toggle_btn.setStyleSheet(
            Styles.get_large_button(Colors.BG_LIGHT, Colors.BG_MEDIUM)
        )
        self.camera_toggle_btn.toggled.connect(self.on_camera_toggle)
        layout.addWidget(self.camera_toggle_btn)

        # Status message area (kept at far right)
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(Styles.get_status_label_style())
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.status_label, stretch=3)

        return bar

    def create_camera_preview_widget(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("cameraPreviewFrame")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.camera_tiles = {}

        if not self.camera_order:
            placeholder = QLabel("No cameras configured")
            placeholder.setStyleSheet("color: #909090; font-size: 13px;")
            placeholder.setAlignment(Qt.AlignCenter)
            layout.addWidget(placeholder)
            return frame

        for name in self.camera_order:
            display_name = name.replace("_", " ").title()
            tile = CameraPreviewTile(name, display_name)
            tile.clicked.connect(self.on_camera_tile_clicked)
            layout.addWidget(tile)
            self.camera_tiles[name] = tile
            default_state = "idle" if name in self.vision_zones else "nominal"
            tile.set_status(default_state)

        layout.addStretch(1)
        return frame
    
    def create_run_selector(self):
        """Create task selector with loop toggle and master speed control."""
        frame = QFrame()
        frame.setFixedHeight(150)
        frame.setStyleSheet(Styles.get_status_panel_style())

        layout = QHBoxLayout(frame)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 12, 20, 12)

        # Task selection column
        task_column = QVBoxLayout()
        task_column.setSpacing(8)
        task_column.setContentsMargins(0, 0, 0, 0)

        task_label = QLabel("Task")
        task_label.setStyleSheet(Styles.get_label_style(size="large", bold=True))
        task_column.addWidget(task_label)

        self.run_combo = QComboBox()
        self.run_combo.setStyleSheet(Styles.get_dropdown_style())
        self.run_combo.currentTextChanged.connect(self.on_run_selection_changed)
        task_column.addWidget(self.run_combo)

        layout.addLayout(task_column, stretch=3)

        # Control column (loop + speed)
        control_column = QVBoxLayout()
        control_column.setSpacing(12)
        control_column.setContentsMargins(0, 0, 0, 0)

        # Loop toggle
        self.loop_toggle = QPushButton()
        self.loop_toggle.setCheckable(True)
        self.loop_toggle.setMinimumHeight(80)
        self.loop_toggle.toggled.connect(self.on_loop_toggle_changed)
        control_column.addWidget(self.loop_toggle)

        # Master speed slider
        speed_container = QVBoxLayout()
        speed_container.setSpacing(4)
        speed_label = QLabel("Master Speed")
        speed_label.setStyleSheet("color: #f0f0f0; font-size: 16px; font-weight: bold;")
        speed_container.addWidget(speed_label)

        value_row = QHBoxLayout()
        value_row.setSpacing(6)
        self.speed_value_label = QLabel("")
        self.speed_value_label.setStyleSheet("color: #f0f0f0; font-size: 20px; font-weight: bold;")
        value_row.addWidget(self.speed_value_label)
        value_row.addStretch(1)
        speed_container.addLayout(value_row)

        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(10, 120)
        self.speed_slider.setSingleStep(5)
        self.speed_slider.setPageStep(5)
        self.speed_slider.setTickPosition(QSlider.TicksBelow)
        self.speed_slider.setTickInterval(5)
        self.speed_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #444444;
                height: 14px;
                background: #2e2e2e;
                border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: #4CAF50;
                border-radius: 7px;
            }
            QSlider::add-page:horizontal {
                background: #555555;
                border-radius: 7px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                border: 1px solid #4CAF50;
                width: 28px;
                height: 28px;
                margin: -8px 0;
                border-radius: 14px;
            }
        """)
        self.speed_slider.valueChanged.connect(self.on_speed_slider_changed)
        speed_container.addWidget(self.speed_slider)

        control_column.addLayout(speed_container)
        layout.addLayout(control_column, stretch=2)

        # Populate dropdown and initialise controls
        self.refresh_run_selector()
        self.loop_toggle.setChecked(self.loop_enabled)
        self._refresh_loop_toggle_style()

        initial_speed = int(round(self.master_speed * 100))
        self.speed_slider.blockSignals(True)
        self.speed_slider.setValue(initial_speed)
        self.speed_slider.blockSignals(False)
        self.on_speed_slider_changed(initial_speed)

        return frame

    def _refresh_loop_toggle_style(self):
        if self.loop_enabled:
            self.loop_toggle.setText("Loop On")
            self.loop_toggle.setStyleSheet(Styles.get_large_button(Colors.SUCCESS, Colors.SUCCESS_HOVER))
        else:
            self.loop_toggle.setText("Loop Off")
            self.loop_toggle.setStyleSheet(Styles.get_large_button(Colors.BG_LIGHT, Colors.BG_MEDIUM))

    def on_loop_toggle_changed(self, checked: bool):
        self.loop_enabled = checked
        self._refresh_loop_toggle_style()
        control_cfg = self.config.setdefault("control", {})
        control_cfg["loop_enabled"] = checked
        state_text = "Loop enabled" if checked else "Loop disabled"
        self.log(state_text)
        self.config_changed.emit(self.config)

    def on_speed_slider_changed(self, value: int):
        aligned = max(10, min(120, 5 * round(value / 5)))
        if aligned != value:
            self.speed_slider.blockSignals(True)
            self.speed_slider.setValue(aligned)
            self.speed_slider.blockSignals(False)

        self.master_speed = aligned / 100.0
        self.speed_value_label.setText(f"{aligned}%")

        control_cfg = self.config.setdefault("control", {})
        control_cfg["speed_multiplier"] = self.master_speed
        self.config_changed.emit(self.config)
    
    def create_main_controls(self):
        """Create main control buttons"""
        layout = QHBoxLayout()
        layout.setSpacing(15)
        
        # START/STOP button (giant, always responsive)
        self.start_stop_btn = QPushButton("START")
        self.start_stop_btn.setCheckable(True)
        self.start_stop_btn.setStyleSheet(
            Styles.get_giant_button(Colors.SUCCESS, Colors.SUCCESS_HOVER)
        )
        # CRITICAL: Button stays enabled during operation for emergency stop
        self.start_stop_btn.clicked.connect(self.toggle_start_stop)
        layout.addWidget(self.start_stop_btn, stretch=3)
        
        # HOME button (square)
        self.home_btn = QPushButton("⌂")
        self.home_btn.setFixedSize(150, 150)
        self.home_btn.setStyleSheet(
            Styles.get_giant_button(Colors.INFO, Colors.INFO_HOVER)
        )
        self.home_btn.clicked.connect(self.go_home)
        layout.addWidget(self.home_btn)
        
        return layout

    # ------------------------------------------------------------------
    # Vision + camera preview helpers

    def _load_vision_zones(self) -> Dict[str, List[dict]]:
        zones_map: Dict[str, List[dict]] = {}
        sequences_dir = ROOT / "data" / "sequences"
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
                        "metric": metric,
                        "color": zone.get("color")
                    })

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
        normalized_source = None
        if source_id:
            normalized_source = self._normalize_camera_identifier(source_id)
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
        # Default intensity metric
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

    def _ensure_preview_cap(self, camera_name: str):
        if cv2 is None:
            return None
        cap = self.preview_caps.get(camera_name)
        if cap is None or not cap or not cap.isOpened():
            cfg = self.config.get("cameras", {}).get(camera_name, {})
            identifier = cfg.get("index_or_path", 0)
            cap = cv2.VideoCapture(identifier)
            if not cap or not cap.isOpened():
                self.preview_caps[camera_name] = None
                return None
            width = min(640, int(cfg.get("width", 640)))
            height = min(480, int(cfg.get("height", 480)))
            fps = max(5, min(15, int(cfg.get("fps", 30))))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_FPS, fps)
            self.preview_caps[camera_name] = cap
        return cap

    def _release_preview_caps(self):
        for cap in list(self.preview_caps.values()):
            if cap is None:
                continue
            try:
                cap.release()
            except Exception:
                pass
        self.preview_caps.clear()

    def on_camera_toggle(self, checked: bool):
        self.camera_toggle_btn.setText("Close Cameras" if checked else "📷 Cameras")
        if checked:
            self.enter_camera_mode()
        else:
            self.exit_camera_mode()

    def enter_camera_mode(self):
        if self.camera_view_active:
            return
        if cv2 is None:
            self.log("Camera preview unavailable (OpenCV not installed)")
            self.camera_toggle_btn.blockSignals(True)
            self.camera_toggle_btn.setChecked(False)
            self.camera_toggle_btn.blockSignals(False)
            return

        self.camera_view_active = True
        self.status_stack.setCurrentIndex(1)
        self.camera_preview_timer.start(300)
        self.update_camera_previews()

    def exit_camera_mode(self):
        if not self.camera_view_active:
            return
        self.camera_view_active = False
        self.status_stack.setCurrentIndex(0)
        self.camera_preview_timer.stop()
        self._release_preview_caps()

        for name, tile in self.camera_tiles.items():
            tile.update_pixmap(None)
            if name in self.vision_zones:
                tile.set_status("idle")
            else:
                tile.set_status("nominal")

    def update_camera_previews(self):
        if not self.camera_view_active or cv2 is None or np is None:
            return

        for name in self.camera_order:
            tile = self.camera_tiles.get(name)
            if tile is None:
                continue

            cap = self._ensure_preview_cap(name)
            if cap is None:
                tile.update_pixmap(None)
                tile.set_status("offline")
                continue

            ret, frame = cap.read()
            if not ret or frame is None:
                tile.update_pixmap(None)
                tile.set_status("offline")
                continue

            scaled_frame = cv2.resize(frame, (400, 225))
            render_frame, status = self._render_camera_frame(name, scaled_frame.copy())

            display_frame = cv2.resize(render_frame, (220, 124))
            rgb = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
            height, width, channel = rgb.shape
            image = QImage(rgb.data, width, height, channel * width, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(image)
            tile.update_pixmap(pixmap)

            if status not in {"triggered", "idle"}:
                status = "nominal" if status != "offline" else "offline"
            tile.set_status(status)

    def on_camera_tile_clicked(self, camera_name: str):
        camera_cfg = self.config.get("cameras", {}).get(camera_name)
        if not camera_cfg:
            return
        zones = self.vision_zones.get(camera_name, [])
        dialog = CameraDetailDialog(camera_name, camera_cfg, zones, self._render_camera_frame, self)
        dialog.exec()
    
    def create_bottom_area(self):
        """Create bottom area with settings, live record, and log"""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Button row
        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        
        # Settings button
        self.settings_btn = QPushButton("⚙️\nSettings")
        self.settings_btn.setStyleSheet(
            Styles.get_large_button(Colors.BG_LIGHT, Colors.BG_MEDIUM)
        )
        self.settings_btn.clicked.connect(self.open_settings)
        button_row.addWidget(self.settings_btn)
        
        button_row.addStretch()
        
        # Live Record button
        self.live_record_btn = QPushButton("🔴\nLive Record")
        self.live_record_btn.setStyleSheet(
            Styles.get_large_button(Colors.ERROR, Colors.ERROR_HOVER)
        )
        self.live_record_btn.clicked.connect(self.open_live_record)
        button_row.addWidget(self.live_record_btn)
        
        layout.addLayout(button_row)
        
        # Minimal log display (60px, last 2 lines only)
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFixedHeight(60)
        self.log_display.setStyleSheet(Styles.get_log_display_style())
        self.log_display.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self.log_display)
        
        # Initial log message
        self.log("System ready")
        
        return layout
    
    def setup_timers(self):
        """Setup background timers"""
        # Connection check timer (every 5 seconds)
        self.connection_timer = QTimer()
        self.connection_timer.timeout.connect(self.check_connections)
        self.connection_timer.start(5000)
        
        # Elapsed time timer (every second when running)
        self.elapsed_timer = QTimer()
        self.elapsed_timer.timeout.connect(self.update_elapsed_time)
    
    def refresh_run_selector(self):
        """Populate RUN selector with models and live recordings"""
        self.run_combo.blockSignals(True)
        self.run_combo.clear()
        
        # Add placeholder
        self.run_combo.addItem("-- Select --")
        
        # Scan for trained models
        try:
            base_path = Path(self.config.get("policy", {}).get("base_path", "outputs/train"))
            if base_path.exists():
                for model_dir in sorted(base_path.iterdir()):
                    if model_dir.is_dir():
                        checkpoints_dir = model_dir / "checkpoints" / "last" / "pretrained_model"
                        if checkpoints_dir.exists():
                            self.run_combo.addItem(f"🤖 Model: {model_dir.name}")
        except Exception as e:
            print(f"[WARN] Failed to scan models: {e}")
        
        # Scan for live recordings
        try:
            from utils.actions_manager import ActionsManager
            actions_mgr = ActionsManager()
            for name in actions_mgr.list_live_recordings():
                self.run_combo.addItem(f"🔴 Recording: {name}")
        except Exception as e:
            print(f"[WARN] Failed to scan recordings: {e}")

        self.run_combo.blockSignals(False)
    
    def on_run_selection_changed(self, text):
        """Handle RUN selector change"""
        if text.startswith("🤖 Model:"):
            model_name = text.replace("🤖 Model: ", "")
            self.log(f"Selected model: {model_name}")
            # Update config with model path
            try:
                base_path = Path(self.config["policy"]["base_path"])
                model_path = base_path / model_name / "checkpoints" / "last" / "pretrained_model"
                self.config["policy"]["path"] = str(model_path)
            except Exception as e:
                self.log(f"ERROR: {e}")
        elif text.startswith("🔴 Recording:"):
            recording_name = text.replace("🔴 Recording: ", "")
            self.log(f"Selected recording: {recording_name}")
    
    def check_connections(self):
        """Check robot and camera connections (non-blocking)"""
        # Don't check during operation
        if self.is_running:
            return
        
        # Check robot port
        robot_port = self.config.get("robot", {}).get("port", "")
        if os.path.exists(robot_port):
            self.robot_dot1.set_connected(True)
        else:
            self.robot_dot1.set_connected(False)

        # Check cameras
        cameras = list(self.config.get("cameras", {}).items())
        dots = [self.camera_dot1, self.camera_dot2, self.camera_dot3]

        active_names = set()
        for idx, dot in enumerate(dots):
            if idx >= len(cameras):
                dot.set_disabled()
                continue

            name, cam_cfg = cameras[idx]
            active_names.add(name)
            identifier = cam_cfg.get("index_or_path", 0)

            if cv2 is None:
                dot.set_disabled()
                if not self.camera_view_active and name in self.camera_tiles:
                    self.camera_tiles[name].set_status("offline")
                continue

            cap = self._camera_caps.get(name)
            if cap is None or not cap.isOpened():
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
                cap = cv2.VideoCapture(identifier)
                if cap and cap.isOpened():
                    self._camera_caps[name] = cap
                else:
                    self._camera_caps[name] = None

            cap_ref = self._camera_caps.get(name)
            if cap_ref is not None and cap_ref and cap_ref.isOpened():
                dot.set_connected(True)
                if not self.camera_view_active and name in self.camera_tiles:
                    default_state = "idle" if name in self.vision_zones else "nominal"
                    self.camera_tiles[name].set_status(default_state)
            else:
                dot.set_connected(False)
                if not self.camera_view_active and name in self.camera_tiles:
                    self.camera_tiles[name].set_status("offline")
                if cap_ref is not None:
                    try:
                        cap_ref.release()
                    except Exception:
                        pass
                    self._camera_caps[name] = None

        # Disable dots for remaining indicators
        if len(cameras) < len(dots):
            for dot in dots[len(cameras):]:
                dot.set_disabled()

        # Release unused camera handles
        for name, cap in list(self._camera_caps.items()):
            if name not in active_names or cap is None:
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
                if name not in active_names:
                    self._camera_caps.pop(name, None)

    def _release_camera_handles(self):
        for cap in list(self._camera_caps.values()):
            if cap is None:
                continue
            try:
                cap.release()
            except Exception:
                pass
        self._camera_caps.clear()

    def closeEvent(self, event):
        self._release_camera_handles()
        self._release_preview_caps()
        super().closeEvent(event)
    
    def toggle_start_stop(self):
        """Toggle START/STOP - ALWAYS RESPONSIVE"""
        if self.start_stop_btn.isChecked():
            self.start_operation()
        else:
            self.stop_operation()
    
    def start_operation(self):
        """Start robot operation in separate thread"""
        # Validate selection
        selected = self.run_combo.currentText()
        if selected.startswith("--"):
            self.log("ERROR: No item selected")
            self.start_stop_btn.setChecked(False)
            return
        
        # Update UI state
        self.is_running = True
        self.start_stop_btn.setText("STOP")
        self.start_stop_btn.setStyleSheet(
            Styles.get_giant_button(Colors.ERROR, Colors.ERROR_HOVER)
        )
        self.status_label.setText("Starting...")
        
        # Disable controls that shouldn't be changed during operation
        self.run_combo.setEnabled(False)
        self.home_btn.setEnabled(False)
        self.settings_btn.setEnabled(False)
        self.live_record_btn.setEnabled(False)
        
        # Start elapsed time
        self.start_time = datetime.now()
        self.elapsed_seconds = 0
        self.elapsed_timer.start(1000)
        
        self.log(f"Starting: {selected}")
        self.log(f"Loop {'ON' if self.loop_enabled else 'OFF'} • Speed {int(self.master_speed * 100)}%")
        
        # Create and start worker thread
        # Prevent double-start if a worker is still active
        if self.worker and self.worker.isRunning():
            self.log("WARN: Worker already running")
            return

        self.worker = RobotWorker(self.config)

        # Connect signals
        self.worker.status_update.connect(self.on_status_update)
        self.worker.log_message.connect(self.on_log_message)
        self.worker.progress_update.connect(self.on_progress_update)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.run_completed.connect(self.on_run_completed)
        self.worker.finished.connect(self.on_worker_finished)

        # Start worker (runs in separate thread - UI stays responsive)
        try:
            self.worker.start()
        except Exception as exc:
            self.log(f"ERROR: Failed to start worker: {exc}")
            self.status_label.setText("⚠️ Start failed")
            self.reset_ui_after_stop()

    def stop_operation(self):
        """
        EMERGENCY STOP - Maximum response time: 100ms
        
        CRITICAL SAFETY:
        - Called immediately when STOP button pressed
        - Stops worker thread with escalating signals
        - Visual feedback to operator
        """
        self.log("STOPPING...")
        self.status_label.setText("⚠️ STOPPING...")
        
        # Stop worker immediately
        if self.worker and self.worker.isRunning():
            self.worker.stop()  # Sets flag and kills subprocess
            # Don't wait here - let run_completed handle cleanup
        else:
            # No worker running, just reset UI
            self.reset_ui_after_stop()
    
    def emergency_stop(self):
        """Emergency stop called on application close"""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(2000)  # Wait max 2 seconds
    
    def reset_ui_after_stop(self):
        """Reset UI to ready state"""
        self.is_running = False
        self.start_stop_btn.setChecked(False)
        self.start_stop_btn.setText("START")
        self.start_stop_btn.setStyleSheet(
            Styles.get_giant_button(Colors.SUCCESS, Colors.SUCCESS_HOVER)
        )
        self.status_label.setText("Ready")

        # Re-enable controls
        self.run_combo.setEnabled(True)
        self.home_btn.setEnabled(True)
        self.settings_btn.setEnabled(True)
        self.live_record_btn.setEnabled(True)

        # Stop elapsed timer
        self.elapsed_timer.stop()
        self.time_label.setText("00:00")

        # Resume connection checking
        self.check_connections()

        # Clear worker reference when stopped and thread is no longer running
        if self.worker and not self.worker.isRunning():
            self.worker = None

    def go_home(self):
        """Move robot to home position"""
        self.log("Moving to home...")
        self.status_label.setText("Moving to home...")
        
        try:
            # Call HomePos.py in separate process
            env = os.environ.copy()
            env["LEROBOT_SPEED_MULTIPLIER"] = f"{self.master_speed:.2f}"
            result = subprocess.run(
                [sys.executable, str(ROOT / "HomePos.py"), "--go"],
                capture_output=True,
                text=True,
                timeout=30,
                env=env
            )
            
            if result.returncode == 0:
                self.log("✓ Home position reached")
                self.status_label.setText("Ready")
            else:
                self.log(f"ERROR: Home failed")
                self.status_label.setText("⚠️ Home failed")
        except subprocess.TimeoutExpired:
            self.log("ERROR: Home timeout")
            self.status_label.setText("⚠️ Home timeout")
        except Exception as e:
            self.log(f"ERROR: {e}")
            self.status_label.setText("⚠️ Home error")
    
    def open_settings(self):
        """Open settings modal"""
        self.log("Opening settings...")
        # TODO: Implement settings modal
        from kiosk_settings import SettingsModal
        modal = SettingsModal(self.config, self)
        if modal.exec():
            self.config = modal.get_config()
            self.config_changed.emit(self.config)
            self.log("Settings saved")
    
    def open_live_record(self):
        """Open live record modal"""
        self.log("Opening live record...")
        # TODO: Implement live record modal
        from kiosk_live_record import LiveRecordModal
        modal = LiveRecordModal(self.config, self)
        if modal.exec():
            self.log("Recording saved")
            self.refresh_run_selector()
    
    def log(self, message: str):
        """Add message to log display (keeps last 2 lines)"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_display.append(f"[{timestamp}] {message}")
        
        # Keep only last 2 lines
        doc = self.log_display.document()
        while doc.lineCount() > 2:
            cursor = self.log_display.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.select(cursor.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()  # Remove newline
    
    # === Worker Signal Handlers ===
    
    def on_status_update(self, status: str):
        """Handle status update from worker"""
        self.status_label.setText(status)
    
    def on_log_message(self, level: str, message: str):
        """Handle log message from worker"""
        if level == "error":
            self.log(f"ERROR: {message}")
        elif level == "warning":
            self.log(f"WARN: {message}")
        else:
            self.log(message)
    
    def on_progress_update(self, current: int, total: int):
        """Handle progress update from worker"""
        self.status_label.setText(f"Episode {current}/{total}")
    
    def on_error(self, error_key: str, context: dict):
        """Handle error from worker"""
        error_detail = context.get('error') or context.get('stderr', '')
        if error_detail:
            self.log(f"ERROR: {error_key} - {error_detail}")
        else:
            self.log(f"ERROR: {error_key}")
        self.status_label.setText(f"⚠️ Error: {error_key}")
    
    def on_run_completed(self, success: bool, message: str):
        """Handle run completion from worker"""
        if success:
            self.log(f"✓ {message}")
            self.status_label.setText("✓ Complete")
        else:
            self.log(f"✗ {message}")
            self.status_label.setText("⚠️ Stopped")

        # Reset UI
        self.reset_ui_after_stop()

    def update_elapsed_time(self):
        """Update elapsed time display"""
        if self.start_time:
            self.elapsed_seconds = int((datetime.now() - self.start_time).total_seconds())
            minutes = self.elapsed_seconds // 60
            seconds = self.elapsed_seconds % 60
            self.time_label.setText(f"{minutes:02d}:{seconds:02d}")

    def on_worker_finished(self):
        """Ensure worker reference is cleared when thread finishes"""
        self.worker = None
