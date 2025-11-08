"""Transport controls (record, playback, velocity) for RecordTab."""

from __future__ import annotations

from typing import Any, Dict, List

from PySide6.QtCore import QTimer


class TransportControlsMixin:
    """Provides live recording and playback helpers for RecordTab."""

    def toggle_live_recording(self):
        """Toggle industrial precision live recording."""
        if not self.is_live_recording:
            self._live_record_connected_locally = False
            try:
                if not self.motor_controller.bus:
                    if not self.motor_controller.connect():
                        self.status_label.setText("❌ Failed to connect for live recording")
                        self.live_record_btn.setChecked(False)
                        return
                    self._live_record_connected_locally = True
            except Exception as exc:
                self.status_label.setText(f"❌ Live record error: {exc}")
                self.live_record_btn.setChecked(False)
                return

            self.is_live_recording = True
            self.last_recorded_position = None
            self.live_recorded_data = []
            self.live_record_start_time = None

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
            except Exception:
                pass
        self._live_record_connected_locally = False

        point_count = len(self.live_recorded_data)
        if point_count > 0:
            name = f"Recording {self.position_counter}"
            speed = 100

            action = {
                "type": "live_recording",
                "name": name,
                "speed": speed,
                "recorded_data": self.live_recorded_data,
                "point_count": point_count,
            }

            self.table.add_live_recording(name, self.live_recorded_data, speed)
            self.position_counter += 1

            self.status_label.setText(f"✓ Live recording saved ({point_count} points)")
            print(f"[LIVE RECORD] ✓ SAVED {point_count} points as '{name}'")
            print(f"[LIVE RECORD] Data sample: {self.live_recorded_data[:3]} ...")
        else:
            self.status_label.setText("⚠️ No positions captured")
            print("[LIVE RECORD] ⚠️ No positions captured")

        self.live_recorded_data = []
        self.live_record_start_time = None
        self.last_recorded_position = None

    def capture_live_position(self):
        """Capture a live position sample at the configured frequency."""
        if not self.is_live_recording:
            return

        try:
            import time

            if self.live_record_start_time is None:
                self.live_record_start_time = time.time()

            positions = self.motor_controller.read_positions_from_bus()
            if not positions:
                positions = self.motor_controller.read_positions()
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
            print(f"[LIVE RECORD] ❌ ERROR: {exc}")
            import traceback

            traceback.print_exc()
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

        try:
            if not self.motor_controller.connect():
                self.status_label.setText("❌ Failed to connect for playback")
                self.play_btn.setChecked(False)
                return
        except Exception as exc:
            self.status_label.setText(f"❌ Playback error: {exc}")
            self.play_btn.setChecked(False)
            return

        self.is_playing = True
        self.play_btn.setText("⏹ STOP")
        self.set_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.live_record_btn.setEnabled(False)

        self.playback_actions = actions
        self.playback_index = 0

        self.status_label.setText("▶ Playing actions...")
        self.playback_status.emit("playing")

        print("[PLAYBACK] Executing first action...")
        QTimer.singleShot(100, self.playback_step)

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
                try:
                    self.motor_controller.disconnect()
                except Exception:
                    pass
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
            if action['type'] == 'position':
                self._execute_single_position(action, is_last)
            elif action['type'] == 'live_recording':
                self._execute_live_recording(action, is_last)
        except Exception as exc:
            print(f"[PLAYBACK] ❌ ERROR: {exc}")
            import traceback

            traceback.print_exc()
            self.status_label.setText(f"❌ Playback error: {exc}")
            try:
                self.motor_controller.disconnect()
            except Exception:
                pass
            self.stop_playback()

    def _execute_single_position(self, action: Dict[str, Any], is_last: bool):
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

        self.status_label.setText(f"▶ {action['name']} @ {speed}%")
        self.motor_controller.set_positions(
            positions,
            velocity,
            wait=True,
            keep_connection=keep_alive,
        )

        print("[PLAYBACK]   ✓ Position reached")
        QTimer.singleShot(100, self.continue_playback)

    def _execute_live_recording(self, action: Dict[str, Any], is_last: bool):
        """Execute a recorded trajectory with time-based interpolation."""
        recorded_data = action['recorded_data']
        speed = action['speed']
        point_count = action['point_count']

        print(f"[PLAYBACK]   Live recording: {point_count} points, speed={speed}%")

        keep_alive = (not is_last) or self.play_loop
        if not self.motor_controller.bus:
            self.motor_controller.connect()

        for name in self.motor_controller.motor_names:
            self.motor_controller.bus.write("Torque_Enable", name, 1, normalize=False)

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

            for idx, name in enumerate(self.motor_controller.motor_names):
                self.motor_controller.bus.write("Goal_Velocity", name, velocity, normalize=False)
                self.motor_controller.bus.write("Goal_Position", name, point['positions'][idx], normalize=False)

            last_point_index = i

            if i % 10 == 0:
                progress = int((i / point_count) * 100)
                self.status_label.setText(f"▶ {action['name']} {progress}% @ {speed}%")

        if is_last and not self.play_loop:
            time.sleep(0.5)

        print("[PLAYBACK]   ✓ Recording playback complete")

        if not keep_alive:
            self.motor_controller.disconnect()

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
            try:
                self.motor_controller.disconnect()
            except Exception:
                pass

        self.status_label.setText("⏹ Playback stopped")
        self.playback_status.emit("stopped")
