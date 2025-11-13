"""
Device Manager - Centralized device discovery and status tracking

Handles:
- Robot arm detection
- Camera detection
- Status synchronization across Dashboard and Settings
- Startup device discovery
"""

import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Dict, List, Optional
from PySide6.QtCore import QObject, Signal

from utils.camera_backend import open_capture
from utils.app_state import AppStateStore
from utils.capabilities import detect_capabilities
from utils.camera_support import prepare_camera_source
from utils.logging_utils import log_exception


def safe_print(*args, **kwargs):
    """Print that handles BrokenPipeError gracefully for GUI apps."""
    try:
        print(*args, **kwargs)
    except BrokenPipeError:
        # Ignore broken pipe errors (common when output is piped/redirected)
        pass

try:  # Optional dependency for coordinating shared camera access
    from utils.camera_hub import CameraStreamHub
except Exception:  # pragma: no cover - avoid hard dependency during bootstrapping
    CameraStreamHub = None


def safe_print(*args, **kwargs) -> None:
    """Print helper that swallows BrokenPipeError in GUI contexts."""
    try:
        print(*args, **kwargs)
    except BrokenPipeError:
        pass


class DeviceManager(QObject):
    """Manages device discovery and status tracking"""
    
    # Signals for status updates
    robot_status_changed = Signal(str)      # empty/online/offline
    robot_arm_status_changed = Signal(str, str)  # (arm_name, status)
    camera_status_changed = Signal(str, str)  # (camera_name, status)
    discovery_log = Signal(str)  # Log messages for Dashboard
    
    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self._state_store = AppStateStore.instance()
        
        # Device status tracking
        self.robot_status = "empty"
        self.robot_arm_statuses: Dict[str, str] = {}
        self.camera_front_status = "empty"
        self.camera_wrist_status = "empty"
        self.camera_wrist_right_status = "empty"
        self.camera_statuses: Dict[str, str] = {}
        self.discovered_robot_ports: Dict[str, str] = {}
        self._sync_robot_arm_status_map(initial=True)
        self._sync_camera_status_map(initial=True)

        # Discovered devices
        self.discovered_cameras = {}

        # Seed shared app state
        self._state_store.set_state("robot.status", self.robot_status)
        for arm_name, status in self.robot_arm_statuses.items():
            self._state_store.set_state(f"robot.arm.{arm_name}", status)
        for camera_name, status in self.camera_statuses.items():
            self._state_store.set_state(f"cameras.{camera_name}", status)

        capabilities = detect_capabilities(self.config)
        self._state_store.set_state("capabilities.robot.followers", capabilities["robot"]["followers"]) 
        self._state_store.set_state("capabilities.robot.leaders", capabilities["robot"]["leaders"]) 
        for cam_name, available in capabilities["cameras"].items():
            self._state_store.set_state(f"capabilities.camera.{cam_name}", available)

    # ------------------------------------------------------------------
    # Internal helpers

    def _sync_robot_arm_status_map(self, initial: bool = False) -> None:
        """Ensure status entries exist for each configured robot arm."""

        robot_cfg = self.config.get("robot", {}) or {}
        arms = robot_cfg.get("arms", []) or []
        if not arms:
            if "robot" not in self.robot_arm_statuses:
                self.robot_arm_statuses["robot"] = "empty"
                if not initial:
                    self.robot_arm_status_changed.emit("robot", "empty")
            for key in list(self.robot_arm_statuses.keys()):
                if key != "robot":
                    del self.robot_arm_statuses[key]
                    if not initial:
                        self.robot_arm_status_changed.emit(key, "empty")
            return

        active_keys = set()
        for idx, arm_cfg in enumerate(arms):
            key = self._robot_arm_key(idx, arm_cfg)
            active_keys.add(key)
            if key not in self.robot_arm_statuses:
                self.robot_arm_statuses[key] = "empty"
                if not initial:
                    self.robot_arm_status_changed.emit(key, "empty")

        for stale in list(self.robot_arm_statuses.keys()):
            if stale not in active_keys:
                del self.robot_arm_statuses[stale]
                if not initial:
                    self.robot_arm_status_changed.emit(stale, "empty")

    def _robot_arm_key(self, idx: int, arm_cfg: Dict) -> str:
        """Return a stable identifier for a robot arm entry."""

        return arm_cfg.get("id") or arm_cfg.get("name") or f"arm_{idx + 1}"

    def _set_robot_arm_status(self, arm_name: str, status: str) -> bool:
        """Persist a robot arm status update."""

        previous = self.robot_arm_statuses.get(arm_name, "empty")
        if previous == status:
            return False
        self.robot_arm_statuses[arm_name] = status
        self.robot_arm_status_changed.emit(arm_name, status)
        self._state_store.set_state(f"robot.arm.{arm_name}", status)
        return True

    def _set_overall_robot_status(self, status: str) -> bool:
        """Update aggregate robot status and emit if it changed."""

        if status == self.robot_status:
            return False
        self.robot_status = status
        self.robot_status_changed.emit(status)
        self._state_store.set_state("robot.status", status)
        return True

    def _list_robot_ports(self) -> Dict[str, str]:
        """Return a mapping of available robot serial ports."""

        try:
            import serial.tools.list_ports
        except Exception as exc:
            log_exception("DeviceManager: serial tools unavailable", exc, level="warning")
            return {}

        ports: Dict[str, str] = {}
        for port in serial.tools.list_ports.comports():
            if not ("ttyACM" in port.device or "ttyUSB" in port.device):
                continue
            ports[port.device] = port.description or "Serial Device"
        return ports

    def _probe_robot_arm_status(self, port: str, available_ports: Dict[str, str]) -> str:
        """Determine status for a configured robot arm port."""

        port = (port or "").strip()
        if not port:
            return "empty"
        if Path(port).exists() or port in available_ports:
            return "online"
        return "offline"

    def _aggregate_robot_status(self) -> str:
        """Collapse per-arm statuses into a single summary."""

        if not self.robot_arm_statuses:
            return "empty"
        statuses = list(self.robot_arm_statuses.values())
        if all(state == "empty" for state in statuses):
            return "empty"
        if all(state == "online" for state in statuses):
            return "online"
        if any(state == "online" for state in statuses):
            return "offline"
        return "offline"

    def _sync_camera_status_map(self, initial: bool = False) -> None:
        """Ensure status entries exist for every configured camera."""

        cameras_cfg = self.config.get("cameras", {}) or {}
        for name in cameras_cfg.keys():
            if name not in self.camera_statuses:
                self.camera_statuses[name] = "empty"
                if not initial:
                    self.camera_status_changed.emit(name, "empty")
            setattr(self, f"camera_{name}_status", self.camera_statuses.get(name, "empty"))
            if name == "front":
                self.camera_front_status = self.camera_statuses[name]
            elif name == "wrist":
                self.camera_wrist_status = self.camera_statuses[name]
            elif name == "wrist_right":
                self.camera_wrist_right_status = self.camera_statuses[name]

        for name in list(self.camera_statuses.keys()):
            if name not in cameras_cfg:
                del self.camera_statuses[name]
                setattr(self, f"camera_{name}_status", "empty")
                if not initial:
                    self.camera_status_changed.emit(name, "empty")

    def _set_camera_status(self, camera_name: str, status: str) -> None:
        """Persist a camera status update and notify listeners when it changes."""

        previous = self.camera_statuses.get(camera_name, "empty")
        if previous == status:
            return

        self.camera_statuses[camera_name] = status
        setattr(self, f"camera_{camera_name}_status", status)
        if camera_name == "front":
            self.camera_front_status = status
        elif camera_name == "wrist":
            self.camera_wrist_status = status
        elif camera_name == "wrist_right":
            self.camera_wrist_right_status = status
        self.camera_status_changed.emit(camera_name, status)
        self._state_store.set_state(f"cameras.{camera_name}", status)

    def _camera_matches_config(self, configured: str, discovered_path: str, discovered_index: str) -> bool:
        """Return True if a discovered camera looks like the configured entry."""

        value = (configured or "").strip()
        if not value:
            return False

        normalized_value = value.lower()
        normalized_path = (discovered_path or "").strip().lower()
        normalized_index = (discovered_index or "").strip()

        if normalized_path and normalized_value == normalized_path:
            return True

        if normalized_index and (normalized_value == normalized_index or normalized_index in normalized_value):
            return True

        if normalized_path and normalized_path in normalized_value:
            return True

        if normalized_value.startswith("/dev/video"):
            suffix = normalized_value.split("/dev/video", 1)[-1]
            if suffix.isdigit() and suffix == normalized_index:
                return True

        if normalized_value.startswith("camera:"):
            suffix = normalized_value.split(":", 1)[-1]
            if suffix.isdigit() and suffix == normalized_index:
                return True

        if "sensor-id=" in normalized_value:
            suffix = normalized_value.split("sensor-id=", 1)[-1].split()[0]
            if suffix.isdigit() and suffix == normalized_index:
                return True

        return False

    def _mark_cameras_missing(self) -> None:
        """Mark configured cameras offline (or empty) when discovery fails."""

        cameras_cfg = self.config.get("cameras", {}) or {}
        for name, cfg in cameras_cfg.items():
            identifier = str(cfg.get("index_or_path", "")).strip()
            fallback = "empty" if not identifier else "offline"
            self._set_camera_status(name, fallback)
    
    def discover_all_devices(self) -> Dict[str, any]:
        """Run full device discovery on startup
        
        Returns:
            dict: Discovery results with robot and camera info
        """
        import sys
        
        results = {
            "robot": [],
            "cameras": [],
            "errors": []
        }
        
        # Discover robot
        robot_infos: List[Dict] = []
        robot_count = 0
        try:
            robot_infos = self._discover_robot()
            results["robot"] = robot_infos
            robot_count = sum(1 for info in robot_infos if info.get("port"))
        except Exception as exc:
            log_exception("DeviceManager: robot discovery failed", exc)
            error_msg = f"Robot discovery error: {exc}"
            results["errors"].append(error_msg)
            self._set_overall_robot_status("empty")
            robot_infos = []

        # Discover cameras
        self._sync_camera_status_map()
        camera_assignments = {}
        try:
            cameras_info = self._discover_cameras()
            if cameras_info:
                results["cameras"] = cameras_info
                # Try to match cameras to config
                camera_assignments = self._match_cameras_to_config(cameras_info)
            else:
                self._mark_cameras_missing()
        except Exception as exc:
            log_exception("DeviceManager: camera discovery failed", exc)
            error_msg = f"Camera discovery error: {exc}"
            results["errors"].append(error_msg)
            self._mark_cameras_missing()
        
        # Print compact summary (both terminal and GUI)
        safe_print("\n=== Detecting Ports ===", flush=True)
        self.discovery_log.emit("=== Detecting Ports ===")
        
        safe_print(f"----- Robot Arms: {robot_count} -----", flush=True)
        self.discovery_log.emit(f"----- Robot Arms: {robot_count} -----")
        if robot_infos:
            for info in robot_infos:
                port_msg = f"{info.get('name', 'arm').title()}: {info.get('port', 'Unknown')}"
                safe_print(port_msg, flush=True)
                self.discovery_log.emit(port_msg)
        
        cameras_cfg = self.config.get("cameras", {}) or {}
        friendly_names = {
            "front": "Front Camera",
            "wrist": "Wrist L Camera",
            "wrist_right": "Wrist R Camera",
        }
        safe_print(f"----- Cameras: {len(camera_assignments)} -----", flush=True)
        self.discovery_log.emit(f"----- Cameras: {len(camera_assignments)} -----")

        if not cameras_cfg:
            msg = "No cameras configured."
            safe_print(msg, flush=True)
            self.discovery_log.emit(msg)
        else:
            for cam_name in cameras_cfg.keys():
                label = friendly_names.get(cam_name, cam_name.replace("_", " ").title())
                if cam_name in camera_assignments:
                    msg = f"{label}: {camera_assignments[cam_name]}"
                else:
                    configured_path = cameras_cfg.get(cam_name, {}).get("index_or_path", "")
                    if configured_path:
                        msg = f"{label}: {configured_path} (not detected)"
                    else:
                        msg = f"{label}: not configured"
                safe_print(msg, flush=True)
                self.discovery_log.emit(msg)
        
        safe_print("", flush=True)  # Blank line at end
        try:
            sys.stdout.flush()
        except BrokenPipeError:
            pass
        
        return results

    def refresh_status(self) -> bool:
        """Refresh device status without a full discovery scan.

        Returns:
            bool: True if any status changed, False otherwise.
        """

        status_changed = False

        # Robot arm statuses
        robot_cfg = self.config.get("robot", {}) or {}
        arms = robot_cfg.get("arms", []) or []
        self._sync_robot_arm_status_map()
        if arms:
            ports = self._list_robot_ports()
            for idx, arm_cfg in enumerate(arms):
                key = self._robot_arm_key(idx, arm_cfg)
                status = self._probe_robot_arm_status(arm_cfg.get("port", ""), ports)
                if self._set_robot_arm_status(key, status):
                    status_changed = True
            if self._set_overall_robot_status(self._aggregate_robot_status()):
                status_changed = True
        else:
            # Legacy single-port configs
            try:
                robot_port = self.config.get("robot", {}).get("port")
                if robot_port:
                    new_status = "online" if Path(robot_port).exists() else "offline"
                else:
                    new_status = "empty"
                if self._set_overall_robot_status(new_status):
                    status_changed = True
            except Exception as exc:  # pragma: no cover - defensive
                log_exception("DeviceManager: legacy robot status check failed", exc, level="warning")
                if self._set_overall_robot_status("empty"):
                    status_changed = True
                self.discovery_log.emit(f"Device check error (robot): {exc}")

        # Camera statuses
        cameras_cfg = self.config.get("cameras", {}) or {}
        self._sync_camera_status_map()
        pause_ctx = CameraStreamHub.paused() if CameraStreamHub else nullcontext()
        with pause_ctx:
            for camera_name, camera_cfg in cameras_cfg.items():
                status = self._probe_camera_status(camera_cfg)
                previous = self.camera_statuses.get(camera_name, "empty")
                if status != previous:
                    self._set_camera_status(camera_name, status)
                    status_changed = True

        return status_changed

    def _probe_camera_status(self, camera_cfg) -> str:
        """Check whether a configured camera source appears online."""

        if not camera_cfg:
            return "empty"

        width = int(camera_cfg.get("width", 640) or 0)
        height = int(camera_cfg.get("height", 480) or 0)
        fps = float(camera_cfg.get("fps", 30) or 0.0)
        source, backend = prepare_camera_source(camera_cfg, width, height, fps)

        # Try OpenCV if available for a reliable check
        try:
            import cv2  # type: ignore
            backend_name, cap = open_capture(source, preferred_backend=backend)

            if cap is not None and cap.isOpened():
                try:
                    buffer_prop = getattr(cv2, "CAP_PROP_BUFFERSIZE", None)
                    if buffer_prop is not None:
                        cap.set(buffer_prop, 1)
                except Exception as exc:
                    log_exception("DeviceManager: camera buffer tuning failed", exc, level="debug")
                cap.release()
                return "online"
            if cap is not None:
                cap.release()
            return "offline"
        except Exception as exc:
            log_exception("DeviceManager: OpenCV camera probe failed", exc, level="warning")
            # Fall back to filesystem check for path-based sources
            if isinstance(source, str) and Path(source).exists():
                return "online"
            return "offline"
    
    def _discover_robot(self) -> List[Dict]:
        """Scan serial ports for robot arms."""

        robot_cfg = self.config.get("robot", {}) or {}
        arms = robot_cfg.get("arms", []) or []
        self._sync_robot_arm_status_map()

        if not arms:
            legacy = self._discover_single_robot()
            if legacy:
                self._set_robot_arm_status("robot", "online")
                self._set_overall_robot_status("online")
                self.discovered_robot_ports = {"robot": legacy["port"]}
                return [legacy]
            self._set_robot_arm_status("robot", "empty")
            self._set_overall_robot_status("empty")
            self.discovered_robot_ports = {}
            return []

        ports = self._list_robot_ports()
        discovered: List[Dict] = []
        for idx, arm_cfg in enumerate(arms):
            key = self._robot_arm_key(idx, arm_cfg)
            port = arm_cfg.get("port", "")
            status = self._probe_robot_arm_status(port, ports)
            self._set_robot_arm_status(key, status)
            if status == "online":
                discovered.append(
                    {
                        "name": key,
                        "port": port,
                        "description": ports.get(port, "Configured Robot Arm"),
                    }
                )
        self.discovered_robot_ports = {item["name"]: item["port"] for item in discovered}
        self._set_overall_robot_status(self._aggregate_robot_status())
        return discovered

    def _discover_single_robot(self) -> Optional[Dict]:
        """Legacy single-arm discovery for backward compatibility."""

        try:
            import serial.tools.list_ports
        except Exception as exc:
            log_exception("DeviceManager: robot scan unavailable", exc, level="warning")
            return None

        configured_port = self.config.get("robot", {}).get("port", "/dev/ttyACM0")
        if Path(configured_port).exists():
            return {
                "name": "robot",
                "port": configured_port,
                "description": "Configured Robot",
            }

        for port in serial.tools.list_ports.comports():
            if not ("ttyACM" in port.device or "ttyUSB" in port.device):
                continue
            return {
                "name": port.description or "robot",
                "port": port.device,
                "description": port.description or "Serial Device",
            }
        return None
    
    def _discover_cameras(self) -> List[Dict]:
        """Scan for available cameras
        
        Returns:
            list: List of camera info dicts
        """
        try:
            import cv2
            import sys

            found_cameras: List[Dict] = []

            def _read_resolution(capture) -> Optional[tuple[int, int]]:
                if capture is None or not capture.isOpened():
                    return None
                for _ in range(3):
                    ret, frame = capture.read()
                    if ret and frame is not None and frame.size:
                        height, width = frame.shape[:2]
                        return width, height
                width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
                if width > 0 and height > 0:
                    return width, height
                return None

            # Scan /dev/video* devices (0-9). Skip indices without device nodes to avoid noisy OpenCV warnings.
            is_linux = sys.platform.startswith("linux")
            pause_ctx = CameraStreamHub.paused() if CameraStreamHub else nullcontext()
            with pause_ctx:
                for i in range(10):
                    if is_linux:
                        video_path = Path(f"/dev/video{i}")
                        if not video_path.exists():
                            continue

                    backend_name, cap = open_capture(i)
                    try:
                        if not cap or not cap.isOpened():
                            continue
                        resolution = _read_resolution(cap)
                        if resolution:
                            width, height = resolution
                            found_cameras.append(
                                {
                                    "index": i,
                                    "path": f"/dev/video{i}",
                                    "resolution": f"{width}x{height}",
                                    "width": width,
                                    "height": height,
                                    "backend": backend_name or "default",
                                }
                            )
                    finally:
                        if cap:
                            cap.release()

            return found_cameras

        except Exception as exc:
            log_exception("DeviceManager: camera scan error", exc)
            return []

    def scan_available_cameras(self) -> List[Dict]:
        """Public helper used by settings UI to inspect camera hardware."""

        return self._discover_cameras()
    
    def _match_cameras_to_config(self, cameras: List[Dict]) -> Dict[str, str]:
        """Try to match discovered cameras to config settings."""

        assignments: Dict[str, str] = {}
        cameras_cfg = self.config.get("cameras", {}) or {}
        used = set()

        for cam_name, cam_cfg in cameras_cfg.items():
            expected = str(cam_cfg.get("index_or_path", "")).strip()
            matched_entry = None

            if expected:
                for cam in cameras:
                    cam_key = (cam.get("path"), cam.get("index"))
                    if cam_key in used:
                        continue
                    path = str(cam.get("path", ""))
                    index_str = str(cam.get("index", ""))
                    if self._camera_matches_config(expected, path, index_str):
                        matched_entry = cam
                        used.add(cam_key)
                        break

            if matched_entry:
                assignments[cam_name] = matched_entry.get("path", expected)
                self._set_camera_status(cam_name, "online")
            else:
                fallback = "empty" if not expected else "offline"
                self._set_camera_status(cam_name, fallback)

        return assignments
    
    def update_robot_status(self, status: str):
        """Update robot status and emit signal
        
        Args:
            status: "empty", "online", or "offline"
        """
        if not self.robot_arm_statuses:
            self.robot_arm_statuses["robot"] = status
        self._set_overall_robot_status(status)
    
    def update_camera_status(self, camera_name: str, status: str):
        """Update camera status and emit signal."""
        self._set_camera_status(camera_name, status)
    
    def get_robot_status(self) -> str:
        """Get current robot status"""
        return self.robot_status
    
    def get_camera_status(self, camera_name: str) -> str:
        """Get current camera status
        
        Args:
            camera_name: "front" or "wrist"
        """
        return self.camera_statuses.get(camera_name, "empty")
