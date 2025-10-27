"""Vision settings tab providing per-camera pipeline controls."""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
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

from vision_pipelines import (
    PIPELINE_DEFINITIONS,
    VISION_PROFILE_PATH,
    VisionEventBus,
    load_vision_profile,
    save_vision_profile,
)


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
        self.enabled_check.stateChanged.connect(self.config_changed.emit)
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
                widget.stateChanged.connect(self.config_changed.emit)
            elif field_type == "float":
                widget = QDoubleSpinBox()
                widget.setDecimals(2)
                widget.setSingleStep(field.get("step", 0.05))
                widget.setRange(field.get("min", 0.0), field.get("max", 1.0))
                widget.setValue(float(defaults.get(field["name"], field.get("default", widget.minimum()))))
                widget.valueChanged.connect(self.config_changed.emit)
            else:
                widget = QLineEdit()
                widget.setText(str(defaults.get(field["name"], field.get("default", ""))))
                widget.textChanged.connect(self.config_changed.emit)
            widget.setMinimumWidth(160)
            self.field_container.addWidget(widget, row, 1)
            self.field_widgets[field["name"]] = widget
        self.config_changed.emit()

    # ------------------------------------------------------------------

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

        for camera_name, camera_cfg in self._profile.get("cameras", {}).items():
            group = QGroupBox(camera_cfg.get("display_name", camera_name.title()))
            group.setStyleSheet(
                "QGroupBox { border: 1px solid #3a3a3a; border-radius: 8px; margin-top: 12px; padding: 10px; "
                "color: #ffffff; font-size: 15px; font-weight: bold; }"
            )
            group_layout = QVBoxLayout(group)
            group_layout.setSpacing(10)

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

    def _on_slot_changed(self) -> None:
        self.status_label.setText("Vision profile modified – remember to save.")
        self.status_label.setStyleSheet("color: #FFB74D; font-size: 13px; padding: 6px;")

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


__all__ = ["VisionSettingsWidget"]
