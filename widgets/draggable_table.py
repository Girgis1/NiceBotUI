"""
Draggable Table Widget - Touch-friendly drag-and-drop table
"""

from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDrag, QColor


class DraggableTableWidget(QTableWidget):
    """Table widget with touch-friendly drag-and-drop row reordering"""
    
    # Signal emitted when rows are reordered
    rows_reordered = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Enable drag-drop
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDropIndicatorShown(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        
        # Touch-friendly settings
        self.verticalHeader().setDefaultSectionSize(60)  # 60px row height
        self.verticalHeader().hide()  # Hide row numbers
        
        # Styling
        self.setStyleSheet("""
            QTableWidget {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #404040;
                border-radius: 4px;
                font-size: 14px;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid #404040;
            }
            QTableWidget::item:selected {
                background-color: #2196F3;
            }
            QTableWidget::item:focus {
                background-color: #1976D2;
                outline: none;
            }
            QHeaderView::section {
                background-color: #404040;
                color: #ffffff;
                padding: 10px;
                border: none;
                font-weight: bold;
                font-size: 14px;
            }
        """)
    
    def dropEvent(self, event):
        """Handle drop event - reorder rows"""
        if event.source() == self:
            # Get the row being dragged
            source_row = self.currentRow()
            
            # Get drop position
            drop_pos = event.position().toPoint()
            target_row = self.indexAt(drop_pos).row()
            
            if target_row == -1:
                # Dropped outside table, append to end
                target_row = self.rowCount()
            
            if source_row != target_row and source_row != -1:
                # Move the row
                self.move_row(source_row, target_row)
                self.rows_reordered.emit()
                
                # Clear selection to avoid stuck blue highlight
                self.clearSelection()
            
            event.accept()
        else:
            event.ignore()
    
    def move_row(self, source_row: int, target_row: int):
        """Move a row from source to target position"""
        if source_row == target_row:
            return
        
        # Save row data
        row_data = []
        for col in range(self.columnCount()):
            item = self.takeItem(source_row, col)
            row_data.append(item)
        
        # Remove source row
        self.removeRow(source_row)
        
        # Adjust target if needed
        if target_row > source_row:
            target_row -= 1
        
        # Insert at target
        self.insertRow(target_row)
        for col, item in enumerate(row_data):
            if item:
                self.setItem(target_row, col, item)
        
        # Select the moved row
        self.selectRow(target_row)
    
    def get_all_rows_data(self) -> list[dict]:
        """Get all row data as list of dicts
        
        Returns:
            List of dicts with column headers as keys
        """
        headers = [self.horizontalHeaderItem(i).text() for i in range(self.columnCount())]
        rows = []
        
        for row in range(self.rowCount()):
            row_data = {}
            for col in range(self.columnCount()):
                item = self.item(row, col)
                row_data[headers[col]] = item.text() if item else ""
            rows.append(row_data)
        
        return rows

