#!/usr/bin/env python3
"""
QThread worker for managing LeRobot async inference (policy server + robot client).
Handles command building, process management, and error parsing.
"""

import json
import subprocess
import sys
import signal
import re
import time
from pathlib import Path
from PySide6.QtCore import QThread, Signal


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
        
    def run(self):
        """Main worker thread execution - async inference (server + client)"""
        self._stop_requested = False
        
        try:
            # Step 1: Start policy server
            self.log_message.emit('info', "Starting policy server...")
            self.status_update.emit("Starting policy server...")
            
            server_args = self._build_server_command()
            self.server_proc = subprocess.Popen(
                server_args,
                stdout=subprocess.DEVNULL,  # Don't capture - prevents pipe deadlock
                stderr=subprocess.DEVNULL,  # Don't capture - prevents pipe deadlock
                text=True,
                bufsize=1
            )
            
            # Wait for server to be ready (give it 3 seconds)
            time.sleep(3)
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
            
            self.connection_changed.emit(True)
            self.status_update.emit("Robot running...")
            
            # Monitor client process output
            self._monitor_process()
            
        except FileNotFoundError as e:
            self.error_occurred.emit('lerobot_not_found', {'error': str(e)})
            self.run_completed.emit(False, "LeRobot not found")
        except Exception as e:
            self.error_occurred.emit('unknown', {'error': str(e)})
            self.run_completed.emit(False, f"Failed to start: {e}")
        finally:
            self._cleanup_processes()
            self.connection_changed.emit(False)
            
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
        r = self.config["robot"]
        p = self.config["policy"]
        cams = self.config.get("cameras", {})
        async_cfg = self.config.get("async_inference", {})
        
        # Build camera dict string
        camera_dict = self._build_camera_dict(cams)
        
        # Server address
        server_host = async_cfg.get("server_host", "127.0.0.1")
        server_port = async_cfg.get("server_port", 8080)
        server_address = f"{server_host}:{server_port}"
        
        args = [
            sys.executable, "-m", "lerobot.async_inference.robot_client",
            f"--server_address={server_address}",
            "--robot.type", r["type"],
            "--robot.port", r["port"],
            "--robot.id", r.get("id", "follower_arm"),
            f"--robot.cameras={camera_dict}",
            "--policy_type", async_cfg.get("policy_type", "act"),
            f"--pretrained_name_or_path={p['path']}",
            "--policy_device", p.get("device", "cpu"),
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
            # Read client stdout line by line (stderr is merged in)
            for line in self.client_proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                
                # Save all output for error parsing
                output_buffer.append(line)
                    
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
                    self.status_update.emit("Moving to rest position...")
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
            
    def _parse_error(self, stderr_text, return_code):
        """Parse stderr to determine error type"""
        stderr_lower = stderr_text.lower()
        
        # Serial permission error
        if 'permission denied' in stderr_lower and '/dev/tty' in stderr_lower:
            port = self.config["robot"]["port"]
            return 'serial_permission', {'port': port, 'stderr': stderr_text}
            
        # Serial not found
        if 'no such file or directory' in stderr_lower and '/dev/tty' in stderr_lower:
            port = self.config["robot"]["port"]
            return 'serial_not_found', {'port': port, 'stderr': stderr_text}
            
        # Port busy
        if 'device or resource busy' in stderr_lower and '/dev/tty' in stderr_lower:
            port = self.config["robot"]["port"]
            return 'serial_busy', {'port': port, 'stderr': stderr_text}
            
        # Camera error
        if 'could not open camera' in stderr_lower or 'videoio' in stderr_lower:
            cam_idx = self.config["cameras"]["front"]["index_or_path"]
            return 'camera_not_found', {'index': cam_idx, 'stderr': stderr_text}
            
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
            path = self.config["policy"]["path"]
            return 'policy_not_found', {'path': path, 'stderr': stderr_text}
            
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
        self._cleanup_processes()

