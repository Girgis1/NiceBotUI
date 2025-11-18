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
            # Store the raw recording name as user data so we can
            # load/save correctly even though the label includes an icon.
            self.action_combo.addItem(f"{icon} {action}", action)

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

        # The combo box label may include an icon prefix (e.g. "👤 MyAction").
        # Always prefer the stored userData as the actual recording name.
        raw_name = self.action_combo.currentData()
        load_name = raw_name or name

        action_data = self.actions_manager.load_action(load_name)
        if action_data:
            self.current_action_name = load_name
            self.load_action_to_table(action_data)
            self.status_label.setText(f"Loaded action: {load_name}")

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
                        meta = component_data.get("metadata")
                        self.table.add_live_recording(step_name, recorded_data, step_speed, metadata=meta)
                        print(f"[LOAD] ✓ Added live recording: {step_name} ({len(recorded_data)} points)")
                        self.position_counter += 1

                elif step_type == "position_set":
                    positions = component_data.get("positions", [])
                    for pos_data in positions:
                        pos_name = pos_data.get("name", step_name)
                        motor_positions = pos_data.get("motor_positions", [])
                        velocity = pos_data.get("velocity", 600)
                        self.table.add_single_position(pos_name, motor_positions, velocity, metadata=pos_data.get("metadata"))
                        self.position_counter += 1
                    print(f"[LOAD] ✓ Added position set: {step_name} ({len(positions)} positions)")

        elif action_type == "live_recording":
            recorded_data = action_data.get("recorded_data", [])
            speed = action_data.get("speed", 100)
            print(f"[LOAD] Live recording has {len(recorded_data)} points in file")
            if recorded_data:
                name = action_data.get("name", f"Recording {self.position_counter}")
                self.table.add_live_recording(name, recorded_data, speed, metadata=action_data.get("metadata"))
                print(f"[LOAD] ✓ Added live recording to table: {name}")
                self.position_counter += 1

        else:
            positions = action_data.get("positions", [])
            print(f"[LOAD] Position set has {len(positions)} positions in file")
            for pos_data in positions:
                pos_name = pos_data.get("name", f"Position {self.position_counter}")
                motor_positions = pos_data.get("motor_positions", [])
                velocity = pos_data.get("velocity", 600)
                self.table.add_single_position(pos_name, motor_positions, velocity, metadata=pos_data.get("metadata"))
                self.position_counter += 1

        print(f"[LOAD] ✓ Loaded recording with {self.position_counter - 1} item(s) in table")

    def record_position(self):
        """Record one single position action."""
        try:
            if getattr(self, "_is_teleop_active", lambda: False)():
                self.status_label.setText("⚠️ Stop teleop before capturing a position.")
                return
            print("[RECORD] Reading motor positions...")
            self.status_label.setText("Reading motor positions...")
            capture_fn = getattr(self, "_capture_positions_for_target", None)
            if callable(capture_fn):
                captures = capture_fn()
            else:
                positions = getattr(self, "_read_motor_positions_safe", lambda prefer_bus=False: [])(prefer_bus=False)
                captures = [(getattr(self, "active_arm_index", 0), positions)] if positions else []

            if not captures:
                print("[RECORD] ❌ Failed to read positions for selected arm(s)")
                self.status_label.setText("❌ Failed to read motor positions")
                return

            name = f"Position {self.position_counter}"
            velocity = self.default_velocity
            metadata_builder = getattr(self, "_build_teleop_metadata", None)
            recorded_names = []
            for arm_index, positions in captures:
                print(f"[RECORD] ✓ Read positions for arm {arm_index}: {positions}")
                tag = getattr(self, "_arm_tag_for_index", lambda idx: f"A{idx+1}")(arm_index)
                display_name = f"{name} ({tag})" if tag else name
                metadata = metadata_builder() if callable(metadata_builder) else {}
                if isinstance(metadata, dict):
                    metadata = dict(metadata)
                metadata = metadata or {}
                metadata.update({
                    "arm_selection": getattr(self, "teleop_target", "both"),
                    "arm_index": arm_index,
                    "arm_tag": tag,
                })
                self.table.add_single_position(display_name, positions, velocity, metadata=metadata)
                self.position_counter += 1
                recorded_names.append(display_name)

            try:
                if self.motor_controller.bus:
                    for motor_name in self.motor_controller.motor_names:
                        self.motor_controller.bus.write("Torque_Enable", motor_name, 1, normalize=False)
                    print("[RECORD] ✓ Torque kept enabled")
            except Exception as exc:  # pragma: no cover - hardware specific
                print(f"[RECORD] ⚠️ Could not ensure torque: {exc}")

            if recorded_names:
                summary = ", ".join(recorded_names)
                self.status_label.setText(f"✓ Recorded {summary} @ vel {velocity}")
                print(f"[RECORD] Added position action(s): {summary} with velocity {velocity}")

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
                # Store the bare recording name as user data so later
                # lookups can ignore any icon/text decoration.
                self.action_combo.addItem(name, name)
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
                if action.get("metadata"):
                    action_data["metadata"] = action["metadata"]
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
                if action.get("metadata"):
                    action_data["positions"][0]["metadata"] = action["metadata"]
                print(f"[SAVE] Saving single position (mode: {current_mode})")

        else:
            steps: List[Dict[str, Any]] = []
            for action in actions:
                if action['type'] == 'live_recording':
                    component_data = {
                        "recorded_data": action.get("recorded_data", [])
                    }
                    if action.get("metadata"):
                        component_data["metadata"] = action["metadata"]
                    step = {
                        "type": "live_recording",
                        "name": action['name'],
                        "speed": action.get("speed", 100),
                        "enabled": True,
                        "delay_after": 0.0,
                        "component_data": component_data,
                    }
                    steps.append(step)
                    print(f"[SAVE] Adding live recording step: {action['name']}")

                elif action['type'] == 'position':
                    position_entry = {
                        "name": action['name'],
                        "motor_positions": action['positions'],
                        "velocity": 600,
                        "wait_for_completion": True,
                    }
                    if action.get("metadata"):
                        position_entry["metadata"] = action["metadata"]
                    step = {
                        "type": "position_set",
                        "name": action['name'],
                        "speed": action.get("speed", 100),
                        "enabled": True,
                        "delay_after": 0.0,
                        "component_data": {
                            "positions": [position_entry]
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
