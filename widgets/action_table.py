"""
Action Table Widget - Industrial precision action management
Each row is ONE complete action (single position OR live recording)
"""

from __future__ import annotations

from PySide6.QtWidgets import QPushButton, QTableWidgetItem
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from .draggable_table import DraggableTableWidget


class ActionTableWidget(DraggableTableWidget):
    """Industrial-grade action table - each row is ONE contained action"""
    
    # Signals
    delete_clicked = Signal(int)  # row index
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Set up columns: Action Name | Type | Vel/Speed | Delete
        # (Velocity for positions, Speed % for live recordings)
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(["Action Name", "Type", "Vel/Speed", ""])
        
        # Set column widths
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)  # Name stretches
        header.setSectionResizeMode(1, header.ResizeMode.ResizeToContents)  # Type
        header.setSectionResizeMode(2, header.ResizeMode.Fixed)  # Speed
        header.setSectionResizeMode(3, header.ResizeMode.Fixed)  # Delete
        
        header.resizeSection(2, 100)  # Speed column
        header.resizeSection(3, 80)   # Delete button
    
    def add_single_position(
        self,
        name: str,
        positions: list[int],
        velocity: int = 600,
        metadata: dict | None = None,
    ):
        """Add ONE single position action
        
        Args:
            name: Action name
            positions: List of 6 motor positions [shoulder_pan, ...]
            velocity: Motor velocity (50-1000)
        """
        row = self.rowCount()
        self.insertRow(row)
        
        # Column 0: Name (editable)
        name_item = QTableWidgetItem(name)
        name_item.setFlags(name_item.flags() | Qt.ItemIsEditable)
        
        # Store action data
        name_item.setData(Qt.UserRole + 1, {
            'type': 'position',
            'positions': positions,
            'velocity': velocity,  # Store as velocity for positions
            'metadata': metadata or {},
        })
        self.setItem(row, 0, name_item)
        
        # Column 1: Type indicator
        type_item = QTableWidgetItem("📍 Position")
        type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
        type_item.setForeground(QColor("#2196F3"))
        self.setItem(row, 1, type_item)
        
        # Column 2: Velocity (editable, for positions)
        vel_item = QTableWidgetItem(str(velocity))
        vel_item.setData(Qt.UserRole, velocity)
        vel_item.setFlags(vel_item.flags() | Qt.ItemIsEditable)
        vel_item.setTextAlignment(Qt.AlignCenter)
        self.setItem(row, 2, vel_item)
        
        # Column 3: Delete button
        self._add_delete_button(row)
    
    def add_live_recording(
        self,
        name: str,
        recorded_data: list[dict],
        speed: int = 100,
        metadata: dict | None = None,
    ):
        """Add ONE complete live recording action
        
        Args:
            name: Action name
            recorded_data: List of {positions: [6 ints], timestamp: float, velocity: int}
            speed: Playback speed percentage (25-200%)
        """
        row = self.rowCount()
        self.insertRow(row)
        
        # Column 0: Name (editable)
        name_item = QTableWidgetItem(name)
        name_item.setFlags(name_item.flags() | Qt.ItemIsEditable)
        
        # Store complete recording data
        name_item.setData(Qt.UserRole + 1, {
            'type': 'live_recording',
            'recorded_data': recorded_data,
            'speed': speed,
            'point_count': len(recorded_data),
            'metadata': metadata or {},
        })
        self.setItem(row, 0, name_item)
        
        # Column 1: Type indicator with point count
        type_item = QTableWidgetItem(f"🔴 Recording ({len(recorded_data)} pts)")
        type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
        type_item.setForeground(QColor("#f44336"))
        self.setItem(row, 1, type_item)
        
        # Column 2: Speed % (editable, for live recordings)
        speed_item = QTableWidgetItem(str(speed))
        speed_item.setData(Qt.UserRole, speed)
        speed_item.setFlags(speed_item.flags() | Qt.ItemIsEditable)
        speed_item.setTextAlignment(Qt.AlignCenter)
        self.setItem(row, 2, speed_item)
        
        # Column 3: Delete button
        self._add_delete_button(row)
    
    def _add_delete_button(self, row: int):
        """Add delete button to row"""
        delete_btn = QPushButton("🗑️")
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 20px;
                padding: 8px;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #c62828;
            }
        """)
        # Use lambda to pass button itself, not row number (which can change)
        delete_btn.clicked.connect(lambda checked, btn=delete_btn: self._on_delete_clicked(btn))
        self.setCellWidget(row, 3, delete_btn)
    
    def _on_delete_clicked(self, button):
        """Handle delete button click - find row and emit signal
        
        Args:
            button: The delete button that was clicked
        """
        print(f"[TABLE] Delete clicked, button: {button}")
        
        # Find which row contains this button
        for current_row in range(self.rowCount()):
            if self.cellWidget(current_row, 3) == button:
                print(f"[TABLE] Found button at row {current_row}, emitting delete_clicked signal")
                self.delete_clicked.emit(current_row)
                return
        
        print(f"[TABLE] WARNING: Could not find button in table!")
    
    def ensure_delete_buttons(self):
        """Ensure all rows have delete buttons after editing"""
        for row in range(self.rowCount()):
            if not self.cellWidget(row, 3):
                self._add_delete_button(row)
    
    def get_all_actions(self) -> list[dict]:
        """Get all actions from table for playback/saving
        
        Returns:
            List of action dicts:
            {
                'name': str,
                'type': 'position' | 'live_recording',
                'speed': int (percentage),
                'positions': [6 ints] (if type='position'),
                'recorded_data': list[dict] (if type='live_recording')
            }
        """
        actions = []
        
        for row in range(self.rowCount()):
            name_item = self.item(row, 0)
            speed_item = self.item(row, 2)
            
            if not name_item:
                continue
            
            # Get stored action data
            action_data = name_item.data(Qt.UserRole + 1)
            if not action_data:
                continue
            
            # Get current velocity/speed (may have been edited)
            value_text = speed_item.text().strip().rstrip('%')  # Remove % if user added it
            try:
                value = int(value_text)
            except:
                # Default based on type
                if action_data['type'] == 'position':
                    value = action_data.get('velocity', 600)
                else:
                    value = action_data.get('speed', 100)
            
            # Build action dict
            action = {
                'name': name_item.text(),
                'type': action_data['type']
            }
            
            if action_data['type'] == 'position':
                action['positions'] = action_data['positions']
                action['velocity'] = value  # Use as velocity for positions
            elif action_data['type'] == 'live_recording':
                action['recorded_data'] = action_data['recorded_data']
                action['point_count'] = action_data['point_count']
                action['speed'] = value  # Use as speed % for live recordings
            
            metadata = action_data.get('metadata') or {}
            if metadata:
                action['metadata'] = metadata
            
            actions.append(action)
        
        return actions
    
    def get_all_data(self):
        """Compatibility method for old code - returns actions in old format"""
        actions = self.get_all_actions()
        positions = []
        delays = {}
        
        for action in actions:
            if action['type'] == 'position':
                positions.append({
                    'name': action['name'],
                    'motor_positions': action['positions'],
                    'velocity': 600  # Default velocity
                })
        
        return positions, delays
