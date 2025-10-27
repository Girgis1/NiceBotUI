"""
Device Manager - Centralized device discovery and status tracking

Handles:
- Robot arm detection
- Camera detection
- Status synchronization across Dashboard and Settings
- Startup device discovery
"""

from pathlib import Path
from typing import Optional, Dict, List
from PySide6.QtCore import QObject, Signal


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
                self.camera_front_status = "empty"
                self.camera_wrist_status = "empty"
                self.camera_status_changed.emit("front", "empty")
                self.camera_status_changed.emit("wrist", "empty")
        except Exception as e:
            error_msg = f"Camera discovery error: {e}"
            results["errors"].append(error_msg)
            self.camera_front_status = "empty"
            self.camera_wrist_status = "empty"
            self.camera_status_changed.emit("front", "empty")
            self.camera_status_changed.emit("wrist", "empty")
        
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
            status = self._probe_camera_status(camera_cfg.get("index_or_path"))
            attr_name = f"camera_{camera_name}_status"
            previous = getattr(self, attr_name, "empty")
            if status != previous:
                setattr(self, attr_name, status)
                self.camera_status_changed.emit(camera_name, status)
                status_changed = True

        return status_changed

    def _probe_camera_status(self, source) -> str:
        """Check whether a configured camera source appears online."""

        if source is None:
            return "empty"

        # Handle integer indices passed as strings
        probe_source = source
        if isinstance(source, str) and source.isdigit():
            probe_source = int(source)

        # Try OpenCV if available for a reliable check
        try:
            import cv2  # type: ignore

            cap = cv2.VideoCapture(probe_source)
            if cap.isOpened():
                cap.release()
                return "online"
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
            
            found_cameras = []
            
            # Scan /dev/video* devices (0-9)
            for i in range(10):
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
        # Get configured camera paths
        front_config = self.config.get("cameras", {}).get("front", {}).get("index_or_path", "")
        wrist_config = self.config.get("cameras", {}).get("wrist", {}).get("index_or_path", "")
        
        assignments = {}
        front_found = False
        wrist_found = False
        
        for cam in cameras:
            # Check if this camera matches front config
            if cam["path"] == front_config or str(cam["index"]) in front_config:
                front_found = True
                self.camera_front_status = "online"
                self.camera_status_changed.emit("front", "online")
                assignments["front"] = cam["path"]
            
            # Check if this camera matches wrist config
            if cam["path"] == wrist_config or str(cam["index"]) in wrist_config:
                wrist_found = True
                self.camera_wrist_status = "online"
                self.camera_status_changed.emit("wrist", "online")
                assignments["wrist"] = cam["path"]
        
        # If no matches, just mark as empty (not configured)
        if not front_found:
            self.camera_front_status = "empty"
            self.camera_status_changed.emit("front", "empty")
        
        if not wrist_found:
            self.camera_wrist_status = "empty"
            self.camera_status_changed.emit("wrist", "empty")
        
        return assignments
    
    def update_robot_status(self, status: str):
        """Update robot status and emit signal
        
        Args:
            status: "empty", "online", or "offline"
        """
        self.robot_status = status
        self.robot_status_changed.emit(status)
    
    def update_camera_status(self, camera_name: str, status: str):
        """Update camera status and emit signal
        
        Args:
            camera_name: "front" or "wrist"
            status: "empty", "online", or "offline"
        """
        if camera_name == "front":
            self.camera_front_status = status
        elif camera_name == "wrist":
            self.camera_wrist_status = status
        
        self.camera_status_changed.emit(camera_name, status)
    
    def get_robot_status(self) -> str:
        """Get current robot status"""
        return self.robot_status
    
    def get_camera_status(self, camera_name: str) -> str:
        """Get current camera status
        
        Args:
            camera_name: "front" or "wrist"
        """
        if camera_name == "front":
            return self.camera_front_status
        elif camera_name == "wrist":
            return self.camera_wrist_status
        return "empty"
