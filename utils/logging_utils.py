"""Lightweight logging helpers with consistent formatting."""

from __future__ import annotations

import logging
from typing import Optional

LOGGER_NAME = "NiceBotUI"
_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def _ensure_configured() -> logging.Logger:
    """Return the shared logger, configuring the root handler if needed."""
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(level=logging.INFO, format=_FORMAT)
    return logging.getLogger(LOGGER_NAME)


def log_message(message: str, *, level: str = "info") -> None:
    """Log a plain message at the requested level."""
    logger = _ensure_configured()
    level_value = getattr(logging, level.upper(), logging.INFO)
    logger.log(level_value, message)


def log_exception(
    context: str,
    exc: BaseException,
    *,
    level: str = "error",
    stack: bool = False,
) -> None:
    """Log an exception with contextual text.

    Args:
        context: Human-friendly description of what failed.
        exc: Captured exception instance.
        level: Logging level name (info, warning, error, debug, ...).
        stack: When True, include traceback information.
    """
    logger = _ensure_configured()
    level_value = getattr(logging, level.upper(), logging.ERROR)
    message = f"{context} ({exc.__class__.__name__}: {exc})"
    logger.log(level_value, message, exc_info=stack)


__all__ = ["log_message", "log_exception"]
