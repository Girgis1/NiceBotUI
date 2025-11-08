"""Helpers for notifying other tabs when recordings change."""

from __future__ import annotations


class TabBridgeMixin:
    """Provides hooks for cross-tab refresh signals."""

    def _notify_parent_refresh(self):
        """Attempt to refresh the dashboard tab's run selector."""
        try:
            parent = self.parent()
            while parent:
                if hasattr(parent, "dashboard_tab"):
                    parent.dashboard_tab.refresh_run_selector()
                    print("[RECORD] ✓ Refreshed dashboard dropdown")
                    return
                parent = parent.parent()
        except Exception as exc:  # pragma: no cover - defensive logging
            print(f"[WARNING] Could not refresh parent: {exc}")
