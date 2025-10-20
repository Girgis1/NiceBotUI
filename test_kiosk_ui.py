"""Pytest-based smoke tests for the NiceBot UI package."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Iterable

import pytest

REQUIRED_FILES: Iterable[Path] = (
    Path("NiceBot.py"),
    Path("kiosk_dashboard.py"),
    Path("kiosk_settings.py"),
    Path("kiosk_live_record.py"),
    Path("kiosk_styles.py"),
    Path("robot_worker.py"),
    Path("rest_pos.py"),
    Path("utils/motor_controller.py"),
    Path("utils/actions_manager.py"),
)


try:  # pragma: no cover - executed only when PySide6 is available
    from PySide6.QtWidgets import QApplication

    PYSIDE_AVAILABLE = True
    PYSIDE_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - executed when PySide6 is missing
    QApplication = None  # type: ignore[assignment]
    PYSIDE_AVAILABLE = False
    PYSIDE_IMPORT_ERROR = exc

PYSIDE_SKIP_REASON = (
    "PySide6 is not available"
    if PYSIDE_IMPORT_ERROR is None
    else f"PySide6 is not available: {PYSIDE_IMPORT_ERROR}"
)


@pytest.mark.parametrize("path", REQUIRED_FILES)
def test_required_files_exist(path: Path) -> None:
    """Ensure all critical application files are present in the repository."""

    assert path.exists(), f"Missing required file: {path}"


def test_styles_generate_css() -> None:
    """Basic smoke test to ensure the style helpers are importable and usable."""

    from kiosk_styles import Colors, StatusIndicator, Styles

    assert hasattr(Colors, "BG_DARKEST"), "Colors palette is missing expected attributes"
    assert hasattr(StatusIndicator, "get_style"), "StatusIndicator is missing helpers"

    base_style = Styles.get_base_style()
    assert isinstance(base_style, str) and base_style.strip(), "Base style should be a non-empty string"


@pytest.mark.skipif(not PYSIDE_AVAILABLE, reason=PYSIDE_SKIP_REASON)
@pytest.mark.parametrize(
    "module_name",
    (
        "NiceBot",
        "kiosk_dashboard",
        "kiosk_settings",
        "kiosk_live_record",
        "robot_worker",
        "utils.motor_controller",
        "utils.actions_manager",
    ),
)
def test_modules_import(module_name: str) -> None:
    """Verify the primary application modules can be imported when PySide6 is installed."""

    importlib.import_module(module_name)


@pytest.fixture(name="qt_app")
def fixture_qt_app():  # type: ignore[return-annotation]
    """Provide a QApplication instance configured for headless environments."""

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    app = QApplication.instance() or QApplication([])

    try:
        yield app
    finally:
        # Ensure resources are released even though the event loop never starts
        app.quit()


@pytest.mark.skipif(not PYSIDE_AVAILABLE, reason=PYSIDE_SKIP_REASON)
def test_application_initialises(qt_app):  # type: ignore[no-untyped-def]
    """Instantiate the main window to catch gross initialisation errors."""

    from NiceBot import KioskApplication

    window = KioskApplication()

    try:
        assert window.width() > 0 and window.height() > 0
    finally:
        window.close()

