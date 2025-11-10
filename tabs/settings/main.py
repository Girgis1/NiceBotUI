"""Main SettingsTab widget composed from modular mixins."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QLabel,
)

from tabs.diagnostics_tab import DiagnosticsTab

from .camera_panel import CameraPanelMixin
from .data_access import SettingsDataAccessMixin
from .diagnostics_panel import DiagnosticsPanelMixin
from .multi_arm import MultiArmMixin


class SettingsTab(
    QWidget,
    CameraPanelMixin,
    DiagnosticsPanelMixin,
    SettingsDataAccessMixin,
    MultiArmMixin,
):
    """Modernized Settings tab that composes extracted helpers."""

    config_changed = Signal()

    def __init__(self, config: dict, parent: Optional[QWidget] = None, device_manager=None):
        super().__init__(parent)
        self.config = config
        self.config_path = Path(__file__).resolve().parent.parent / "config.json"
        self.device_manager = device_manager
        self._home_thread: Optional[QThread] = None
        self._home_worker = None
        self._pending_home_velocity: Optional[int] = None

        # Mode selector + arm widgets (populated in mixins)
        self.robot_mode_selector = None
        self.teleop_mode_selector = None
        self.solo_arm_selector = None
        self.solo_arm_config = None
        self.robot_arm1_config = None
        self.robot_arm2_config = None
        self.teleop_solo_arm_selector = None
        self.teleop_solo_arm_config = None
        self.teleop_arm1_config = None
        self.teleop_arm2_config = None

        # Device-state tracking
        self.robot_status = "empty"
        self.camera_front_status = "empty"
        self.camera_wrist_status = "empty"
        self.camera_extra_status = "empty"
        self.robot_status_circle = None
        self.camera_front_circle = None
        self.camera_wrist_circle = None
        self.camera_extra_circle = None
        self.extra_camera_label = None
        self.extra_camera_key: Optional[str] = None

        self.init_ui()
        self.load_settings()

        if self.device_manager:
            self.device_manager.robot_status_changed.connect(self.on_robot_status_changed)
            self.device_manager.camera_status_changed.connect(self.on_camera_status_changed)

    # --------------------------------------------------------------------- UI
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("⚙️ Settings")
        title.setStyleSheet(
            """
            QLabel {
                color: #ffffff;
                font-size: 22px;
                font-weight: bold;
                padding: 8px;
            }
            """
        )
        main_layout.addWidget(title)

        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tab_widget.setStyleSheet(
            """
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
            """
        )
        self.tab_widget.tabBar().setCursor(Qt.PointingHandCursor)

        robot_tab = self.wrap_tab(self.create_robot_tab())
        self.tab_widget.addTab(robot_tab, "🤖 Robot")

        camera_tab = self.wrap_tab(self.create_camera_tab())
        self.tab_widget.addTab(camera_tab, "📷 Camera")

        policy_tab = self.wrap_tab(self.create_policy_tab())
        self.tab_widget.addTab(policy_tab, "🧠 Policy")

        control_tab = self.wrap_tab(self.create_control_tab())
        self.tab_widget.addTab(control_tab, "🎮 Control")

        safety_tab = self.wrap_tab(self.create_safety_tab())
        self.tab_widget.addTab(safety_tab, "🛡️ Safety")

        self.diagnostics_tab = DiagnosticsTab(self.config, self)
        self.diagnostics_tab.status_changed.connect(self.on_diagnostics_status)
        diagnostics_wrapper = self.wrap_tab(self.diagnostics_tab)
        self.tab_widget.addTab(diagnostics_wrapper, "🔧 Diagnostics")

        main_layout.addWidget(self.tab_widget)

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

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 14px; padding: 6px; }")
        main_layout.addWidget(self.status_label)

    def get_button_style(self, color1: str, color2: str) -> str:
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

    # ------------------------------------------------------------ Tab Builders
    def create_policy_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.policy_base_edit = self.add_setting_row(layout, "Base Path:", "outputs/train")
        self.policy_device_edit = self.add_setting_row(layout, "Device:", "cuda")

        mode_section = QLabel("Execution Mode:")
        mode_section.setStyleSheet(
            "QLabel { color: #e0e0e0; font-size: 16px; font-weight: bold; padding: 10px 0 5px 0; }"
        )
        layout.addWidget(mode_section)

        self.policy_local_check = QCheckBox("Use Local Mode (lerobot-record)")
        self.policy_local_check.setChecked(True)
        self.policy_local_check.setStyleSheet(
            """
            QCheckBox {
                color: #e0e0e0;
                font-size: 15px;
                padding: 8px;
            }
            QCheckBox::indicator {
                width: 24px;
                height: 24px;
            }
            """
        )
        layout.addWidget(self.policy_local_check)

        mode_help = QLabel(
            "Local: Uses lerobot-record with policy (auto-cleans eval folders)\n"
            "Server: Uses async inference (policy server + robot client)"
        )
        mode_help.setStyleSheet("QLabel { color: #909090; font-size: 13px; padding: 5px 25px; }")
        mode_help.setWordWrap(True)
        layout.addWidget(mode_help)

        section = QLabel("Async Inference (Server Mode):")
        section.setStyleSheet(
            "QLabel { color: #e0e0e0; font-size: 16px; font-weight: bold; padding: 10px 0 5px 0; }"
        )
        layout.addWidget(section)

        self.async_host_edit = self.add_setting_row(layout, "Server Host:", "127.0.0.1")
        self.async_port_spin = self.add_spinbox_row(layout, "Server Port:", 1024, 65535, 8080)

        layout.addStretch()
        return widget

    def create_control_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.num_episodes_spin = self.add_spinbox_row(layout, "Episodes:", 1, 100, 10)
        self.episode_time_spin = self.add_doublespinbox_row(layout, "Episode Time (s):", 1.0, 300.0, 20.0)
        self.warmup_spin = self.add_doublespinbox_row(layout, "Warmup (s):", 0.0, 60.0, 3.0)
        self.reset_time_spin = self.add_doublespinbox_row(layout, "Reset Time (s):", 0.0, 60.0, 8.0)
        self.robot_fps_spin = self.add_spinbox_row(layout, "Robot Hertz (FPS):", 1, 120, 60)
        self.position_tolerance_spin = self.add_spinbox_row(layout, "Position Tolerance (units):", 1, 100, 45)

        self.position_verification_check = QCheckBox("Enable Position Verification")
        self.position_verification_check.setStyleSheet(
            "QCheckBox { color: #e0e0e0; font-size: 15px; padding: 8px; }"
        )
        layout.addWidget(self.position_verification_check)

        self.display_data_check = QCheckBox("Display Data")
        self.display_data_check.setStyleSheet(
            "QCheckBox { color: #e0e0e0; font-size: 15px; padding: 8px; }"
        )
        layout.addWidget(self.display_data_check)

        self.object_gate_check = QCheckBox("Object Gate")
        self.object_gate_check.setStyleSheet(
            "QCheckBox { color: #e0e0e0; font-size: 15px; padding: 8px; }"
        )
        layout.addWidget(self.object_gate_check)

        layout.addStretch()
        return widget

    # -------------------------------------------------------- Form utilities
    def add_setting_row(self, layout: QVBoxLayout, label_text: str, default_value: str) -> QLineEdit:
        row = QHBoxLayout()
        label = QLabel(label_text)
        label.setStyleSheet(
            """
            QLabel {
                color: #e0e0e0;
                font-size: 14px;
                min-width: 150px;
            }
            """
        )
        row.addWidget(label)

        edit = QLineEdit(default_value)
        edit.setStyleSheet(
            """
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
            """
        )
        edit.setFixedHeight(45)
        row.addWidget(edit)
        row.addStretch()
        layout.addLayout(row)
        return edit

    def add_spinbox_row(
        self, layout: QVBoxLayout, label_text: str, min_val: int, max_val: int, default: int
    ) -> QSpinBox:
        row = QHBoxLayout()
        label = QLabel(label_text)
        label.setStyleSheet(
            """
            QLabel {
                color: #e0e0e0;
                font-size: 14px;
                min-width: 180px;
            }
            """
        )
        row.addWidget(label)

        spin = QSpinBox()
        spin.setRange(min_val, max_val)
        spin.setValue(default)
        spin.setFixedHeight(45)
        spin.setButtonSymbols(QSpinBox.NoButtons)
        spin.setStyleSheet(
            """
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
            """
        )
        row.addWidget(spin)
        row.addStretch()
        layout.addLayout(row)
        return spin

    def add_doublespinbox_row(
        self, layout: QVBoxLayout, label_text: str, min_val: float, max_val: float, default: float
    ) -> QDoubleSpinBox:
        row = QHBoxLayout()
        label = QLabel(label_text)
        label.setStyleSheet(
            """
            QLabel {
                color: #e0e0e0;
                font-size: 14px;
                min-width: 180px;
            }
            """
        )
        row.addWidget(label)

        spin = QDoubleSpinBox()
        spin.setRange(min_val, max_val)
        spin.setValue(default)
        spin.setDecimals(1)
        spin.setSingleStep(0.5)
        spin.setFixedHeight(45)
        spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        spin.setStyleSheet(
            """
            QDoubleSpinBox {
                background-color: #505050;
                color: #ffffff;
                border: 2px solid #707070;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
            }
            QDoubleSpinBox:focus {
                border-color: #4CAF50;
                background-color: #555555;
            }
            """
        )
        row.addWidget(spin)
        row.addStretch()
        layout.addLayout(row)
        return spin
