#!/usr/bin/env python3
"""
QThread worker for managing LeRobot async inference (policy server + robot client).
Handles command building, process management, and error parsing.
"""

import json
import re
import signal
import socket
import subprocess
import sys
import time
import threading
from typing import List, Optional

from PySide6.QtCore import QThread, Signal, Slot

from utils.motor_controller import MotorController


class RobotWorker(QThread):
    """Worker thread that runs LeRobot async inference (policy server + robot client)"""
    
    # Signals for UI updates
    status_update = Signal(str)           # Current action/status text
    log_message = Signal(str, str)        # (level, message) - level: 'info', 'warning', 'error'
    progress_update = Signal(int, int)    # (current_episode, total_episodes)
    error_occurred = Signal(str, dict)    # (error_key, context_dict)
    run_completed = Signal(bool, str)     # (success, summary_message)
    connection_changed = Signal(bool)     # (connected)
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.server_proc = None  # Policy server process
        self.client_proc = None  # Robot client process
        self._stop_requested = False
        self.motor_controller: Optional[MotorController] = None
        try:
            self.motor_controller = MotorController(config)
        except Exception as exc:  # pragma: no cover - hardware dependent
            print(f"[ROBOT_WORKER] Motor controller unavailable: {exc}")

        safety_cfg = self.config.get("safety", {})
        self._hold_enabled = bool(safety_cfg.get("hand_hold_position", True))
        self._resume_delay = float(safety_cfg.get("hand_resume_delay_s", 0.5))
        self._safety_paused = False
        self._resume_cancel_event = threading.Event()
        self._hold_loop_event: Optional[threading.Event] = None
        self._hold_thread: Optional[threading.Thread] = None
        self._hold_positions: Optional[List[int]] = None
        self._hold_lock = threading.Lock()
        self._hold_error_reported = False
        
    def run(self):
        """Main worker thread execution - async inference (server + client)"""
        self._stop_requested = False
        self._safety_paused = False
        self._resume_cancel_event = threading.Event()
        self._stop_hold_loop()

        try:
            # Step 1: Start policy server
            self.log_message.emit('info', "Starting policy server...")
            self.status_update.emit("Starting policy server...")

            server_args = self._build_server_command()
            async_cfg = self.config.get("async_inference", {})
            server_host = async_cfg.get("server_host", "127.0.0.1")
            server_port = async_cfg.get("server_port", 8080)
            self.server_proc = subprocess.Popen(
                server_args,
                stdout=subprocess.DEVNULL,  # Don't capture - prevents pipe deadlock
                stderr=subprocess.DEVNULL,  # Don't capture - prevents pipe deadlock
                text=True,
                bufsize=1
            )

            # Wait for server to be ready (fail fast if it crashes)
            self._wait_for_server_ready(server_host, server_port)
            self.log_message.emit('info', "Policy server ready")

            # Step 2: Start robot client
            self.log_message.emit('info', "Starting robot client...")
            self.status_update.emit("Connecting to robot...")

            client_args = self._build_client_command()
            self.log_message.emit('info', f"Launching client: {' '.join(client_args)}")

            self.client_proc = subprocess.Popen(
                client_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Merge stderr into stdout - prevents pipe deadlock
                text=True,
                bufsize=1
            )

            if self.client_proc.poll() is not None:
                raise RuntimeError("Robot client failed to start")
            
            self.connection_changed.emit(True)
            self.status_update.emit("Robot running...")
            
            # Monitor client process output
            self._monitor_process()
            
        except FileNotFoundError as e:
            self.error_occurred.emit('lerobot_not_found', {'error': str(e)})
            self.run_completed.emit(False, "LeRobot not found")
        except ValueError as e:
            self.error_occurred.emit('config_error', {'error': str(e)})
            self.run_completed.emit(False, str(e))
        except RuntimeError as e:
            self.error_occurred.emit('startup_failed', {'error': str(e)})
            self.run_completed.emit(False, str(e))
        except Exception as e:
            self.error_occurred.emit('unknown', {'error': str(e)})
            self.run_completed.emit(False, f"Failed to start: {e}")
        finally:
            self._stop_hold_loop()
            self._cleanup_processes()
            self.connection_changed.emit(False)

    def _capture_hold_positions(self):  # pragma: no cover - hardware dependent
        if not (self.motor_controller and self._hold_enabled):
            return

        try:
            if not self.motor_controller.bus:
                if not self.motor_controller.connect():
                    self.log_message.emit('warning', "[SAFETY] Could not connect to motors for hold")
                    return

            positions = self.motor_controller.read_positions_from_bus()
            if not positions:
                self.log_message.emit('warning', "[SAFETY] Failed to read positions for hold")
                return

            with self._hold_lock:
                self._hold_positions = list(positions)
                self._hold_error_reported = False

            for name in self.motor_controller.motor_names:
                self.motor_controller.bus.write("Torque_Enable", name, 1, normalize=False)

        except Exception as exc:
            self.log_message.emit('warning', f"[SAFETY] Hold capture error: {exc}")

    def _start_hold_loop(self):  # pragma: no cover - hardware dependent
        if not (self.motor_controller and self._hold_enabled):
            return
        if self._hold_thread and self._hold_thread.is_alive():
            return

        self._hold_loop_event = threading.Event()
        self._hold_loop_event.set()

        def _loop():
            while (
                self._hold_loop_event
                and self._hold_loop_event.is_set()
                and not self._stop_requested
            ):
                self._reapply_hold_positions()
                time.sleep(0.1)

        self._hold_thread = threading.Thread(target=_loop, daemon=True)
        self._hold_thread.start()

    def _reapply_hold_positions(self):  # pragma: no cover - hardware dependent
        if not self.motor_controller or not self.motor_controller.bus:
            return

        with self._hold_lock:
            positions = list(self._hold_positions) if self._hold_positions else None

        if not positions:
            return

        try:
            for idx, name in enumerate(self.motor_controller.motor_names):
                self.motor_controller.bus.write("Goal_Position", name, positions[idx], normalize=False)
        except Exception as exc:
            if not self._hold_error_reported:
                self.log_message.emit('warning', f"[SAFETY] Hold maintain error: {exc}")
                self._hold_error_reported = True

    def _stop_hold_loop(self):  # pragma: no cover - hardware dependent
        if self._hold_loop_event:
            self._hold_loop_event.clear()
        if self._hold_thread and self._hold_thread.is_alive():
            self._hold_thread.join(timeout=0.5)
        self._hold_thread = None
        self._hold_loop_event = None
        with self._hold_lock:
            self._hold_positions = None
        self._hold_error_reported = False

    @Slot()
    def handle_hand_detected(self):
        if self._stop_requested or self._safety_paused:
            return

        self._resume_cancel_event.set()
        self._safety_paused = True
        self.log_message.emit('warning', "[SAFETY] Hand detected — pausing async inference")
        self.status_update.emit("⚠️ Hand detected — pausing")

        if self.client_proc and self.client_proc.poll() is None:
            try:
                self.client_proc.send_signal(signal.SIGSTOP)
            except Exception as exc:  # pragma: no cover - process control
                self.log_message.emit('warning', f"[SAFETY] Failed to pause client: {exc}")

        self._capture_hold_positions()
        self._start_hold_loop()

    @Slot()
    def handle_hand_cleared(self):
        if not self._safety_paused:
            return

        self._resume_cancel_event.set()
        resume_event = threading.Event()
        self._resume_cancel_event = resume_event

        self.log_message.emit('info', "[SAFETY] Hand cleared — resuming soon")
        self.status_update.emit("Hand cleared — resuming")

        def _resume_after_delay():
            waited = 0.0
            step = 0.05
            target = max(0.0, self._resume_delay)
            while waited < target and not resume_event.is_set() and not self._stop_requested:
                time.sleep(step)
                waited += step

            if resume_event.is_set() or self._stop_requested:
                return

            self._stop_hold_loop()
            if self.client_proc and self.client_proc.poll() is None:
                try:
                    self.client_proc.send_signal(signal.SIGCONT)
                except Exception as exc:  # pragma: no cover - process control
                    self.log_message.emit('warning', f"[SAFETY] Failed to resume client: {exc}")

            self._safety_paused = False
            self.status_update.emit("Resumed")
            self.log_message.emit('info', "[SAFETY] Safety pause cleared")

        threading.Thread(target=_resume_after_delay, daemon=True).start()

    def force_release_safety_pause(self):
        self._resume_cancel_event.set()
        self._stop_hold_loop()
        if self._safety_paused and self.client_proc and self.client_proc.poll() is None:
            try:
                self.client_proc.send_signal(signal.SIGCONT)
            except Exception:
                pass
        self._safety_paused = False
    def _build_server_command(self):
        """Build policy server command"""
        # Server just needs host and port
        server_host = self.config.get("async_inference", {}).get("server_host", "127.0.0.1")
        server_port = self.config.get("async_inference", {}).get("server_port", 8080)
        
        args = [
            sys.executable, "-m", "lerobot.async_inference.policy_server",
            f"--host={server_host}",
            f"--port={server_port}"
        ]
        
        return args
    
    def _build_client_command(self):
        """Build robot client command from config"""
        r = self.config.get("robot", {})
        p = self.config.get("policy", {})
        cams = self.config.get("cameras", {})
        async_cfg = self.config.get("async_inference", {})
        
        # Validate required robot configuration
        if not isinstance(r, dict):
            raise ValueError("Robot configuration missing or invalid")

        robot_type = r.get("type")
        robot_port = r.get("port")
        robot_id = r.get("id", "follower_arm")

        if not robot_type:
            raise ValueError("Robot type not configured")
        if not robot_port:
            raise ValueError("Robot port not configured")

        # Build camera dict string
        camera_dict = self._build_camera_dict(cams)

        # Server address
        server_host = async_cfg.get("server_host", "127.0.0.1")
        server_port = async_cfg.get("server_port", 8080)
        server_address = f"{server_host}:{server_port}"

        # Validate policy configuration
        pretrained_path = p.get("path") if isinstance(p, dict) else None
        if not pretrained_path:
            raise ValueError("Policy path not configured")

        args = [
            sys.executable, "-m", "lerobot.async_inference.robot_client",
            f"--server_address={server_address}",
            "--robot.type", robot_type,
            "--robot.port", robot_port,
            "--robot.id", robot_id,
            f"--robot.cameras={camera_dict}",
            "--policy_type", async_cfg.get("policy_type", "act"),
            f"--pretrained_name_or_path={pretrained_path}",
            "--policy_device", p.get("device", "cpu") if isinstance(p, dict) else "cpu",
            "--actions_per_chunk", str(async_cfg.get("actions_per_chunk", 30)),
            "--chunk_size_threshold", str(async_cfg.get("chunk_size_threshold", 0.6)),
            "--debug_visualize_queue_size=False"
        ]

        return args

    def _build_camera_dict(self, cameras):
        """Build camera dictionary string for command line"""
        if not cameras:
            return "{}"

        # Format: { front: {type: opencv, index_or_path: "/dev/video0", ...}, wrist: {...} }
        cam_parts = []
        for name, cfg in cameras.items():
            index_or_path = cfg.get("index_or_path", 0)
            # Quote strings so Hydra/YAML parsing is reliable, but keep numeric
            # indices unquoted for convenience.
            if isinstance(index_or_path, str) and index_or_path.isdigit():
                path_str = index_or_path
            elif isinstance(index_or_path, str):
                path_str = json.dumps(index_or_path)
            else:
                path_str = str(index_or_path)

            cam_type = cfg.get("type", "opencv")

            cam_str = (
                f"{name}: {{type: {cam_type}, index_or_path: {path_str}, "
                f"width: {cfg.get('width', 640)}, height: {cfg.get('height', 480)}, "
                f"fps: {cfg.get('fps', 30)}}}"
            )
            cam_parts.append(cam_str)

        return "{ " + ", ".join(cam_parts) + " }"

    def _monitor_process(self):
        """Monitor robot client subprocess output and parse for status/errors"""
        output_buffer = []  # Capture all output (stdout + stderr merged)
        current_episode = 0
        total_episodes = 1  # Async inference runs continuously

        try:
            if not self.client_proc or not self.client_proc.stdout:
                raise RuntimeError("Robot client process not started correctly")

            # Read client stdout line by line (stderr is merged in)
            if not self.client_proc or not self.client_proc.stdout:
                raise RuntimeError("Robot client stdout is unavailable")

            for line in self.client_proc.stdout:
                line = line.rstrip()
                if not line:
                    continue

                # Save all output for error parsing
                output_buffer.append(line)
                # Prevent unbounded memory growth - keep latest 1000 lines
                if len(output_buffer) > 1000:
                    output_buffer.pop(0)
                    

                self.log_message.emit('info', line)
                
                # Parse for episode progress
                episode_match = re.search(r'episode[:\s]+(\d+)', line, re.IGNORECASE)
                if episode_match:
                    current_episode = int(episode_match.group(1))
                    self.progress_update.emit(current_episode, total_episodes)
                    self.status_update.emit(f"Recording Episode {current_episode}/{total_episodes}")
                
                # Parse for status keywords
                if 'warmup' in line.lower():
                    self.status_update.emit("Warming up...")
                elif 'reset' in line.lower() or 'rest' in line.lower():
                    self.status_update.emit("Returning Home...")
                elif 'recording' in line.lower():
                    self.status_update.emit(f"Recording Episode {current_episode}/{total_episodes}")
                
            # Wait for client to complete
            return_code = self.client_proc.wait()
            
            # Check results
            if self._stop_requested:
                self.log_message.emit('warning', "Stopped by user")
                self.run_completed.emit(False, "Stopped by user")
            elif return_code == 0:
                self.log_message.emit('info', "✓ Run completed successfully")
                self.run_completed.emit(True, f"Completed {total_episodes} episodes")
            else:
                # Parse errors from captured output
                output_text = '\n'.join(output_buffer)
                error_key, context = self._parse_error(output_text, return_code)
                self.error_occurred.emit(error_key, context)
                self.log_message.emit('error', f"Process exited with code {return_code}")
                if output_text:
                    self.log_message.emit('error', output_text)
                self.run_completed.emit(False, f"Failed with code {return_code}")
                
        except Exception as e:
            self.log_message.emit('error', f"Monitor error: {e}")
            self.run_completed.emit(False, str(e))
        finally:
            if self.client_proc and self.client_proc.stdout:
                try:
                    self.client_proc.stdout.close()
                except Exception:
                    pass
            
    def _parse_error(self, stderr_text, return_code):
        """Parse stderr to determine error type"""
        stderr_lower = stderr_text.lower()
        
        robot_cfg = self.config.get("robot", {})
        cameras_cfg = self.config.get("cameras", {})

        # Serial permission error
        if 'permission denied' in stderr_lower and '/dev/tty' in stderr_lower:
            port = robot_cfg.get("port", "unknown")
            return 'serial_permission', {'port': port, 'stderr': stderr_text}

        # Serial not found
        if 'no such file or directory' in stderr_lower and '/dev/tty' in stderr_lower:
            port = robot_cfg.get("port", "unknown")
            return 'serial_not_found', {'port': port, 'stderr': stderr_text}

        # Port busy
        if 'device or resource busy' in stderr_lower and '/dev/tty' in stderr_lower:
            port = robot_cfg.get("port", "unknown")
            return 'serial_busy', {'port': port, 'stderr': stderr_text}

        # Camera error
        if 'could not open camera' in stderr_lower or 'videoio' in stderr_lower:
            cameras_cfg = self.config.get("cameras", {})
            first_name, first_camera = next(iter(cameras_cfg.items()), ("unknown", {}))
            cam_idx = first_camera.get("index_or_path", "unknown")
            return 'camera_not_found', {
                'camera': first_name,
                'index': cam_idx,
                'stderr': stderr_text
            }


        # Servo timeout (specific motor)
        servo_match = re.search(r'motor[:\s]+(\d+)', stderr_lower)
        if servo_match and ('timeout' in stderr_lower or 'not respond' in stderr_lower):
            motor_id = int(servo_match.group(1))
            return 'servo_timeout', {'motor_id': motor_id, 'stderr': stderr_text}
            
        # Power loss (unexpected exit)
        if return_code < 0 or return_code == 137:  # Killed or SIGKILL
            return 'power_loss', {'return_code': return_code, 'stderr': stderr_text}
            
        # Policy not found
        if 'no such file or directory' in stderr_lower and 'checkpoint' in stderr_lower:
            policy_path = self.config.get("policy", {}).get("path", "unknown")
            return 'policy_not_found', {'path': policy_path, 'stderr': stderr_text}
            
        # Generic error
        return 'unknown', {'stderr': stderr_text, 'return_code': return_code}
        
    def _cleanup_processes(self):
        """Stop both server and client processes - FAST for emergency stops"""
        # Stop client first (FAST - we need the serial port released ASAP)
        if self.client_proc:
            try:
                self.client_proc.send_signal(signal.SIGINT)
                self.client_proc.wait(timeout=1)  # Reduced from 5s to 1s for emergency
            except subprocess.TimeoutExpired:
                self.client_proc.terminate()
                try:
                    self.client_proc.wait(timeout=0.5)  # Reduced from 2s to 0.5s
                except subprocess.TimeoutExpired:
                    self.client_proc.kill()  # Force kill if still not dead
            except:
                pass
            finally:
                if self.client_proc and self.client_proc.stdout:
                    try:
                        self.client_proc.stdout.close()
                    except Exception:
                        pass
                self.client_proc = None
        
        # Then stop server
        if self.server_proc:
            try:
                self.server_proc.send_signal(signal.SIGINT)
                self.server_proc.wait(timeout=1)  # Reduced from 3s to 1s
            except subprocess.TimeoutExpired:
                self.server_proc.terminate()
                try:
                    self.server_proc.wait(timeout=0.5)  # Reduced from 2s to 0.5s
                except subprocess.TimeoutExpired:
                    self.server_proc.kill()  # Force kill
            except:
                pass
            finally:
                self.server_proc = None
    
    def stop(self):
        """Request worker to stop - stop both server and client"""
        self._stop_requested = True
        self.force_release_safety_pause()
        self._cleanup_processes()

    def _wait_for_server_ready(self, host, port, timeout=5.0):
        """Wait until the policy server accepts TCP connections.

        Raises:
            RuntimeError: If the server process exits before becoming ready.
            TimeoutError: If the server does not become ready within timeout.
        """

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.server_proc and self.server_proc.poll() is not None:
                raise RuntimeError("Policy server exited unexpectedly")

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.2)
                try:
                    sock.connect((host, port))
                except (ConnectionRefusedError, OSError, socket.timeout):
                    time.sleep(0.1)
                    continue
                else:
                    return

        raise TimeoutError("Timed out waiting for policy server to become ready")

