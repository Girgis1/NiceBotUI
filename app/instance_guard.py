"""Single-instance guard for the NiceBot UI."""

from __future__ import annotations

from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX platforms
    fcntl = None


class SingleInstanceError(RuntimeError):
    """Raised when another instance is already running."""


class SingleInstanceGuard:
    """Context manager ensuring only one UI instance runs per machine."""

    def __init__(self, lockfile: Path | None = None):
        self.lockfile_path = lockfile or Path.home() / ".nicebot.lock"
        self._handle = None

    def __enter__(self):
        if fcntl is None:
            raise SingleInstanceError(
                "SingleInstanceGuard requires POSIX fcntl locking; "
                "this build targets Linux kiosks."
            )
        self._handle = open(self.lockfile_path, "w")
        try:
            fcntl.lockf(self._handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:  # pragma: no cover - depends on OS state
            self._handle.close()
            self._handle = None
            raise SingleInstanceError("NiceBot UI is already running") from exc
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._handle:
            try:
                fcntl.lockf(self._handle, fcntl.LOCK_UN)
            except OSError:
                pass
            self._handle.close()
            self._handle = None
        return False
