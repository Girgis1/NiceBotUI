#!/usr/bin/env python3
"""Standalone launcher for the modern vision designer UI."""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from PySide6.QtWidgets import QApplication

try:
    from app import configure_app_palette  # Reuse main app styling
except ImportError:  # Fallback palette helper if app module is unavailable
    from PySide6.QtGui import QPalette, QColor

    def configure_app_palette(app: QApplication):  # type: ignore
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

from vision_ui import VisionDesignerWindow, create_default_vision_config


class VisionApp(VisionDesignerWindow):
    """Compatibility wrapper around the new designer window."""

    def __init__(self, standalone: bool = True, step_data: Optional[dict] = None):
        super().__init__(step_data or create_default_vision_config())
        self.standalone = standalone


def main():
    parser = argparse.ArgumentParser(description="Vision trigger designer")
    parser.add_argument("--vision", action="store_true", help="Legacy flag (ignored)")
    args = parser.parse_args()  # noqa: F841 - kept for CLI compatibility

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    configure_app_palette(app)

    window = VisionApp(standalone=True)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
