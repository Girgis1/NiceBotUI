"""Action table management mixin for the Record tab."""

from __future__ import annotations

from typing import Any, Dict, List

from PySide6.QtWidgets import QMessageBox, QInputDialog


class RecordStoreMixin:
    """Encapsulates loading, editing, and saving of action data."""

    def refresh_action_list(self):
        """Refresh the action dropdown list with mode icons."""
        from utils.mode_utils import get_mode_icon

        self.action_combo.blockSignals(True)
        current = self.action_combo.currentText()

        self.action_combo.clear()
        self.action_combo.addItem("NewAction01")

        actions = self.actions_manager.list_actions()
        for action in actions:
            action_data = self.actions_manager.load_action(action)
            mode = action_data.get("mode", "solo") if action_data else "solo"
            icon = get_mode_icon(mode)
            self.action_combo.addItem(f"{icon} {action}")

        index = self.action_combo.findText(current)
        if index >= 0:
            self.action_combo.setCurrentIndex(index)

        self.action_combo.blockSignals(False)

    def on_action_changed(self, name: str):
        """Handle action selection change."""
        if not name or name == "NewAction01":
            self.current_action_name = "NewAction01"
            self.table.setRowCount(0)
            self.position_counter = 1
            return

        action_data = self.actions_manager.load_action(name)
        if action_data:
            self.current_action_name = name
            self.load_action_to_table(action_data)
            self.status_label.setText(f"Loaded action: {name}")

    def load_action_to_table(self, action_data: Dict[str, Any]):
        """Load action data into table - handles composite recordings."""
        self.table.setRowCount(0)
        self.position_counter = 1

        action_type = action_data.get("type", "position")
        print(f"[LOAD] Loading {action_type} from file")

        if action_type == "composite_recording":
            steps = action_data.get("steps", [])
            print(f"[LOAD] Composite recording has {len(steps)} steps")

            for step in steps:
                step_type = step.get("type")
                step_name = step.get("name", f"Step {self.position_counter}")
                step_speed = step.get("speed", 100)
                component_data = step.get("component_data", {})

                if step_type == "live_recording":
                    recorded_data = component_data.get("recorded_data", [])
                    if recorded_data:
                        self.table.add_live_recording(step_name, recorded_data, step_speed)
                        print(f"[LOAD] ✓ Added live recording: {step_name} ({len(recorded_data)} points)")
                        self.position_counter += 1

                elif step_type == "position_set":
                    positions = component_data.get("positions", [])
                    for pos_data in positions:
                        pos_name = pos_data.get("name", step_name)
                        motor_positions = pos_data.get("motor_positions", [])
                        velocity = pos_data.get("velocity", 600)
                        self.table.add_single_position(pos_name, motor_positions, velocity)
                        self.position_counter += 1
                    print(f"[LOAD] ✓ Added position set: {step_name} ({len(positions)} positions)")

        elif action_type == "live_recording":
            recorded_data = action_data.get("recorded_data", [])
            speed = action_data.get("speed", 100)
            print(f"[LOAD] Live recording has {len(recorded_data)} points in file")
            if recorded_data:
                name = action_data.get("name", f"Recording {self.position_counter}")
                self.table.add_live_recording(name, recorded_data, speed)
                print(f"[LOAD] ✓ Added live recording to table: {name}")
                self.position_counter += 1

        else:
            positions = action_data.get("positions", [])
            print(f"[LOAD] Position set has {len(positions)} positions in file")
            for pos_data in positions:
                pos_name = pos_data.get("name", f"Position {self.position_counter}")
                motor_positions = pos_data.get("motor_positions", [])
                velocity = pos_data.get("velocity", 600)
                self.table.add_single_position(pos_name, motor_positions, velocity)
                self.position_counter += 1

        print(f"[LOAD] ✓ Loaded recording with {self.position_counter - 1} item(s) in table")

    def record_position(self):
        """Record one single position action."""
        try:
            print("[RECORD] Reading motor positions...")
            self.status_label.setText("Reading motor positions...")
            positions = self.motor_controller.read_positions()

            if not positions or len(positions) != 6:
                print(f"[RECORD] ❌ Failed to read positions: {positions}")
                self.status_label.setText("❌ Failed to read motor positions")
                return

            print(f"[RECORD] ✓ Read positions: {positions}")
            name = f"Position {self.position_counter}"
            velocity = self.default_velocity

            self.table.add_single_position(name, positions, velocity)
            self.position_counter += 1

            try:
                if self.motor_controller.bus:
                    for motor_name in self.motor_controller.motor_names:
                        self.motor_controller.bus.write("Torque_Enable", motor_name, 1, normalize=False)
                    print("[RECORD] ✓ Torque kept enabled")
            except Exception as exc:  # pragma: no cover - hardware specific
                print(f"[RECORD] ⚠️ Could not ensure torque: {exc}")

            self.status_label.setText(f"✓ Recorded {name} @ vel {velocity}")
            print(f"[RECORD] Added single position action: {name} with velocity {velocity}")

        except Exception as exc:  # pragma: no cover - hardware specific
            self.status_label.setText(f"❌ Error: {exc}")
            print(f"Error recording position: {exc}")

    def on_table_item_changed(self, item):
        """Handle table item changes - ensure delete buttons persist."""
        self.table.ensure_delete_buttons()

    def create_new_action(self):
        """Prompt for a new action and clear the table."""
        name, ok = QInputDialog.getText(
            self, "New Action", "Enter action name:"
        )

        if ok and name:
            name = name.strip()
            if name:
                self.action_combo.addItem(name)
                self.action_combo.setCurrentText(name)
                self.table.setRowCount(0)
                self.position_counter = 1
                self.status_label.setText(f"✓ Created new action: {name}")

    def delete_position(self, row: int):
        """Delete a position."""
        print(f"[RECORD] delete_position called with row: {row}")

        reply = QMessageBox.question(
            self,
            "Delete Position",
            "Are you sure you want to delete this position?",
            QMessageBox.Yes | QMessageBox.No,
        )

        print(f"[RECORD] User replied: {reply == QMessageBox.Yes}")

        if reply == QMessageBox.Yes:
            self.table.removeRow(row)
            if self.table.rowCount() == 0:
                self.position_counter = 1
            self.status_label.setText("Position deleted")

    def save_action(self):
        """Save current action to file with mode metadata."""
        from utils.mode_utils import get_current_robot_mode

        name = self.action_combo.currentText().strip()

        if not name or name == "NewAction01":
            name, ok = QInputDialog.getText(
                self, "Save Action", "Action name:"
            )
            if not ok or not name:
                return

        current_mode = get_current_robot_mode(self.config)
        actions = self.table.get_all_actions()

        if not actions:
            self.status_label.setText("❌ No positions to save")
            return

        print(f"[SAVE] Got {len(actions)} action(s) from table:")
        for i, action in enumerate(actions):
            print(f"  [{i}] type={action['type']}, name={action['name']}")
            if action['type'] == 'live_recording':
                point_count = len(action.get('recorded_data', []))
                print(f"      recorded_data has {point_count} points")

        if len(actions) == 1:
            action = actions[0]

            if action['type'] == 'live_recording':
                recorded_data = action.get("recorded_data", [])
                action_data = {
                    "type": "live_recording",
                    "speed": action.get("speed", 100),
                    "recorded_data": recorded_data,
                    "mode": current_mode,
                }
                print(f"[SAVE] Saving single live_recording with {len(recorded_data)} points (mode: {current_mode})")

            elif action['type'] == 'position':
                action_data = {
                    "type": "position",
                    "speed": action.get("speed", 100),
                    "positions": [
                        {
                            "name": action['name'],
                            "motor_positions": action['positions'],
                            "velocity": 600,
                            "wait_for_completion": True,
                        }
                    ],
                    "mode": current_mode,
                }
                print(f"[SAVE] Saving single position (mode: {current_mode})")

        else:
            steps: List[Dict[str, Any]] = []
            for action in actions:
                if action['type'] == 'live_recording':
                    step = {
                        "type": "live_recording",
                        "name": action['name'],
                        "speed": action.get("speed", 100),
                        "enabled": True,
                        "delay_after": 0.0,
                        "component_data": {
                            "recorded_data": action.get("recorded_data", [])
                        },
                    }
                    steps.append(step)
                    print(f"[SAVE] Adding live recording step: {action['name']}")

                elif action['type'] == 'position':
                    step = {
                        "type": "position_set",
                        "name": action['name'],
                        "speed": action.get("speed", 100),
                        "enabled": True,
                        "delay_after": 0.0,
                        "component_data": {
                            "positions": [
                                {
                                    "name": action['name'],
                                    "motor_positions": action['positions'],
                                    "velocity": 600,
                                    "wait_for_completion": True,
                                }
                            ]
                        },
                    }
                    steps.append(step)
                    print(f"[SAVE] Adding position step: {action['name']}")

            action_data = {
                "type": "composite_recording",
                "steps": steps,
                "mode": current_mode,
            }
            print(f"[SAVE] Saving composite recording with {len(steps)} steps (mode: {current_mode})")

        try:
            if action_data['type'] == 'live_recording':
                print(f"[SAVE] About to save live_recording with {len(action_data['recorded_data'])} points")

            success = self.actions_manager.save_action(name, action_data)

            if success:
                self.current_action_name = name
                self.status_label.setText(f"✓ Saved: {name}")

                verify_data = self.actions_manager.load_action(name)
                if verify_data:
                    if verify_data['type'] == 'composite_recording':
                        step_count = len(verify_data.get('steps', []))
                        print(f"[SAVE] ✓ Saved composite recording: {name} - {step_count} steps")
                    else:
                        print(f"[SAVE] ✓ Saved recording: {name}")

                self.refresh_action_list()
                self._notify_parent_refresh()

                index = self.action_combo.findText(name)
                if index >= 0:
                    self.action_combo.setCurrentIndex(index)
            else:
                self.status_label.setText("❌ Failed to save")

        except Exception as exc:  # pragma: no cover - disk IO
            import traceback
            traceback.print_exc()
            self.status_label.setText(f"❌ Save error: {exc}")
