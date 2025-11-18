"""
Sequence Tab - Sequence Builder
Combine actions, trained models, and delays into complex sequences
"""

from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QInputDialog, QMessageBox, QListWidget, QListWidgetItem,
    QDialog, QCheckBox, QFrame
)
from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QColor

from utils.sequences_manager import SequencesManager
from utils.actions_manager import ActionsManager
from utils.logging_utils import log_exception
from utils.config_compat import format_arm_label, iter_arm_configs
from utils.model_paths import list_model_task_dirs
from utils.palletize_runtime import (
    compute_pallet_cells,
    create_default_palletize_config,
)

# Vision designer dialog (new modular UI)
try:
    from vision_ui import VisionConfigDialog, create_default_vision_config
except ImportError:
    VisionConfigDialog = None  # Fallback if vision UI not yet available

    def create_default_vision_config():
        return {
            "type": "vision",
            "name": "Setup Vision Trigger",
            "camera": {
                "index": 0,
                "label": "Camera 0",
                "resolution": [640, 480],
                "source_id": "camera:0",
            },
            "trigger": {
                "display_name": "Detection Zone",
                "mode": "presence",
                "settings": {
                    "metric": "intensity",
                    "threshold": 0.55,
                    "invert": False,
                    "hold_time": 0.0,
                    "sensitivity": 0.6,
                },
                "zones": [],
            },
        }


# Palletize designer dialog (optional)
try:
    from palletize_ui import PalletizeConfigDialog
except ImportError:
    PalletizeConfigDialog = None


class HomeStepWidget(QFrame):
    """Custom widget for home steps with arm selection checkboxes"""
    
    def __init__(self, step_number: int, step_data: dict, parent=None):
        super().__init__(parent)
        self.step_data = step_data
        self.step_number = step_number
        
        # Style tweaks so the entry renders consistently across platforms
        self.setObjectName("homeStepWidget")
        self.setStyleSheet("""
            #homeStepWidget {
                background-color: #1b5e20;
                border-radius: 4px;
                padding: 6px;
            }
            #homeStepWidget QLabel {
                color: #e8f5e9;
                font-weight: bold;
            }
            #homeStepWidget QCheckBox {
                color: #e8f5e9;
            }
        """)
        self.setMinimumHeight(42)
        self.setFrameShape(QFrame.StyledPanel)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)
        
        # Step label
        label = QLabel(f"{step_number}. 🏠 Home:")
        layout.addWidget(label)
        
        # Arm 1 checkbox
        self.arm1_check = QCheckBox("Arm 1")
        self.arm1_check.setChecked(step_data.get("home_arm_1", True))
        self.arm1_check.stateChanged.connect(self._on_arm_changed)
        layout.addWidget(self.arm1_check)
        
        # Arm 2 checkbox
        self.arm2_check = QCheckBox("Arm 2")
        self.arm2_check.setChecked(step_data.get("home_arm_2", True))
        self.arm2_check.stateChanged.connect(self._on_arm_changed)
        layout.addWidget(self.arm2_check)

        layout.addStretch()

    def sizeHint(self) -> QSize:  # pragma: no cover - Qt layout helper
        return QSize(260, 44)
    
    def _on_arm_changed(self):
        """Update step data when checkboxes change"""
        self.step_data["home_arm_1"] = self.arm1_check.isChecked()
        self.step_data["home_arm_2"] = self.arm2_check.isChecked()
    
    def get_step_data(self) -> dict:
        """Return updated step data"""
        return self.step_data


