"""
Dashboard Widgets - Reusable UI components for the dashboard

This package contains extracted UI components from the monolithic dashboard_tab.py
"""

from .status_indicators import StatusIndicator, CircularProgress
from .camera_preview import CameraPreviewWidget, CameraDetailDialog
from .control_panel import RunSelector, ControlButtons, SpeedControl, LogDisplay

__all__ = [
    'StatusIndicator',
    'CircularProgress',
    'CameraPreviewWidget',
    'CameraDetailDialog',
    'RunSelector',
    'ControlButtons',
    'SpeedControl',
    'LogDisplay',
]
