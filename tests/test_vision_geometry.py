"""Tests for coordinate helpers in :mod:`vision_ui.designer`."""

from __future__ import annotations

import pathlib
import sys
import types

import numpy as np

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Provide lightweight stubs for OpenCV and PySide6 so the designer module can
# be imported in CI environments without graphical dependencies.
cv2_stub = types.SimpleNamespace(
    COLOR_BGR2RGB=0,
    COLOR_BGR2GRAY=0,
    VideoCapture=lambda *_, **__: None,
    cvtColor=lambda frame, _: frame,
    rectangle=lambda *_, **__: None,
    circle=lambda *_, **__: None,
    Canny=lambda *_, **__: np.zeros((1, 1), dtype=np.uint8),
    bitwise_and=lambda *_, **__: np.zeros((1, 1), dtype=np.uint8),
    fillPoly=lambda *_, **__: None,
    mean=lambda *_, **__: (0,),
)
sys.modules.setdefault("cv2", cv2_stub)


class _Signal:
    def __init__(self, *_, **__):
        pass

    def connect(self, *_):  # pragma: no cover - stub
        pass

    def emit(self, *_):  # pragma: no cover - stub
        pass


class _Qt:
    LeftButton = 1
    NoPen = 0
    SolidLine = 0
    DashLine = 0
    RoundCap = 0
    RoundJoin = 0
    OddEvenFill = 0
    AlignCenter = 0
    AlignLeft = 0
    AlignTop = 0
    ScrollBarAlwaysOff = 0
    ScrollBarAlwaysOn = 1


class _QAbstractItemView:
    SingleSelection = 1
    SelectRows = 0


def _make_dummy(name):
    return type(name, (), {"__init__": lambda self, *args, **kwargs: None})


class _QApplication:
    def __init__(self, *_, **__):
        pass

    @staticmethod
    def instance():
        return None

    def setStyle(self, *_):
        pass

    def exec(self):
        return 0

    def setPalette(self, *_):
        pass


qtcore_stub = types.SimpleNamespace(
    QPointF=_make_dummy("QPointF"),
    QRectF=_make_dummy("QRectF"),
    Qt=_Qt,
    QTimer=_make_dummy("QTimer"),
    Signal=_Signal,
)

qtgui_stub = types.SimpleNamespace(
    QColor=_make_dummy("QColor"),
    QFont=_make_dummy("QFont"),
    QImage=_make_dummy("QImage"),
    QPainter=_make_dummy("QPainter"),
    QPen=_make_dummy("QPen"),
    QPolygonF=_make_dummy("QPolygonF"),
)

qtwidgets_stub = types.SimpleNamespace(
    QApplication=_QApplication,
    QCheckBox=_make_dummy("QCheckBox"),
    QComboBox=_make_dummy("QComboBox"),
    QDialog=_make_dummy("QDialog"),
    QDoubleSpinBox=_make_dummy("QDoubleSpinBox"),
    QFormLayout=_make_dummy("QFormLayout"),
    QFrame=_make_dummy("QFrame"),
    QGroupBox=_make_dummy("QGroupBox"),
    QHBoxLayout=_make_dummy("QHBoxLayout"),
    QLabel=_make_dummy("QLabel"),
    QLineEdit=_make_dummy("QLineEdit"),
    QListWidget=_make_dummy("QListWidget"),
    QListWidgetItem=_make_dummy("QListWidgetItem"),
    QMessageBox=_make_dummy("QMessageBox"),
    QPushButton=_make_dummy("QPushButton"),
    QScrollArea=_make_dummy("QScrollArea"),
    QSizePolicy=_make_dummy("QSizePolicy"),
    QSlider=_make_dummy("QSlider"),
    QSpinBox=_make_dummy("QSpinBox"),
    QVBoxLayout=_make_dummy("QVBoxLayout"),
    QWidget=_make_dummy("QWidget"),
    QAbstractItemView=_QAbstractItemView,
    QTableWidget=_make_dummy("QTableWidget"),
    QTableWidgetItem=_make_dummy("QTableWidgetItem"),
)

pyside_stub = types.ModuleType("PySide6")
pyside_stub.QtCore = qtcore_stub
pyside_stub.QtGui = qtgui_stub
pyside_stub.QtWidgets = qtwidgets_stub

sys.modules.setdefault("PySide6", pyside_stub)
sys.modules.setdefault("PySide6.QtCore", qtcore_stub)
sys.modules.setdefault("PySide6.QtGui", qtgui_stub)
sys.modules.setdefault("PySide6.QtWidgets", qtwidgets_stub)

from vision_ui.designer import _normalized_polygon_to_pixels, _pixels_to_normalized


def test_normalized_polygon_to_pixels_clamps_upper_bounds():
    pts = _normalized_polygon_to_pixels([(0.0, 0.0), (1.0, 1.0)], width=640, height=480)

    assert np.array_equal(pts[0], np.array([0, 0]))
    # Ensure the upper edge does not exceed the valid pixel index
    assert np.array_equal(pts[1], np.array([639, 479]))


def test_pixels_to_normalized_round_trip():
    original = [(0, 0), (639, 479)]
    normalized = _pixels_to_normalized(original, width=640, height=480)
    reconstructed = _normalized_polygon_to_pixels(normalized, width=640, height=480)

    assert np.array_equal(reconstructed, np.array(original))
