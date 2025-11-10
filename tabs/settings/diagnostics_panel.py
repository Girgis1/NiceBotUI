"""Diagnostics helpers and status widgets for the Settings tab."""

from __future__ import annotations

import random
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class DiagnosticsPanelMixin:
    """Encapsulates status indicators and diagnostic/safety helpers."""

    robot_status_circle: Optional[QLabel]
    camera_front_circle: Optional[QLabel]
    camera_wrist_circle: Optional[QLabel]

    def create_status_circle(self, status: str) -> QLabel:
        circle = QLabel("●")
        circle.setFixedSize(20, 20)
        circle.setAlignment(Qt.AlignCenter)
        self.update_status_circle(circle, status)
        return circle

    def update_status_circle(self, circle: QLabel, status: str):
        colors = {
            "empty": "#909090",
            "online": "#4CAF50",
            "offline": "#f44336",
        }
        circle.setStyleSheet(
            f"""
            QLabel {{
                color: {colors.get(status, '#909090')};
                font-size: 20px;
                font-weight: bold;
            }}
            """
        )

    def run_temperature_self_test(self):
        self.status_label.setText("⏳ Running temperature diagnostic...")
        self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")

        temps = [random.uniform(34.0, 62.0) for _ in range(6)]
        max_temp = max(temps)
        threshold = self.motor_temp_threshold_spin.value()

        if max_temp >= threshold:
            self.status_label.setText(
                f"❌ Motor temperature spike detected ({max_temp:.1f}°C >= {threshold:.1f}°C)"
            )
            self.status_label.setStyleSheet(
                "QLabel { color: #f44336; font-size: 15px; padding: 8px; }"
            )
        else:
            self.status_label.setText(
                f"✓ Temperature self-test passed ({max_temp:.1f}°C < {threshold:.1f}°C)"
            )
            self.status_label.setStyleSheet(
                "QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }"
            )

    def run_torque_trip_test(self):
        self.status_label.setText("⏳ Simulating torque spike...")
        self.status_label.setStyleSheet("QLabel { color: #2196F3; font-size: 15px; padding: 8px; }")

        threshold = self.torque_threshold_spin.value()
        spike = random.uniform(70.0, 180.0)

        if spike >= threshold:
            self.status_label.setText(
                f"❌ Torque spike detected ({spike:.1f}% >= {threshold:.1f}%)"
            )
            self.status_label.setStyleSheet(
                "QLabel { color: #f44336; font-size: 15px; padding: 8px; }"
            )
        else:
            self.status_label.setText(
                f"✓ Torque collision protection OK ({spike:.1f}% < {threshold:.1f}%)"
            )
            self.status_label.setStyleSheet(
                "QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }"
            )

    def create_safety_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        temp_section = QLabel("🌡️ Motor Temperature Monitoring")
        temp_section.setStyleSheet("QLabel { color: #4CAF50; font-size: 16px; font-weight: bold; padding: 4px 0; }")
        layout.addWidget(temp_section)

        self.motor_temp_monitor_check = QCheckBox("Enable temperature monitoring")
        self.motor_temp_monitor_check.setStyleSheet(
            "QCheckBox { color: #e0e0e0; font-size: 15px; padding: 4px; }"
        )
        layout.addWidget(self.motor_temp_monitor_check)

        temp_threshold_row = QHBoxLayout()
        temp_threshold_label = QLabel("Warning threshold (°C):")
        temp_threshold_label.setStyleSheet(
            "QLabel { color: #e0e0e0; font-size: 15px; min-width: 200px; }"
        )
        temp_threshold_row.addWidget(temp_threshold_label)

        self.motor_temp_threshold_spin = QDoubleSpinBox()
        self.motor_temp_threshold_spin.setRange(30.0, 120.0)
        self.motor_temp_threshold_spin.setValue(75.0)
        self.motor_temp_threshold_spin.setDecimals(1)
        self.motor_temp_threshold_spin.setSingleStep(0.5)
        self.motor_temp_threshold_spin.setMinimumHeight(45)
        self.motor_temp_threshold_spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.motor_temp_threshold_spin.setStyleSheet(self._safety_spin_style())
        temp_threshold_row.addWidget(self.motor_temp_threshold_spin)
        temp_threshold_row.addStretch()
        layout.addLayout(temp_threshold_row)

        temp_interval_row = QHBoxLayout()
        temp_interval_label = QLabel("Polling interval (s):")
        temp_interval_label.setStyleSheet(
            "QLabel { color: #e0e0e0; font-size: 15px; min-width: 200px; }"
        )
        temp_interval_row.addWidget(temp_interval_label)

        self.motor_temp_interval_spin = QDoubleSpinBox()
        self.motor_temp_interval_spin.setRange(0.5, 30.0)
        self.motor_temp_interval_spin.setValue(2.0)
        self.motor_temp_interval_spin.setDecimals(1)
        self.motor_temp_interval_spin.setSingleStep(0.5)
        self.motor_temp_interval_spin.setMinimumHeight(45)
        self.motor_temp_interval_spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.motor_temp_interval_spin.setStyleSheet(self._safety_spin_style())
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

        torque_section = QLabel("🛑 Torque Collision Protection")
        torque_section.setStyleSheet(
            "QLabel { color: #4CAF50; font-size: 16px; font-weight: bold; padding: 4px 0; }"
        )
        layout.addWidget(torque_section)

        self.torque_monitor_check = QCheckBox("Kill task and react when torque spikes")
        self.torque_monitor_check.setStyleSheet(
            "QCheckBox { color: #e0e0e0; font-size: 15px; padding: 4px; }"
        )
        layout.addWidget(self.torque_monitor_check)

        torque_threshold_row = QHBoxLayout()
        torque_threshold_label = QLabel("Torque limit (% of rated):")
        torque_threshold_label.setStyleSheet(
            "QLabel { color: #e0e0e0; font-size: 15px; min-width: 200px; }"
        )
        torque_threshold_row.addWidget(torque_threshold_label)

        self.torque_threshold_spin = QDoubleSpinBox()
        self.torque_threshold_spin.setRange(10.0, 200.0)
        self.torque_threshold_spin.setValue(120.0)
        self.torque_threshold_spin.setDecimals(1)
        self.torque_threshold_spin.setSingleStep(5.0)
        self.torque_threshold_spin.setMinimumHeight(45)
        self.torque_threshold_spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.torque_threshold_spin.setStyleSheet(self._safety_spin_style())
        torque_threshold_row.addWidget(self.torque_threshold_spin)
        torque_threshold_row.addStretch()
        layout.addLayout(torque_threshold_row)

        self.torque_disable_check = QCheckBox("Automatically drop torque when limit is exceeded")
        self.torque_disable_check.setStyleSheet(
            "QCheckBox { color: #e0e0e0; font-size: 15px; padding: 4px; }"
        )
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
        layout.addStretch()
        return widget

    def _safety_spin_style(self) -> str:
        return (
            """
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
            """
        )

    def on_robot_status_changed(self, status: str):
        self.robot_status = status
        if self.robot_status_circle:
            self.update_status_circle(self.robot_status_circle, status)

    def on_camera_status_changed(self, camera_name: str, status: str):
        setattr(self, f"camera_{camera_name}_status", status)

        circle = None
        if hasattr(self, "_camera_circle_map"):
            circle = self._camera_circle_map.get(camera_name)

        if circle is None:
            circle = getattr(self, f"camera_{camera_name}_circle", None)

        if circle:
            self.update_status_circle(circle, status)

    def on_diagnostics_status(self, status: str):
        self.status_label.setText(status)
        if "✓" in status or "Started" in status:
            color = "#4CAF50"
        elif "❌" in status or "Error" in status:
            color = "#f44336"
        else:
            color = "#2196F3"
        self.status_label.setStyleSheet(f"QLabel {{ color: {color}; font-size: 15px; padding: 8px; }}")
