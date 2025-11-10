"""
Device Manager - Centralized device discovery and status tracking

Handles:
- Robot arm detection
- Camera detection
- Status synchronization across Dashboard and Settings
- Startup device discovery
"""

from pathlib import Path
from typing import Optional, Dict, List, Set
from PySide6.QtCore import QObject, Signal

from utils.camera_support import prepare_camera_source


class DeviceManager(QObject):
    """Manages device discovery and status tracking"""
    
    # Signals for status updates
    robot_status_changed = Signal(str)      # empty/online/offline
    camera_status_changed = Signal(str, str)  # (camera_name, status)
    discovery_log = Signal(str)  # Log messages for Dashboard
    
    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        
        # Device status tracking
        self.robot_status = "empty"
        self.camera_front_status = "empty"
        self.camera_wrist_status = "empty"
        self.camera_statuses: Dict[str, str] = {}
        for name in (self.config.get("cameras", {}) or {}):
            self.camera_statuses[name] = "empty"
            setattr(self, f"camera_{name}_status", "empty")
        
        # Discovered devices
        self.discovered_robot_port = None
        self.discovered_cameras = {}
    
    def discover_all_devices(self) -> Dict[str, any]:
        """Run full device discovery on startup
        
        Returns:
            dict: Discovery results with robot and camera info
        """
        import sys
        
        results = {
            "robot": None,
            "cameras": [],
            "errors": []
        }
        
        # Discover robot
        robot_count = 0
        robot_port = None
        try:
            robot_info = self._discover_robot()
            if robot_info:
                results["robot"] = robot_info
                self.robot_status = "online"
                self.discovered_robot_port = robot_info["port"]
                self.robot_status_changed.emit("online")
                robot_count = 1
                robot_port = robot_info["port"]
            else:
                self.robot_status = "empty"
                self.robot_status_changed.emit("empty")
        except Exception as e:
            error_msg = f"Robot discovery error: {e}"
            results["errors"].append(error_msg)
            self.robot_status = "empty"
            self.robot_status_changed.emit("empty")
        
        # Discover cameras
        camera_assignments = {}
        try:
            cameras_info = self._discover_cameras()
            if cameras_info:
                results["cameras"] = cameras_info
                # Try to match cameras to config
                camera_assignments = self._match_cameras_to_config(cameras_info)
            else:
                for camera_name in (self.config.get("cameras", {}) or {}):
                    self._set_camera_status(camera_name, "empty")
        except Exception as e:
            error_msg = f"Camera discovery error: {e}"
            results["errors"].append(error_msg)
            for camera_name in (self.config.get("cameras", {}) or {}):
                self._set_camera_status(camera_name, "empty")
        
        # Print compact summary (both terminal and GUI)
        print("\n=== Detecting Ports ===", flush=True)
        self.discovery_log.emit("=== Detecting Ports ===")
        
        print(f"----- Robot Arms: {robot_count} -----", flush=True)
        self.discovery_log.emit(f"----- Robot Arms: {robot_count} -----")
        
        if robot_port:
            print(f"Port: {robot_port}", flush=True)
            self.discovery_log.emit(f"Port: {robot_port}")
        
        print(f"----- Cameras: {len(camera_assignments)} -----", flush=True)
        self.discovery_log.emit(f"----- Cameras: {len(camera_assignments)} -----")
        
        for cam_name, cam_path in camera_assignments.items():
            msg = f"{cam_name.title()}: {cam_path}"
            print(msg, flush=True)
            self.discovery_log.emit(msg)
        
        print("", flush=True)  # Blank line at end
        sys.stdout.flush()
        
        return results

    def refresh_status(self) -> bool:
        """Refresh device status without a full discovery scan.

        Returns:
            bool: True if any status changed, False otherwise.
        """

        status_changed = False

        # Robot status
        try:
            robot_port = self.config.get("robot", {}).get("port")
            if robot_port:
                new_status = "online" if Path(robot_port).exists() else "offline"
            else:
                new_status = "empty"

            if new_status != self.robot_status:
                self.robot_status = new_status
                self.robot_status_changed.emit(new_status)
                status_changed = True
        except Exception as exc:  # pragma: no cover - defensive
            if self.robot_status != "empty":
                self.robot_status = "empty"
                self.robot_status_changed.emit("empty")
                status_changed = True
            self.discovery_log.emit(f"Device check error (robot): {exc}")

        # Camera statuses
        cameras_cfg = self.config.get("cameras", {}) or {}
        for camera_name, camera_cfg in cameras_cfg.items():
            status = self._probe_camera_status(camera_cfg)
            if self._set_camera_status(camera_name, status):
                status_changed = True

        return status_changed

    def _backend_flag(self, backend_name: Optional[str]) -> Optional[int]:
        try:
            import cv2  # type: ignore
        except ImportError:
            return None

        mapping = {
            "gstreamer": getattr(cv2, "CAP_GSTREAMER", None),
            "v4l2": getattr(cv2, "CAP_V4L2", None),
            "ffmpeg": getattr(cv2, "CAP_FFMPEG", None),
        }
        backend = (backend_name or "").lower()
        flag = mapping.get(backend)
        return flag if isinstance(flag, int) else None

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

            backend_flag = self._backend_flag(backend)
            if backend_flag is not None:
                cap = cv2.VideoCapture(source, backend_flag)
            else:
                cap = cv2.VideoCapture(source)

            if cap is not None and cap.isOpened():
                try:
                    buffer_prop = getattr(cv2, "CAP_PROP_BUFFERSIZE", None)
                    if buffer_prop is not None:
                        cap.set(buffer_prop, 1)
                except Exception:
                    pass
                cap.release()
                return "online"
            if cap is not None:
                cap.release()
            return "offline"
        except Exception:
            # Fall back to filesystem check for path-based sources
            if isinstance(source, str) and Path(source).exists():
                return "online"
            return "offline"
    
    def _discover_robot(self) -> Optional[Dict]:
        """Scan serial ports for robot arm
        
        Returns:
            dict or None: Robot info if found
        """
        try:
            import serial.tools.list_ports
            from utils.motor_controller import MotorController
            from pathlib import Path
            
            # First, check if the configured port exists
            configured_port = self.config.get("robot", {}).get("port", "/dev/ttyACM0")
            if Path(configured_port).exists():
                # Port exists - assume robot is there
                # We don't try to connect during discovery to avoid conflicts
                return {
                    "port": configured_port,
                    "motor_count": 6,  # Default assumption for SO-100
                    "description": "Configured Robot",
                    "positions": None  # Don't read positions during discovery
                }
            
            # If configured port doesn't exist, scan for any robot
            ports = serial.tools.list_ports.comports()
            
            for port in ports:
                port_name = port.device
                
                # Only test ttyACM* and ttyUSB* devices
                if not ('ttyACM' in port_name or 'ttyUSB' in port_name):
                    continue
                
                # Port exists - assume it's a robot
                # We don't try to connect to avoid conflicts with the main app
                return {
                    "port": port_name,
                    "motor_count": 6,  # Default assumption
                    "description": port.description,
                    "positions": None
                }
            
            return None
            
        except Exception as e:
            print(f"[DEVICE_MANAGER] Robot scan error: {e}")
            return None
    
    def _discover_cameras(self) -> List[Dict]:
        """Scan for available cameras
        
        Returns:
            list: List of camera info dicts
        """
        try:
            import cv2
            import sys
            
            found_cameras = []
            
            # Scan /dev/video* devices (0-9). Skip indices without device nodes to avoid noisy OpenCV warnings.
            is_linux = sys.platform.startswith("linux")
            for i in range(10):
                if is_linux:
                    video_path = Path(f"/dev/video{i}")
                    if not video_path.exists():
                        continue
                try:
                    cap = cv2.VideoCapture(i)
                    if cap.isOpened():
                        # Try to read a frame to confirm it's working
                        ret, frame = cap.read()
                        if ret:
                            height, width = frame.shape[:2]
                            found_cameras.append({
                                "index": i,
                                "path": f"/dev/video{i}",
                                "resolution": f"{width}x{height}",
                                "width": width,
                                "height": height
                            })
                        cap.release()
                    else:
                        cap.release()
                except Exception:
                    pass
            
            return found_cameras
            
        except Exception as e:
            print(f"[DEVICE_MANAGER] Camera scan error: {e}")
            return []
    
    def _match_cameras_to_config(self, cameras: List[Dict]) -> Dict[str, str]:
        """Try to match discovered cameras to config settings

        Args:
            cameras: List of discovered camera info

        Returns:
            Dict of camera assignments {name: path}
        """
        camera_cfgs = self.config.get("cameras", {}) or {}
        assignments: Dict[str, str] = {}
        matched: Set[str] = set()

        for cam in cameras:
            path = str(cam.get("path", ""))
            index = cam.get("index")
            index_str = str(index) if index is not None else ""

            for name, cfg in camera_cfgs.items():
                if name in matched:
                    continue

                configured_value = str(cfg.get("index_or_path", "")).strip()
                if not configured_value:
                    continue

                if self._camera_matches_config(configured_value, path, index_str):
                    assignments[name] = path or configured_value
                    self._set_camera_status(name, "online")
                    matched.add(name)
                    break

        for name in camera_cfgs.keys():
            if name not in matched:
                self._set_camera_status(name, "empty")

        return assignments

    def _camera_matches_config(self, configured: str, discovered_path: str, discovered_index: str) -> bool:
        """Return True if a discovered camera appears to match a configured source."""

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

        return False
    
    def update_robot_status(self, status: str):
        """Update robot status and emit signal
        
        Args:
            status: "empty", "online", or "offline"
        """
        self.robot_status = status
        self.robot_status_changed.emit(status)
    
    def update_camera_status(self, camera_name: str, status: str):
        """Update camera status and emit signal."""
        self._set_camera_status(camera_name, status)
    
    def get_robot_status(self) -> str:
        """Get current robot status"""
        return self.robot_status
    
    def get_camera_status(self, camera_name: str) -> str:
        """Get current camera status."""
        return self.camera_statuses.get(camera_name, "empty")

    def _set_camera_status(self, camera_name: str, status: str) -> bool:
        """Persist a camera status update, emitting if it changed."""

        previous = self.camera_statuses.get(camera_name, "empty")
        self.camera_statuses[camera_name] = status
        setattr(self, f"camera_{camera_name}_status", status)
        if camera_name == "front":
            self.camera_front_status = status
        elif camera_name == "wrist":
            self.camera_wrist_status = status

        if previous != status:
            self.camera_status_changed.emit(camera_name, status)
            return True
        return False
