"""
Vision UI package

Exports the interactive designer dialog and window so other modules can reuse it.
"""

from .designer import (
    VisionConfigDialog,
    VisionDesignerWindow,
    VisionDesignerWidget,
    create_default_vision_config,
)

__all__ = [
    "VisionConfigDialog",
    "VisionDesignerWindow",
    "VisionDesignerWidget",
    "create_default_vision_config",
]
