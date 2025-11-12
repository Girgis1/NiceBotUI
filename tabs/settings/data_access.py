"""Data-access helpers for the modular Settings tab."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from utils.config_compat import ensure_multi_arm_config, get_home_velocity
from utils.config_store import ConfigStore

DEFAULT_HOME_POSITIONS = [2082, 1106, 2994, 2421, 1044, 2054]


def read_config(path: Path) -> Dict[str, Any]:
    """Read a JSON config file, returning an empty dict on failure."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


class SettingsDataAccessMixin:
    """Mixin housing config serialization helpers for SettingsTab."""

    def _ensure_schema(self) -> Dict[str, Any]:
        self.config = ensure_multi_arm_config(self.config)
        return self.config

    def _ensure_config_store(self) -> None:
        if not hasattr(self, "config_store") or self.config_store is None:
            self.config_store = ConfigStore.instance()

    def load_settings(self):
        """Populate UI widgets from the in-memory config."""
        self._ensure_config_store()
        self.config = self.config_store.get_config()
        config = self._ensure_schema()

        # Load robot mode and set UI
        robot_mode = config.get("robot", {}).get("mode", "solo")
        if self.robot_mode_selector:
            self.robot_mode_selector.set_mode(robot_mode)
            self.on_robot_mode_changed(robot_mode)

        # Load arm configurations
        arms = config.get("robot", {}).get("arms", [])

        if arms:
            arm1 = arms[0]
            if self.robot_arm1_config:
                self.robot_arm1_config.set_port(arm1.get("port", ""))
                self.robot_arm1_config.set_id(arm1.get("id", ""))
                self.robot_arm1_config.set_home_positions(arm1.get("home_positions", []))

        if len(arms) > 1 and self.robot_arm2_config:
            arm2 = arms[1]
            self.robot_arm2_config.set_port(arm2.get("port", ""))
            self.robot_arm2_config.set_id(arm2.get("id", ""))
            self.robot_arm2_config.set_home_positions(arm2.get("home_positions", []))

        if self.solo_arm_config and self.solo_arm_selector:
            self.on_solo_arm_changed(self.solo_arm_selector.currentIndex())

        self.robot_fps_spin.setValue(config.get("robot", {}).get("fps", 30))
        self.position_tolerance_spin.setValue(config.get("robot", {}).get("position_tolerance", 10))
        self.position_verification_check.setChecked(config.get("robot", {}).get("position_verification_enabled", True))

        # Home velocity for backward compatibility with the old home button
        home_vel = get_home_velocity(config, 0)
        if hasattr(self, "rest_velocity_spin") and self.rest_velocity_spin:
            blocked = self.rest_velocity_spin.blockSignals(True)
            self.rest_velocity_spin.setValue(home_vel)
            self.rest_velocity_spin.blockSignals(blocked)

        # Teleop configuration
        teleop_mode = config.get("teleop", {}).get("mode", "solo")
        if self.teleop_mode_selector:
            self.teleop_mode_selector.set_mode(teleop_mode)
            self.on_teleop_mode_changed(teleop_mode)

        teleop_arms = config.get("teleop", {}).get("arms", [])
        if teleop_arms:
            teleop_arm1 = teleop_arms[0]
            if self.teleop_arm1_config:
                self.teleop_arm1_config.set_port(teleop_arm1.get("port", ""))
                self.teleop_arm1_config.set_id(teleop_arm1.get("id", ""))
            if self.teleop_solo_arm_config:
                self.teleop_solo_arm_config.set_port(teleop_arm1.get("port", ""))
                self.teleop_solo_arm_config.set_id(teleop_arm1.get("id", ""))

        if len(teleop_arms) > 1 and self.teleop_arm2_config:
            teleop_arm2 = teleop_arms[1]
            self.teleop_arm2_config.set_port(teleop_arm2.get("port", ""))
            self.teleop_arm2_config.set_id(teleop_arm2.get("id", ""))

        # Cameras
        cameras = config.get("cameras", {})
        front_cam = cameras.get("front", {})
        wrist_cam = cameras.get("wrist", {})
        self.cam_front_edit.setText(str(front_cam.get("index_or_path", "/dev/video1")))
        self.cam_wrist_edit.setText(str(wrist_cam.get("index_or_path", "/dev/video3")))
        self.cam_width_spin.setValue(front_cam.get("width", 640))
        self.cam_height_spin.setValue(front_cam.get("height", 480))
        self.cam_fps_spin.setValue(front_cam.get("fps", 30))

        wrist_right = cameras.get("wrist_right", {})
        if hasattr(self, "cam_wrist_right_edit"):
            self.cam_wrist_right_edit.setText(str(wrist_right.get("index_or_path", "/dev/video5")))

        # Policy settings
        self.policy_base_edit.setText(str(config.get("policy", {}).get("base_path", "outputs/train")))
        self.policy_device_edit.setText(str(config.get("policy", {}).get("device", "cuda")))
        self.policy_local_check.setChecked(config.get("policy", {}).get("local_mode", True))

        # Async inference
        async_cfg = config.get("async_inference", {})
        self.async_host_edit.setText(str(async_cfg.get("server_host", "127.0.0.1")))
        self.async_port_spin.setValue(async_cfg.get("server_port", 8080))

        # Control
        control_cfg = config.get("control", {})
        self.num_episodes_spin.setValue(control_cfg.get("num_episodes", 10))
        self.episode_time_spin.setValue(control_cfg.get("episode_time_s", 20.0))
        self.warmup_spin.setValue(control_cfg.get("warmup_time_s", 3.0))
        self.reset_time_spin.setValue(control_cfg.get("reset_time_s", 8.0))
        self.display_data_check.setChecked(control_cfg.get("display_data", True))

        # UI
        ui_cfg = config.get("ui", {})
        self.object_gate_check.setChecked(ui_cfg.get("object_gate", False))

        # Safety
        safety_cfg = config.get("safety", {})
        self.motor_temp_monitor_check.setChecked(safety_cfg.get("motor_temp_monitoring_enabled", False))
        self.motor_temp_threshold_spin.setValue(safety_cfg.get("motor_temp_threshold_c", 75))
        self.motor_temp_interval_spin.setValue(safety_cfg.get("motor_temp_poll_interval_s", 2.0))
        self.torque_monitor_check.setChecked(safety_cfg.get("torque_monitoring_enabled", False))
        self.torque_threshold_spin.setValue(safety_cfg.get("torque_limit_percent", 120.0))
        self.torque_disable_check.setChecked(safety_cfg.get("torque_auto_disable", True))

    def save_settings(self):
        """Collect UI state and persist it to disk."""
        config = self._ensure_schema()

        robot_cfg = config.setdefault("robot", {})
        arms: List[Dict[str, Any]] = []
        robot_cfg["arms"] = arms

        if self.robot_mode_selector and self.robot_mode_selector.get_mode() == "solo":
            existing_arms = config.get("robot", {}).get("arms", [])
            current_arm_index = self.solo_arm_selector.currentIndex() if self.solo_arm_selector else 0

            while len(existing_arms) < 2:
                existing_arms.append({})

            arm1_data = self._build_solo_arm_payload(existing_arms[0] if existing_arms else {}, current_arm_index == 0, arm_index=1)
            arm2_data = self._build_solo_arm_payload(existing_arms[1] if len(existing_arms) > 1 else {}, current_arm_index == 1, arm_index=2)
            arms.extend([arm1_data, arm2_data])
        else:
            arms.append(self._build_dual_arm_payload(self.robot_arm1_config, name="Follower 1", arm_index=1))
            arms.append(self._build_dual_arm_payload(self.robot_arm2_config, name="Follower 2", arm_index=2))

        robot_cfg["mode"] = self.robot_mode_selector.get_mode() if self.robot_mode_selector else "solo"
        robot_cfg["fps"] = self.robot_fps_spin.value()
        robot_cfg["position_tolerance"] = self.position_tolerance_spin.value()
        robot_cfg["position_verification_enabled"] = self.position_verification_check.isChecked()

        # Cameras
        cameras = config.setdefault("cameras", {})
        front_cfg = cameras.setdefault("front", {})
        wrist_cfg = cameras.setdefault("wrist", {})
        wrist_right_cfg = cameras.setdefault("wrist_right", {})
        front_cfg.update({
            "index_or_path": self.cam_front_edit.text(),
            "width": self.cam_width_spin.value(),
            "height": self.cam_height_spin.value(),
            "fps": self.cam_fps_spin.value(),
        })
        wrist_cfg.update({
            "index_or_path": self.cam_wrist_edit.text(),
            "width": self.cam_width_spin.value(),
            "height": self.cam_height_spin.value(),
            "fps": self.cam_fps_spin.value(),
        })
        wrist_right_cfg.update({
            "index_or_path": self.cam_wrist_right_edit.text() if hasattr(self, "cam_wrist_right_edit") else "",
            "width": self.cam_width_spin.value(),
            "height": self.cam_height_spin.value(),
            "fps": self.cam_fps_spin.value(),
        })

        # Policy
        policy_cfg = config.setdefault("policy", {})
        policy_cfg["base_path"] = self.policy_base_edit.text()
        policy_cfg["device"] = self.policy_device_edit.text()
        policy_cfg["local_mode"] = self.policy_local_check.isChecked()

        # Async inference
        async_cfg = config.setdefault("async_inference", {})
        async_cfg["server_host"] = self.async_host_edit.text()
        async_cfg["server_port"] = self.async_port_spin.value()

        # Control
        control_cfg = config.setdefault("control", {})
        control_cfg["num_episodes"] = self.num_episodes_spin.value()
        control_cfg["episode_time_s"] = self.episode_time_spin.value()
        control_cfg["warmup_time_s"] = self.warmup_spin.value()
        control_cfg["reset_time_s"] = self.reset_time_spin.value()
        control_cfg["display_data"] = self.display_data_check.isChecked()

        # UI
        ui_cfg = config.setdefault("ui", {})
        ui_cfg["object_gate"] = self.object_gate_check.isChecked()

        # Safety
        safety_cfg = config.setdefault("safety", {})
        safety_cfg["motor_temp_monitoring_enabled"] = self.motor_temp_monitor_check.isChecked()
        safety_cfg["motor_temp_threshold_c"] = self.motor_temp_threshold_spin.value()
        safety_cfg["motor_temp_poll_interval_s"] = self.motor_temp_interval_spin.value()
        safety_cfg["torque_monitoring_enabled"] = self.torque_monitor_check.isChecked()
        safety_cfg["torque_limit_percent"] = self.torque_threshold_spin.value()
        safety_cfg["torque_auto_disable"] = self.torque_disable_check.isChecked()

        try:
            self.config_store.set_config(config)
            self.config = self.config_store.get_config()
            self.status_label.setText("✓ Settings saved successfully!")
            self.status_label.setStyleSheet("QLabel { color: #4CAF50; font-size: 15px; padding: 8px; }")
            self.config_changed.emit()
        except Exception as exc:
            self.status_label.setText(f"❌ Error: {exc}")
            self.status_label.setStyleSheet("QLabel { color: #f44336; font-size: 15px; padding: 8px; }")

    def reset_defaults(self):
        """Restore UI controls to known-safe defaults."""
        self._ensure_config_store()
        if self.robot_mode_selector:
            self.robot_mode_selector.set_mode("solo")
            self.on_robot_mode_changed("solo")

        if self.solo_arm_config:
            self.solo_arm_config.set_port("/dev/ttyACM0")
            self.solo_arm_config.set_id("follower_arm")
            self.solo_arm_config.set_home_positions(DEFAULT_HOME_POSITIONS)
        if self.robot_arm1_config:
            self.robot_arm1_config.set_port("/dev/ttyACM0")
            self.robot_arm1_config.set_id("follower_arm")
            self.robot_arm1_config.set_home_positions(DEFAULT_HOME_POSITIONS)
        if self.robot_arm2_config:
            self.robot_arm2_config.set_port("/dev/ttyACM1")
            self.robot_arm2_config.set_id("follower_arm_2")
            self.robot_arm2_config.set_home_positions(DEFAULT_HOME_POSITIONS)

        if self.teleop_mode_selector:
            self.teleop_mode_selector.set_mode("solo")
            self.on_teleop_mode_changed("solo")
        if self.teleop_solo_arm_config:
            self.teleop_solo_arm_config.set_port("/dev/ttyACM1")
            self.teleop_solo_arm_config.set_id("leader_arm")
        if self.teleop_arm1_config:
            self.teleop_arm1_config.set_port("/dev/ttyACM1")
            self.teleop_arm1_config.set_id("leader_arm")
        if self.teleop_arm2_config:
            self.teleop_arm2_config.set_port("/dev/ttyACM2")
            self.teleop_arm2_config.set_id("leader_arm_2")

        self.robot_fps_spin.setValue(30)
        self.position_tolerance_spin.setValue(10)
        self.position_verification_check.setChecked(True)
        if hasattr(self, "rest_velocity_spin") and self.rest_velocity_spin:
            blocked = self.rest_velocity_spin.blockSignals(True)
            self.rest_velocity_spin.setValue(600)
            self.rest_velocity_spin.blockSignals(blocked)

        self.cam_front_edit.setText("/dev/video1")
        self.cam_wrist_edit.setText("/dev/video3")
        if hasattr(self, "cam_wrist_right_edit"):
            self.cam_wrist_right_edit.setText("/dev/video5")
        if hasattr(self, "_apply_camera_assignment_to_config"):
            self._apply_camera_assignment_to_config("front", "/dev/video1")
            self._apply_camera_assignment_to_config("wrist", "/dev/video3")
            self._apply_camera_assignment_to_config("wrist_right", "/dev/video5")
        self.cam_width_spin.setValue(640)
        self.cam_height_spin.setValue(480)
        self.cam_fps_spin.setValue(30)

        self.policy_base_edit.setText("outputs/train")
        self.policy_device_edit.setText("cuda")
        self.policy_local_check.setChecked(True)

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

        self.config_store.save()
        self.config = self.config_store.get_config()
        self.status_label.setText("⚠️ Defaults loaded and saved.")
        self.status_label.setStyleSheet("QLabel { color: #FF9800; font-size: 15px; padding: 8px; }")

    # Helpers -----------------------------------------------------------------

    def _build_solo_arm_payload(self, existing: Dict[str, Any], is_selected: bool, arm_index: int) -> Dict[str, Any]:
        """Create the payload for solo mode arms, preserving unselected slots."""
        if is_selected and self.solo_arm_config:
            return {
                "enabled": True,
                "name": f"Follower {arm_index}",
                "type": "so100_follower",
                "port": self.solo_arm_config.get_port(),
                "id": self.solo_arm_config.get_id(),
                "arm_id": arm_index,
                "home_positions": self.solo_arm_config.get_home_positions(),
                "home_velocity": self.rest_velocity_spin.value(),
            }

        payload = existing.copy()
        payload.setdefault("port", f"/dev/ttyACM{arm_index - 1}")
        payload.setdefault("id", f"follower_arm_{'' if arm_index == 1 else arm_index}")
        payload.setdefault("home_positions", DEFAULT_HOME_POSITIONS)
        payload.setdefault("home_velocity", self.rest_velocity_spin.value())
        payload.update(
            {
                "enabled": False,
                "name": f"Follower {arm_index}",
                "type": "so100_follower",
                "arm_id": arm_index,
            }
        )
        return payload

    def _build_dual_arm_payload(self, widget, name: str, arm_index: int) -> Dict[str, Any]:
        """Translate a SingleArmConfig widget into config data."""
        if not widget:
            return {
                "enabled": True,
                "name": name,
                "type": "so100_follower",
                "port": f"/dev/ttyACM{arm_index - 1}",
                "id": f"follower_{arm_index}",
                "arm_id": arm_index,
                "home_positions": DEFAULT_HOME_POSITIONS,
                "home_velocity": self.rest_velocity_spin.value(),
            }
        return {
            "enabled": True,
            "name": name,
            "type": "so100_follower",
            "port": widget.get_port(),
            "id": widget.get_id(),
            "arm_id": arm_index,
            "home_positions": widget.get_home_positions(),
            "home_velocity": self.rest_velocity_spin.value(),
        }
