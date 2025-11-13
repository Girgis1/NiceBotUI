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
    # Temporarily redirect stdout to handle BrokenPipeError during Qt initialization
    import os
    import sys
    from contextlib import redirect_stdout, redirect_stderr

    # Create a safe stdout that ignores BrokenPipeError
    class SafeStdout:
        def __init__(self, original):
            self.original = original

        def write(self, data):
            try:
                self.original.write(data)
                self.original.flush()
            except (BrokenPipeError, OSError):
                pass  # Ignore pipe errors during GUI app startup

        def flush(self):
            try:
                self.original.flush()
            except (BrokenPipeError, OSError):
                pass

        def __getattr__(self, name):
            return getattr(self.original, name)

    # Wrap stdout during Qt initialization
    with redirect_stdout(SafeStdout(sys.stdout)), redirect_stderr(SafeStdout(sys.stderr)):
        app = QApplication(list(argv) if argv is not None else sys.argv)
        app.setStyle("Fusion")
        configure_app_palette(app)

    return app
