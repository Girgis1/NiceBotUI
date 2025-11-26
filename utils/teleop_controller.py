"""Centralized teleop controller + mode manager."""

from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtCore import QObject, Signal, QProcess, QThread, QProcessEnvironment, QMetaObject, Q_ARG, Qt

from utils.app_state import AppStateStore
from utils.config_compat import get_arm_port
from utils.logging_utils import log_exception
from utils.safe_print import safe_print
from utils.teleop_preflight import TeleopPreflight

# LeRobot imports for programmatic teleop
try:
    import lerobot
    import lerobot.teleoperators.so100_leader
    import lerobot.teleoperators.so101_leader
    import lerobot.teleoperators.bi_so100_leader
    import lerobot.robots.so100_follower
    import lerobot.robots.so101_follower
    import lerobot.robots.bi_so100_follower
    LEROBOT_AVAILABLE = True
except ImportError:
    LEROBOT_AVAILABLE = False
    lerobot = None

PROGRAMMATIC_TELEOP_ENABLED = (
    os.environ.get("ENABLE_PROGRAMMATIC_TELEOP", "0") == "1" and LEROBOT_AVAILABLE
)


JETSON_FLAG = Path("/etc/nv_tegra_release")
REPO_ROOT = Path(__file__).resolve().parents[1]


class CompositeBimanualRobot:
    """Simple wrapper to route combined actions to two follower instances."""

    def __init__(self, left_robot, right_robot):
        self.left_robot = left_robot
        self.right_robot = right_robot

    def connect(self):
        self.left_robot.connect()
        self.right_robot.connect()

    def is_connected(self):  # pragma: no cover - passthrough
        return (
            hasattr(self.left_robot, "is_connected")
            and self.left_robot.is_connected()
            and hasattr(self.right_robot, "is_connected")
            and self.right_robot.is_connected()
        )

    def send_action(self, action):
        if not isinstance(action, dict) or "left" not in action or "right" not in action:
            raise ValueError("Composite robot expects action dict with left/right keys")
        self.left_robot.send_action(action["left"])
        self.right_robot.send_action(action["right"])

    def disconnect(self):  # pragma: no cover - passthrough
        with contextlib.suppress(Exception):
            self.left_robot.disconnect()
        with contextlib.suppress(Exception):
            self.right_robot.disconnect()


