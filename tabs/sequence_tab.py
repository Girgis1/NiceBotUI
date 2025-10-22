"""
Sequence Tab - Sequence Builder
Combine actions, trained models, and delays into complex sequences
"""

import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QInputDialog, QMessageBox, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.sequences_manager import SequencesManager
from utils.actions_manager import ActionsManager


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
        except Exception as e:
            print(f"[WARNING] Could not refresh parent: {e}")
    
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
            text = f"{number}. 🎬 Action: {step.get('name', 'Unknown')}"
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
            text = f"{number}. 🏠 Home: Return Home"
            color = QColor("#4CAF50")
        else:
            text = f"{number}. ❓ Unknown step"
            color = QColor("#909090")
        
        item = QListWidgetItem(text)
        item.setData(Qt.UserRole, step)  # Store step data
        item.setBackground(color.darker(200))
        item.setForeground(QColor("#ffffff"))
        
        self.steps_list.addItem(item)
    
    def add_action_step(self):
        """Add an action step"""
        actions = self.actions_manager.list_actions()
        
        if not actions:
            self.status_label.setText("❌ No saved actions. Create one in the Record tab first.")
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
        # Get available tasks from config
        train_dir = Path(self.config["policy"].get("base_path", ""))
        
        if not train_dir.exists():
            self.status_label.setText("❌ No trained models found")
            return
        
        # Get tasks
        tasks = []
        for item in train_dir.iterdir():
            if item.is_dir() and (item / "checkpoints").exists():
                tasks.append(item.name)
        
        if not tasks:
            self.status_label.setText("❌ No trained models found")
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
        self.add_delay_btn.setEnabled(True)
        self.add_home_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.new_btn.setEnabled(True)
        
        self.status_label.setText("⏹ Sequence stopped")

