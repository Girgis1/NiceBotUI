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
        print("\n" + "="*60, flush=True)
        print("🔍 DEVICE DISCOVERY - Starting...", flush=True)
        print("="*60, flush=True)
        sys.stdout.flush()
        
        results = {
            "robot": None,
            "cameras": [],
            "errors": []
        }
        
        # Discover robot
        try:
            robot_info = self._discover_robot()
            if robot_info:
                results["robot"] = robot_info
                self.robot_status = "online"
                self.discovered_robot_port = robot_info["port"]
                self.robot_status_changed.emit("online")
                
                print(f"\n✅ ROBOT ARM FOUND:", flush=True)
                print(f"   Port: {robot_info['port']}", flush=True)
                print(f"   Motors: {robot_info['motor_count']}", flush=True)
                print(f"   Description: {robot_info['description']}", flush=True)
            else:
                print(f"\n⚪ ROBOT ARM: Not found", flush=True)
                self.robot_status = "empty"
                self.robot_status_changed.emit("empty")
        except Exception as e:
            error_msg = f"Robot discovery error: {e}"
            results["errors"].append(error_msg)
            print(f"\n❌ ROBOT ARM ERROR: {e}", flush=True)
            self.robot_status = "empty"
            self.robot_status_changed.emit("empty")
        
        # Discover cameras
        try:
            cameras_info = self._discover_cameras()
            if cameras_info:
                results["cameras"] = cameras_info
                
                print(f"\n✅ CAMERAS FOUND: {len(cameras_info)}", flush=True)
                for cam in cameras_info:
                    print(f"   {cam['path']} - {cam['resolution']}", flush=True)
                
                # Try to match cameras to config
                self._match_cameras_to_config(cameras_info)
            else:
                print(f"\n⚪ CAMERAS: None found", flush=True)
                self.camera_front_status = "empty"
                self.camera_wrist_status = "empty"
                self.camera_status_changed.emit("front", "empty")
                self.camera_status_changed.emit("wrist", "empty")
        except Exception as e:
            error_msg = f"Camera discovery error: {e}"
            results["errors"].append(error_msg)
            print(f"\n❌ CAMERA ERROR: {e}", flush=True)
            self.camera_front_status = "empty"
            self.camera_wrist_status = "empty"
            self.camera_status_changed.emit("front", "empty")
            self.camera_status_changed.emit("wrist", "empty")
        
        print("\n" + "="*60, flush=True)
        print("🔍 DEVICE DISCOVERY - Complete", flush=True)
        print("="*60 + "\n", flush=True)
        sys.stdout.flush()
        
        return results
    
    def _discover_robot(self) -> Optional[Dict]:
        """Scan serial ports for robot arm
        
        Returns:
            dict or None: Robot info if found
        """
        try:
            import serial.tools.list_ports
            from utils.motor_controller import MotorController
            
            # Scan all serial ports
            ports = serial.tools.list_ports.comports()
            
            for port in ports:
                port_name = port.device
                
                # Only test ttyACM* and ttyUSB* devices
                if not ('ttyACM' in port_name or 'ttyUSB' in port_name):
                    continue
                
                # Try to connect and detect robot
                try:
                    test_config = self.config.get("robot", {}).copy()
                    test_config["port"] = port_name
                    motor_controller = MotorController(test_config)
                    
                    if motor_controller.connect():
                        # Try to read positions (confirms it's a robot)
                        positions = motor_controller.read_positions()
                        motor_controller.disconnect()
                        
                        if positions:
                            return {
                                "port": port_name,
                                "motor_count": len(positions),
                                "description": port.description,
                                "positions": positions
                            }
                except Exception:
                    pass  # Not a robot, continue scanning
            
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
    
    def _match_cameras_to_config(self, cameras: List[Dict]):
        """Try to match discovered cameras to config settings
        
        Args:
            cameras: List of discovered camera info
        """
        # Get configured camera paths
        front_config = self.config.get("cameras", {}).get("front", {}).get("index_or_path", "")
        wrist_config = self.config.get("cameras", {}).get("wrist", {}).get("index_or_path", "")
        
        front_found = False
        wrist_found = False
        
        for cam in cameras:
            # Check if this camera matches front config
            if cam["path"] == front_config or str(cam["index"]) in front_config:
                front_found = True
                self.camera_front_status = "online"
                self.camera_status_changed.emit("front", "online")
                print(f"   ✓ Front camera matched: {cam['path']}", flush=True)
            
            # Check if this camera matches wrist config
            if cam["path"] == wrist_config or str(cam["index"]) in wrist_config:
                wrist_found = True
                self.camera_wrist_status = "online"
                self.camera_status_changed.emit("wrist", "online")
                print(f"   ✓ Wrist camera matched: {cam['path']}", flush=True)
        
        # If no matches, just mark as empty (not configured)
        if not front_found:
            self.camera_front_status = "empty"
            self.camera_status_changed.emit("front", "empty")
        
        if not wrist_found:
            self.camera_wrist_status = "empty"
            self.camera_status_changed.emit("wrist", "empty")
    
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

