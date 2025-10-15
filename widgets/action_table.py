"""
Action Table Widget - Specialized table for action recording
"""

from PySide6.QtWidgets import QPushButton, QLineEdit, QWidget, QHBoxLayout
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from .draggable_table import DraggableTableWidget


class ActionTableWidget(DraggableTableWidget):
    """Specialized table for recording and displaying motor positions"""
    
    # Signals
    delete_clicked = Signal(int)  # row index
    delay_marker_clicked = Signal(int)  # row index (row after which delay is shown)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Set up columns: Name | Motor Positions | Velocity | Delete
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(["Name", "Motor Positions", "Velocity", "Delete"])
        
        # Set column widths (for 954px content area width)
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, header.ResizeMode.Interactive)  # Name - 150px
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)      # Positions - stretch
        header.setSectionResizeMode(2, header.ResizeMode.Fixed)        # Velocity - 100px
        header.setSectionResizeMode(3, header.ResizeMode.Fixed)        # Delete - 80px
        
        header.resizeSection(0, 150)
        header.resizeSection(2, 100)
        header.resizeSection(3, 80)
    
    def add_position_row(self, name: str, positions: list[int], velocity: int, row: int = -1):
        """Add a position row to the table
        
        Args:
            name: Position name (e.g., "Pos 1")
            positions: List of 6 motor positions
            velocity: Movement velocity
            row: Row index to insert at (-1 = append)
        """
        if row == -1:
            row = self.rowCount()
        
        self.insertRow(row)
        
        # Name column
        from PySide6.QtWidgets import QTableWidgetItem
        name_item = QTableWidgetItem(name)
        name_item.setData(Qt.UserRole, "position")  # Mark as position row
        name_item.setFlags(name_item.flags() | Qt.ItemIsEditable)  # Make editable
        self.setItem(row, 0, name_item)
        
        # Motor positions (full display)
        positions_str = str(positions)
        positions_item = QTableWidgetItem(positions_str)
        positions_item.setData(Qt.UserRole + 1, positions)  # Store full positions
        positions_item.setFlags(positions_item.flags() & ~Qt.ItemIsEditable)  # Not editable
        self.setItem(row, 1, positions_item)
        
        # Velocity
        velocity_item = QTableWidgetItem(str(velocity))
        velocity_item.setFlags(velocity_item.flags() | Qt.ItemIsEditable)  # Make editable
        self.setItem(row, 2, velocity_item)
        
        # Delete button (now in column 3)
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
        delete_btn.clicked.connect(lambda checked, r=row: self._on_delete_clicked(r))
        self.setCellWidget(row, 3, delete_btn)
    
    def add_delay_row(self, delay_seconds: float, row: int = -1):
        """Add a delay indicator row
        
        Args:
            delay_seconds: Delay duration in seconds
            row: Row index to insert at (-1 = append)
        """
        if row == -1:
            row = self.rowCount()
        
        self.insertRow(row)
        
        # First column: "Delay" label (not editable)
        from PySide6.QtWidgets import QTableWidgetItem
        delay_label = QTableWidgetItem("⏱️ Delay")
        delay_label.setData(Qt.UserRole, "delay")  # Mark as delay row
        delay_label.setTextAlignment(Qt.AlignCenter)
        delay_label.setBackground(QColor("#FF9800"))  # Orange background
        delay_label.setForeground(QColor("#ffffff"))
        delay_label.setFlags(delay_label.flags() & ~Qt.ItemIsEditable)  # Not editable
        self.setItem(row, 0, delay_label)
        
        # Second column: Editable time value
        delay_value = QTableWidgetItem(f"{delay_seconds:.1f}")
        delay_value.setData(Qt.UserRole, "delay_time")  # Mark as delay time
        delay_value.setData(Qt.UserRole + 1, delay_seconds)  # Store delay value
        delay_value.setTextAlignment(Qt.AlignCenter)
        delay_value.setBackground(QColor("#FF9800"))
        delay_value.setForeground(QColor("#ffffff"))
        delay_value.setFlags(delay_value.flags() | Qt.ItemIsEditable)  # Editable!
        self.setItem(row, 1, delay_value)
        
        # Third column: "seconds" label (merged with velocity column)
        seconds_label = QTableWidgetItem("seconds")
        seconds_label.setTextAlignment(Qt.AlignCenter)
        seconds_label.setBackground(QColor("#FF9800"))
        seconds_label.setForeground(QColor("#ffffff"))
        seconds_label.setFlags(seconds_label.flags() & ~Qt.ItemIsEditable)
        self.setItem(row, 2, seconds_label)
        
        # Delete button for delay
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
        delete_btn.clicked.connect(lambda checked, r=row: self._on_delete_clicked(r))
        self.setCellWidget(row, 3, delete_btn)
    
    def _on_delete_clicked(self, row: int):
        """Handle delete button click"""
        # Emit signal for the button's row
        self.delete_clicked.emit(row)
    
    def ensure_delete_buttons(self):
        """Ensure all rows have delete buttons (called after edits or drag-drop)"""
        for row in range(self.rowCount()):
            if not self.cellWidget(row, 3):
                # Re-add delete button if missing
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
                delete_btn.clicked.connect(lambda checked, r=row: self._on_delete_clicked(r))
                self.setCellWidget(row, 3, delete_btn)
    
    def get_position_data(self, row: int) -> dict:
        """Get position data from a row
        
        Returns:
            {"name": str, "motor_positions": list, "velocity": int}
        """
        name_item = self.item(row, 0)
        if not name_item or name_item.data(Qt.UserRole) != "position":
            return None
        
        positions_item = self.item(row, 1)
        velocity_item = self.item(row, 2)
        
        return {
            "name": name_item.text(),
            "motor_positions": positions_item.data(Qt.UserRole + 1),
            "velocity": int(velocity_item.text()) if velocity_item else 600
        }
    
    def is_delay_row(self, row: int) -> bool:
        """Check if a row is a delay row"""
        item = self.item(row, 0)
        return item and item.data(Qt.UserRole) == "delay"
    
    def get_delay_value(self, row: int) -> float:
        """Get delay value from a delay row"""
        # Check if this is a delay row
        if not self.is_delay_row(row):
            return 0.0
        
        # Get value from second column (editable time field)
        time_item = self.item(row, 1)
        if time_item:
            try:
                return float(time_item.text())
            except ValueError:
                return 0.0
        return 0.0
    
    def get_all_data(self) -> tuple[list, dict]:
        """Get all positions and delays
        
        Returns:
            (positions_list, delays_dict)
            positions_list: List of position dicts
            delays_dict: Dict mapping position index to delay seconds
        """
        positions = []
        delays = {}
        
        for row in range(self.rowCount()):
            if self.is_delay_row(row):
                # This is a delay - associate with previous position
                if positions:
                    delays[len(positions) - 1] = self.get_delay_value(row)
            else:
                # This is a position
                pos_data = self.get_position_data(row)
                if pos_data:
                    positions.append(pos_data)
        
        return positions, delays

