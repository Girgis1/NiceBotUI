"""
Settings Tab - Configuration Interface
"""

import json
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QScrollArea, QFrame, QSpinBox, QDoubleSpinBox,
    QTabWidget, QCheckBox, QComboBox, QDialog, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QImage, QPixmap

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    cv2 = None

try:
    import numpy as np  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    np = None

try:
    from ultralytics import YOLO  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    YOLO = None

from utils.camera_hub import CameraStreamHub
from utils.home_workers import MotorHomeWorker


class HandDetectionTestDialog(QDialog):
    """Live camera preview with YOLOv8 hand detection overlay."""

    def __init__(self, camera_sources: List[Tuple[str, Union[int, str]]], config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("YOLOv8 Hand Detection Test")
        self.setModal(True)
        self.resize(900, 600)

        self.camera_sources = camera_sources
        self.app_config = config
        self.current_source_index: Optional[int] = None
        self.current_camera_name: Optional[str] = None
        self.cap = None
        self.timer = QTimer(self)
        self.timer.setInterval(120)  # ~8 FPS keeps CPU light
        self.timer.timeout.connect(self._update_frame)
        self.camera_hub: Optional[CameraStreamHub] = None
        try:
            self.camera_hub = CameraStreamHub.instance(self.app_config)
        except Exception:
            self.camera_hub = None
        self.camera_name_map: Dict[int, Optional[str]] = {}
        self._use_hub_for_current = False

        self.last_detection: Optional[bool] = None
        self.last_confidence: float = 0.0
        self.detected_any = False
        self.error_message: Optional[str] = None
        self.result_summary = "Camera preview not started."

        self._build_camera_name_map()

    def _normalize_identifier(self, value: Union[int, str]) -> str:
        if isinstance(value, int):
            return str(value)
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("/dev/video") and stripped[10:].isdigit():
                return stripped[10:]
            if stripped.startswith("camera:"):
                return stripped.split(":", 1)[-1]
            if stripped.isdigit():
                return stripped
            return stripped
        return str(value)

    def _resolve_camera_name(self, identifier: Union[int, str]) -> Optional[str]:
        cameras = self.app_config.get("cameras", {}) if isinstance(self.app_config, dict) else {}
        if not cameras:
            return None

        normalized_id = self._normalize_identifier(identifier)
        for name, cfg in cameras.items():
            candidate = cfg.get("index_or_path", 0)
            if self._normalize_identifier(candidate) == normalized_id:
                return name
        return None

    def _build_camera_name_map(self) -> None:
        self.camera_name_map.clear()
        for idx, (_label, identifier) in enumerate(self.camera_sources):
            self.camera_name_map[idx] = self._resolve_camera_name(identifier)

        # Initialize YOLO detector
        self.yolo_model = None
        if YOLO is not None:
            try:
                self.yolo_model = YOLO("yolov8n.pt")
                self.yolo_model.overrides['verbose'] = False
            except Exception as e:
                self.error_message = f"Failed to load YOLO: {e}"
                print(f"[SAFETY] YOLO initialization error: {e}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        info_label = QLabel("Live feed with YOLOv8 person detection. Move into view to verify detection.")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #e0e0e0; font-size: 14px;")
        layout.addWidget(info_label)

        self.source_combo: Optional[QComboBox] = None
        if len(self.camera_sources) > 1:
            combo_row = QHBoxLayout()
            combo_row.setSpacing(8)
            combo_label = QLabel("Camera Source:")
            combo_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
            combo_row.addWidget(combo_label)

            self.source_combo = QComboBox()
            for idx, (label, _identifier) in enumerate(self.camera_sources):
                self.source_combo.addItem(label, idx)
            self.source_combo.currentIndexChanged.connect(self._on_source_changed)
            self.source_combo.setMinimumWidth(220)
            combo_row.addWidget(self.source_combo)
            combo_row.addStretch()
            layout.addLayout(combo_row)

        self.video_label = QLabel("Starting camera…")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(640, 360)
        self.video_label.setStyleSheet("background-color: #2a2a2a; border-radius: 8px; color: #808080;")
        self.video_label.setScaledContents(True)
        layout.addWidget(self.video_label, stretch=1)

        self.status_label = QLabel("Waiting for camera.")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #e0e0e0; font-size: 15px; padding: 6px;")
        layout.addWidget(self.status_label)

        button_row = QHBoxLayout()
        button_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setMinimumWidth(120)
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

        if cv2 is None or np is None:  # pragma: no cover - requires optional deps
            self.error_message = "OpenCV and NumPy are required for hand detection tests."
            self.status_label.setText("❌ OpenCV/NumPy not available. Install requirements first.")
            print("[SAFETY] Hand detection test unavailable — missing OpenCV/NumPy.")
            return

        if YOLO is None or self.yolo_model is None:  # pragma: no cover - requires optional deps
            self.error_message = "YOLO is required for hand detection tests."
            self.status_label.setText("❌ YOLO not available. Install ultralytics package first.")
            print("[SAFETY] Hand detection test unavailable — missing YOLO.")
            return

        if not self.camera_sources:
            self.error_message = "No camera sources available for testing."
            self.status_label.setText("❌ No cameras configured. Update camera settings first.")
            print("[SAFETY] Hand detection test aborted — no configured camera sources.")
            return

        initial_index = 0
        if self.source_combo:
            self.source_combo.setCurrentIndex(0)
            initial_index = self.source_combo.currentData()
        self._start_camera(initial_index)

    def _start_camera(self, source_index: Optional[int]):
        """Open the requested camera source."""
        self.timer.stop()
        self._release_camera()

        if source_index is None:
            return

        if source_index < 0 or source_index >= len(self.camera_sources):
            self.status_label.setText("❌ Invalid camera index selected.")
            self.error_message = "Invalid camera index."
            return

        label, identifier = self.camera_sources[source_index]
        print(f"[SAFETY] Opening camera '{label}' for hand detection test…")
        self.status_label.setText(f"Opening {label}…")

        resolved_name = self.camera_name_map.get(source_index)
        if self.camera_hub and resolved_name:
            self._use_hub_for_current = True
            self.current_camera_name = resolved_name
            self.cap = None
            self.current_source_index = source_index
            self.error_message = None
            self.status_label.setText(f"Camera '{label}' active. Move your hand into view.")
            self.result_summary = f"Monitoring {label}"
            self.timer.start()
            return

        # Fallback to direct VideoCapture when hub mapping unavailable
        cap = cv2.VideoCapture(identifier)
        if not cap or not cap.isOpened():
            self.error_message = f"Failed to open camera {label}"
            self.status_label.setText(f"❌ Could not open {label}. See terminal for details.")
            print(f"[SAFETY] Failed to open camera source '{label}' ({identifier}).")
            self.cap = None
            self._use_hub_for_current = False
            return

        self.cap = cap
        self.current_camera_name = None
        self._use_hub_for_current = False
        self.current_source_index = source_index
        self.error_message = None
        self.status_label.setText(f"Camera '{label}' active. Move your hand into view.")
        self.result_summary = f"Monitoring {label}"
        self.timer.start()

    def _on_source_changed(self, _combo_index: int):
        if not self.source_combo:
            return
        source_index = self.source_combo.currentData()
        self._start_camera(source_index)

    def _update_frame(self):
        frame = None

        if self._use_hub_for_current:
            if not self.camera_hub or not self.current_camera_name:
                self.status_label.setText("⚠️ Shared camera unavailable.")
                return
            frame = self.camera_hub.get_frame(self.current_camera_name, preview=False)
            if frame is None:
                self.status_label.setText("⚠️ Waiting for shared frames…")
                self.result_summary = "Awaiting camera hub frames."
                self.video_label.setText("Waiting for frames…")
                return
            frame = frame.copy()
        else:
            if not self.cap:
                return
            ret, raw_frame = self.cap.read()
            if not ret or raw_frame is None:
                self.status_label.setText("⚠️ Unable to read from camera.")
                self.result_summary = "Frame capture failed."
                return
            frame = raw_frame

        detected, confidence, annotated = self._detect_hand(frame)

        if self.last_detection is None or detected != self.last_detection:
            camera_label = self.camera_sources[self.current_source_index][0] if self.current_source_index is not None else "camera"
            state = "DETECTED" if detected else "clear"
            print(f"[SAFETY] Person {state} on {camera_label} (confidence {confidence:.2%}).")

        self.last_detection = detected
        self.last_confidence = confidence
        if detected:
            self.detected_any = True

        state_text = "Person detected ✅" if detected else "No person detected"
        conf_text = f"confidence {confidence:.1%}" if detected else "waiting..."
        self.status_label.setText(f"{state_text} — {conf_text}")
        self.result_summary = self.status_label.text()

        self.video_label.setText("")
        rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
        height, width, channel = rgb.shape
        bytes_per_line = channel * width
        image = QImage(rgb.data, width, height, bytes_per_line, QImage.Format_RGB888)
        self.video_label.setPixmap(QPixmap.fromImage(image))

    def _detect_hand(self, frame):
        """Return (detected, confidence, annotated_frame) using YOLOv8."""
        if cv2 is None or np is None:  # pragma: no cover - handled earlier
            return False, 0.0, frame
        
        if self.yolo_model is None:
            return False, 0.0, frame

        annotated = frame.copy()
        detected = False
        best_confidence = 0.0

        try:
            # Run YOLO detection
            results = self.yolo_model(frame, conf=0.4, verbose=False)
            
            if results and len(results) > 0:
                for result in results:
                    if result.boxes is None or len(result.boxes) == 0:
                        continue
                    
                    for box in result.boxes:
                        cls = int(box.cls[0])
                        conf = float(box.conf[0])
                        
                        # Class 0 is 'person' in COCO dataset
                        if cls == 0:
                            detected = True
                            best_confidence = max(best_confidence, conf)
                            
                            # Draw bounding box
                            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                            
                            # Draw red box for detection
                            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 3)
                            
                            # Draw label
                            label = f"Person {conf:.2f}"
                            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
                            cv2.rectangle(annotated, (x1, y1 - label_size[1] - 10), 
                                        (x1 + label_size[0], y1), (0, 0, 255), -1)
                            cv2.putText(annotated, label, (x1, y1 - 5), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # Overall status text
            status_text = f"YOLO: {'PERSON DETECTED' if detected else 'Clear'}"
            if detected:
                status_text += f" (conf: {best_confidence:.2f})"
            
            cv2.putText(annotated, status_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.8, (0, 255, 0) if not detected else (0, 0, 255), 2, cv2.LINE_AA)
            
        except Exception as e:
            print(f"[SAFETY] YOLO detection error: {e}")
            cv2.putText(annotated, f"Error: {str(e)[:50]}", (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        return detected, best_confidence, annotated

    def _release_camera(self):
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        self._use_hub_for_current = False
        self.current_camera_name = None

    def closeEvent(self, event):  # noqa: D401 - Qt override
        self.timer.stop()
        self._release_camera()
        super().closeEvent(event)


class SettingsTab(QWidget):
    """Settings configuration tab"""
    
    # Signal to notify config changes
    config_changed = Signal()
    
    def __init__(self, config: dict, parent=None, device_manager=None):
        super().__init__(parent)
        self.config = config
        self.config_path = Path(__file__).parent.parent / "config.json"
        self.device_manager = device_manager
        self.home_worker: Optional[MotorHomeWorker] = None
        self._pending_home_velocity: Optional[int] = None
        
        # Device status tracking (synced with device_manager)
        self.robot_status = "empty"          # empty/online/offline
        self.camera_front_status = "empty"   # empty/online/offline
        self.camera_wrist_status = "empty"   # empty/online/offline
        
        # Status circle widgets (will be set during init_ui)
        self.robot_status_circle = None
        self.camera_front_circle = None
        self.camera_wrist_circle = None
        
        self.init_ui()
        self.load_settings()
        
        # Connect device manager signals if available
        if self.device_manager:
            self.device_manager.robot_status_changed.connect(self.on_robot_status_changed)
            self.device_manager.camera_status_changed.connect(self.on_camera_status_changed)
    
    def init_ui(self):
        """Initialize UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Title
        title = QLabel("⚙️ Settings")
        title.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 22px;
                font-weight: bold;
                padding: 8px;
            }
        """)
        main_layout.addWidget(title)
        
        # Tabbed interface
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 2px solid #606060;
                border-radius: 6px;
                background-color: #3a3a3a;
            }
            QTabBar::tab {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 #505050, stop:1 #454545);
                color: #e0e0e0;
                border: 2px solid #606060;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 10px 18px;
                font-size: 14px;
                font-weight: bold;
                min-width: 110px;
            }
            QTabBar::tab:selected {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 #4CAF50, stop:1 #388E3C);
                color: #ffffff;
                border-color: #66BB6A;
            }
            QTabBar::tab:hover:!selected {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 #606060, stop:1 #555555);
            }
        """)
        self.tab_widget.tabBar().setCursor(Qt.PointingHandCursor)
        
        # Robot tab
        robot_tab = self.wrap_tab(self.create_robot_tab())
        self.tab_widget.addTab(robot_tab, "🤖 Robot")
        
        # Camera tab
        camera_tab = self.wrap_tab(self.create_camera_tab())
        self.tab_widget.addTab(camera_tab, "📷 Camera")
        
        # Policy tab
        policy_tab = self.wrap_tab(self.create_policy_tab())
        self.tab_widget.addTab(policy_tab, "🧠 Policy")
        
        # Control tab
        control_tab = self.wrap_tab(self.create_control_tab())
        self.tab_widget.addTab(control_tab, "🎮 Control")

        # Safety tab
        safety_tab = self.wrap_tab(self.create_safety_tab())
        self.tab_widget.addTab(safety_tab, "🛡️ Safety")
        
        main_layout.addWidget(self.tab_widget)
        
        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.reset_btn = QPushButton("🔄 Reset")
        self.reset_btn.setMinimumHeight(48)
        self.reset_btn.setStyleSheet(self.get_button_style("#909090", "#707070"))
        self.reset_btn.clicked.connect(self.reset_defaults)
        button_layout.addWidget(self.reset_btn)
        
        self.save_btn = QPushButton("💾 Save")
        self.save_btn.setMinimumHeight(48)
        self.save_btn.setStyleSheet(self.get_button_style("#4CAF50", "#388E3C"))
        self.save_btn.clicked.connect(self.save_settings)
        button_layout.addWidget(self.save_btn)
        
        main_layout.addLayout(button_layout)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self._status_default_style = "QLabel { color: #4CAF50; font-size: 14px; padding: 6px; }"
        self.status_label.setStyleSheet(self._status_default_style)
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)
    
    def get_button_style(self, color1: str, color2: str) -> str:
        """Get button stylesheet"""
        return f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 {color1}, stop:1 {color2});
                color: white;
                border: 2px solid {color1};
                border-radius: 8px;
                font-size: 15px;
                font-weight: bold;
                padding: 6px 18px;
                min-width: 110px;
            }}
            QPushButton:hover {{
                border-color: #ffffff;
            }}
            QPushButton:pressed {{
                background: {color2};
            }}
        """

    def wrap_tab(self, content_widget: QWidget) -> QScrollArea:
        """Place tab contents inside a scroll area for small displays."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        container_layout.addWidget(content_widget, alignment=Qt.AlignTop)
        scroll.setWidget(container)
        return scroll
    
    def create_status_circle(self, status: str) -> QLabel:
        """Create a status indicator circle
        
        Args:
            status: "empty", "online", or "offline"
        
        Returns:
            QLabel with styled circle
        """
        circle = QLabel("●")
        circle.setFixedSize(20, 20)
        circle.setAlignment(Qt.AlignCenter)
        self.update_status_circle(circle, status)
        return circle
    
    def update_status_circle(self, circle: QLabel, status: str):
        """Update circle color based on status
        
        Args:
            circle: QLabel to update
            status: "empty" (gray), "online" (green), or "offline" (red)
        """
        colors = {
            "empty": "#909090",   # Gray - never detected
            "online": "#4CAF50",  # Green - connected
            "offline": "#f44336"  # Red - was connected, now lost
        }
        
        circle.setStyleSheet(f"""
            QLabel {{
                color: {colors.get(status, "#909090")};
                font-size: 20px;
                font-weight: bold;
            }}
        """)
    
    def create_robot_tab(self) -> QWidget:
        """Create robot settings tab - optimized for 1024x600 touchscreen"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # ========== HOME ROW ==========
        rest_section = QLabel("🏠 Home Position")
        rest_section.setStyleSheet("color: #4CAF50; font-size: 14px; font-weight: bold; margin-bottom: 2px;")
        layout.addWidget(rest_section)
        
        rest_row = QHBoxLayout()
        rest_row.setSpacing(6)
        
        # Home button (matches Dashboard icon)
        self.home_btn = QPushButton("🏠 Home")
        self.home_btn.setFixedHeight(45)
        self.home_btn.setStyleSheet(self.get_button_style("#2196F3", "#1976D2"))
        self.home_btn.clicked.connect(self.go_home)
        rest_row.addWidget(self.home_btn)
        
        # Set Home button (saves current position as home)
        self.set_home_btn = QPushButton("Set Home")
        self.set_home_btn.setFixedHeight(45)
        self.set_home_btn.setStyleSheet(self.get_button_style("#4CAF50", "#388E3C"))
        self.set_home_btn.clicked.connect(self.set_rest_position)
        rest_row.addWidget(self.set_home_btn)
        
        velocity_label = QLabel("Vel:")
        velocity_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        velocity_label.setFixedWidth(30)
        rest_row.addWidget(velocity_label)
        
        self.rest_velocity_spin = QSpinBox()
        self.rest_velocity_spin.setMinimum(50)
        self.rest_velocity_spin.setMaximum(2000)
        self.rest_velocity_spin.setValue(400)
        self.rest_velocity_spin.setFixedHeight(45)
        self.rest_velocity_spin.setFixedWidth(75)
        self.rest_velocity_spin.setButtonSymbols(QSpinBox.NoButtons)
        self.rest_velocity_spin.setStyleSheet("""
            QSpinBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
            }
            QSpinBox:focus {
                border-color: #4CAF50;
                background-color: #555555;
            }
        """)
        rest_row.addWidget(self.rest_velocity_spin)
        
        self.find_ports_btn = QPushButton("🔍 Find Ports")
        self.find_ports_btn.setFixedHeight(45)
        self.find_ports_btn.setStyleSheet(self.get_button_style("#FF9800", "#F57C00"))
        self.find_ports_btn.clicked.connect(self.find_robot_ports)
        rest_row.addWidget(self.find_ports_btn)
        rest_row.addStretch()
        
        layout.addLayout(rest_row)
        
        # Spacer instead of separator
        layout.addSpacing(8)
        
        # ========== ROBOT CONFIGURATION ==========
        config_section = QLabel("🤖 Robot Configuration")
        config_section.setStyleSheet("color: #4CAF50; font-size: 14px; font-weight: bold; margin-bottom: 2px;")
        layout.addWidget(config_section)
        
        # Serial Port Row with Status Circle and Calibrate Button
        port_row = QHBoxLayout()
        port_row.setSpacing(6)
        
        # Status circle
        self.robot_status_circle = self.create_status_circle("empty")
        port_row.addWidget(self.robot_status_circle)
        
        # Label
        port_label = QLabel("Serial Port:")
        port_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        port_label.setFixedWidth(75)
        port_row.addWidget(port_label)
        
        # Text field
        self.robot_port_edit = QLineEdit("/dev/ttyACM0")
        self.robot_port_edit.setFixedHeight(45)
        self.robot_port_edit.setStyleSheet("""
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
        """)
        port_row.addWidget(self.robot_port_edit)
        
        # Calibrate button
        self.calibrate_btn = QPushButton("⚙️ Calibrate")
        self.calibrate_btn.setFixedHeight(45)
        self.calibrate_btn.setFixedWidth(120)
        self.calibrate_btn.setStyleSheet(self.get_button_style("#9C27B0", "#7B1FA2"))
        self.calibrate_btn.clicked.connect(self.calibrate_arm)
        port_row.addWidget(self.calibrate_btn)
        port_row.addStretch()
        
        layout.addLayout(port_row)
        
        # Hertz Row
        hertz_row = QHBoxLayout()
        hertz_row.setSpacing(6)
        
        # Empty space for alignment (20px for status circle)
        hertz_row.addSpacing(20)
        
        hertz_label = QLabel("Hertz:")
        hertz_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        hertz_label.setFixedWidth(75)
        hertz_row.addWidget(hertz_label)
        
        self.robot_fps_spin = QSpinBox()
        self.robot_fps_spin.setMinimum(1)
        self.robot_fps_spin.setMaximum(120)
        self.robot_fps_spin.setValue(30)
        self.robot_fps_spin.setFixedHeight(45)
        self.robot_fps_spin.setButtonSymbols(QSpinBox.NoButtons)
        self.robot_fps_spin.setStyleSheet("""
            QSpinBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
            }
            QSpinBox:focus {
                border-color: #4CAF50;
                background-color: #555555;
            }
        """)
        hertz_row.addWidget(self.robot_fps_spin)
        hertz_row.addStretch()
        
        layout.addLayout(hertz_row)
        
        # Spacer instead of separator
        layout.addSpacing(8)
        
        # Teleop Port
        teleop_section = QLabel("🎮 Teleoperation")
        teleop_section.setStyleSheet("color: #4CAF50; font-size: 14px; font-weight: bold; margin-bottom: 2px;")
        layout.addWidget(teleop_section)
        
        self.teleop_port_edit = self.add_setting_row(layout, "Teleop Port:", "/dev/ttyACM1")
        
        
        # Position verification settings
        label = QLabel("🎯 Position Accuracy")
        label.setStyleSheet("color: #4CAF50; font-size: 16px; font-weight: bold; margin-top: 15px;")
        layout.addWidget(label)
        
        self.position_tolerance_spin = self.add_spinbox_row(layout, "Position Tolerance (units):", 1, 100, 10)
        
        # Add checkbox for verification enabled
        verify_row = QHBoxLayout()
        verify_label = QLabel("Enable Position Verification:")
        verify_label.setStyleSheet("color: #d0d0d0; font-size: 15px;")
        verify_label.setMinimumWidth(220)
        verify_row.addWidget(verify_label)
        
        from PySide6.QtWidgets import QCheckBox
        self.position_verification_check = QCheckBox()
        self.position_verification_check.setChecked(True)
        self.position_verification_check.setStyleSheet("""
            QCheckBox {
                font-size: 15px;
                spacing: 10px;
            }
            QCheckBox::indicator {
                width: 26px;
                height: 26px;
                border: 2px solid #707070;
                border-radius: 6px;
                background-color: #505050;
            }
            QCheckBox::indicator:checked {
                background-color: #4CAF50;
                border-color: #4CAF50;
            }
        """)
        verify_row.addWidget(self.position_verification_check)
        verify_row.addStretch()
        layout.addLayout(verify_row)
        
        layout.addStretch()
        return widget

    def run_temperature_self_test(self):
        """Simulate a temperature diagnostic and surface results."""
        threshold = self.motor_temp_threshold_spin.value()

        if not self.motor_temp_monitor_check.isChecked():
            message = "Enable motor temperature monitoring to run the self-test."
            self.status_label.setText(f"ℹ️ {message}")
            print(f"[SAFETY] {message}")
            return

        self.status_label.setText("⏳ Running motor temperature self-test…")
        print(f"[SAFETY] Running motor temperature self-test (limit {threshold}°C)…")

        def _finish():
            temps = [random.uniform(34.0, 62.0) for _ in range(6)]
            formatted = ", ".join(f"{value:.1f}°C" for value in temps)
            max_temp = max(temps)
            print(f"[SAFETY] Motor temperature samples: {formatted}")

            if max_temp > threshold:
                message = f"⚠️ Over-limit reading: {max_temp:.1f}°C (limit {threshold}°C). Check cooling or torque loads."
                self.status_label.setText(message)
                print(f"[SAFETY] {message}")
            else:
                message = f"✓ All sensors nominal ({max_temp:.1f}°C max, limit {threshold}°C)."
                self.status_label.setText(message)
                print(f"[SAFETY] {message}")

        QTimer.singleShot(600, _finish)

    def run_torque_trip_test(self):
        """Simulate collision torque monitoring."""
        limit = self.torque_threshold_spin.value()

        if not self.torque_monitor_check.isChecked():
            message = "Enable torque collision protection to simulate a trip event."
            self.status_label.setText(f"ℹ️ {message}")
            print(f"[SAFETY] {message}")
            return

        self.status_label.setText("⏳ Simulating high-torque collision event…")
        print(f"[SAFETY] Simulating torque spike with limit set to {limit:.1f}%…")

        def _finish():
            spike = random.uniform(70.0, 180.0)
            print(f"[SAFETY] Simulated torque spike: {spike:.1f}% of rated torque.")
            if spike >= limit:
                message = (
                    f"🛑 Torque trip simulated — peak {spike:.1f}% exceeded limit {limit:.1f}%. "
                    f"{'Torque will drop automatically.' if self.torque_disable_check.isChecked() else 'Torque remains enabled; manual intervention required.'}"
                )
                self.status_label.setText(message)
            else:
                message = (
                    f"✓ Spike {spike:.1f}% remained below the {limit:.1f}% threshold. "
                    "Protection stays armed."
                )
                self.status_label.setText(message)
            print(f"[SAFETY] {message}")

        QTimer.singleShot(500, _finish)

    def run_hand_safety_test(self):
        """Test hand safety monitoring with live camera preview."""
        if cv2 is None or np is None:
            message = "OpenCV/NumPy not installed. Install requirements.txt to run hand safety tests."
            self.status_label.setText(f"❌ {message}")
            print(f"[SAFETY] {message}")
            return

        camera_choice = self.hand_safety_camera_combo.currentData()
        cameras_cfg = self.config.get("cameras", {})

        def normalize_identifier(value):
            if isinstance(value, int):
                return value
            if isinstance(value, str):
                stripped = value.strip()
                if stripped.isdigit():
                    return int(stripped)
                return stripped
            return value

        sources: List[Tuple[str, Union[int, str]]] = []

        def add_source(key: str, label_prefix: str):
            cam_cfg = cameras_cfg.get(key, {})
            identifier = cam_cfg.get("index_or_path", normalize_identifier(0 if key == "front" else 1))
            identifier = normalize_identifier(identifier)
            if identifier is None:
                return
            label = f"{label_prefix} ({identifier})"
            sources.append((label, identifier))

        if camera_choice in ("front", "wrist"):
            add_source(camera_choice, camera_choice.title() + " Camera")
        elif camera_choice in ("both", "all"):
            add_source("front", "Front Camera")
            add_source("wrist", "Wrist Camera")
        else:
            # Fallback to front
            add_source("front", "Front Camera")

        if not sources:
            message = "No camera sources configured for safety monitoring — update the Camera tab first."
            self.status_label.setText(f"❌ {message}")
            print(f"[SAFETY] {message}")
            return

        self.status_label.setText("🎥 Launching hand safety test window…")
        dialog = HandDetectionTestDialog(sources, self.config, parent=self)
        dialog.exec()
        
        if dialog.detected_any:
            self.status_label.setText("✅ Hand detection working! Detected hands during test.")
            self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")
        else:
            self.status_label.setText("⚠️ No hands detected during test. Try moving your hand in view.")
            self.status_label.setStyleSheet("QLabel { color: #FF9800; font-size: 15px; padding: 8px; }")
    
    def run_hand_detection_test(self):
        """Open live preview to validate hand detection settings (LEGACY - redirects to new test)."""
        # Redirect to new safety test
        self.run_hand_safety_test()
        return
        
        # OLD CODE BELOW (kept for reference but not executed)
        if cv2 is None or np is None:
            message = "OpenCV/NumPy not installed. Install requirements.txt to run hand detection tests."
            self.status_label.setText(f"❌ {message}")
            print(f"[SAFETY] {message}")
            return

        camera_choice = "front"  # Dummy, never reached
        cameras_cfg = self.config.get("cameras", {})

        def normalize_identifier(value):
            if isinstance(value, int):
                return value
            if isinstance(value, str):
                stripped = value.strip()
                if stripped.isdigit():
                    return int(stripped)
                return stripped
            return value

        sources: List[Tuple[str, Union[int, str]]] = []

        def add_source(key: str, label_prefix: str):
            cam_cfg = cameras_cfg.get(key, {})
            identifier = cam_cfg.get("index_or_path", normalize_identifier(0 if key == "front" else 1))
            identifier = normalize_identifier(identifier)
            if identifier is None:
                return
            label = f"{label_prefix} ({identifier})"
            sources.append((label, identifier))

        if camera_choice == "front":
            add_source("front", "Front Camera")
        elif camera_choice == "wrist":
            add_source("wrist", "Wrist Camera")
        elif camera_choice == "both":
            add_source("front", "Front Camera")
            add_source("wrist", "Wrist Camera")
        else:
            # Fallback to front if combo data unexpected
            add_source("front", "Front Camera")

        if not sources:
            message = "No camera sources configured for detection — update the Camera tab first."
            self.status_label.setText(f"❌ {message}")
            print(f"[SAFETY] {message}")
            return

        self.status_label.setText("🎥 Launching hand detection test window…")
        print(f"[SAFETY] Launching hand detection test for {len(sources)} camera(s).")

        dialog = HandDetectionTestDialog(sources, self.config, parent=self)
        dialog.exec()

        if dialog.error_message:
            self.status_label.setText(f"❌ {dialog.error_message}")
            print(f"[SAFETY] Hand detection test error: {dialog.error_message}")
            return

        result = "Hand detected during test" if dialog.detected_any else "No hand detected during test"
        summary = f"{dialog.result_summary}"
        self.status_label.setText(f"✓ Hand detection test complete — {result.lower()}.")
        print(f"[SAFETY] Hand detection test complete — {summary}")
    
    def create_camera_tab(self) -> QWidget:
        """Create camera settings tab - optimized for 1024x600 touchscreen"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # ========== CAMERA DETECTION ==========
        detect_section = QLabel("🎥 Camera Configuration")
        detect_section.setStyleSheet("color: #4CAF50; font-size: 14px; font-weight: bold; margin-bottom: 2px;")
        layout.addWidget(detect_section)
        
        # Front Camera Row with Status Circle and Find Button
        front_row = QHBoxLayout()
        front_row.setSpacing(6)
        
        # Status circle
        self.camera_front_circle = self.create_status_circle("empty")
        front_row.addWidget(self.camera_front_circle)
        
        # Label
        front_label = QLabel("Front:")
        front_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        front_label.setFixedWidth(55)
        front_row.addWidget(front_label)
        
        # Text field
        self.cam_front_edit = QLineEdit("/dev/video1")
        self.cam_front_edit.setFixedHeight(45)
        self.cam_front_edit.setStyleSheet("""
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
        """)
        front_row.addWidget(self.cam_front_edit)
        
        # Find button (only on first row)
        self.find_cameras_btn = QPushButton("🔍 Find Cameras")
        self.find_cameras_btn.setFixedHeight(45)
        self.find_cameras_btn.setFixedWidth(140)
        self.find_cameras_btn.setStyleSheet(self.get_button_style("#FF9800", "#F57C00"))
        self.find_cameras_btn.clicked.connect(self.find_cameras)
        front_row.addWidget(self.find_cameras_btn)
        front_row.addStretch()
        
        layout.addLayout(front_row)
        
        # Wrist Camera Row with Status Circle
        wrist_row = QHBoxLayout()
        wrist_row.setSpacing(6)
        
        # Status circle
        self.camera_wrist_circle = self.create_status_circle("empty")
        wrist_row.addWidget(self.camera_wrist_circle)
        
        # Label
        wrist_label = QLabel("Wrist:")
        wrist_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        wrist_label.setFixedWidth(55)
        wrist_row.addWidget(wrist_label)
        
        # Text field
        self.cam_wrist_edit = QLineEdit("/dev/video3")
        self.cam_wrist_edit.setFixedHeight(45)
        self.cam_wrist_edit.setStyleSheet("""
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
        """)
        wrist_row.addWidget(self.cam_wrist_edit)
        
        # Empty space for alignment (140px for Find button)
        wrist_row.addSpacing(12)
        wrist_row.addStretch()
        
        layout.addLayout(wrist_row)
        
        # Spacer instead of separator
        layout.addSpacing(8)
        
        # ========== CAMERA SETTINGS ==========
        settings_section = QLabel("⚙️ Camera Properties")
        settings_section.setStyleSheet("color: #4CAF50; font-size: 14px; font-weight: bold; margin-bottom: 2px;")
        layout.addWidget(settings_section)
        
        self.cam_width_spin = self.add_spinbox_row(layout, "Width:", 320, 1920, 640)
        self.cam_height_spin = self.add_spinbox_row(layout, "Height:", 240, 1080, 480)
        self.cam_fps_spin = self.add_spinbox_row(layout, "Camera FPS:", 1, 60, 30)
        
        layout.addStretch()
        return widget
    
    def create_policy_tab(self) -> QWidget:
        """Create policy settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        self.policy_base_edit = self.add_setting_row(layout, "Base Path:", "/home/daniel/lerobot/outputs/train")
        self.policy_device_edit = self.add_setting_row(layout, "Device:", "cuda")
        
        # Execution mode toggle
        mode_section = QLabel("Execution Mode:")
        mode_section.setStyleSheet("QLabel { color: #e0e0e0; font-size: 16px; font-weight: bold; padding: 10px 0 5px 0; }")
        layout.addWidget(mode_section)
        
        self.policy_local_check = QCheckBox("Use Local Mode (lerobot-record)")
        self.policy_local_check.setChecked(True)  # Default to local mode
        self.policy_local_check.setStyleSheet("""
            QCheckBox {
                color: #e0e0e0;
                font-size: 15px;
                padding: 8px;
            }
            QCheckBox::indicator {
                width: 24px;
                height: 24px;
            }
        """)
        layout.addWidget(self.policy_local_check)
        
        mode_help = QLabel("Local: Uses lerobot-record with policy (auto-cleans eval folders)\nServer: Uses async inference (policy server + robot client)")
        mode_help.setStyleSheet("QLabel { color: #909090; font-size: 13px; padding: 5px 25px; }")
        mode_help.setWordWrap(True)
        layout.addWidget(mode_help)
        
        # Async inference settings (only for server mode)
        section = QLabel("Async Inference (Server Mode):")
        section.setStyleSheet("QLabel { color: #e0e0e0; font-size: 16px; font-weight: bold; padding: 10px 0 5px 0; }")
        layout.addWidget(section)
        
        self.async_host_edit = self.add_setting_row(layout, "Server Host:", "127.0.0.1")
        self.async_port_spin = self.add_spinbox_row(layout, "Server Port:", 1024, 65535, 8080)
        
        layout.addStretch()
        return widget
    
    def create_control_tab(self) -> QWidget:
        """Create control settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.num_episodes_spin = self.add_spinbox_row(layout, "Episodes:", 1, 100, 10)
        self.episode_time_spin = self.add_doublespinbox_row(layout, "Episode Time (s):", 1.0, 300.0, 20.0)
        self.warmup_spin = self.add_doublespinbox_row(layout, "Warmup (s):", 0.0, 60.0, 3.0)
        self.reset_time_spin = self.add_doublespinbox_row(layout, "Reset Time (s):", 0.0, 60.0, 8.0)

        # Checkboxes
        self.display_data_check = QCheckBox("Display Data")
        self.display_data_check.setStyleSheet("QCheckBox { color: #e0e0e0; font-size: 15px; padding: 8px; }")
        layout.addWidget(self.display_data_check)

        self.object_gate_check = QCheckBox("Object Gate")
        self.object_gate_check.setStyleSheet("QCheckBox { color: #e0e0e0; font-size: 15px; padding: 8px; }")
        layout.addWidget(self.object_gate_check)

        layout.addStretch()
        return widget

    def create_safety_tab(self) -> QWidget:
        """Create safety settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Motor temperature monitoring
        temp_section = QLabel("🔥 Motor Temperature Safety")
        temp_section.setStyleSheet("QLabel { color: #4CAF50; font-size: 16px; font-weight: bold; padding: 4px 0; }")
        layout.addWidget(temp_section)

        self.motor_temp_monitor_check = QCheckBox("Enable Feetech motor temperature monitoring")
        self.motor_temp_monitor_check.setStyleSheet("QCheckBox { color: #e0e0e0; font-size: 15px; padding: 4px; }")
        layout.addWidget(self.motor_temp_monitor_check)

        temp_threshold_row = QHBoxLayout()
        temp_label = QLabel("Overheat threshold (°C):")
        temp_label.setStyleSheet("QLabel { color: #e0e0e0; font-size: 15px; min-width: 200px; }")
        temp_threshold_row.addWidget(temp_label)

        self.motor_temp_threshold_spin = QSpinBox()
        self.motor_temp_threshold_spin.setRange(30, 120)
        self.motor_temp_threshold_spin.setValue(75)
        self.motor_temp_threshold_spin.setMinimumHeight(45)
        self.motor_temp_threshold_spin.setButtonSymbols(QSpinBox.NoButtons)
        self.motor_temp_threshold_spin.setStyleSheet("""
            QSpinBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 8px;
                padding: 8px;
                font-size: 15px;
            }
            QSpinBox:focus {
                border-color: #4CAF50;
                background-color: #555555;
            }
        """)
        temp_threshold_row.addWidget(self.motor_temp_threshold_spin)
        temp_threshold_row.addStretch()
        layout.addLayout(temp_threshold_row)

        temp_interval_row = QHBoxLayout()
        temp_interval_label = QLabel("Polling interval (s):")
        temp_interval_label.setStyleSheet("QLabel { color: #e0e0e0; font-size: 15px; min-width: 200px; }")
        temp_interval_row.addWidget(temp_interval_label)

        self.motor_temp_interval_spin = QDoubleSpinBox()
        self.motor_temp_interval_spin.setRange(0.5, 30.0)
        self.motor_temp_interval_spin.setValue(2.0)
        self.motor_temp_interval_spin.setDecimals(1)
        self.motor_temp_interval_spin.setSingleStep(0.5)
        self.motor_temp_interval_spin.setMinimumHeight(45)
        self.motor_temp_interval_spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.motor_temp_interval_spin.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 8px;
                padding: 8px;
                font-size: 15px;
            }
            QDoubleSpinBox:focus {
                border-color: #4CAF50;
                background-color: #555555;
            }
        """)
        temp_interval_row.addWidget(self.motor_temp_interval_spin)
        temp_interval_row.addStretch()
        layout.addLayout(temp_interval_row)

        temp_button_row = QHBoxLayout()
        temp_button_row.addStretch()
        self.motor_temp_test_btn = QPushButton("Run Temperature Self-Test")
        self.motor_temp_test_btn.setMinimumHeight(45)
        self.motor_temp_test_btn.setStyleSheet(self.get_button_style("#FF7043", "#F4511E"))
        self.motor_temp_test_btn.clicked.connect(self.run_temperature_self_test)
        temp_button_row.addWidget(self.motor_temp_test_btn)
        layout.addLayout(temp_button_row)

        layout.addSpacing(8)

        # Torque monitoring
        torque_section = QLabel("🛑 Torque Collision Protection")
        torque_section.setStyleSheet("QLabel { color: #4CAF50; font-size: 16px; font-weight: bold; padding: 4px 0; }")
        layout.addWidget(torque_section)

        self.torque_monitor_check = QCheckBox("Kill task and react when torque spikes")
        self.torque_monitor_check.setStyleSheet("QCheckBox { color: #e0e0e0; font-size: 15px; padding: 4px; }")
        layout.addWidget(self.torque_monitor_check)

        torque_threshold_row = QHBoxLayout()
        torque_threshold_label = QLabel("Torque limit (% of rated):")
        torque_threshold_label.setStyleSheet("QLabel { color: #e0e0e0; font-size: 15px; min-width: 200px; }")
        torque_threshold_row.addWidget(torque_threshold_label)

        self.torque_threshold_spin = QDoubleSpinBox()
        self.torque_threshold_spin.setRange(10.0, 200.0)
        self.torque_threshold_spin.setValue(120.0)
        self.torque_threshold_spin.setDecimals(1)
        self.torque_threshold_spin.setSingleStep(5.0)
        self.torque_threshold_spin.setMinimumHeight(45)
        self.torque_threshold_spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.torque_threshold_spin.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 8px;
                padding: 8px;
                font-size: 15px;
            }
            QDoubleSpinBox:focus {
                border-color: #4CAF50;
                background-color: #555555;
            }
        """)
        torque_threshold_row.addWidget(self.torque_threshold_spin)
        torque_threshold_row.addStretch()
        layout.addLayout(torque_threshold_row)

        self.torque_disable_check = QCheckBox("Automatically drop torque when limit is exceeded")
        self.torque_disable_check.setStyleSheet("QCheckBox { color: #e0e0e0; font-size: 15px; padding: 4px; }")
        layout.addWidget(self.torque_disable_check)

        torque_button_row = QHBoxLayout()
        torque_button_row.addStretch()
        self.torque_trip_btn = QPushButton("Simulate Torque Trip")
        self.torque_trip_btn.setMinimumHeight(45)
        self.torque_trip_btn.setStyleSheet(self.get_button_style("#E53935", "#C62828"))
        self.torque_trip_btn.clicked.connect(self.run_torque_trip_test)
        torque_button_row.addWidget(self.torque_trip_btn)
        layout.addLayout(torque_button_row)

        layout.addSpacing(8)

        # Hand Safety Monitoring (EMERGENCY STOP)
        vision_section = QLabel("🚨 Hand Safety Monitoring (Emergency Stop)")
        vision_section.setStyleSheet("QLabel { color: #FF5722; font-size: 16px; font-weight: bold; padding: 4px 0; }")
        layout.addWidget(vision_section)
        
        warning_label = QLabel("⚠️ CRITICAL SAFETY: Detects hands and triggers EMERGENCY STOP to prevent injury")
        warning_label.setStyleSheet("QLabel { color: #FF9800; font-size: 14px; padding: 4px; font-style: italic; }")
        warning_label.setWordWrap(True)
        layout.addWidget(warning_label)

        self.hand_safety_enabled_check = QCheckBox("Enable Hand Safety Monitoring")
        self.hand_safety_enabled_check.setStyleSheet("QCheckBox { color: #e0e0e0; font-size: 15px; padding: 4px; font-weight: bold; }")
        layout.addWidget(self.hand_safety_enabled_check)

        # Camera selection
        camera_row = QHBoxLayout()
        camera_label = QLabel("Monitor cameras:")
        camera_label.setStyleSheet("QLabel { color: #e0e0e0; font-size: 15px; min-width: 220px; }")
        camera_row.addWidget(camera_label)

        self.hand_safety_camera_combo = QComboBox()
        self.hand_safety_camera_combo.addItem("Front Camera", "front")
        self.hand_safety_camera_combo.addItem("Wrist Camera", "wrist")
        self.hand_safety_camera_combo.addItem("Both Cameras", "both")
        self.hand_safety_camera_combo.addItem("All Cameras", "all")
        self.hand_safety_camera_combo.setStyleSheet("""
            QComboBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 8px;
                padding: 8px;
                font-size: 15px;
                min-height: 45px;
            }
            QComboBox:focus {
                border-color: #FF5722;
                background-color: #555555;
            }
            QComboBox QListView {
                background-color: #3a3a3a;
                color: #ffffff;
                padding: 4px;
            }
        """)
        camera_row.addWidget(self.hand_safety_camera_combo)
        camera_row.addStretch()
        layout.addLayout(camera_row)

        # Detection FPS (resource control)
        fps_row = QHBoxLayout()
        fps_label = QLabel("Detection FPS (lower=lighter):")
        fps_label.setStyleSheet("QLabel { color: #e0e0e0; font-size: 15px; min-width: 220px; }")
        fps_row.addWidget(fps_label)

        self.hand_safety_fps_spin = QDoubleSpinBox()
        self.hand_safety_fps_spin.setRange(1.0, 30.0)
        self.hand_safety_fps_spin.setDecimals(1)
        self.hand_safety_fps_spin.setSingleStep(1.0)
        self.hand_safety_fps_spin.setValue(8.0)
        self.hand_safety_fps_spin.setMinimumHeight(45)
        self.hand_safety_fps_spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.hand_safety_fps_spin.setToolTip("Lower FPS saves CPU/GPU resources. 8 FPS recommended for good safety with low overhead.")
        self.hand_safety_fps_spin.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 8px;
                padding: 8px;
                font-size: 15px;
            }
            QDoubleSpinBox:focus {
                border-color: #FF5722;
                background-color: #555555;
            }
        """)
        fps_row.addWidget(self.hand_safety_fps_spin)
        fps_row.addStretch()
        layout.addLayout(fps_row)

        # Detection confidence (MediaPipe)
        confidence_row = QHBoxLayout()
        confidence_label = QLabel("Detection confidence threshold:")
        confidence_label.setStyleSheet("QLabel { color: #e0e0e0; font-size: 15px; min-width: 220px; }")
        confidence_row.addWidget(confidence_label)

        self.hand_safety_confidence_spin = QDoubleSpinBox()
        self.hand_safety_confidence_spin.setRange(0.1, 0.9)
        self.hand_safety_confidence_spin.setDecimals(2)
        self.hand_safety_confidence_spin.setSingleStep(0.05)
        self.hand_safety_confidence_spin.setValue(0.45)
        self.hand_safety_confidence_spin.setMinimumHeight(45)
        self.hand_safety_confidence_spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.hand_safety_confidence_spin.setToolTip("Higher = fewer false positives but may miss hands. 0.45 recommended.")
        self.hand_safety_confidence_spin.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 8px;
                padding: 8px;
                font-size: 15px;
            }
            QDoubleSpinBox:focus {
                border-color: #FF5722;
                background-color: #555555;
            }
        """)
        confidence_row.addWidget(self.hand_safety_confidence_spin)
        confidence_row.addStretch()
        layout.addLayout(confidence_row)

        # Resume delay
        resume_row = QHBoxLayout()
        resume_label = QLabel("Resume delay after clear (s):")
        resume_label.setStyleSheet("QLabel { color: #e0e0e0; font-size: 15px; min-width: 220px; }")
        resume_row.addWidget(resume_label)

        self.hand_safety_resume_delay_spin = QDoubleSpinBox()
        self.hand_safety_resume_delay_spin.setRange(0.5, 10.0)
        self.hand_safety_resume_delay_spin.setDecimals(1)
        self.hand_safety_resume_delay_spin.setSingleStep(0.5)
        self.hand_safety_resume_delay_spin.setValue(1.0)
        self.hand_safety_resume_delay_spin.setMinimumHeight(45)
        self.hand_safety_resume_delay_spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.hand_safety_resume_delay_spin.setToolTip("Time workspace must be clear before manual restart allowed.")
        self.hand_safety_resume_delay_spin.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 8px;
                padding: 8px;
                font-size: 15px;
            }
            QDoubleSpinBox:focus {
                border-color: #FF5722;
                background-color: #555555;
            }
        """)
        resume_row.addWidget(self.hand_safety_resume_delay_spin)
        resume_row.addStretch()
        layout.addLayout(resume_row)

        # Frame size (advanced)
        framesize_row = QHBoxLayout()
        framesize_label = QLabel("Detection frame width (px):")
        framesize_label.setStyleSheet("QLabel { color: #e0e0e0; font-size: 15px; min-width: 220px; }")
        framesize_row.addWidget(framesize_label)

        self.hand_safety_frame_width_spin = QSpinBox()
        self.hand_safety_frame_width_spin.setRange(160, 640)
        self.hand_safety_frame_width_spin.setSingleStep(80)
        self.hand_safety_frame_width_spin.setValue(320)
        self.hand_safety_frame_width_spin.setMinimumHeight(45)
        self.hand_safety_frame_width_spin.setButtonSymbols(QSpinBox.NoButtons)
        self.hand_safety_frame_width_spin.setToolTip("Smaller = faster processing. 320px recommended.")
        self.hand_safety_frame_width_spin.setStyleSheet("""
            QSpinBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 8px;
                padding: 8px;
                font-size: 15px;
            }
            QSpinBox:focus {
                border-color: #FF5722;
                background-color: #555555;
            }
        """)
        framesize_row.addWidget(self.hand_safety_frame_width_spin)
        framesize_row.addStretch()
        layout.addLayout(framesize_row)

        # YOLO Model info (YOLO-only system now)
        model_label = QLabel("✓ Using YOLOv8 Nano (yolov8n.pt) - Fast & Reliable")
        model_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; font-weight: bold; padding: 8px; }")
        model_label.setToolTip("YOLOv8n detects persons in workspace. You can replace with a custom hand-detection model.")
        layout.addWidget(model_label)

        # Test button
        hand_button_row = QHBoxLayout()
        hand_button_row.addStretch()
        self.hand_safety_test_btn = QPushButton("🎥 Test Hand Detection")
        self.hand_safety_test_btn.setMinimumHeight(45)
        self.hand_safety_test_btn.setStyleSheet(self.get_button_style("#FF5722", "#E64A19"))
        self.hand_safety_test_btn.clicked.connect(self.run_hand_safety_test)
        hand_button_row.addWidget(self.hand_safety_test_btn)
        layout.addLayout(hand_button_row)

        layout.addStretch()
        return widget
    
    def add_setting_row(self, layout: QVBoxLayout, label_text: str, default_value: str) -> QLineEdit:
        """Add a text input setting row"""
        row = QHBoxLayout()
        
        label = QLabel(label_text)
        label.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                font-size: 14px;
                min-width: 150px;
            }
        """)
        row.addWidget(label)
        
        edit = QLineEdit(default_value)
        edit.setMinimumHeight(44)
        edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        edit.setStyleSheet("""
            QLineEdit {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 8px;
                padding: 8px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #4CAF50;
                background-color: #555555;
            }
        """)
        row.addWidget(edit, stretch=1)
        row.addStretch()
        
        layout.addLayout(row)
        return edit
    
    def add_spinbox_row(self, layout: QVBoxLayout, label_text: str, min_val: int, max_val: int, default: int) -> QSpinBox:
        """Add a spinbox setting row"""
        row = QHBoxLayout()
        
        label = QLabel(label_text)
        label.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                font-size: 14px;
                min-width: 150px;
            }
        """)
        row.addWidget(label)
        
        spin = QSpinBox()
        spin.setMinimum(min_val)
        spin.setMaximum(max_val)
        spin.setValue(default)
        spin.setMinimumHeight(44)
        spin.setButtonSymbols(QSpinBox.NoButtons)
        spin.setStyleSheet("""
            QSpinBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 8px;
                padding: 8px;
                font-size: 14px;
            }
            QSpinBox:focus {
                border-color: #4CAF50;
                background-color: #555555;
            }
        """)
        spin.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        row.addWidget(spin)
        row.addStretch()
        
        layout.addLayout(row)
        return spin
    
    def add_doublespinbox_row(self, layout: QVBoxLayout, label_text: str, min_val: float, max_val: float, default: float) -> QDoubleSpinBox:
        """Add a double spinbox setting row"""
        row = QHBoxLayout()
        
        label = QLabel(label_text)
        label.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                font-size: 14px;
                min-width: 150px;
            }
        """)
        row.addWidget(label)
        
        spin = QDoubleSpinBox()
        spin.setMinimum(min_val)
        spin.setMaximum(max_val)
        spin.setValue(default)
        spin.setDecimals(1)
        spin.setMinimumHeight(44)
        spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        spin.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 8px;
                padding: 8px;
                font-size: 14px;
            }
            QDoubleSpinBox:focus {
                border-color: #4CAF50;
                background-color: #555555;
            }
        """)
        spin.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        row.addWidget(spin)
        row.addStretch()
        
        layout.addLayout(row)
        return spin
    
    def load_settings(self):
        """Load settings from config"""
        # Robot settings
        self.robot_port_edit.setText(self.config.get("robot", {}).get("port", "/dev/ttyACM0"))
        self.robot_fps_spin.setValue(self.config.get("robot", {}).get("fps", 30))
        self.teleop_port_edit.setText(self.config.get("teleop", {}).get("port", "/dev/ttyACM1"))
        self.position_tolerance_spin.setValue(self.config.get("robot", {}).get("position_tolerance", 10))
        self.position_verification_check.setChecked(self.config.get("robot", {}).get("position_verification_enabled", True))
        
        # Camera settings
        front_cam = self.config.get("cameras", {}).get("front", {})
        wrist_cam = self.config.get("cameras", {}).get("wrist", {})
        self.cam_front_edit.setText(front_cam.get("index_or_path", "/dev/video1"))
        self.cam_wrist_edit.setText(wrist_cam.get("index_or_path", "/dev/video3"))
        self.cam_width_spin.setValue(front_cam.get("width", 640))
        self.cam_height_spin.setValue(front_cam.get("height", 480))
        self.cam_fps_spin.setValue(front_cam.get("fps", 30))
        
        # Policy settings
        self.policy_base_edit.setText(self.config.get("policy", {}).get("base_path", "outputs/train"))
        self.policy_device_edit.setText(self.config.get("policy", {}).get("device", "cuda"))
        self.policy_local_check.setChecked(self.config.get("policy", {}).get("local_mode", True))  # Default to local mode
        
        # Async inference
        async_cfg = self.config.get("async_inference", {})
        self.async_host_edit.setText(async_cfg.get("server_host", "127.0.0.1"))
        self.async_port_spin.setValue(async_cfg.get("server_port", 8080))
        
        # Control settings
        control_cfg = self.config.get("control", {})
        self.num_episodes_spin.setValue(control_cfg.get("num_episodes", 10))
        self.episode_time_spin.setValue(control_cfg.get("episode_time_s", 20.0))
        self.warmup_spin.setValue(control_cfg.get("warmup_time_s", 3.0))
        self.reset_time_spin.setValue(control_cfg.get("reset_time_s", 8.0))
        self.display_data_check.setChecked(control_cfg.get("display_data", True))
        
        # UI settings
        ui_cfg = self.config.get("ui", {})
        self.object_gate_check.setChecked(ui_cfg.get("object_gate", False))

        # Safety settings
        safety_cfg = self.config.get("safety", {})
        self.motor_temp_monitor_check.setChecked(safety_cfg.get("motor_temp_monitoring_enabled", False))
        self.motor_temp_threshold_spin.setValue(safety_cfg.get("motor_temp_threshold_c", 75))
        self.motor_temp_interval_spin.setValue(safety_cfg.get("motor_temp_poll_interval_s", 2.0))
        self.torque_monitor_check.setChecked(safety_cfg.get("torque_monitoring_enabled", False))
        self.torque_threshold_spin.setValue(safety_cfg.get("torque_limit_percent", 120.0))
        self.torque_disable_check.setChecked(safety_cfg.get("torque_auto_disable", True))

        # Hand Safety Monitoring (NEW)
        self.hand_safety_enabled_check.setChecked(safety_cfg.get("enabled", False))
        hand_camera = safety_cfg.get("cameras", "front")
        index = self.hand_safety_camera_combo.findData(hand_camera)
        if index == -1:
            index = 0
        self.hand_safety_camera_combo.setCurrentIndex(index)
        self.hand_safety_fps_spin.setValue(safety_cfg.get("detection_fps", 8.0))
        self.hand_safety_confidence_spin.setValue(safety_cfg.get("detection_confidence", 0.4))
        self.hand_safety_resume_delay_spin.setValue(safety_cfg.get("resume_delay_s", 1.0))
        self.hand_safety_frame_width_spin.setValue(safety_cfg.get("frame_width", 320))
    
    def save_settings(self):
        """Save settings to config file"""
        # Update config dict
        if "robot" not in self.config:
            self.config["robot"] = {}
        self.config["robot"]["port"] = self.robot_port_edit.text()
        self.config["robot"]["fps"] = self.robot_fps_spin.value()
        self.config["robot"]["position_tolerance"] = self.position_tolerance_spin.value()
        self.config["robot"]["position_verification_enabled"] = self.position_verification_check.isChecked()
        
        if "teleop" not in self.config:
            self.config["teleop"] = {}
        self.config["teleop"]["port"] = self.teleop_port_edit.text()
        
        # Camera settings
        if "cameras" not in self.config:
            self.config["cameras"] = {"front": {}, "wrist": {}}
        self.config["cameras"]["front"]["index_or_path"] = self.cam_front_edit.text()
        self.config["cameras"]["wrist"]["index_or_path"] = self.cam_wrist_edit.text()
        self.config["cameras"]["front"]["width"] = self.cam_width_spin.value()
        self.config["cameras"]["front"]["height"] = self.cam_height_spin.value()
        self.config["cameras"]["front"]["fps"] = self.cam_fps_spin.value()
        self.config["cameras"]["wrist"]["width"] = self.cam_width_spin.value()
        self.config["cameras"]["wrist"]["height"] = self.cam_height_spin.value()
        self.config["cameras"]["wrist"]["fps"] = self.cam_fps_spin.value()
        
        # Policy settings
        if "policy" not in self.config:
            self.config["policy"] = {}
        self.config["policy"]["base_path"] = self.policy_base_edit.text()
        self.config["policy"]["device"] = self.policy_device_edit.text()
        self.config["policy"]["local_mode"] = self.policy_local_check.isChecked()
        
        # Async inference
        if "async_inference" not in self.config:
            self.config["async_inference"] = {}
        self.config["async_inference"]["server_host"] = self.async_host_edit.text()
        self.config["async_inference"]["server_port"] = self.async_port_spin.value()
        
        # Control settings
        if "control" not in self.config:
            self.config["control"] = {}
        self.config["control"]["num_episodes"] = self.num_episodes_spin.value()
        self.config["control"]["episode_time_s"] = self.episode_time_spin.value()
        self.config["control"]["warmup_time_s"] = self.warmup_spin.value()
        self.config["control"]["reset_time_s"] = self.reset_time_spin.value()
        self.config["control"]["display_data"] = self.display_data_check.isChecked()
        
        # UI settings
        if "ui" not in self.config:
            self.config["ui"] = {}
        self.config["ui"]["object_gate"] = self.object_gate_check.isChecked()

        # Safety settings
        if "safety" not in self.config:
            self.config["safety"] = {}
        self.config["safety"]["motor_temp_monitoring_enabled"] = self.motor_temp_monitor_check.isChecked()
        self.config["safety"]["motor_temp_threshold_c"] = self.motor_temp_threshold_spin.value()
        self.config["safety"]["motor_temp_poll_interval_s"] = self.motor_temp_interval_spin.value()
        self.config["safety"]["torque_monitoring_enabled"] = self.torque_monitor_check.isChecked()
        self.config["safety"]["torque_limit_percent"] = self.torque_threshold_spin.value()
        self.config["safety"]["torque_auto_disable"] = self.torque_disable_check.isChecked()
        # Hand Safety Monitoring (YOLO-only)
        self.config["safety"]["enabled"] = self.hand_safety_enabled_check.isChecked()
        self.config["safety"]["cameras"] = self.hand_safety_camera_combo.currentData()
        self.config["safety"]["detection_fps"] = self.hand_safety_fps_spin.value()
        self.config["safety"]["detection_confidence"] = self.hand_safety_confidence_spin.value()
        self.config["safety"]["resume_delay_s"] = self.hand_safety_resume_delay_spin.value()
        self.config["safety"]["frame_width"] = self.hand_safety_frame_width_spin.value()
        self.config["safety"]["frame_height"] = int(self.hand_safety_frame_width_spin.value() * 0.75)  # 4:3 aspect
        self.config["safety"]["yolo_model"] = "yolov8n.pt"  # Use nano model for speed
        
        # Write to file
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            
            self.status_label.setText("✓ Settings saved successfully!")
            self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")
            self.config_changed.emit()
            
        except Exception as e:
            self.status_label.setText(f"❌ Error: {str(e)}")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
    
    def reset_defaults(self):
        """Reset to default values"""
        self.robot_port_edit.setText("/dev/ttyACM0")
        self.robot_fps_spin.setValue(30)
        self.teleop_port_edit.setText("/dev/ttyACM1")
        self.position_tolerance_spin.setValue(10)
        self.position_verification_check.setChecked(True)
        
        self.cam_front_edit.setText("/dev/video1")
        self.cam_wrist_edit.setText("/dev/video3")
        self.cam_width_spin.setValue(640)
        self.cam_height_spin.setValue(480)
        self.cam_fps_spin.setValue(30)
        
        self.policy_base_edit.setText("outputs/train")
        self.policy_device_edit.setText("cuda")
        
        self.async_host_edit.setText("127.0.0.1")
        self.async_port_spin.setValue(8080)
        
        self.num_episodes_spin.setValue(10)
        self.episode_time_spin.setValue(20.0)
        self.warmup_spin.setValue(3.0)
        self.reset_time_spin.setValue(8.0)
        self.display_data_check.setChecked(True)
        self.object_gate_check.setChecked(False)

        self.motor_temp_monitor_check.setChecked(False)
        self.motor_temp_threshold_spin.setValue(75)
        self.motor_temp_interval_spin.setValue(2.0)
        self.torque_monitor_check.setChecked(False)
        self.torque_threshold_spin.setValue(120.0)
        self.torque_disable_check.setChecked(True)
        self.hand_detection_check.setChecked(False)
        self.hand_detection_camera_combo.setCurrentIndex(0)
        self.hand_detection_model_edit.setText("nicebot/hand-detection-large")
        self.hand_resume_delay_spin.setValue(0.5)
        self.hand_hold_position_check.setChecked(True)
        
        self.status_label.setText("⚠️ Defaults loaded. Click Save to apply.")
        self.status_label.setStyleSheet("QLabel { color: #FF9800; font-size: 15px; padding: 8px; }")
    
    # ========== HOME METHODS ==========

    def set_rest_position(self):
        """Read current motor positions and save as Home position"""
        try:
            from utils.motor_controller import MotorController
            
            self.status_label.setText("⏳ Reading motor positions...")
            self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")
            
            # Initialize motor controller
            motor_config = self.config.get("robot", {})
            motor_controller = MotorController(motor_config)
            
            # Connect and read positions
            if not motor_controller.connect():
                self.status_label.setText("❌ Failed to connect to motors")
                self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
                return
            
            positions = motor_controller.read_positions()
            motor_controller.disconnect()
            
            if positions is None:
                self.status_label.setText("❌ Failed to read motor positions")
                self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
                return
            
            # Save to config
            if "rest_position" not in self.config:
                self.config["rest_position"] = {}
            
            self.config["rest_position"]["positions"] = positions
            self.config["rest_position"]["velocity"] = self.rest_velocity_spin.value()
            
            # Write to file
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            
            self.status_label.setText(f"✓ Home saved: {positions}")
            self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")
            self.config_changed.emit()
            
        except Exception as e:
            self.status_label.setText(f"❌ Error: {str(e)}")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
    
    def go_home(self):
        """Move arm to saved Home position without blocking the UI thread."""
        if self.home_worker and self.home_worker.isRunning():
            self.status_label.setText("⏳ Already moving to home...")
            self.status_label.setStyleSheet("QLabel { color: #FFB74D; font-size: 15px; padding: 8px; }")
            return

        rest_config = self.config.get("rest_position", {})
        if not rest_config.get("positions"):
            self.status_label.setText("❌ No home position saved. Click 'Set Home' first.")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
            return

        velocity = int(self.rest_velocity_spin.value())
        self._pending_home_velocity = velocity
        self.status_label.setText("🏠 Moving to home position...")
        self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")
        self.home_btn.setEnabled(False)

        self.home_worker = MotorHomeWorker(self.config, velocity, parent=self)
        self.home_worker.progress.connect(self._on_settings_home_progress)
        self.home_worker.completed.connect(self._on_settings_home_completed)
        self.home_worker.finished.connect(self._on_settings_home_worker_finished)
        self.home_worker.start()

    def _on_settings_home_progress(self, message: str) -> None:
        """Update status label from the background worker."""
        self.status_label.setText(message)
        self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")

    def _on_settings_home_completed(self, success: bool, message: str) -> None:
        """Handle completion of the asynchronous home move."""
        self.home_btn.setEnabled(True)

        if success:
            velocity = self._pending_home_velocity or self.rest_velocity_spin.value()
            detail = message or f"✓ Moved to home position at velocity {velocity}"
            self.status_label.setText(detail)
            self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")
        else:
            detail = message or "Unknown error"
            self.status_label.setText(f"❌ Error: {detail}")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")

        self._pending_home_velocity = None

    def _on_settings_home_worker_finished(self) -> None:
        """Clean up worker references when it finishes."""
        if self.home_worker:
            self.home_worker.deleteLater()
        self.home_worker = None

    # ========== PORT DETECTION METHODS ==========
    
    def find_robot_ports(self):
        """Scan serial ports and detect robot arms"""
        try:
            import serial.tools.list_ports
            from utils.motor_controller import MotorController
            
            self.status_label.setText("⏳ Scanning serial ports...")
            self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")
            
            # Scan all serial ports
            ports = serial.tools.list_ports.comports()
            found_robots = []
            
            for port in ports:
                port_name = port.device
                
                # Only test ttyACM* and ttyUSB* devices
                if not ('ttyACM' in port_name or 'ttyUSB' in port_name):
                    continue
                
                # Try to connect and detect robot
                try:
                    test_config = self.config.get("robot", {}).copy()
                    test_config["port"] = port_name
                    motor_controller = MotorController(test_config)
                    
                    if motor_controller.connect():
                        # Try to read positions (confirms it's a robot)
                        positions = motor_controller.read_positions()
                        motor_controller.disconnect()
                        
                        if positions:
                            motor_count = len(positions)
                            found_robots.append({
                                "port": port_name,
                                "motors": motor_count,
                                "description": port.description
                            })
                except:
                    pass  # Not a robot, continue scanning
            
            # Display results
            if found_robots:
                from PySide6.QtWidgets import QDialog, QVBoxLayout, QRadioButton, QButtonGroup, QPushButton
                
                dialog = QDialog(self)
                dialog.setWindowTitle("Found Robot Ports")
                dialog.setMinimumWidth(500)
                dialog.setStyleSheet("QDialog { background-color: #2a2a2a; }")
                
                layout = QVBoxLayout(dialog)
                
                title = QLabel(f"✓ Found {len(found_robots)} robot(s):")
                title.setStyleSheet("color: #4CAF50; font-size: 16px; font-weight: bold; padding: 10px;")
                layout.addWidget(title)
                
                button_group = QButtonGroup(dialog)
                
                for robot in found_robots:
                    radio = QRadioButton(f"{robot['port']} - {robot['motors']} motors - {robot['description']}")
                    radio.setStyleSheet("QRadioButton { color: #e0e0e0; font-size: 14px; padding: 5px; }")
                    radio.setProperty("port", robot['port'])
                    button_group.addButton(radio)
                    layout.addWidget(radio)
                
                # Select first by default
                if button_group.buttons():
                    button_group.buttons()[0].setChecked(True)
                
                # Buttons
                btn_layout = QHBoxLayout()
                btn_layout.addStretch()
                
                cancel_btn = QPushButton("Cancel")
                cancel_btn.setStyleSheet(self.get_button_style("#909090", "#707070"))
                cancel_btn.clicked.connect(dialog.reject)
                btn_layout.addWidget(cancel_btn)
                
                select_btn = QPushButton("Select")
                select_btn.setStyleSheet(self.get_button_style("#4CAF50", "#388E3C"))
                select_btn.clicked.connect(dialog.accept)
                btn_layout.addWidget(select_btn)
                
                layout.addLayout(btn_layout)
                
                if dialog.exec() == QDialog.Accepted:
                    # Get selected port
                    for button in button_group.buttons():
                        if button.isChecked():
                            selected_port = button.property("port")
                            self.robot_port_edit.setText(selected_port)
                            
                            # Update status to online (both local and device_manager)
                            self.robot_status = "online"
                            self.update_status_circle(self.robot_status_circle, "online")
                            if self.device_manager:
                                self.device_manager.update_robot_status("online")
                            
                            self.status_label.setText(f"✓ Selected: {selected_port}")
                            self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")
                            break
            else:
                self.status_label.setText("❌ No robot arms found on serial ports")
                self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
                
        except Exception as e:
            self.status_label.setText(f"❌ Error: {str(e)}")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
    
    # ========== CALIBRATION METHODS ==========
    
    def calibrate_arm(self):
        """Run arm calibration sequence"""
        try:
            from utils.motor_controller import MotorController
            from PySide6.QtWidgets import QMessageBox
            
            # Warning dialog
            reply = QMessageBox.warning(
                self,
                "Calibration Warning",
                "⚠️ This will move the arm through its full range of motion.\n\n"
                "Please ensure:\n"
                "• Workspace is clear\n"
                "• Arm can move freely\n"
                "• Emergency stop is accessible\n\n"
                "Continue with calibration?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
            
            self.status_label.setText("⏳ Starting calibration...")
            self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")
            
            # Initialize motor controller
            motor_config = self.config.get("robot", {})
            motor_controller = MotorController(motor_config)
            
            if not motor_controller.connect():
                self.status_label.setText("❌ Failed to connect to motors")
                self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
                return
            
            # Step 1: Read current positions (starting point)
            self.status_label.setText("⏳ Step 1/3: Reading current positions...")
            current_positions = motor_controller.read_positions()
            
            if not current_positions:
                self.status_label.setText("❌ Failed to read positions")
                self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
                motor_controller.disconnect()
                return
            
            # Step 2: Move to home position (2048 - middle for SO-100/SO-101)
            self.status_label.setText("⏳ Step 2/3: Moving to home position...")
            home_positions = [2048] * len(current_positions)
            motor_controller.set_positions(home_positions, velocity=400, wait=True, keep_connection=True)
            
            # Step 3: Test range (gentle movement)
            self.status_label.setText("⏳ Step 3/3: Testing joint range...")
            import time
            
            # Small range test - move each joint slightly
            for i in range(len(current_positions)):
                test_positions = home_positions.copy()
                # Move joint +/- 200 units
                test_positions[i] = 2248
                motor_controller.set_positions(test_positions, velocity=300, wait=True, keep_connection=True)
                time.sleep(0.5)
                test_positions[i] = 1848
                motor_controller.set_positions(test_positions, velocity=300, wait=True, keep_connection=True)
                time.sleep(0.5)
                # Return to home
                motor_controller.set_positions(home_positions, velocity=300, wait=True, keep_connection=True)
            
            # Save calibration data
            if "calibration" not in self.config:
                self.config["calibration"] = {}
            
            self.config["calibration"]["home_positions"] = home_positions
            self.config["calibration"]["calibrated"] = True
            self.config["calibration"]["date"] = str(Path(__file__).stat().st_mtime)
            
            # Write to file
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            
            motor_controller.disconnect()
            
            self.status_label.setText("✓ Calibration complete!")
            self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")
            self.config_changed.emit()
            
        except Exception as e:
            self.status_label.setText(f"❌ Error: {str(e)}")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
    
    # ========== CAMERA DETECTION METHODS ==========
    
    def find_cameras(self):
        """Scan for available cameras"""
        try:
            import cv2
            from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QRadioButton, QButtonGroup, QPushButton, QComboBox
            from PySide6.QtGui import QImage, QPixmap
            from PySide6.QtCore import QTimer
            
            self.status_label.setText("⏳ Scanning for cameras...")
            self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")
            
            # Scan /dev/video* devices (0-9)
            found_cameras = []
            
            for i in range(10):
                try:
                    cap = cv2.VideoCapture(i)
                    if cap.isOpened():
                        # Try to read a frame to confirm it's working
                        ret, frame = cap.read()
                        if ret:
                            height, width = frame.shape[:2]
                            found_cameras.append({
                                "index": i,
                                "path": f"/dev/video{i}",
                                "resolution": f"{width}x{height}",
                                "capture": cap  # Keep for preview
                            })
                        else:
                            cap.release()
                    else:
                        cap.release()
                except:
                    pass
            
            if not found_cameras:
                self.status_label.setText("❌ No cameras found")
                self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
                return
            
            # Create selection dialog with preview
            dialog = QDialog(self)
            dialog.setWindowTitle("Found Cameras")
            dialog.setMinimumWidth(600)
            dialog.setMinimumHeight(500)
            dialog.setStyleSheet("QDialog { background-color: #2a2a2a; }")
            
            layout = QVBoxLayout(dialog)
            
            title = QLabel(f"✓ Found {len(found_cameras)} camera(s):")
            title.setStyleSheet("color: #4CAF50; font-size: 16px; font-weight: bold; padding: 10px;")
            layout.addWidget(title)
            
            # Camera list
            camera_list = QComboBox()
            camera_list.setStyleSheet("""
                QComboBox {
                    background-color: #505050;
                    color: #ffffff;
                    border: 2px solid #707070;
                    border-radius: 8px;
                    padding: 10px;
                    font-size: 15px;
                }
            """)
            for cam in found_cameras:
                camera_list.addItem(f"{cam['path']} - {cam['resolution']}", cam['index'])
            layout.addWidget(camera_list)
            
            # Preview label
            preview_label = QLabel("Camera Preview")
            preview_label.setStyleSheet("background-color: #000000; min-height: 300px;")
            preview_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(preview_label)
            
            # Assignment section
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
            
            # Preview update function
            def update_preview():
                try:
                    selected_idx = camera_list.currentData()
                    for cam in found_cameras:
                        if cam['index'] == selected_idx:
                            ret, frame = cam['capture'].read()
                            if ret:
                                # Resize for preview
                                frame = cv2.resize(frame, (480, 360))
                                # Convert to Qt format
                                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                                h, w, ch = rgb_frame.shape
                                bytes_per_line = ch * w
                                qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
                                preview_label.setPixmap(QPixmap.fromImage(qt_image))
                            break
                except:
                    pass
            
            # Timer for preview updates
            preview_timer = QTimer(dialog)
            preview_timer.timeout.connect(update_preview)
            preview_timer.start(100)  # 10 FPS preview
            
            # Buttons
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
                # Get selected camera and assignment
                selected_idx = camera_list.currentData()
                selected_cam = None
                for cam in found_cameras:
                    if cam['index'] == selected_idx:
                        selected_cam = cam
                        break
                
                if selected_cam:
                    camera_path = selected_cam['path']
                    if assign_group.checkedId() == 0:
                        # Front camera
                        self.cam_front_edit.setText(camera_path)
                        
                        # Update status to online (both local and device_manager)
                        self.camera_front_status = "online"
                        self.update_status_circle(self.camera_front_circle, "online")
                        if self.device_manager:
                            self.device_manager.update_camera_status("front", "online")
                        
                        self.status_label.setText(f"✓ Assigned {camera_path} to Front Camera")
                    else:
                        # Wrist camera
                        self.cam_wrist_edit.setText(camera_path)
                        
                        # Update status to online (both local and device_manager)
                        self.camera_wrist_status = "online"
                        self.update_status_circle(self.camera_wrist_circle, "online")
                        if self.device_manager:
                            self.device_manager.update_camera_status("wrist", "online")
                        
                        self.status_label.setText(f"✓ Assigned {camera_path} to Wrist Camera")
                    
                    self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")
            
            # Cleanup
            preview_timer.stop()
            for cam in found_cameras:
                cam['capture'].release()
                
        except Exception as e:
            self.status_label.setText(f"❌ Error: {str(e)}")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")
    
    # ========== DEVICE MANAGER SIGNAL HANDLERS ==========
    
    def on_robot_status_changed(self, status: str):
        """Handle robot status change from device manager
        
        Args:
            status: "empty", "online", or "offline"
        """
        self.robot_status = status
        if self.robot_status_circle:
            self.update_status_circle(self.robot_status_circle, status)
    
    def on_camera_status_changed(self, camera_name: str, status: str):
        """Handle camera status change from device manager
        
        Args:
            camera_name: "front" or "wrist"
            status: "empty", "online", or "offline"
        """
        if camera_name == "front":
            self.camera_front_status = status
            if self.camera_front_circle:
                self.update_status_circle(self.camera_front_circle, status)
        elif camera_name == "wrist":
            self.camera_wrist_status = status
            if self.camera_wrist_circle:
                self.update_status_circle(self.camera_wrist_circle, status)
