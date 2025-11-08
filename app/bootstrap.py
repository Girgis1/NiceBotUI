"""Bootstrap helpers for the GUI entrypoint."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from PySide6.QtWidgets import QApplication

from app.theme import configure_app_palette


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LeRobot Operator Console")
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="Start in windowed mode instead of fullscreen",
    )
    parser.add_argument(
        "--no-fullscreen",
        action="store_true",
        help="Disable fullscreen mode (same as --windowed)",
    )
    parser.add_argument(
        "--screen",
        type=int,
        default=0,
        help="Screen index for the main window (0=primary)",
    )
    parser.add_argument(
        "--vision",
        action="store_true",
        help="Launch only the vision designer interface",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = build_arg_parser()
    return parser.parse_args(argv)


def should_use_fullscreen(args: argparse.Namespace) -> bool:
    return not (args.windowed or args.no_fullscreen)


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    app = QApplication(list(argv) if argv is not None else sys.argv)
    app.setStyle("Fusion")
    configure_app_palette(app)
    return app
