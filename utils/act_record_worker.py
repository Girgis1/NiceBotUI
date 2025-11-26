"""Worker thread for recording single ACT dataset episodes via ``lerobot-record``.

This is intentionally focused on the Train tab:
- It records **one episode per run** with ``--dataset.num_episodes=1``.
- TrainTab is responsible for looping over episodes and updating metadata.
"""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, List, Tuple

from PySide6.QtCore import QThread, Signal

from utils.config_compat import get_first_enabled_arm


class ActRecordWorker(QThread):
    """Run ``lerobot-record`` once to capture a single episode.

    The worker is parameterised by a dataset repo id and episode settings.
    TrainTab drives higher-level episode counting and metadata; this worker
    just reports status/logs and whether the call succeeded.
    """

    status_update = Signal(str)          # Human-friendly status line
    log_message = Signal(str, str)       # (level, message)
    episode_progress = Signal(int, int)  # (current_episode_index, target_episodes)
    completed = Signal(bool, str)        # (success, summary)

    def __init__(
        self,
        config: Dict,
        *,
        repo_id: str,
        single_task: str,
        episode_index: int,
        target_episodes: int,
        episode_time_s: int,
        arm_mode: str = "bimanual",  # "left", "right", "bimanual"
        resume: bool = True,
        display_data: bool = False,
    ) -> None:
        super().__init__()
        self.config = config
        self.repo_id = repo_id
        self.single_task = single_task
        self.episode_index = max(1, int(episode_index))
        self.target_episodes = max(self.episode_index, int(target_episodes))
        self.episode_time_s = max(1, int(episode_time_s))
        self.arm_mode = arm_mode or "bimanual"
        self.resume = bool(resume)
        self.display_data = bool(display_data)

        self._stop_requested = False
        self._process: subprocess.Popen | None = None

    # ------------------------------------------------------------------ utils
    @staticmethod
    def _infer_bimanual_robot_type(left_type: str, right_type: str) -> str:
        left = (left_type or "").lower()
        right = (right_type or left).lower()
        if "so101" in left and "so101" in right:
            return "bi_so101_follower"
        return "bi_so100_follower"

    @staticmethod
    def _infer_bimanual_leader_type(left_type: str, right_type: str) -> str:
        left = (left_type or "").lower()
        right = (right_type or left).lower()
        if "so101" in left and "so101" in right:
            return "bi_so101_leader"
        return "bi_so100_leader"

    @staticmethod
    def _build_camera_dict(cameras: Dict) -> str:
        """Build the ``--robot.cameras={...}`` string.

        Mirrors the robust quoting logic used in RobotWorker.
        """
        if not cameras:
            return "{}"

        parts: List[str] = []
        for name, cfg in cameras.items():
            index_or_path = cfg.get("index_or_path", cfg.get("path", "/dev/video0"))
            if isinstance(index_or_path, str) and index_or_path.isdigit():
                path_str = index_or_path
            elif isinstance(index_or_path, str):
                # JSON-encode arbitrary strings (handles spaces, special chars)
                import json as _json

                path_str = _json.dumps(index_or_path)
            else:
                path_str = str(index_or_path)

            cam_type = cfg.get("type", "opencv")
            width = cfg.get("width", 640)
            height = cfg.get("height", 480)
            fps = cfg.get("fps", 30)

            part = (
                f"{name}: {{type: {cam_type}, index_or_path: {path_str}, "
                f"width: {width}, height: {height}, fps: {fps}}}"
            )
            parts.append(part)

        return "{ " + ", ".join(parts) + " }"

    # ------------------------------------------------------------------ QThread
    def run(self) -> None:  # type: ignore[override]
        self._stop_requested = False

        try:
            cmd, lerobot_dir = self._build_command()
        except Exception as exc:
            self.log_message.emit("error", f"Failed to build lerobot-record command: {exc}")
            self.completed.emit(False, "Command build failed")
            return

        cmd_display = " ".join(cmd)
        self.log_message.emit("info", f"[ACT] Starting episode {self.episode_index}/{self.target_episodes}")
        self.log_message.emit("info", f"[ACT] lerobot-record: {cmd_display}")
        self.status_update.emit(f"Recording ep {self.episode_index}/{self.target_episodes}…")
        self.episode_progress.emit(self.episode_index, self.target_episodes)

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(lerobot_dir),
            )
            self._process = process
        except FileNotFoundError as exc:
            self.log_message.emit("error", f"lerobot-record not found: {exc}")
            self.completed.emit(False, "lerobot-record CLI not available")
            return
        except Exception as exc:
            self.log_message.emit("error", f"Failed to start lerobot-record: {exc}")
            self.completed.emit(False, "lerobot-record startup failed")
            return

        output_lines: List[str] = []

        def read_output() -> None:
            try:
                assert process.stdout is not None
                for line in iter(process.stdout.readline, ""):
                    if not line:
                        break
                    line = line.rstrip()
                    output_lines.append(line)

                    # Surface key information into the GUI log
                    if "Recording episode" in line:
                        self.log_message.emit("info", f"[lerobot] {line}")
                        self.status_update.emit(
                            f"Recording ep {self.episode_index}/{self.target_episodes}…"
                        )
                    elif "ERROR" in line or "Error" in line:
                        self.log_message.emit("error", f"[lerobot] {line}")
                    elif "INFO" in line or "Info" in line:
                        # Keep info logs, but avoid spamming every line
                        self.log_message.emit("info", f"[lerobot] {line}")
            except Exception as exc:
                self.log_message.emit("warning", f"Output reading error: {exc}")
            finally:
                if process.stdout:
                    try:
                        process.stdout.close()
                    except Exception:
                        pass

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()

        # Run for episode_time_s + small buffer
        total_time = self.episode_time_s + 10
        start_time = time.time()

        while True:
            if self._stop_requested:
                self.log_message.emit("warning", "Stopping lerobot-record by user request…")
                break

            if process.poll() is not None:
                break

            elapsed = time.time() - start_time
            if elapsed >= total_time:
                self.log_message.emit("warning", "Episode timeout reached, stopping process…")
                break

            time.sleep(0.5)

        # If still running, ask it to terminate
        if process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.log_message.emit("warning", "Force killing lerobot-record…")
                process.kill()
                process.wait()
            except Exception as exc:
                self.log_message.emit("warning", f"Error while stopping lerobot-record: {exc}")

        reader.join(timeout=2)
        exit_code = process.returncode

        if self._stop_requested:
            self.status_update.emit("Recording stopped")
            self.completed.emit(False, "Episode stopped by user")
            return

        if exit_code == 0:
            self.log_message.emit(
                "info",
                f"✓ Episode {self.episode_index}/{self.target_episodes} completed successfully",
            )
            self.status_update.emit(
                f"✓ Episode {self.episode_index}/{self.target_episodes} saved"
            )
            self.completed.emit(True, "Episode completed")
        else:
            self.log_message.emit(
                "error",
                f"lerobot-record failed with exit code {exit_code}",
            )
            # Print last few lines to stdout for debugging
            for line in output_lines[-10:]:
                print(f"[lerobot] {line}")
            self.status_update.emit("Recording failed")
            self.completed.emit(False, f"Episode failed (exit {exit_code})")

    # ------------------------------------------------------------------ helpers
    def _build_command(self) -> Tuple[List[str], Path]:
        """Construct the lerobot-record command and working directory."""
        robot_cfg = self.config.get("robot", {}) or {}
        cameras = self.config.get("cameras", {}) or {}
        teleop_cfg = self.config.get("teleop", {}) or {}

        camera_str = self._build_camera_dict(cameras)

        # Base dataset arguments
        cmd: List[str] = [
            "lerobot-record",
            f"--dataset.repo_id={self.repo_id}",
            f'--dataset.single_task={self.single_task}',
            "--dataset.num_episodes=1",
            f"--dataset.episode_time_s={self.episode_time_s}",
            "--dataset.push_to_hub=false",
            f"--display_data={'true' if self.display_data else 'false'}",
            f"--resume={'true' if self.resume else 'false'}",
        ]

        robot_ports_to_check: List[str] = []
        teleop_ports_to_check: List[str] = []

        # Robot arguments (solo left/right vs bimanual)
        arms = [arm for arm in robot_cfg.get("arms", []) if arm.get("enabled", True)]
        mode = self.arm_mode or "bimanual"

        if mode == "bimanual":
            if len(arms) < 2:
                raise ValueError("Bimanual mode requires two enabled robot arms")
            left_arm, right_arm = arms[0], arms[1]
            left_port = left_arm.get("port")
            right_port = right_arm.get("port")
            if not left_port or not right_port:
                raise ValueError("Bimanual mode requires both robot arm ports configured")
            robot_ports_to_check.extend([left_port, right_port])
            robot_type = self._infer_bimanual_robot_type(
                left_arm.get("type", ""),
                right_arm.get("type", left_arm.get("type", "")),
            )
            robot_id = robot_cfg.get("id", "bimanual_follower")
            cmd += [
                f"--robot.type={robot_type}",
                f"--robot.left_arm_port={left_port}",
                f"--robot.right_arm_port={right_port}",
                f"--robot.id={robot_id}",
            ]
        else:
            # Solo left/right: pick index 0 for left, 1 for right (if available)
            index = 0 if mode == "left" else 1
            if index >= len(arms):
                # Fall back to first enabled arm
                arm = get_first_enabled_arm(self.config, "robot")
            else:
                arm = arms[index]

            if not arm:
                raise ValueError("No enabled robot arm configured")

            robot_type = arm.get("type", robot_cfg.get("type", "so100_follower"))
            robot_port = arm.get("port", robot_cfg.get("port", "/dev/ttyACM0"))
            robot_id = arm.get("id", "follower_arm")
            if not robot_port:
                raise ValueError("Robot port is not configured")
            robot_ports_to_check.append(robot_port)
            cmd += [
                f"--robot.type={robot_type}",
                f"--robot.port={robot_port}",
                f"--robot.id={robot_id}",
            ]

        cmd.append(f"--robot.cameras={camera_str}")

        # Teleop arguments (optional but strongly recommended)
        teleop_arms = [arm for arm in teleop_cfg.get("arms", []) if arm.get("enabled", True)]
        teleop_mode = mode  # match UI arm_mode by default
        teleop_id = teleop_cfg.get("id", "leader")

        if teleop_mode == "bimanual":
            if len(teleop_arms) < 2:
                raise ValueError("Bimanual teleop requires two enabled leader arms")
            left_leader, right_leader = teleop_arms[0], teleop_arms[1]
            left_port = left_leader.get("port")
            right_port = right_leader.get("port")
            if not left_port or not right_port:
                raise ValueError("Both leader arms must have ports configured for bimanual teleop")
            teleop_ports_to_check.extend([left_port, right_port])
            teleop_type = self._infer_bimanual_leader_type(
                left_leader.get("type", ""),
                right_leader.get("type", left_leader.get("type", "")),
            )
            cmd += [
                f"--teleop.type={teleop_type}",
                f"--teleop.left_arm_port={left_port}",
                f"--teleop.right_arm_port={right_port}",
                f"--teleop.id={teleop_id}",
            ]
        else:
            # Solo left/right teleop: mirror robot side if we can
            index = 0 if teleop_mode == "left" else 1
            teleop_arm = None
            if index < len(teleop_arms):
                teleop_arm = teleop_arms[index]
            elif teleop_arms:
                teleop_arm = teleop_arms[0]

            if teleop_arm:
                teleop_type = teleop_arm.get("type", teleop_cfg.get("type", "so100_leader"))
                teleop_port = teleop_arm.get("port", teleop_cfg.get("port", "/dev/ttyACM1"))
                teleop_id = teleop_arm.get("id", teleop_id)
                if teleop_port:
                    teleop_ports_to_check.append(teleop_port)
                    cmd += [
                        f"--teleop.type={teleop_type}",
                        f"--teleop.port={teleop_port}",
                        f"--teleop.id={teleop_id}",
                    ]

        # Port sanity checks
        for label, port in (
            [(f"Robot arm {i+1}", p) for i, p in enumerate(robot_ports_to_check)]
            + [(f"Leader arm {i+1}", p) for i, p in enumerate(teleop_ports_to_check)]
        ):
            if not port:
                continue
            dev = Path(port)
            if not dev.exists():
                raise ValueError(f"{label} port not found: {port}")

        # lerobot working directory
        lerobot_dir = Path.home() / "lerobot"
        if not lerobot_dir.exists():
            # Fallback used in existing execution manager
            lerobot_dir = Path("/home/daniel/lerobot")

        return cmd, lerobot_dir

    def request_stop(self) -> None:
        """Signal the worker to stop and terminate the subprocess."""
        self._stop_requested = True
        proc = self._process
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass


__all__ = ["ActRecordWorker"]