class ProgrammaticTeleopWorker(QThread):
    """Worker thread for programmatic lerobot teleop (single-arm and bimanual)."""

    finished = Signal()
    error = Signal(str)
    log_message = Signal(str)

    def __init__(self, config: dict, arm_target: str):
        super().__init__()
        self.config = config
        self.arm_target = arm_target  # "left", "right", or "both"
        self.running = False
        self.teleop = None
        self.robot = None
        self._stopping = False

    def stop(self):
        """Stop the teleop session."""
        self._stopping = True
        self.running = False
        self.requestInterruption()
        self.wait(2000)  # Wait up to 2 seconds for clean shutdown

    def run(self):
        """Main teleop execution loop."""
        if not LEROBOT_AVAILABLE:
            self._emit_error_safe("LeRobot library not available")
            return

        try:
            self.running = True
            self._emit_log_safe(f"Starting programmatic {self.arm_target} teleop...")

            # Create teleoperator and robot instances
            teleop_result, self.robot = self._create_teleop_instances()

            # Handle mixed-type or dual leader case
            if self.arm_target == "both" and isinstance(teleop_result, tuple):
                # Dual teleops: (left_teleop, right_teleop)
                self.left_teleop, self.right_teleop = teleop_result
                self.teleop = None
                self._is_mixed_bimanual = True
            else:
                # Single-arm or combined bimanual teleop
                self.teleop = teleop_result
                self.left_teleop = None
                self.right_teleop = None
                self._is_mixed_bimanual = False

            # Connect and calibrate teleoperators
            if self._is_mixed_bimanual:
                self._emit_log_safe("Connecting left teleoperator…")
                self.left_teleop.connect()
                self._emit_log_safe("Connecting right teleoperator…")
                self.right_teleop.connect()
                self._emit_log_safe("Calibrating left teleoperator…")
                self.left_teleop.calibrate()
                self._emit_log_safe("Calibrating right teleoperator…")
                self.right_teleop.calibrate()
            else:
                self._emit_log_safe("Connecting teleoperator…")
                self.teleop.connect()
                self._emit_log_safe("Calibrating teleoperator…")
                self.teleop.calibrate()

            self._emit_log_safe("Connecting robot...")
            self.robot.connect()

            self._emit_log_safe(f"🎮 {self.arm_target.title()} teleop active - move leader arms to control")

            # Main teleop loop
            while self.running:
                try:
                    if self._is_mixed_bimanual:
                        # Get actions from both teleoperators
                        left_action = self.left_teleop.get_action()
                        right_action = self.right_teleop.get_action()

                        combined_action = {"left": left_action, "right": right_action}
                        self.robot.send_action(combined_action)
                    else:
                        # Single teleoperator case
                        action = self.teleop.get_action()
                        self.robot.send_action(action)

                    # Small delay to prevent overwhelming the system
                    time.sleep(0.01)

                except Exception as e:
                    if self.running:  # Only emit error if we're still supposed to be running
                        self._emit_log_safe(f"Teleop error: {e}")
                        break

            # Cleanup
            self._cleanup()

            if self.running and not self._stopping:  # Normal completion
                self._emit_log_safe("✅ Teleop session completed")
            else:  # Stopped by user
                self._emit_log_safe("🛑 Teleop stopped by user")

        except Exception as e:
            self._emit_log_safe(f"❌ Teleop failed: {e}")
            self._emit_error_safe(str(e))
        finally:
            self.running = False
            self.finished.emit()
            self._stopping = False

    def _create_teleop_instances(self) -> Tuple:
        """Create the appropriate teleoperator and robot instances based on arm_target."""
        robot_cfg = self.config.get("robot", {})
        teleop_cfg = self.config.get("teleop", {})

        if self.arm_target in ("left", "right"):
            # Single-arm teleop
            return self._create_single_arm_instances()
        else:
            # Bimanual teleop
            return self._create_bimanual_instances()

    def _create_single_arm_instances(self):
        """Create single-arm teleoperator and robot from config types."""
        arm_index = 0 if self.arm_target == "left" else 1

        teleop_cfg = (self.config.get("teleop", {}) or {}).get("arms", [])
        robot_cfg = (self.config.get("robot", {}) or {}).get("arms", [])
        teleop_arm = teleop_cfg[arm_index] if arm_index < len(teleop_cfg) else {}
        robot_arm = robot_cfg[arm_index] if arm_index < len(robot_cfg) else {}

        robot_port = get_arm_port(self.config, arm_index, "robot")
        teleop_port = get_arm_port(self.config, arm_index, "teleop")

        if not robot_port or not teleop_port:
            raise ValueError(f"Missing ports for {self.arm_target} arm teleop")

        teleop_type = (teleop_arm.get("type") or "SO100").upper()
        robot_type = (robot_arm.get("type") or "SO101").upper()
        teleop_id = teleop_arm.get("id") or f"{self.arm_target}_leader"
        robot_id = robot_arm.get("id") or f"{self.arm_target}_follower"

        teleop = self._build_leader(teleop_type, teleop_port, teleop_id)
        robot = self._build_follower(robot_type, robot_port, robot_id)

        return teleop, robot

    # ------------------------------------------------------------------
    # Safe signal helpers (queued to main thread)

    def _emit_log_safe(self, message: str) -> None:
        QMetaObject.invokeMethod(
            self, "_emit_log_slot", Qt.QueuedConnection, Q_ARG(str, message)
        )

    def _emit_error_safe(self, message: str) -> None:
        QMetaObject.invokeMethod(
            self, "_emit_error_slot", Qt.QueuedConnection, Q_ARG(str, message)
        )

    def _emit_log_slot(self, message: str) -> None:  # pragma: no cover - Qt slot
        try:
            self.log_message.emit(message)
        except Exception:
            pass

    def _emit_error_slot(self, message: str) -> None:  # pragma: no cover - Qt slot
        try:
            self.error.emit(message)
        except Exception:
            pass

    def _create_bimanual_instances(self):
        """Create bimanual teleoperator and robot honoring per-arm types."""
        teleop_cfg = (self.config.get("teleop", {}) or {}).get("arms", [])
        robot_cfg = (self.config.get("robot", {}) or {}).get("arms", [])

        if len(teleop_cfg) < 2 or len(robot_cfg) < 2:
            raise ValueError("Bimanual teleop requires two configured teleop and robot arms")

        left_teleop_type = (teleop_cfg[0].get("type") or "SO100").upper()
        right_teleop_type = (teleop_cfg[1].get("type") or "SO100").upper()
        left_robot_type = (robot_cfg[0].get("type") or "SO101").upper()
        right_robot_type = (robot_cfg[1].get("type") or "SO101").upper()

        left_teleop_port = get_arm_port(self.config, 0, "teleop")
        right_teleop_port = get_arm_port(self.config, 1, "teleop")
        left_robot_port = get_arm_port(self.config, 0, "robot")
        right_robot_port = get_arm_port(self.config, 1, "robot")

        if not all([left_teleop_port, right_teleop_port, left_robot_port, right_robot_port]):
            raise ValueError("Bimanual teleop requires 2 robot and 2 teleop ports")

        left_teleop = self._build_leader(
            left_teleop_type,
            left_teleop_port,
            teleop_cfg[0].get("id") or "left_leader",
        )
        right_teleop = self._build_leader(
            right_teleop_type,
            right_teleop_port,
            teleop_cfg[1].get("id") or "right_leader",
        )

        teleop_instance = None
        if left_teleop_type == right_teleop_type == "SO100":
            teleop_instance = lerobot.teleoperators.bi_so100_leader.BiSO100Leader(
                lerobot.teleoperators.bi_so100_leader.BiSO100LeaderConfig(
                    left_arm_port=left_teleop_port,
                    right_arm_port=right_teleop_port,
                    id="bimanual_leader_so100",
                )
            )

        left_robot = self._build_follower(
            left_robot_type,
            left_robot_port,
            robot_cfg[0].get("id") or "left_follower",
        )
        right_robot = self._build_follower(
            right_robot_type,
            right_robot_port,
            robot_cfg[1].get("id") or "right_follower",
        )

        if left_robot_type == right_robot_type == "SO100":
            robot_instance = lerobot.robots.bi_so100_follower.BiSO100Follower(
                lerobot.robots.bi_so100_follower.BiSO100FollowerConfig(
                    left_arm_port=left_robot_port,
                    right_arm_port=right_robot_port,
                    id="bimanual_follower_so100",
                )
            )
        else:
            robot_instance = CompositeBimanualRobot(left_robot, right_robot)

        if teleop_instance:
            return teleop_instance, robot_instance

        return (left_teleop, right_teleop), robot_instance

    def _build_leader(self, arm_type: str, port: str, arm_id: str):
        if arm_type == "SO100":
            cfg = lerobot.teleoperators.so100_leader.SO100LeaderConfig(port=port, id=arm_id)
            return lerobot.teleoperators.so100_leader.SO100Leader(cfg)
        if arm_type == "SO101":
            cfg = lerobot.teleoperators.so101_leader.SO101LeaderConfig(port=port, id=arm_id)
            return lerobot.teleoperators.so101_leader.SO101Leader(cfg)
        raise ValueError(f"Unsupported teleop arm type: {arm_type}")

    def _build_follower(self, arm_type: str, port: str, arm_id: str):
        if arm_type == "SO100":
            cfg = lerobot.robots.so100_follower.So100FollowerConfig(port=port, id=arm_id)
            return lerobot.robots.so100_follower.So100Follower(cfg)
        if arm_type == "SO101":
            cfg = lerobot.robots.so101_follower.So101FollowerConfig(port=port, id=arm_id)
            return lerobot.robots.so101_follower.So101Follower(cfg)
        raise ValueError(f"Unsupported robot arm type: {arm_type}")

    def _cleanup(self):
        """Clean up teleop and robot connections."""
        # Clean up teleoperators
        try:
            if hasattr(self, '_is_mixed_bimanual') and self._is_mixed_bimanual:
                # Mixed bimanual case
                if self.left_teleop and self.left_teleop.is_connected():
                    self.left_teleop.disconnect()
                if self.right_teleop and self.right_teleop.is_connected():
                    self.right_teleop.disconnect()
            elif self.teleop and self.teleop.is_connected():
                # Single teleoperator case
                self.teleop.disconnect()
        except Exception as e:
            self.log_message.emit(f"Warning: teleop disconnect failed: {e}")

        # Clean up robot
        try:
            if self.robot and self.robot.is_connected():
                self.robot.disconnect()
        except Exception as e:
            self.log_message.emit(f"Warning: robot disconnect failed: {e}")


