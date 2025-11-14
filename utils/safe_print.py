"""Safe print helper that swallows BrokenPipeError for GUI apps."""

from __future__ import annotations

import builtins
from typing import Any


def safe_print(*args: Any, **kwargs: Any) -> None:
    try:
        builtins.print(*args, **kwargs)
    except BrokenPipeError:  # pragma: no cover - depends on environment
        pass

__all__ = ["safe_print"]
