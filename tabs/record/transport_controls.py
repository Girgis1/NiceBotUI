"""Transport controls (record, playback, velocity) for RecordTab."""

from __future__ import annotations

import contextlib
from typing import Any, Dict, List

from PySide6.QtCore import QTimer

from utils.logging_utils import log_exception
from utils.motor_controller import MotorController
from utils.motor_manager import get_motor_handle, MotorManager


class TransportControlsMixin:
    """Provides live recording and playback helpers for RecordTab."""

    def toggle_live_recording(self):
        """Toggle industrial precision live recording."""
        teleop_active = getattr(self, "_is_teleop_active", lambda: False)()
        if not self.is_live_recording:
            self._live_record_connected_locally = False
            if teleop_active:
                self.status_label.setText("⚠️ Live Record disabled while teleop is running (shared serial bus).")
                self.live_record_btn.setChecked(False)
                return
            else:
                controller = getattr(self, "motor_controller", None)
                if not controller:
                    self.status_label.setText("❌ Motor controller unavailable")
                    self.live_record_btn.setChecked(False)
                    return
                try:
                    if not controller.bus:
                        if not controller.connect():
                            self.status_label.setText("❌ Failed to connect for live recording")
                            self.live_record_btn.setChecked(False)
                            return
                        self._live_record_connected_locally = True
                except Exception as exc:
                    log_exception("RecordTab: live recording connect failed", exc)
                    self.status_label.setText(f"❌ Live record error: {exc}")
                    self.live_record_btn.setChecked(False)
                    return

            self.is_live_recording = True
            self.last_recorded_position = None
            self.live_recorded_data = []
            self.live_record_start_time = None
            self._live_record_arm_index = getattr(self, "active_arm_index", 0)

            self.set_btn.setEnabled(False)
            self.play_btn.setEnabled(False)
            self.save_btn.setEnabled(False)
            self.action_combo.setEnabled(False)

            interval_ms = int(1000 / self.live_record_rate)
            self.live_record_timer.start(interval_ms)

            self.live_record_btn.setText("⏹ STOP")
            self.status_label.setText(f"🔴 LIVE RECORDING @ {self.live_record_rate}Hz - Move the arm...")
            print(f"[LIVE RECORD] 🎬 STARTED: {self.live_record_rate}Hz, threshold={self.live_position_threshold} units")
        else:
            self.stop_live_recording()

    def stop_live_recording(self):
        """Stop live recording and turn the capture buffer into a table entry."""
        self.is_live_recording = False
        self.live_record_timer.stop()

        self.set_btn.setEnabled(True)
        self.play_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.action_combo.setEnabled(True)

        self.live_record_btn.setChecked(False)
        self.live_record_btn.setText("🔴 LIVE RECORD")
        self.live_record_btn.setEnabled(True)

        if self._live_record_connected_locally:
            try:
                self.motor_controller.disconnect()
            except Exception as exc:
                log_exception("RecordTab: live recording disconnect failed", exc, level="warning")
        self._live_record_connected_locally = False

        point_count = len(self.live_recorded_data)
        if point_count > 0:
            name = f"Recording {self.position_counter}"
            speed = 100
            arm_index = getattr(self, "_live_record_arm_index", getattr(self, "active_arm_index", 0))
            tag_getter = getattr(self, "_arm_tag_for_index", None)
            arm_tag = tag_getter(arm_index) if callable(tag_getter) else ""
            display_name = f"{name} ({arm_tag})" if arm_tag else name

            action = {
                "type": "live_recording",
                "name": display_name,
                "speed": speed,
                "recorded_data": self.live_recorded_data,
                "point_count": point_count,
            }

            metadata_builder = getattr(self, "_build_teleop_metadata", None)
            metadata = metadata_builder() if callable(metadata_builder) else {}
            metadata = dict(metadata) if isinstance(metadata, dict) else {}
            metadata.update({
                "arm_selection": getattr(self, "teleop_target", "both"),
                "arm_index": arm_index,
                "arm_tag": arm_tag,
            })
            if metadata:
                action["metadata"] = metadata

            self.table.add_live_recording(display_name, self.live_recorded_data, speed, metadata=metadata)
            self.position_counter += 1

            self.status_label.setText(f"✓ Live recording saved ({point_count} pts) [{arm_tag or 'Arm'}]")
            print(f"[LIVE RECORD] ✓ SAVED {point_count} points as '{display_name}'")
            print(f"[LIVE RECORD] Data sample: {self.live_recorded_data[:3]} ...")
        else:
            self.status_label.setText("⚠️ No positions captured")
            print("[LIVE RECORD] ⚠️ No positions captured")

        self.live_recorded_data = []
        self.live_record_start_time = None
        self.last_recorded_position = None
        self._live_record_arm_index = getattr(self, "active_arm_index", 0)

    def capture_live_position(self):
        """Capture a live position sample at the configured frequency."""
        if not self.is_live_recording:
            return

        try:
            import time

            if self.live_record_start_time is None:
                self.live_record_start_time = time.time()

            read_fn = getattr(self, "_read_motor_positions_safe", None)
            if callable(read_fn):
                positions = read_fn()
            else:
                positions = []
                controller = getattr(self, "motor_controller", None)
                if controller:
                    positions = controller.read_positions_from_bus()
                    if not positions:
                        positions = controller.read_positions()
            if not positions or len(positions) != 6:
                print("[LIVE RECORD] ⚠️ Failed to read positions")
                return

            timestamp = time.time() - self.live_record_start_time

            max_change = 0
            if self.last_recorded_position is not None:
                max_change = max(
                    abs(positions[i] - self.last_recorded_position[i]) for i in range(6)
                )
                if max_change < self.live_position_threshold:
                    return

            current_velocity = self.velocity_slider.value()
            self.live_recorded_data.append(
                {
                    "positions": positions,
                    "timestamp": timestamp,
                    "velocity": current_velocity,
                }
            )

            self.last_recorded_position = positions

            point_count = len(self.live_recorded_data)
            self.status_label.setText(f"🔴 REC: {point_count} pts, {timestamp:.1f}s")
            print(f"[LIVE RECORD] Point {point_count}: t={timestamp:.3f}s, Δ={max_change} units")

        except Exception as exc:
            log_exception("RecordTab: capture_live_position failed", exc, stack=True)
            print(f"[LIVE RECORD] ❌ ERROR: {exc}")
            self.stop_live_recording()
            self.status_label.setText(f"❌ Recording error: {exc}")

    def on_velocity_changed(self, value: int):
        """Handle velocity slider change - snap to multiples of 10."""
        snapped_value = round(value / 10) * 10
        if snapped_value != value:
            self.velocity_slider.setValue(snapped_value)
        else:
            self.default_velocity = snapped_value
            self.velocity_display.setText(str(snapped_value))

    def toggle_playback(self):
        """Toggle playback of the table actions."""
        if self.play_btn.isChecked():
            self.start_playback()
        else:
            self.stop_playback()

    def toggle_loop(self, checked: bool):
        """Toggle looping playback."""
        self.play_loop = checked
        if checked:
            self.loop_btn.setText("🔁 Looping")
        else:
            self.loop_btn.setText("🔁 Loop")

    def start_playback(self):
        """Start executing the queued actions."""
        actions: List[Dict[str, Any]] = self.table.get_all_actions()
        if not actions:
            self.status_label.setText("⚠️ No actions to play")
            self.play_btn.setChecked(False)
            return

        self.is_playing = True
        self.play_btn.setText("⏹ STOP")
        self.set_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.live_record_btn.setEnabled(False)

        self.playback_actions = actions
        self.playback_index = 0
        self._playback_controller_cache: Dict[int, MotorController] = {}

        self.status_label.setText("▶ Playing actions...")
        self.playback_status.emit("playing")

        print("[PLAYBACK] Executing first action...")
        QTimer.singleShot(100, self.playback_step)

    def _resolve_action_arm_index(self, action: Dict[str, Any]) -> int:
        metadata = action.get("metadata") or {}
        arm_index = metadata.get("arm_index")
        if arm_index is not None:
            try:
                return int(arm_index)
            except (TypeError, ValueError):
                pass

        selection = metadata.get("arm_selection") or action.get("arm_selection") or getattr(self, "teleop_target", "both")
        indices = []
        target_fn = getattr(self, "_target_arm_indices", None)
        if callable(target_fn):
            indices = target_fn()
        if not indices:
            indices = [getattr(self, "active_arm_index", 0)]

        if selection == "left":
            return indices[0]
        if selection == "right" and len(indices) > 1:
            return indices[1]
        if selection == "both" and len(indices) > 1:
            return indices[0]
        return indices[0]

    def _get_playback_controller(self, action: Dict[str, Any]) -> MotorController | None:
        arm_index = self._resolve_action_arm_index(action)
        metadata = action.setdefault("metadata", {})
        metadata["arm_index"] = arm_index
        active_index = getattr(self, "active_arm_index", 0)
        base_controller = getattr(self, "motor_controller", None)

        if arm_index == active_index and base_controller is not None:
            controller = base_controller
        else:
            cache = getattr(self, "_playback_controller_cache", {})
            controller = cache.get(arm_index)
            if controller is None:
                try:
                    controller = get_motor_handle(arm_index, self.config)
                except Exception as exc:
                    log_exception(f"RecordTab: playback controller init failed (arm {arm_index})", exc)
                    return None
                cache[arm_index] = controller
                self._playback_controller_cache = cache

        try:
            if not controller.bus:
                controller.connect()
            return controller
        except Exception as exc:
            log_exception(f"RecordTab: controller connect failed (arm {arm_index})", exc)
            return None

    def playback_step(self):
        """Execute the next action in the playback queue."""
        if not self.is_playing:
            print("[PLAYBACK] Stopped")
            return

        if self.playback_index >= len(self.playback_actions):
            print("[PLAYBACK] ✅ COMPLETE")

            if self.play_loop:
                print("[PLAYBACK] 🔁 LOOPING - keeping torque ON")
                self.playback_index = 0
                if not self.play_btn.isChecked():
                    self.play_btn.blockSignals(True)
                    self.play_btn.setChecked(True)
                    self.play_btn.blockSignals(False)
                if not self.is_playing:
                    self.is_playing = True
                    self.playback_status.emit("playing")
                self.status_label.setText("🔁 Looping...")
                QTimer.singleShot(500, self.playback_step)
            else:
                print("[PLAYBACK] Disconnecting...")
                self._disconnect_playback_controllers()
                self.stop_playback()
            return

        action = self.playback_actions[self.playback_index]
        is_last = self.playback_index == len(self.playback_actions) - 1

        self.table.selectRow(self.playback_index)

        print(
            f"[PLAYBACK] Action {self.playback_index + 1}/{len(self.playback_actions)}: "
            f"{action['name']} ({action['type']})"
        )

        try:
            controller = self._get_playback_controller(action)
            if controller is None:
                raise RuntimeError("No available controller for playback")
            if action['type'] == 'position':
                self._execute_single_position(action, controller, is_last)
            elif action['type'] == 'live_recording':
                self._execute_live_recording(action, controller, is_last)
        except Exception as exc:
            log_exception("RecordTab: playback step failed", exc, stack=True)
            print(f"[PLAYBACK] ❌ ERROR: {exc}")
            self.status_label.setText(f"❌ Playback error: {exc}")
            self._disconnect_playback_controllers()
            self.stop_playback()

    def _execute_single_position(self, action: Dict[str, Any], controller: MotorController, is_last: bool):
        """Execute a single position action with precision."""
        positions = action['positions']

        if 'velocity' in action:
            velocity = action['velocity']
            speed = int((velocity / 600.0) * 100)
        elif 'speed' in action:
            speed = action['speed']
            velocity = int(600 * (speed / 100.0))
        else:
            velocity = 600
            speed = 100

        print(f"[PLAYBACK]   Single position, speed={speed}%, velocity={velocity}")

        keep_alive = (not is_last) or self.play_loop

        arm_tag = (action.get("metadata") or {}).get("arm_tag")
        self.status_label.setText(f"▶ {action['name']} [{arm_tag or 'Arm'}] @ {speed}%")
        controller.set_positions(
            positions,
            velocity,
            wait=True,
            keep_connection=keep_alive,
        )

        print("[PLAYBACK]   ✓ Position reached")
        if not keep_alive and controller is not self.motor_controller:
            with contextlib.suppress(Exception):
                controller.disconnect()
        QTimer.singleShot(100, self.continue_playback)

    def _execute_live_recording(self, action: Dict[str, Any], controller: MotorController, is_last: bool):
        """Execute a recorded trajectory with time-based interpolation."""
        recorded_data = action['recorded_data']
        speed = action['speed']
        point_count = action['point_count']

        print(f"[PLAYBACK]   Live recording: {point_count} points, speed={speed}%")

        keep_alive = (not is_last) or self.play_loop
        if not controller.bus:
            controller.connect()

        for name in controller.motor_names:
            controller.bus.write("Torque_Enable", name, 1, normalize=False)

        import time

        start_time = time.time()
        last_point_index = 0

        for i, point in enumerate(recorded_data):
            if not self.is_playing:
                return

            target_time = point['timestamp'] * (100.0 / speed)

            while (time.time() - start_time) < target_time:
                if not self.is_playing:
                    return
                time.sleep(0.001)

            velocity = int(point['velocity'] * (speed / 100.0))

            for idx, name in enumerate(controller.motor_names):
                controller.bus.write("Goal_Velocity", name, velocity, normalize=False)
                controller.bus.write("Goal_Position", name, point['positions'][idx], normalize=False)

            last_point_index = i

            if i % 10 == 0:
                progress = int((i / point_count) * 100)
                self.status_label.setText(f"▶ {action['name']} {progress}% @ {speed}%")

        if is_last and not self.play_loop:
            time.sleep(0.5)

        print("[PLAYBACK]   ✓ Recording playback complete")

        if not keep_alive and controller is not self.motor_controller:
            controller.disconnect()

        QTimer.singleShot(100, self.continue_playback)

    def continue_playback(self):
        """Advance to the next action, if any."""
        self.playback_index += 1
        QTimer.singleShot(100, self.playback_step)

    def stop_playback(self):
        """Stop playback and reset UI state."""
        print("[PLAYBACK] Stopping playback")
        self.is_playing = False
        self.play_btn.setChecked(False)
        self.play_btn.setText("▶ PLAY")
        self.set_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.live_record_btn.setEnabled(True)

        self.table.clearSelection()

        if not self.play_loop:
            print("[PLAYBACK] Disconnecting motors")
            self._disconnect_playback_controllers()

        # Emergency stop for safety
        try:
            MotorManager.instance().emergency_stop_all()
        except Exception:
            pass

        self.status_label.setText("⏹ Playback stopped")
        self.playback_status.emit("stopped")

    def _disconnect_playback_controllers(self) -> None:
        cache = getattr(self, "_playback_controller_cache", {})
        for controller in list(cache.values()):
            if controller is self.motor_controller:
                continue
            with contextlib.suppress(Exception):
                if controller.bus:
                    controller.disconnect()
        cache.clear()
        self._playback_controller_cache = cache
        if self.motor_controller and self.motor_controller.bus:
            with contextlib.suppress(Exception):
                self.motor_controller.disconnect()