class SequenceTab(QWidget):
    """Sequence builder tab - combine actions, models, and delays"""
    
    # Signal to request sequence execution from Dashboard
    execute_sequence_signal = Signal(str, bool)  # (sequence_name, loop)
    
    # Signal to request model execution from main app (legacy)
    execute_model = Signal(str, str, float)  # task, checkpoint, duration
    
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.sequences_manager = SequencesManager()
        self.actions_manager = ActionsManager()
        
        self.current_sequence_name = "NewSequence01"
        self.is_running = False
        self.run_loop = False
        
        self.init_ui()
        self.refresh_sequence_list()
        self._highlighted_step_row = None
    
    def init_ui(self):
        """Initialize UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Top bar: Sequence selector
        top_bar = QHBoxLayout()
        
        seq_label = QLabel("SEQUENCE:")
        seq_label.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        top_bar.addWidget(seq_label)
        
        self.sequence_combo = QComboBox()
        self.sequence_combo.setEditable(True)
        self.sequence_combo.setMinimumHeight(60)
        self.sequence_combo.setStyleSheet("""
            QComboBox {
                background-color: #404040;
                color: #ffffff;
                border: 2px solid #505050;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 16px;
                font-weight: bold;
            }
            QComboBox:hover {
                border-color: #2196F3;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 30px;
                border: none;
            }
            QComboBox::down-arrow {
                width: 0;
                height: 0;
                border-style: solid;
                border-width: 6px 4px 0 4px;
                border-color: #ffffff transparent transparent transparent;
            }
            QComboBox QAbstractItemView {
                background-color: #404040;
                color: #ffffff;
                selection-background-color: #2196F3;
                font-size: 15px;
            }
        """)
        self.sequence_combo.currentTextChanged.connect(self.on_sequence_changed)
        top_bar.addWidget(self.sequence_combo, stretch=2)
        
        self.save_btn = QPushButton("💾 SAVE")
        self.save_btn.setMinimumHeight(45)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
        """)
        self.save_btn.clicked.connect(self.save_sequence)
        top_bar.addWidget(self.save_btn)
        
        # Vision button
        self.new_btn = QPushButton("✨ NEW")
        self.new_btn.setMinimumHeight(45)
        self.new_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        self.new_btn.clicked.connect(self.new_sequence)
        top_bar.addWidget(self.new_btn)
        
        layout.addLayout(top_bar)
        
        # Add item buttons
        add_bar = QHBoxLayout()
        add_bar.setSpacing(10)
        
        self.add_action_btn = QPushButton("+ Action")
        self.add_action_btn.setMinimumHeight(45)
        self.add_action_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        self.add_action_btn.clicked.connect(self.add_action_step)
        add_bar.addWidget(self.add_action_btn)
        
        self.add_model_btn = QPushButton("+ Model")
        self.add_model_btn.setMinimumHeight(45)
        self.add_model_btn.setStyleSheet("""
            QPushButton {
                background-color: #9C27B0;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7B1FA2;
            }
        """)
        self.add_model_btn.clicked.connect(self.add_model_step)
        add_bar.addWidget(self.add_model_btn)
        
        self.add_vision_btn = QPushButton("+ Vision")
        self.add_vision_btn.setMinimumHeight(45)
        self.add_vision_btn.setStyleSheet("""
            QPushButton {
                background-color: #AA00FF;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #8E24AA;
            }
        """)
        self.add_vision_btn.clicked.connect(self.add_vision_step)
        add_bar.addWidget(self.add_vision_btn)

        self.add_palletize_btn = QPushButton("+ Palletize")
        self.add_palletize_btn.setMinimumHeight(45)
        self.add_palletize_btn.setStyleSheet("""
            QPushButton {
                background-color: #00bfa5;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #008e76;
            }
        """)
        self.add_palletize_btn.clicked.connect(self.add_palletize_step)
        add_bar.addWidget(self.add_palletize_btn)

        self.add_delay_btn = QPushButton("⏱ Delay")
        self.add_delay_btn.setMinimumHeight(45)
        self.add_delay_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
        """)
        self.add_delay_btn.clicked.connect(self.add_delay_step)
        add_bar.addWidget(self.add_delay_btn)
        
        self.add_home_btn = QPushButton("🏠 Home")
        self.add_home_btn.setMinimumHeight(45)
        self.add_home_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
        """)
        self.add_home_btn.clicked.connect(self.add_home_step)
        add_bar.addWidget(self.add_home_btn)
        
        add_bar.addStretch()
        
        layout.addLayout(add_bar)
        
        # Sequence steps list (drag-drop enabled)
        self.steps_list = QListWidget()
        self.steps_list.setDragDropMode(QListWidget.InternalMove)
        self.steps_list.setMinimumHeight(250)
        self.steps_list.setStyleSheet("""
            QListWidget {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #404040;
                border-radius: 4px;
                font-size: 13px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 12px;
                border-bottom: 1px solid #404040;
                border-radius: 4px;
                margin: 2px;
            }
            QListWidget::item:selected {
                background-color: #2196F3;
            }
            QListWidget::item:hover {
                background-color: #404040;
            }
        """)
        self.steps_list.itemDoubleClicked.connect(self.edit_step)
        layout.addWidget(self.steps_list, stretch=1)
        
        # Run controls
        run_bar = QHBoxLayout()
        run_bar.setSpacing(10)
        
        self.run_btn = QPushButton("▶️ RUN SEQUENCE")
        self.run_btn.setMinimumHeight(55)
        self.run_btn.setCheckable(True)
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
            QPushButton:checked {
                background-color: #f44336;
            }
            QPushButton:checked:hover {
                background-color: #c62828;
            }
        """)
        self.run_btn.clicked.connect(self.toggle_run)
        run_bar.addWidget(self.run_btn, stretch=3)
        
        self.loop_btn = QPushButton("🔁 Loop")
        self.loop_btn.setMinimumHeight(55)
        self.loop_btn.setCheckable(True)
        self.loop_btn.setStyleSheet("""
            QPushButton {
                background-color: #909090;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #616161;
            }
            QPushButton:checked {
                background-color: #FF9800;
            }
        """)
        self.loop_btn.clicked.connect(self.toggle_loop)
        run_bar.addWidget(self.loop_btn)
        
        self.delete_step_btn = QPushButton("🗑️ Delete")
        self.delete_step_btn.setMinimumHeight(55)
        self.delete_step_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c62828;
            }
        """)
        self.delete_step_btn.clicked.connect(self.delete_selected_step)
        run_bar.addWidget(self.delete_step_btn)
        
        layout.addLayout(run_bar)
        
        # Status label
        self.status_label = QLabel("Build a sequence by adding actions, models, and delays.")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                background-color: #2d2d2d;
                border: 1px solid #404040;
                border-radius: 4px;
                padding: 10px;
                font-size: 13px;
            }
        """)
        self.status_label.setAlignment(Qt.AlignCenter)
        self._default_status_message = "Build a sequence by adding actions, models, and delays."
        layout.addWidget(self.status_label)
    
    def refresh_sequence_list(self):
        """Refresh sequence dropdown"""
        self.sequence_combo.blockSignals(True)
        current = self.sequence_combo.currentText()
        
        self.sequence_combo.clear()
        self.sequence_combo.addItem("NewSequence01")
        
        sequences = self.sequences_manager.list_sequences()
        for seq in sequences:
            self.sequence_combo.addItem(seq)
        
        index = self.sequence_combo.findText(current)
        if index >= 0:
            self.sequence_combo.setCurrentIndex(index)
        
        self.sequence_combo.blockSignals(False)
    
    def _notify_parent_refresh(self):
        """Notify parent window to refresh dropdowns"""
        try:
            # Walk up to find main window and refresh dashboard
            parent = self.parent()
            while parent:
                if hasattr(parent, 'dashboard_tab'):
                    parent.dashboard_tab.refresh_run_selector()
                    print("[SEQUENCE] ✓ Refreshed dashboard dropdown")
                    break
                parent = parent.parent()
        except Exception as exc:
            log_exception("SequenceTab: failed to notify parent", exc, level="warning")
    
    def on_sequence_changed(self, name: str):
        """Handle sequence selection change"""
        if not name or name == "NewSequence01":
            self.current_sequence_name = "NewSequence01"
            self.steps_list.clear()
            return
        
        # Load sequence
        seq_data = self.sequences_manager.load_sequence(name)
        if seq_data:
            self.current_sequence_name = name
            self.load_sequence_to_list(seq_data)
            self.status_label.setText(f"Loaded sequence: {name}")
    
    def load_sequence_to_list(self, seq_data: dict):
        """Load sequence steps into list"""
        self.steps_list.clear()
        
        steps = seq_data.get("steps", [])
        for idx, step in enumerate(steps, 1):
            self.add_step_to_list(step, idx)
    
    def add_step_to_list(self, step: dict, number: int = None):
        """Add a step to the list widget"""
        if number is None:
            number = self.steps_list.count() + 1
        
        step_type = step.get("type", "")
        
        if step_type == "action":
            from utils.mode_utils import get_mode_icon
            mode = step.get("mode", "solo")
            mode_icon = get_mode_icon(mode)
            text = f"{number}. {mode_icon} 🎬 Action: {step.get('name', 'Unknown')}"
            color = QColor("#2196F3")
        elif step_type == "model":
            task = step.get("task", "Unknown")
            checkpoint = step.get("checkpoint", "last")
            duration = step.get("duration", 25.0)
            text = f"{number}. 🤖 Model: {task} ({checkpoint}) - {duration:.0f}s"
            color = QColor("#9C27B0")
        elif step_type == "delay":
            duration = step.get("duration", 1.0)
            text = f"{number}. ⏱️ Delay: {duration:.1f}s"
            color = QColor("#FF9800")
        elif step_type == "home":
            # Use custom widget for home steps with arm checkboxes and text fallback
            arm1 = "✓" if step.get("home_arm_1", True) else "✗"
            arm2 = "✓" if step.get("home_arm_2", True) else "✗"
            item = QListWidgetItem(f"{number}. 🏠 Home (Arm 1 {arm1} / Arm 2 {arm2})")
            item.setData(Qt.UserRole, step)
            item.setForeground(QColor("#e8f5e9"))
            item.setBackground(QColor("#1b5e20"))
            self.steps_list.addItem(item)
            
            # Create and set custom widget
            widget = HomeStepWidget(number, step, self)
            self.steps_list.setItemWidget(item, widget)
            
            # Set size hint to fit widget content
            item.setSizeHint(widget.sizeHint())
            return  # Early return since we handled this differently
            
        elif step_type == "vision":
            text = self._format_vision_step_text(step, number)
            color = QColor("#AA00FF")
        elif step_type == "palletize":
            text = self._format_palletize_step_text(step, number)
            color = QColor("#00BFA5")
        else:
            text = f"{number}. ❓ Unknown step"
            color = QColor("#909090")
        
        item = QListWidgetItem(text)
        item.setData(Qt.UserRole, step)  # Store step data
        base_bg = color.darker(200)
        item.setData(Qt.UserRole + 1, base_bg.name())
        item.setBackground(base_bg)
        item.setForeground(QColor("#ffffff"))
        
        self.steps_list.addItem(item)
    
    def add_action_step(self):
        """Add an action step"""
        actions = self.actions_manager.list_actions()
        
        if not actions:
            self.status_label.setText(
                "❌ No saved actions. Record one first or run utils/migrate_data.py to import legacy actions.json."
            )
            return
        
        action, ok = QInputDialog.getItem(
            self, "Add Action", "Select action:",
            actions, 0, False
        )
        
        if ok and action:
            step = {"type": "action", "name": action}
            self.add_step_to_list(step)
            self.status_label.setText(f"✓ Added action: {action}")
    
    def add_model_step(self):
        """Add a model execution step"""
        task_dirs = list_model_task_dirs(self.config)
        tasks = [path.name for path in task_dirs]

        if not tasks:
            policy_cfg = self.config.get("policy", {}) if isinstance(self.config, dict) else {}
            base_path = policy_cfg.get("base_path") or "outputs/train"
            self.status_label.setText(
                f"❌ No trained models found. Ensure the base path exists ({base_path}) "
                "and contains task/checkpoints folders."
            )
            return

        task, ok = QInputDialog.getItem(
            self, "Add Model", "Select task:",
            tasks, 0, False
        )
        
        if ok and task:
            # Ask for duration
            duration, ok2 = QInputDialog.getDouble(
                self, "Model Duration", "Execution time (seconds):",
                25.0, 1.0, 300.0, 1
            )
            
            if ok2:
                step = {
                    "type": "model",
                    "task": task,
                    "checkpoint": "last",
                    "duration": duration
                }
                self.add_step_to_list(step)
            self.status_label.setText(f"✓ Added model: {task}")
    
    def add_vision_step(self):
        """Add a vision configuration step"""
        step = create_default_vision_config()

        self.add_step_to_list(step)
        self.status_label.setText("✓ Added vision trigger")
        self._report_vision_status("watching", "Vision step added — configure zones to enable triggers.")

        # Automatically prompt for configuration
        last_item = self.steps_list.item(self.steps_list.count() - 1)
        if last_item:
            self.configure_vision_step(last_item)

    def add_palletize_step(self):
        """Add a palletization step"""
        if PalletizeConfigDialog is None:
            QMessageBox.warning(
                self,
                "Palletize Designer Missing",
                "Palletize UI module is not available. Please ensure palletize_ui/designer.py exists.",
            )
            return

        step = create_default_palletize_config(self.config)
        dialog = PalletizeConfigDialog(self, step, self.config)
        if dialog.exec() == QDialog.Accepted:
            result = dialog.get_step_data()
            if result:
                result["type"] = "palletize"
                self.add_step_to_list(result)
                self.status_label.setText("✓ Added palletize step")
    
    def add_delay_step(self):
        """Add a delay step"""
        delay, ok = QInputDialog.getDouble(
            self, "Add Delay", "Delay duration (seconds):",
            1.0, 0.1, 60.0, 1
        )
        
        if ok:
            step = {"type": "delay", "duration": delay}
            self.add_step_to_list(step)
            self.status_label.setText(f"✓ Added {delay:.1f}s delay")
    
    def add_home_step(self):
        """Add a home position step"""
        step = {"type": "home"}
        self.add_step_to_list(step)
        self.status_label.setText("✓ Added home step")
    
    def delete_selected_step(self):
        """Delete selected step"""
        current_row = self.steps_list.currentRow()
        if current_row >= 0:
            self.steps_list.takeItem(current_row)
            self.renumber_steps()
            self.status_label.setText("✓ Step deleted")
    
    def renumber_steps(self):
        """Renumber all steps after reordering or deletion"""
        for idx in range(self.steps_list.count()):
            item = self.steps_list.item(idx)
            
            # Check if this is a custom widget (like HomeStepWidget)
            widget = self.steps_list.itemWidget(item)
            if widget and isinstance(widget, HomeStepWidget):
                # Recreate widget with new number
                step_data = widget.get_step_data()
                new_widget = HomeStepWidget(idx + 1, step_data, self)
                self.steps_list.setItemWidget(item, new_widget)
            else:
                # Regular text item
                text = item.text()
                # Replace number at start
                parts = text.split(". ", 1)
                if len(parts) == 2:
                    item.setText(f"{idx + 1}. {parts[1]}")
    
    def get_all_steps(self) -> list:
        """Get all steps as list of dicts"""
        steps = []
        for idx in range(self.steps_list.count()):
            item = self.steps_list.item(idx)
            step_data = item.data(Qt.UserRole)
            
            # For home steps with custom widgets, get updated data from widget
            widget = self.steps_list.itemWidget(item)
            if widget and isinstance(widget, HomeStepWidget):
                step_data = widget.get_step_data()
            
            if step_data:
                steps.append(step_data)
        return steps
    
    def save_sequence(self):
        """Save current sequence"""
        name = self.sequence_combo.currentText().strip()
        
        if not name or name == "NewSequence01":
            name, ok = QInputDialog.getText(
                self, "Save Sequence", "Sequence name:"
            )
            if not ok or not name:
                return
        
        steps = self.get_all_steps()
        
        if not steps:
            self.status_label.setText("❌ No steps to save")
            return
        
        loop = self.loop_btn.isChecked() if hasattr(self, 'loop_btn') else False
        success = self.sequences_manager.save_sequence(name, steps, loop)
        
        if success:
            self.current_sequence_name = name
            self.status_label.setText(f"✓ Saved: {name}")
            print(f"[SEQUENCE] ✓ Saved sequence: {name}")
            
            # Refresh dropdown AND signal parent to refresh dashboard
            self.refresh_sequence_list()
            self._notify_parent_refresh()
            
            index = self.sequence_combo.findText(name)
            if index >= 0:
                self.sequence_combo.setCurrentIndex(index)
        else:
            self.status_label.setText("❌ Failed to save")
    
    def new_sequence(self):
        """Create a new sequence"""
        self.sequence_combo.setCurrentText("NewSequence01")
        self.steps_list.clear()
        self.clear_running_highlight()
        self.status_label.setText("New sequence created")
    
    def toggle_loop(self):
        """Toggle loop mode"""
        self.run_loop = self.loop_btn.isChecked()
        if self.run_loop:
            self.status_label.setText("🔁 Loop enabled")
        else:
            self.status_label.setText("Loop disabled")
    
    def toggle_run(self):
        """Toggle sequence execution"""
        if self.run_btn.isChecked():
            self.start_sequence()
        else:
            self.stop_sequence()
    
    def start_sequence(self):
        """Start running the sequence - delegates to Dashboard"""
        steps = self.get_all_steps()
        
        if not steps:
            self.status_label.setText("❌ No steps to run")
            self.run_btn.setChecked(False)
            return
        
        # Check if sequence is saved
        if self.current_sequence_name == "NewSequence01":
            self.status_label.setText("❌ Please save sequence before running")
            self.run_btn.setChecked(False)
            
            # Offer to save
            reply = QMessageBox.question(
                self, "Save Sequence?",
                "Sequence must be saved before running. Save now?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.save_sequence()
                # Check if save was successful
                if self.current_sequence_name == "NewSequence01":
                    return  # User cancelled save
            else:
                return
        
        self.is_running = True
        self.run_btn.setText("⏹ STOP")
        
        # Disable editing while running
        self.add_action_btn.setEnabled(False)
        self.add_model_btn.setEnabled(False)
        self.add_vision_btn.setEnabled(False)
        self.add_palletize_btn.setEnabled(False)
        self.add_delay_btn.setEnabled(False)
        self.add_home_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.new_btn.setEnabled(False)
        
        # Emit signal to Dashboard to execute
        loop = self.loop_btn.isChecked()
        self.execute_sequence_signal.emit(self.current_sequence_name, loop)
        
        self.status_label.setText(f"▶ Running: {self.current_sequence_name} (see Dashboard)")
    
    def stop_sequence(self):
        """Stop sequence execution"""
        self.is_running = False
        self.run_btn.setChecked(False)
        self.run_btn.setText("▶️ RUN SEQUENCE")
        
        # Re-enable editing
        self.add_action_btn.setEnabled(True)
        self.add_model_btn.setEnabled(True)
        self.add_vision_btn.setEnabled(True)
        self.add_palletize_btn.setEnabled(True)
        self.add_delay_btn.setEnabled(True)
        self.add_home_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.new_btn.setEnabled(True)
        
        self.clear_running_highlight()
        self.status_label.setText("⏹ Sequence stopped")
    
    def edit_step(self, item: QListWidgetItem):
        """Handle double-click to edit a step"""
        if not item:
            return
        
        step = item.data(Qt.UserRole) or {}
        step_type = step.get("type")
        
        if step_type == "vision":
            self.configure_vision_step(item)
        elif step_type == "palletize":
            self.configure_palletize_step(item)
        else:
            self.status_label.setText("Editing is available for vision and palletize steps only.")
    
    def configure_vision_step(self, item: QListWidgetItem):
        """Open the vision designer dialog for the given item"""
        if VisionConfigDialog is None:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Vision Designer Missing",
                "Vision designer module is not available. Please ensure vision_ui/designer.py exists."
            )
            return
        
        step = item.data(Qt.UserRole) or {}
        
        dialog = VisionConfigDialog(self, step, self.config)
        if hasattr(dialog, "state_changed"):
            dialog.state_changed.connect(self._handle_designer_state_changed)
        result = dialog.exec()
        if hasattr(dialog, "state_changed"):
            try:
                dialog.state_changed.disconnect(self._handle_designer_state_changed)
            except Exception as exc:
                log_exception("SequenceTab: failed to disconnect vision designer signal", exc, level="debug")
        if result == QDialog.Accepted:
            updated_step = dialog.get_step_data()
            if updated_step:
                updated_step["type"] = "vision"
                if not updated_step.get("name"):
                    updated_step["name"] = updated_step.get("trigger", {}).get("display_name", "Vision Trigger")
                item.setData(Qt.UserRole, updated_step)
                # Refresh text to show updated summary
                number = self.steps_list.row(item) + 1
                item.setText(self._format_vision_step_text(updated_step, number))
                self.status_label.setText("✓ Vision step updated")
                display_name = updated_step.get("trigger", {}).get("display_name", "Vision Trigger")
                self._report_vision_status("watching", f"Vision updated: {display_name}")
        else:
            self.status_label.setText("Vision step unchanged")

    def configure_palletize_step(self, item: QListWidgetItem):
        """Open the palletize designer dialog for the given item"""
        if PalletizeConfigDialog is None:
            QMessageBox.warning(
                self,
                "Palletize Designer Missing",
                "Palletize UI module is not available on this system.",
            )
            return

        step = item.data(Qt.UserRole) or {}
        dialog = PalletizeConfigDialog(self, step, self.config)
        result = dialog.exec()
        if result == QDialog.Accepted:
            updated_step = dialog.get_step_data()
            if updated_step:
                updated_step["type"] = "palletize"
                item.setData(Qt.UserRole, updated_step)
                number = self.steps_list.row(item) + 1
                item.setText(self._format_palletize_step_text(updated_step, number))
                self.status_label.setText("✓ Palletize step updated")
        else:
            self.status_label.setText("Palletize step unchanged")
    
    def _format_vision_step_text(self, step: dict, number: int) -> str:
        """Format the list text for a vision step"""
        camera = step.get("camera", {})
        trigger = step.get("trigger", {})
        
        camera_label = camera.get("label", f"Camera {camera.get('index', 0)}")
        mode = trigger.get("mode", "custom")
        zones = trigger.get("zones", [])
        zone_count = len(zones)
        
        summary = trigger.get("display_name", "Setup Vision Trigger")
        metrics = trigger.get("settings", {}).get("metric", "custom")
        idle_mode = trigger.get("idle_mode", {})
        if idle_mode.get("enabled"):
            idle_text = f"Idle {idle_mode.get('interval_seconds', 2.0):.1f}s"
        else:
            idle_text = "Live"
        
        return (
            f"{number}. 👁️ Vision: {summary} • {camera_label} • "
            f"{mode.title()} • {zone_count} zone{'s' if zone_count != 1 else ''} • "
            f"metric={metrics} • {idle_text}"
        )

    def _format_palletize_step_text(self, step: dict, number: int) -> str:
        divisions = step.get("divisions", {}) or {}
        cells = len(compute_pallet_cells(step))
        cells_text = f"{cells} cell{'s' if cells != 1 else ''}" if cells else "incomplete"
        axis_text = f"{divisions.get('c1_c2', 1)}×{divisions.get('c2_c3', 1)}"
        arm_label = self._get_arm_label(step.get("arm_index", 0))
        return f"{number}. 📦 Palletize: {cells_text} ({axis_text}) • {arm_label}"

    def _get_arm_label(self, arm_index: int) -> str:
        for idx, arm_cfg in iter_arm_configs(self.config, arm_type="robot"):
            if idx == arm_index:
                return format_arm_label(idx, arm_cfg)
        return f"Arm {int(arm_index) + 1}"

    # ------------------------------------------------------------------
    # Dashboard integration helpers

    def _handle_designer_state_changed(self, state: str, payload: dict):
        """Relay live designer updates to dashboard status/log."""
        detail = payload.get("message")
        if not detail:
            if state == "triggered":
                zones = payload.get("zones", [])
                zone_part = ", ".join(zones) if zones else "Vision trigger detected"
                detail = f"Vision Triggered: {zone_part}"
            elif state == "idle":
                interval = payload.get("interval_seconds", 0)
                detail = f"Vision Idle • checking every {interval:.1f}s"
            else:
                detail = "Watching for triggers"
        self._report_vision_status(state, detail, payload)

    def _report_vision_status(self, state: str, detail: str, payload: Optional[dict] = None):
        dashboard = self._get_dashboard_tab()
        if dashboard is None:
            return
        try:
            dashboard.record_vision_status(state, detail, payload)
        except Exception as exc:
            log_exception("SequenceTab: failed to update vision status", exc, level="warning")

    def _get_dashboard_tab(self):
        parent = self.parent()
        while parent:
            if hasattr(parent, "dashboard_tab"):
                return getattr(parent, "dashboard_tab")
            parent = parent.parent()
        return None

    def highlight_running_step(self, index: int, step: dict = None):
        """Visually highlight the running step in the list."""
        if self._highlighted_step_row is not None:
            self._restore_step_style(self._highlighted_step_row)
            self._highlighted_step_row = None

        if index < 0 or index >= self.steps_list.count():
            return

        item = self.steps_list.item(index)
        if not item:
            return

        base_hex = item.data(Qt.UserRole + 1)
        base_color = QColor(base_hex) if base_hex else QColor("#505050")
        highlight = QColor(base_color).lighter(170)
        item.setBackground(highlight)
        item.setForeground(QColor("#000000"))
        self._highlighted_step_row = index

        step_info = step or item.data(Qt.UserRole) or {}
        display_name = step_info.get("name") or step_info.get("trigger", {}).get("display_name") or item.text()
        self.status_label.setText(f"▶ Running: {display_name}")

    def _restore_step_style(self, row: int):
        item = self.steps_list.item(row)
        if not item:
            return
        base_hex = item.data(Qt.UserRole + 1)
        base_color = QColor(base_hex) if base_hex else QColor("#505050")
        item.setBackground(base_color)
        item.setForeground(QColor("#ffffff"))

    def clear_running_highlight(self):
        if self._highlighted_step_row is not None:
            self._restore_step_style(self._highlighted_step_row)
            self._highlighted_step_row = None
            if hasattr(self, "_default_status_message"):
                self.status_label.setText(self._default_status_message)
