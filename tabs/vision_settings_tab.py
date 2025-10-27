"""Vision settings tab providing per-camera pipeline controls."""

from __future__ import annotations

import time
import uuid
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

try:  # Optional dependencies for preview dialog
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except ImportError:  # pragma: no cover - handled gracefully at runtime
    cv2 = None  # type: ignore
    np = None  # type: ignore

from vision_pipelines import (
    PIPELINE_DEFINITIONS,
    VISION_PROFILE_PATH,
    VisionEventBus,
    create_pipeline,
    load_vision_profile,
    save_vision_profile,
)
from utils.camera_hub import CameraStreamHub


def _hex_to_bgr(value: str) -> Tuple[int, int, int]:
    """Convert '#RRGGBB' strings to OpenCV-friendly BGR tuples."""
    if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
        return 51, 255, 153  # default teal accent
    try:
        red = int(value[1:3], 16)
        green = int(value[3:5], 16)
        blue = int(value[5:7], 16)
        return blue, green, red
    except ValueError:
        return 51, 255, 153


class VisionCameraTestDialog(QDialog):
    """Live vision preview dialog for a single camera."""

    def __init__(
        self,
        camera_name: str,
        camera_label: str,
        pipeline_configs: List[Dict],
        app_config: Dict,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Vision Preview — {camera_label}")
        self.resize(920, 600)

        self.camera_name = camera_name
        self.camera_label = camera_label
        self._pipeline_configs = pipeline_configs
        self._app_config = app_config
        self._hub: Optional[CameraStreamHub] = None
        self._pipelines = self._build_pipelines()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        info = QLabel(
            "Live preview with your active vision pipelines. Toggle debug overlays in the slot settings "
            "to visualize masks, heatmaps, and thresholded regions for this camera."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #e0e0e0; font-size: 14px;")
        layout.addWidget(info)

        self.video_label = QLabel("Preparing camera preview…")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(640, 360)
        self.video_label.setStyleSheet("background-color: #2a2a2a; border-radius: 8px; color: #808080;")
        self.video_label.setScaledContents(True)
        layout.addWidget(self.video_label, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #e0e0e0; font-size: 14px; padding: 6px;")
        layout.addWidget(self.status_label)

        button_row = QHBoxLayout()
        button_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setMinimumWidth(120)
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

        if cv2 is None or np is None:  # pragma: no cover - requires optional deps
            self.status_label.setText("❌ OpenCV and NumPy are required for the vision preview.")
            return

        try:
            self._hub = CameraStreamHub.instance(app_config)
        except Exception as exc:  # pragma: no cover - runtime guard
            self.status_label.setText(f"❌ Camera hub unavailable: {exc}")
            print(f"[VISION] Unable to start preview hub: {exc}")
            return

        if not self._pipelines:
            self.status_label.setText("ℹ️ No active pipelines – showing raw camera feed.")
        else:
            names = ", ".join(pipeline.config.get("label", pipeline.pipeline_type.title()) for pipeline in self._pipelines)
            self.status_label.setText(f"Running pipelines: {names}")

        self._timer = QTimer(self)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self._update_frame)
        self._timer.start()

    def _build_pipelines(self) -> List:
        pipelines: List = []
        for cfg in self._pipeline_configs:
            if not isinstance(cfg, dict):
                continue
            if not cfg.get("enabled", True):
                continue
            pipeline_type = cfg.get("type")
            if not pipeline_type:
                continue
            pipeline_id = cfg.get("id") or f"{self.camera_name}_{pipeline_type}_{len(pipelines)}"
            try:
                pipeline = create_pipeline(pipeline_type, pipeline_id, self.camera_name, cfg)
            except ValueError as exc:
                print(f"[VISION] Skipping pipeline preview ({pipeline_type}): {exc}")
                continue
            pipelines.append(pipeline)
        return pipelines

    def _blend_overlay(self, frame: "np.ndarray", overlay: "np.ndarray", metadata: Dict) -> "np.ndarray":
        if cv2 is None or np is None:
            return frame
        try:
            resized = cv2.resize(overlay, (frame.shape[1], frame.shape[0]))
        except Exception:
            return frame

        color_hex = metadata.get("mask_color")
        if isinstance(color_hex, str):
            mask = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
            mask_norm = (mask.astype(np.float32) / 255.0)[..., None]
            b, g, r = _hex_to_bgr(color_hex)
            tint = mask_norm * np.array([b, g, r], dtype=np.float32)
            resized = np.clip(tint, 0, 255).astype("uint8")

        try:
            return cv2.addWeighted(frame, 0.65, resized, 0.35, 0)
        except Exception:
            return frame

    def _draw_status_text(self, frame: "np.ndarray", lines: List[str]) -> "np.ndarray":
        if cv2 is None:
            return frame
        annotated = frame.copy()
        for idx, text in enumerate(lines):
            y = 28 + idx * 24
            cv2.putText(
                annotated,
                text,
                (12, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
        return annotated

    def _update_frame(self) -> None:
        if self._hub is None or cv2 is None or np is None:
            return

        frame = self._hub.get_frame(self.camera_name, preview=True)
        if frame is None:
            self.status_label.setText("⚠️ Waiting for camera frames…")
            self.video_label.setText("Waiting for frames…")
            return

        base = frame.copy()
        status_lines: List[str] = []
        timestamp = time.time()

        display = base
        for pipeline in self._pipelines:
            try:
                result = pipeline.process(base.copy(), timestamp)
            except Exception as exc:  # pragma: no cover - resilience
                label = getattr(pipeline, "pipeline_id", "pipeline")
                status_lines.append(f"{label}: error {exc}")
                continue

            indicator = "✅" if result.detected else "…"
            status_lines.append(f"{result.label} {indicator} ({result.confidence:.0%})")
            if result.overlay is not None:
                display = self._blend_overlay(display, result.overlay, result.metadata)

        if not status_lines:
            status_lines.append("Raw feed only (no pipelines enabled).")

        self.status_label.setText(" • ".join(status_lines))
        display = self._draw_status_text(display, status_lines[:3])

        rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        height, width, channel = rgb.shape
        bytes_per_line = channel * width
        qimage = QImage(rgb.data, width, height, bytes_per_line, QImage.Format_RGB888)
        self.video_label.setPixmap(QPixmap.fromImage(qimage))
        self.video_label.setText("")

    def closeEvent(self, event) -> None:  # noqa: D401 - Qt override
        if hasattr(self, "_timer"):
            self._timer.stop()
        super().closeEvent(event)


class PipelineSlotWidget(QFrame):
    """Widget representing a single pipeline slot for a camera."""

    config_changed = Signal()

    def __init__(
        self,
        camera_name: str,
        slot_index: int,
        initial: Optional[Dict],
    ) -> None:
        super().__init__()
        self.camera_name = camera_name
        self.slot_index = slot_index
        self.pipeline_id = initial.get("id") if initial else f"{camera_name}_slot{slot_index}_{uuid.uuid4().hex[:6]}"
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "QFrame { background-color: #2d2d2d; border: 1px solid #3a3a3a; border-radius: 6px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(QLabel(f"Slot {slot_index + 1}"))

        self.enabled_check = QCheckBox("Enabled")
        self.enabled_check.setChecked(initial.get("enabled", False) if initial else False)
        self.enabled_check.stateChanged.connect(self._notify_config_changed)
        header.addWidget(self.enabled_check)
        header.addStretch()

        layout.addLayout(header)

        self.type_combo = QComboBox()
        self.type_combo.addItem("Disabled", None)
        default_index = 0
        for idx, (key, definition) in enumerate(PIPELINE_DEFINITIONS.items(), start=1):
            self.type_combo.addItem(definition["display_name"], key)
            if initial and initial.get("type") == key:
                default_index = idx
        self.type_combo.setCurrentIndex(default_index)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        layout.addWidget(self.type_combo)

        self.field_container = QGridLayout()
        self.field_container.setContentsMargins(0, 0, 0, 0)
        self.field_container.setSpacing(6)
        layout.addLayout(self.field_container)

        self.field_widgets: Dict[str, QWidget] = {}
        self._on_type_changed()
        if initial:
            self._apply_initial(initial)

    # ------------------------------------------------------------------

    def _apply_initial(self, initial: Dict) -> None:
        options = initial.get("options", {})
        for name, widget in self.field_widgets.items():
            if name not in options:
                continue
            value = options[name]
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value))
            elif isinstance(widget, QLineEdit):
                widget.setText(str(value))

    def _clear_fields(self) -> None:
        while self.field_container.count():
            item = self.field_container.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        self.field_widgets.clear()

    def _on_type_changed(self) -> None:
        self._clear_fields()
        pipeline_type = self.type_combo.currentData()
        if pipeline_type is None:
            self.config_changed.emit()
            return
        definition = PIPELINE_DEFINITIONS.get(pipeline_type, {})
        defaults = definition.get("default", {})
        for row, field in enumerate(definition.get("fields", [])):
            label = QLabel(field.get("label", field["name"]))
            label.setStyleSheet("color: #e0e0e0; font-size: 12px;")
            self.field_container.addWidget(label, row, 0)

            widget: QWidget
            field_type = field.get("type", "text")
            if field_type == "bool":
                widget = QCheckBox()
                widget.setChecked(bool(defaults.get(field["name"], field.get("default", False))))
                widget.stateChanged.connect(self._notify_config_changed)
            elif field_type == "float":
                widget = QDoubleSpinBox()
                widget.setDecimals(2)
                widget.setSingleStep(field.get("step", 0.05))
                widget.setRange(field.get("min", 0.0), field.get("max", 1.0))
                widget.setValue(float(defaults.get(field["name"], field.get("default", widget.minimum()))))
                widget.valueChanged.connect(self._notify_config_changed)
            else:
                widget = QLineEdit()
                widget.setText(str(defaults.get(field["name"], field.get("default", ""))))
                widget.textChanged.connect(self._notify_config_changed)
            widget.setMinimumWidth(160)
            self.field_container.addWidget(widget, row, 1)
            self.field_widgets[field["name"]] = widget
        self.config_changed.emit()

    # ------------------------------------------------------------------
    def _notify_config_changed(self, *_args) -> None:
        """Normalize widget signal signatures and fan out change notification."""
        self.config_changed.emit()

    def to_dict(self) -> Optional[Dict]:
        pipeline_type = self.type_combo.currentData()
        if pipeline_type is None:
            return None
        options: Dict[str, object] = {}
        for name, widget in self.field_widgets.items():
            if isinstance(widget, QCheckBox):
                options[name] = widget.isChecked()
            elif isinstance(widget, QDoubleSpinBox):
                options[name] = float(widget.value())
            elif isinstance(widget, QLineEdit):
                options[name] = widget.text().strip()
        return {
            "id": self.pipeline_id,
            "type": pipeline_type,
            "enabled": self.enabled_check.isChecked(),
            "options": options,
        }

    def reset(self) -> None:
        self.enabled_check.setChecked(False)
        self.type_combo.setCurrentIndex(0)
        self._on_type_changed()


class VisionSettingsWidget(QWidget):
    """Top-level widget for the Vision tab."""

    profile_saved = Signal(dict)

    def __init__(self, app_config: Dict, parent=None):
        super().__init__(parent)
        self._app_config = app_config
        self._profile_path = VISION_PROFILE_PATH
        self._profile = load_vision_profile(self._profile_path, list(app_config.get("cameras", {}).keys()))
        self._bus = VisionEventBus.instance()

        self.camera_sections: Dict[str, List[PipelineSlotWidget]] = {}
        self.camera_labels: Dict[str, str] = {}

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setSpacing(10)
        self.root_layout.setContentsMargins(10, 10, 10, 10)

        self.intro_label = QLabel(
            "Configure up to three lightweight models per camera. Settings are saved to "
            "`runtime/vision_profiles.json` so trained models can be reapplied instantly."
        )
        self.intro_label.setWordWrap(True)
        self.intro_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        self.root_layout.addWidget(self.intro_label)

        self.section_container = QVBoxLayout()
        self.section_container.setSpacing(10)
        self.root_layout.addLayout(self.section_container)

        self.section_container.addStretch(1)

        self.button_row = QHBoxLayout()
        self.button_row.addStretch()
        
        # Model Manager button
        self.manage_models_btn = QPushButton("🤖 Manage Models")
        self.manage_models_btn.setMinimumWidth(150)
        self.manage_models_btn.clicked.connect(self.open_model_manager)
        self.button_row.addWidget(self.manage_models_btn)
        
        self.reset_btn = QPushButton("Reset Vision Defaults")
        self.reset_btn.clicked.connect(self.reset_defaults)
        self.button_row.addWidget(self.reset_btn)
        self.save_btn = QPushButton("Save Vision Profile")
        self.save_btn.clicked.connect(self.save_profile)
        self.button_row.addWidget(self.save_btn)
        self.root_layout.addLayout(self.button_row)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #4CAF50; font-size: 13px; padding: 6px;")
        self.root_layout.addWidget(self.status_label)

        self.refresh_sections()

    # ------------------------------------------------------------------

    def refresh_sections(self) -> None:
        # Remove previous camera widgets
        while self.section_container.count():
            item = self.section_container.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        self.camera_sections.clear()
        self.camera_labels.clear()

        for camera_name, camera_cfg in self._profile.get("cameras", {}).items():
            display_name = camera_cfg.get("display_name", camera_name.title())
            self.camera_labels[camera_name] = display_name

            group = QGroupBox(display_name)
            group.setStyleSheet(
                "QGroupBox { border: 1px solid #3a3a3a; border-radius: 8px; margin-top: 12px; padding: 10px; "
                "color: #ffffff; font-size: 15px; font-weight: bold; }"
            )
            group_layout = QVBoxLayout(group)
            group_layout.setSpacing(10)

            controls = QHBoxLayout()
            controls.addStretch()
            test_btn = QPushButton("Test Vision Camera")
            test_btn.setMinimumWidth(160)
            test_btn.clicked.connect(lambda _checked=False, name=camera_name: self._open_test_dialog(name))
            controls.addWidget(test_btn)
            group_layout.addLayout(controls)

            slots: List[PipelineSlotWidget] = []
            pipelines = camera_cfg.get("pipelines", [])
            for idx in range(int(self._profile.get("max_pipelines_per_camera", 3))):
                initial = pipelines[idx] if idx < len(pipelines) else None
                slot = PipelineSlotWidget(camera_name, idx, initial or {})
                slot.config_changed.connect(self._on_slot_changed)
                group_layout.addWidget(slot)
                slots.append(slot)
            self.camera_sections[camera_name] = slots
            self.section_container.addWidget(group)

        self.section_container.addStretch(1)

    # ------------------------------------------------------------------

    def _collect_camera_pipelines(self, camera_name: str) -> List[Dict]:
        pipelines: List[Dict] = []
        for slot in self.camera_sections.get(camera_name, []):
            data = slot.to_dict()
            if data is None:
                continue
            pipelines.append(data)
        return pipelines

    def _open_test_dialog(self, camera_name: str) -> None:
        dialog = VisionCameraTestDialog(
            camera_name,
            self.camera_labels.get(camera_name, camera_name.title()),
            self._collect_camera_pipelines(camera_name),
            self._app_config,
            self,
        )
        dialog.exec()

    def _on_slot_changed(self) -> None:
        self.status_label.setText("Vision profile modified – remember to save.")
        self.status_label.setStyleSheet("color: #FFB74D; font-size: 13px; padding: 6px;")
    
    def open_model_manager(self) -> None:
        """Open the model manager dialog"""
        try:
            from vision_pipelines.model_manager_ui import ModelManagerDialog
            dialog = ModelManagerDialog(self)
            dialog.exec()
        except Exception as e:
            self.status_label.setText(f"Error opening model manager: {e}")
            self.status_label.setStyleSheet("color: #f44336; font-size: 13px; padding: 6px;")

    def collect_profile(self) -> Dict:
        profile = load_vision_profile(self._profile_path, list(self.camera_sections.keys()))
        profile["version"] = self._profile.get("version", profile.get("version", 1))
        profile["max_pipelines_per_camera"] = self._profile.get(
            "max_pipelines_per_camera", profile.get("max_pipelines_per_camera", 3)
        )
        for camera_name, slots in self.camera_sections.items():
            collected: List[Dict] = []
            for slot in slots:
                data = slot.to_dict()
                if data is None:
                    continue
                collected.append(data)
            profile["cameras"][camera_name]["pipelines"] = collected
        return profile

    def save_profile(self) -> None:
        profile = self.collect_profile()
        save_vision_profile(profile, self._profile_path)
        self._profile = profile
        self.status_label.setText("✓ Vision profile saved")
        self.status_label.setStyleSheet("color: #4CAF50; font-size: 13px; padding: 6px;")
        self.profile_saved.emit(profile)
        self._bus.profileUpdated.emit(profile)

    def reset_defaults(self) -> None:
        for slots in self.camera_sections.values():
            for slot in slots:
                slot.reset()
        self.status_label.setText("Vision defaults restored – click save to persist.")
        self.status_label.setStyleSheet("color: #FF9800; font-size: 13px; padding: 6px;")

    def update_app_config(self, app_config: Dict) -> None:
        self._app_config = app_config
        profile = load_vision_profile(self._profile_path, list(app_config.get("cameras", {}).keys()))
        self._profile = profile
        self.refresh_sections()


__all__ = ["VisionSettingsWidget", "VisionCameraTestDialog"]
