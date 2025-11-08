"""Logging helpers for the dashboard tab."""

from typing import Optional


class DashboardLoggingMixin:
    """Mixin that provides the rich log rendering helpers."""

    def _append_log_entry(
        self,
        level: str,
        message: str,
        action: Optional[str] = None,
        code: Optional[str] = None,
    ) -> None:
        """Render a friendly log entry with simple dedupe logic."""

        clean_message = (message or "").strip()
        if not clean_message:
            return

        if code and self._last_log_code == code and self._last_log_message == clean_message:
            return
        if not code and self._last_log_message == clean_message:
            return

        icon_map = {
            "welcome": "👋",
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "success": "✅",
            "vision": "👀",
            "system": "🛠️",
            "action": "▶️",
            "speed": "🚀",
            "stop": "⏹️",
        }

        icon = icon_map.get(level, icon_map["info"])
        entry_lines = [f"{icon} {clean_message}"]

        if action:
            entry_lines.append(f"   Fix: {action.strip()}")

        entry = "\n".join(entry_lines)
        self.log_text.append(entry)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

        self._last_log_code = code
        self._last_log_message = clean_message


__all__ = ["DashboardLoggingMixin"]