class TeleopMode(QObject):
    """Global teleop mode state manager (speed override + status)."""

    changed = Signal(bool)

    _instance: Optional["TeleopMode"] = None

    def __init__(self) -> None:
        super().__init__()
        self._active = False
        self._saved_multiplier: Optional[float] = None
        self._state_store = AppStateStore.instance()
        self._suppress_state = False
        self._state_store.state_changed.connect(self._on_state_changed)

    @classmethod
    def instance(cls) -> "TeleopMode":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def active(self) -> bool:
        return self._active

    def enter(self, current_multiplier: float) -> None:
        if not self._active:
            self._saved_multiplier = current_multiplier
            self._active = True
            self._set_state("teleop.mode", True)
            self._set_state("control.speed_multiplier_locked", True)
            self._set_state("control.speed_multiplier", 1.0)
            self.changed.emit(True)

    def exit(self) -> Optional[float]:
        if not self._active:
            return None
        self._active = False
        self._set_state("teleop.mode", False)
        self._set_state("control.speed_multiplier_locked", False)
        self.changed.emit(False)
        saved = self._saved_multiplier
        self._saved_multiplier = None
        if saved is not None:
            self._set_state("control.speed_multiplier", saved)
        return saved

    # ------------------------------------------------------------------
    # State helpers

    def _set_state(self, key: str, value) -> None:
        self._suppress_state = True
        self._state_store.set_state(key, value)
        self._suppress_state = False

    def _on_state_changed(self, key: str, value) -> None:
        if self._suppress_state:
            return
        if self._active and key == "control.speed_multiplier" and value != 1.0:
            # Enforce override while in teleop mode
            self._set_state("control.speed_multiplier", 1.0)


