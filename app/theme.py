"""Application-wide palette/theme helpers."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette


def configure_app_palette(app) -> None:
    """Apply a consistent dark theme to the QApplication."""
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(42, 42, 42))
    palette.setColor(QPalette.WindowText, QColor(255, 255, 255))
    palette.setColor(QPalette.Base, QColor(64, 64, 64))
    palette.setColor(QPalette.AlternateBase, QColor(72, 72, 72))
    palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
    palette.setColor(QPalette.ToolTipText, QColor(0, 0, 0))
    palette.setColor(QPalette.Text, QColor(255, 255, 255))
    palette.setColor(QPalette.Button, QColor(70, 70, 70))
    palette.setColor(QPalette.ButtonText, QColor(255, 255, 255))
    palette.setColor(QPalette.BrightText, QColor(255, 100, 100))
    palette.setColor(QPalette.Link, QColor(76, 175, 80))
    palette.setColor(QPalette.Highlight, QColor(76, 175, 80))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)
