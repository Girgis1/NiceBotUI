"""Shared execution context used by strategy helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, TYPE_CHECKING

from utils.actions_manager import ActionsManager
from utils.motor_controller import MotorController
from utils.sequences_manager import SequencesManager
from utils.camera_hub import CameraStreamHub

if TYPE_CHECKING:  # pragma: no cover
    from utils.execution_manager import ExecutionWorker


@dataclass
class ExecutionContext:
    """Stores shared execution state and helper emitters."""

    worker: "ExecutionWorker"
    config: Dict[str, Any]
    motor_controller: MotorController
    actions_mgr: ActionsManager
    sequences_mgr: SequencesManager
    camera_hub: Optional[CameraStreamHub]
    options: Dict[str, Any]

    def log_info(self, message: str) -> None:
        self.worker.log_message.emit("info", message)

    def log_warning(self, message: str) -> None:
        self.worker.log_message.emit("warning", message)

    def log_error(self, message: str) -> None:
        self.worker.log_message.emit("error", message)

    def set_status(self, text: str) -> None:
        self.worker.status_update.emit(text)

    def update_progress(self, current: int, total: int) -> None:
        self.worker.progress_update.emit(current, total)

    def should_stop(self) -> bool:
        return self.worker._stop_requested  # noqa: SLF001