class TeleopController(QObject):
    """Wrapper around lerobot teleop scripts with proper Qt integration."""

    status_changed = Signal(str)
    log_message = Signal(str)
    running_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self.process: Optional[QProcess] = None
        self._worker: Optional[ProgrammaticTeleopWorker] = None
        self._mode = TeleopMode.instance()
        self._state_store = AppStateStore.instance()
        self._state_store.set_state("teleop.running", False)
        self._state_store.set_state("teleop.status", "idle")
        self._preflight = TeleopPreflight(config)

    # ------------------------------------------------------------------
    # Helpers

    @staticmethod
    def is_jetson() -> bool:
        return JETSON_FLAG.exists()

    def _script_path(self, arm_mode: str) -> Path:
        if arm_mode in ("left", "right"):
            return REPO_ROOT / "run_single_teleop.sh"
        return REPO_ROOT / "run_bimanual_teleop.sh"

    def _required_ports(self) -> list[str]:
        ports: list[str] = []
        robot_cfg = self.config.get("robot", {}) or {}
        for idx, _ in enumerate(robot_cfg.get("arms", []) or []):
            port = get_arm_port(self.config, idx, "robot")
            if port:
                ports.append(port)
        teleop_cfg = self.config.get("teleop", {}) or {}
        for idx, _ in enumerate(teleop_cfg.get("arms", []) or []):
            port = get_arm_port(self.config, idx, "teleop")
            if port:
                ports.append(port)
        return ports

    def _check_permissions(self) -> bool:
        missing = [port for port in self._required_ports() if port and not os.access(port, os.R_OK | os.W_OK)]
        if missing:
            msg = (
                "Teleop requires read/write access to leader/follower serial ports.\n"
                f"Fix permissions for: {', '.join(missing)} (udev rules recommended)."
            )
            self._emit_error(msg)
            log_exception("TeleopController: missing port permissions", RuntimeError(msg))
            return False
        return True
    def _emit_status(self, message: str) -> None:
        """Emit status signal and share state globally."""

        self.status_changed.emit(message)
        self._state_store.set_state("teleop.status", message)

    def _emit_error(self, message: str) -> None:
        """Emit error signal and persist last error info."""

        self.error_occurred.emit(message)
        self._state_store.set_state("teleop.last_error", message)
        self._state_store.set_state("teleop.status", message)

    def _set_running(self, running: bool) -> None:
        """Publish running state consistently."""

        self.running_changed.emit(running)
        self._state_store.set_state("teleop.running", running)

    # ------------------------------------------------------------------
    # Public API

    def start(self, arm_mode: str = "both") -> bool:
        if self._worker and self._worker.isRunning():
            self._emit_status("Teleop already running.")
            return False

        arm_mode = arm_mode if arm_mode in ("left", "right", "both") else "both"

        if not self._check_permissions():
            return False

        if not self.is_jetson():
            msg = "Teleop available only on the Jetson device."
            self._emit_error(msg)
            return False

        if not self._preflight.prepare(arm_mode):
            self._emit_error("Teleop preflight failed — check serial connections and try again.")
            return False

        # Programmatic teleop optional (disabled unless explicitly enabled)
        if PROGRAMMATIC_TELEOP_ENABLED:
            return self._start_programmatic(arm_mode)

        safe_print("[TeleopController] Programmatic teleop disabled; using script path.")
        return self._start_script_based(arm_mode)

    def _start_programmatic(self, arm_mode: str) -> bool:
        """Start teleop using programmatic lerobot API."""
        self._emit_status(f"Starting programmatic {arm_mode} teleop…")

        try:
            self._worker = ProgrammaticTeleopWorker(self.config, arm_mode)
            self._worker.log_message.connect(self.log_message)
            self._worker.error.connect(self.error_occurred)
            self._worker.finished.connect(self._handle_worker_finished)

            self._worker.start()
            self._set_running(True)
            safe_print(f"[TeleopController] Programmatic {arm_mode} teleop started")
            return True

        except Exception as e:
            safe_print(f"[TeleopController] Programmatic teleop failed, falling back to script: {e}")
            return self._start_script_based(arm_mode)

    def _start_script_based(self, arm_mode: str) -> bool:
        """Fallback: Start teleop using external scripts."""
        if not self.is_jetson():
            msg = "Teleop available only on the Jetson device."
            self._emit_error(msg)
            return False

        script = self._script_path(arm_mode)
        if not script.exists():
            msg = f"Teleop script missing: {script}"
            self._emit_error(msg)
            return False

        self._emit_status("Starting teleop…")
        self.process = QProcess(self)
        self.process.setProgram(str(script))
        self.process.setArguments([])
        self.process.setWorkingDirectory(str(script.parent))
        env = QProcessEnvironment.systemEnvironment()
        env.insert("AUTO_ACCEPT_CALIBRATION", "1")
        if arm_mode in ("left", "right"):
            env.insert("TARGET_ARM", arm_mode)
        self.process.setProcessEnvironment(env)
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self._handle_finished)
        self.process.start()
        self._set_running(True)
        safe_print("[TeleopController] Script-based teleop process started")
        return True

    def stop(self) -> None:
        # Stop programmatic worker if running
        if self._worker and self._worker.isRunning():
            self._emit_status("Stopping teleop…")
            try:
                self._worker.stop()
                if not self._worker.wait(3000):
                    self._worker.terminate()
                    self._worker.wait(1000)
            finally:
                self._worker = None
                self._set_running(False)
                safe_print("[TeleopController] Programmatic teleop stopped")
            return

        # Stop script-based process if running
        if not self.process:
            return
        self._emit_status("Stopping teleop…")
        if self.process.state() != QProcess.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(5000):
                self.process.kill()
        self.process = None
        self._set_running(False)
        safe_print("[TeleopController] Script-based teleop stopped")

    def is_running(self) -> bool:
        # Check programmatic worker
        if self._worker and self._worker.isRunning():
            return True
        # Check script-based process
        return bool(self.process and self.process.state() != QProcess.NotRunning)

    # ------------------------------------------------------------------
    # Slots

    def _handle_stdout(self) -> None:  # pragma: no cover - requires teleop hardware
        if not self.process:
            return
        text = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="ignore").strip()
        if text:
            self.log_message.emit(text)

    def _handle_stderr(self) -> None:  # pragma: no cover - requires teleop hardware
        if not self.process:
            return
        text = bytes(self.process.readAllStandardError()).decode("utf-8", errors="ignore").strip()
        if text:
            self.log_message.emit(text)

    def _handle_finished(self, exit_code: int, status: QProcess.ExitStatus) -> None:
        msg = "Teleop session finished." if exit_code == 0 and status == QProcess.NormalExit else "Teleop exited unexpectedly."
        self._emit_status(msg)
        self._set_running(False)
        self.process = None
        # Auto-exit teleop mode when process ends
        restored = self._mode.exit()
        if restored is not None:
            self._state_store.set_state("control.speed_multiplier", restored)

    def _handle_worker_finished(self) -> None:
        """Handle completion of programmatic teleop worker."""
        self._emit_status("Teleop session finished.")
        self._set_running(False)
        self._worker = None
        # Auto-exit teleop mode when worker ends
        restored = self._mode.exit()
        if restored is not None:
            self._state_store.set_state("control.speed_multiplier", restored)
