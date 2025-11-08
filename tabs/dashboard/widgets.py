"""Dashboard tab UI widgets."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QWidget


class CircularProgress(QWidget):
    """Circular progress indicator used in the dashboard status bar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.progress = 0
        self.setFixedSize(24, 24)
        self.setVisible(True)

    def set_progress(self, value: int) -> None:
        self.progress = value
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
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
    """Colored dot indicator used across the dashboard."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.connected = False
        self.warning = False
        self.null = False
        self.update_style()

    def set_connected(self, connected: bool) -> None:
        self.connected = connected
        self.warning = False
        self.null = False
        self.update_style()

    def set_warning(self) -> None:
        self.connected = False
        self.warning = True
        self.null = False
        self.update_style()

    def set_null(self) -> None:
        self.connected = False
        self.warning = False
        self.null = True
        self.update_style()

    def update_style(self) -> None:
        if hasattr(self, "null") and self.null:
            self.setFixedSize(20, 20)
            self.setStyleSheet(
                """
                QLabel {
                    background-color: transparent;
                    border: 2px solid #606060;
                    border-radius: 10px;
                }
                """
            )
        elif self.warning:
            color = "#FF9800"
            self.setFixedSize(20, 20)
            self.setStyleSheet(
                f"""
                QLabel {{
                    background-color: {color};
                    border-radius: 10px;
                }}
                """
            )
        elif self.connected:
            color = "#4CAF50"
            self.setFixedSize(20, 20)
            self.setStyleSheet(
                f"""
                QLabel {{
                    background-color: {color};
                    border-radius: 10px;
                }}
                """
            )
        else:
            color = "#E53935"
            self.setFixedSize(20, 20)
            self.setStyleSheet(
                f"""
                QLabel {{
                    background-color: {color};
                    border-radius: 10px;
                }}
                """
            )


__all__ = ["CircularProgress", "StatusIndicator"]
