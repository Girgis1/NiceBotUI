"""Reusable homing sequence runner shared across UI modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Sequence

from PySide6.QtCore import QObject, QThread, Signal, Qt

from utils.config_compat import ensure_multi_arm_config
from utils.config_store import ConfigStore
from utils.home_move_worker import HomeMoveRequest, HomeMoveWorker
from utils.logging_utils import log_exception

HomeSelection = Literal["all", "left", "right"]


@dataclass
class HomeArmInfo:
    arm_index: int
    arm_id: int
    arm_name: str
    velocity: Optional[int]

    def as_dict(self) -> Dict[str, int | str | None]:
        return {
            "arm_index": self.arm_index,
            "arm_id": self.arm_id,
            "arm_name": self.arm_name,
            "velocity": self.velocity,
        }


class HomeSequenceRunner(QObject):
    """Coordinates sequential homing of one or more arms."""

    started = Signal(list)
    progress = Signal(str)
    arm_started = Signal(dict)
    arm_finished = Signal(dict, bool, str)
    finished = Signal(bool, str)
    error = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._store = ConfigStore.instance()
        self._queue: list[HomeArmInfo] = []
        self._config: dict = {}
        self._active_arm: Optional[HomeArmInfo] = None
        self._current_thread: Optional[QThread] = None
        self._current_worker: Optional[HomeMoveWorker] = None
        self._running = False
        self._had_failure = False
        self._parallel_mode = False
        self._parallel_threads: list[QThread] = []
        self._pending_parallel = 0

    @property
    def is_running(self) -> bool:
        return self._running or (self._current_thread is not None)

    def start(
        self,
        *,
        selection: HomeSelection = "all",
        arm_indexes: Optional[Sequence[int]] = None,
        config: Optional[dict] = None,
        reload_from_disk: bool = False,
        velocity_override: Optional[int] = None,
    ) -> bool:
        """Start a homing sequence.

        Args:
            selection: Logical selection helper ("all", "left", "right").
            arm_indexes: Explicit list of arm indexes (overrides selection when provided).
            config: Optional in-memory config to use.
            reload_from_disk: If True (or config is None) reloads config.json from disk.
            velocity_override: Optional velocity applied to every arm in the sequence.
        """

        if self.is_running:
            self.error.emit("Home sequence already running.")
            return False

        try:
            if config is None:
                cfg = self._store.reload() if reload_from_disk else self._store.get_config()
            else:
                store_cfg = self._store.get_config()
                if config is store_cfg:
                    cfg = store_cfg
                else:
                    cfg = ensure_multi_arm_config(dict(config))
        except Exception as exc:
            log_exception("HomeSequenceRunner: failed to load config", exc)
            self.error.emit(f"Configuration error: {exc}")
            return False

        queue = self._build_queue(cfg, arm_indexes, selection, velocity_override)
        if not queue:
            self.error.emit("No enabled arms with home positions.")
            return False

        self._config = cfg
        self._queue = queue
        self._active_arm = None
        self._had_failure = False
        self._parallel_mode = False
        self._parallel_threads = []
        self._pending_parallel = 0
        self._running = True
        self.started.emit([info.as_dict() for info in queue])
        # If all arms requested and we have more than one, run in parallel
        if selection == "all" and len(queue) > 1:
            self._parallel_mode = True
            self._start_parallel(queue)
        else:
            self._start_next_arm()
        return True

    def cancel(self) -> None:
        """Cancel any pending arms once the active arm finishes."""
        self._queue.clear()

    def _build_queue(
        self,
        config: dict,
        arm_indexes: Optional[Sequence[int]],
        selection: HomeSelection,
        velocity_override: Optional[int],
    ) -> list[HomeArmInfo]:
        robot_arms = config.get("robot", {}).get("arms", [])
        indexes: list[int]

        if arm_indexes is not None:
            indexes = []
            for idx in arm_indexes:
                try:
                    clean_idx = int(idx)
                except (ValueError, TypeError):
                    continue
                if clean_idx not in indexes:
                    indexes.append(clean_idx)
        else:
            indexes = self._resolve_selection(robot_arms, selection)

        queue: list[HomeArmInfo] = []
        for idx in indexes:
            if idx < 0 or idx >= len(robot_arms):
                continue
            arm_cfg = robot_arms[idx]
            if not arm_cfg.get("enabled", True):
                continue
            if not arm_cfg.get("home_positions"):
                continue
            queue.append(
                HomeArmInfo(
                    arm_index=idx,
                    arm_id=arm_cfg.get("arm_id", idx + 1),
                    arm_name=arm_cfg.get("name", f"Arm {arm_cfg.get('arm_id', idx + 1)}"),
                    velocity=velocity_override if velocity_override is not None else arm_cfg.get("home_velocity"),
                )
            )
        return queue

    @staticmethod
    def _resolve_selection(arms: list[dict], selection: HomeSelection) -> list[int]:
        enabled = [idx for idx, arm in enumerate(arms) if arm.get("enabled", True)]
        if selection == "all":
            return enabled

        target_id = 1 if selection == "left" else 2
        for idx, arm in enumerate(arms):
            if arm.get("enabled", True) and arm.get("arm_id") == target_id:
                return [idx]

        if selection == "left" and enabled:
            return [enabled[0]]
        if selection == "right" and len(enabled) >= 2:
            return [enabled[1]]
        return enabled[:1]

    def _start_next_arm(self) -> None:
        if self._current_thread:
            return

        if not self._queue:
            self._running = False
            message = "✅ All arms homed" if not self._had_failure else "⚠️ Homing finished with errors"
            self.finished.emit(not self._had_failure, message)
            return

        try:
            info = self._queue.pop(0)
            self._active_arm = info
            self.arm_started.emit(info.as_dict())

            request = HomeMoveRequest(
                config=self._config,
                velocity_override=info.velocity,
                arm_index=info.arm_index,
            )

            worker = HomeMoveWorker(request)
            thread = QThread(self)
            worker.moveToThread(thread)

            thread.started.connect(worker.run)
            worker.progress.connect(self.progress.emit, Qt.QueuedConnection)
            worker.finished.connect(self._handle_arm_finished, Qt.QueuedConnection)
            worker.finished.connect(thread.quit, Qt.QueuedConnection)
            thread.finished.connect(self._on_thread_finished)

            self._current_worker = worker
            self._current_thread = thread
            thread.start()
        except Exception as exc:
            log_exception("HomeSequenceRunner: failed to start arm", exc, level="error", stack=True)
            self._running = False
            self.error.emit(f"Homing error: {exc}")

    def _handle_arm_finished(self, success: bool, message: str) -> None:
        try:
            info = self._active_arm.as_dict() if self._active_arm else {}
            if not success:
                self._had_failure = True
            self.arm_finished.emit(info, success, message)
        except Exception as exc:
            self._had_failure = True
            log_exception("HomeSequenceRunner: arm finished handler failed", exc, level="error", stack=True)
            self.error.emit(f"Homing handler error: {exc}")
        finally:
            self._active_arm = None

    def _on_thread_finished(self) -> None:
        thread = self._current_thread
        worker = self._current_worker
        self._current_thread = None
        self._current_worker = None

        try:
            if thread:
                if thread.isRunning():
                    thread.quit()
                    thread.wait(2000)
                thread.deleteLater()
            if worker:
                worker.deleteLater()
        except Exception as exc:
            log_exception("HomeSequenceRunner: thread cleanup failed", exc, level="warning")
            self._running = False
            self.error.emit(f"Thread cleanup failed: {exc}")
            return

        if self._running:
            self._start_next_arm()

    # ------------------------------------------------------------------
    # Parallel homing helpers

    def _start_parallel(self, queue: list[HomeArmInfo]) -> None:
        """Start homing all arms concurrently."""
        self._pending_parallel = len(queue)
        for info in queue:
            try:
                self._start_parallel_arm(info)
            except Exception as exc:
                self._had_failure = True
                log_exception("HomeSequenceRunner: failed to start parallel arm", exc, level="error", stack=True)
                self.arm_finished.emit(info.as_dict(), False, f"Homing error: {exc}")
                self._pending_parallel -= 1

        if self._pending_parallel <= 0:
            self._finish_parallel()

    def _start_parallel_arm(self, info: HomeArmInfo) -> None:
        """Start a single arm in parallel mode."""
        self.arm_started.emit(info.as_dict())

        request = HomeMoveRequest(
            config=self._config,
            velocity_override=info.velocity,
            arm_index=info.arm_index,
        )

        worker = HomeMoveWorker(request)
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self.progress.emit, Qt.QueuedConnection)
        worker.finished.connect(lambda success, message, info=info: self._handle_parallel_finished(info, success, message), Qt.QueuedConnection)
        worker.finished.connect(thread.quit, Qt.QueuedConnection)
        thread.finished.connect(lambda: self._cleanup_parallel_thread(thread, worker), Qt.QueuedConnection)

        self._parallel_threads.append(thread)
        thread.start()

    def _handle_parallel_finished(self, info: HomeArmInfo, success: bool, message: str) -> None:
        try:
            if not success:
                self._had_failure = True
            self.arm_finished.emit(info.as_dict(), success, message)
        finally:
            self._pending_parallel -= 1
            if self._pending_parallel <= 0:
                self._finish_parallel()

    def _cleanup_parallel_thread(self, thread: QThread, worker: HomeMoveWorker) -> None:
        try:
            if thread.isRunning():
                thread.quit()
                thread.wait(1000)
            worker.deleteLater()
            thread.deleteLater()
        except Exception as exc:
            log_exception("HomeSequenceRunner: parallel thread cleanup failed", exc, level="warning")

    def _finish_parallel(self) -> None:
        self._running = False
        message = "✅ All arms homed" if not self._had_failure else "⚠️ Homing finished with errors"
        self.finished.emit(not self._had_failure, message)
