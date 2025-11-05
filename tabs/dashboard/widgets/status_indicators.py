"""
Status Indicator Widgets - Extracted from dashboard_tab.py

Provides reusable status indicator components for the dashboard.
"""

from PySide6.QtWidgets import QLabel, QWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen, QColor


class CircularProgress(QWidget):
    """Circular progress indicator"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.progress = 0
        self.setFixedSize(24, 24)
        self.setVisible(True)  # Always visible

    def set_progress(self, value):
        self.progress = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        pen = QPen(QColor("#555555"), 2)
        painter.setPen(pen)
        painter.setBrush(QColor("#2d2d2d"))
        painter.drawEllipse(2, 2, 20, 20)

        if self.progress > 0:
            pen = QPen(QColor("#4CAF50"), 3)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)

            start_angle = -90 * 16
            span_angle = -(self.progress * 360 // 100) * 16

            painter.drawArc(3, 3, 18, 18, start_angle, span_angle)


class StatusIndicator(QLabel):
    """Colored dot indicator"""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.connected = False
        self.warning = False
        self.null = False  # Initialize null attribute
        self.update_style()

    def set_connected(self, connected):
        self.connected = connected
        self.warning = False
        self.null = False  # Clear null state when setting connected
        self.update_style()

    def set_warning(self):
        self.connected = False
        self.warning = True
        self.null = False  # Clear null state when setting warning
        self.update_style()

    def set_null(self):
        """Set as null/empty indicator"""
        self.connected = False
        self.warning = False
        self.null = True
        self.update_style()

    def update_style(self):
        if hasattr(self, 'null') and self.null:
            # Null indicator - unfilled black circle
            self.setFixedSize(20, 20)
            self.setStyleSheet("""
                QLabel {
                    background-color: transparent;
                    border: 2px solid #606060;
                    border-radius: 10px;
                }
            """)
        elif self.warning:
            color = "#FF9800"
            self.setFixedSize(20, 20)
            self.setStyleSheet(f"""
                QLabel {{
                    background-color: {color};
                    border-radius: 10px;
                }}
            """)
        elif self.connected:
            color = "#2e7d32"
            self.setFixedSize(20, 20)
            self.setStyleSheet(f"""
                QLabel {{
                    background-color: {color};
                    border-radius: 10px;
                }}
            """)
        else:
            color = "#f44336"
            self.setFixedSize(20, 20)
            self.setStyleSheet(f"""
                QLabel {{
                    background-color: {color};
                    border-radius: 10px;
                }}
            """)
