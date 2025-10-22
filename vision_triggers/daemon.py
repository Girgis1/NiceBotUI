"""
Vision Daemon - Main orchestrator for vision-based triggers

Long-running process that:
- Captures camera frames with adaptive frame rate
- Runs detection on active zones
- Evaluates trigger conditions
- Communicates with sequencer via IPC
- Manages memory and prevents leaks
- Home-gates detection (only runs when robot at home)
- Auto-restarts on errors
"""

import os
import sys
import time
import gc
import signal
import psutil
import cv2
import yaml
import numpy as np
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime
import pytz

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from vision_triggers.detectors.presence import PresenceDetector
from vision_triggers.trigger_rules import TriggerEvaluator
from vision_triggers.triggers_manager import TriggersManager
from vision_triggers.ipc import IPCManager


TIMEZONE = pytz.timezone('Australia/Sydney')


class VisionDaemon:
    """Main vision daemon process"""
    
    def __init__(self, config_path: Path, runtime_dir: Path):
        """
        Initialize vision daemon
        
        Args:
            config_path: Path to vision_config.yaml
            runtime_dir: Path to runtime directory
        """
        self.config_path = config_path
        self.runtime_dir = runtime_dir
        
        # Load configuration
        self.config = self._load_config()
        
        # Initialize components
        self.ipc = IPCManager(runtime_dir)
        self.triggers_manager = TriggersManager()
        self.detector = None
        self.evaluator = TriggerEvaluator()
        
        # Camera
        self.camera = None
        self.camera_index = self.config['camera']['index']
        
        # State
        self.running = False
        self.stop_requested = False
        self.current_fps = self.config['performance']['idle_fps']
        self.last_detection_time = None
        
        # Memory management
        self.frames_processed = 0
        self.detections_processed = 0
        self.process = psutil.Process(os.getpid())
        self.max_memory_mb = self.config['memory']['max_memory_mb']
        self.cleanup_interval = self.config['memory']['cleanup_interval_detections']
        
        # Active triggers cache
        self.active_triggers = {}
        
        print(f"[DAEMON] Initialized (PID: {os.getpid()})")
    
    def _load_config(self) -> Dict:
        """Load configuration from YAML"""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            print(f"[DAEMON] ✓ Loaded config from {self.config_path}")
            return config
        except Exception as e:
            print(f"[DAEMON] Error loading config: {e}")
            # Return default config
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict:
        """Get default configuration"""
        return {
            'camera': {'index': 0, 'width': 1280, 'height': 720, 'fps': 30},
            'detection': {
                'min_blob_area': 1200,
                'stability_check': True,
                'stability_frames': 2,
                'background': {
                    'learning_rate': 0.001,
                    'var_threshold': 16,
                    'detect_shadows': False,
                    'history': 50
                }
            },
            'performance': {
                'idle_fps': 0.2,
                'active_fps': 2.0,
                'max_fps': 10.0,
                'adaptive_framerate': True,
                'slow_until_first_detection': True,
                'return_to_slow_after_seconds': 30
            },
            'memory': {
                'max_memory_mb': 512,
                'frame_buffer_size': 3,
                'cleanup_interval_detections': 100,
                'force_gc': True
            }
        }
    
    def initialize(self) -> bool:
        """Initialize all daemon components"""
        try:
            print("[DAEMON] Initializing components...")
            
            # Initialize IPC
            self.ipc.initialize()
            self.ipc.write_daemon_pid(os.getpid())
            
            # Initialize camera
            if not self._init_camera():
                return False
            
            # Initialize detector
            detection_cfg = self.config['detection']
            bg_cfg = detection_cfg.get('background', {})
            
            self.detector = PresenceDetector(
                min_blob_area=detection_cfg.get('min_blob_area', 1200),
                learning_rate=bg_cfg.get('learning_rate', 0.001),
                var_threshold=bg_cfg.get('var_threshold', 16),
                detect_shadows=bg_cfg.get('detect_shadows', False),
                stability_frames=detection_cfg.get('stability_frames', 2),
                history=bg_cfg.get('history', 50)
            )
            
            if not self.detector.initialize():
                return False
            
            # Load active triggers
            self._load_active_triggers()
            
            # Setup signal handlers
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            
            print("[DAEMON] ✓ All components initialized")
            return True
        
        except Exception as e:
            print(f"[DAEMON] Initialization error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _init_camera(self) -> bool:
        """Initialize camera"""
        try:
            cam_cfg = self.config['camera']
            self.camera = cv2.VideoCapture(self.camera_index)
            
            if not self.camera.isOpened():
                print(f"[DAEMON] ✗ Failed to open camera {self.camera_index}")
                return False
            
            # Set camera properties
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, cam_cfg.get('width', 1280))
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, cam_cfg.get('height', 720))
            self.camera.set(cv2.CAP_PROP_FPS, cam_cfg.get('fps', 30))
            
            print(f"[DAEMON] ✓ Camera {self.camera_index} opened")
            return True
        
        except Exception as e:
            print(f"[DAEMON] Camera initialization error: {e}")
            return False
    
    def _load_active_triggers(self):
        """Load enabled triggers from TriggerManager"""
        try:
            enabled_names = self.triggers_manager.get_enabled_triggers()
            
            for name in enabled_names:
                trigger_data = self.triggers_manager.load_trigger(name)
                if trigger_data:
                    trigger_id = trigger_data['trigger_id']
                    self.active_triggers[trigger_id] = trigger_data
            
            print(f"[DAEMON] Loaded {len(self.active_triggers)} active triggers")
            
            for trigger_id, data in self.active_triggers.items():
                print(f"  - {data['name']} ({data['type']})")
        
        except Exception as e:
            print(f"[DAEMON] Error loading triggers: {e}")
    
    def run(self):
        """Main daemon loop"""
        if not self.initialize():
            print("[DAEMON] ✗ Initialization failed, exiting")
            return 1
        
        self.running = True
        print("[DAEMON] ✓ Starting main loop")
        
        try:
            while self.running and not self.stop_requested:
                loop_start = time.time()
                
                # Check robot state
                robot_state = self.ipc.read_robot_state()
                if not robot_state:
                    time.sleep(1.0)
                    continue
                
                # Home-gating: only detect when robot is at home and accepting triggers
                if robot_state['state'] != 'home' or not robot_state.get('accepting_triggers', False):
                    # Write idle status
                    self.ipc.write_vision_event("idle", None, None)
                    time.sleep(1.0)
                    continue
                
                # Capture frame
                frame = self._capture_frame()
                if frame is None:
                    print("[DAEMON] Failed to capture frame")
                    time.sleep(1.0)
                    continue
                
                # Process each active trigger
                for trigger_id, trigger_data in self.active_triggers.items():
                    self._process_trigger(frame, trigger_data)
                
                self.frames_processed += 1
                
                # Memory management
                if self.detections_processed % self.cleanup_interval == 0:
                    self._cleanup_memory()
                
                # Adaptive frame rate sleep
                loop_duration = time.time() - loop_start
                sleep_time = max(0, (1.0 / self.current_fps) - loop_duration)
                if sleep_time > 0:
                    time.sleep(sleep_time)
            
            print("[DAEMON] Main loop stopped")
            return 0
        
        except Exception as e:
            print(f"[DAEMON] Fatal error in main loop: {e}")
            import traceback
            traceback.print_exc()
            return 1
        
        finally:
            self.cleanup()
    
    def _capture_frame(self) -> Optional[np.ndarray]:
        """Capture a frame from camera"""
        try:
            ret, frame = self.camera.read()
            if not ret or frame is None:
                return None
            return frame
        except Exception as e:
            print(f"[DAEMON] Frame capture error: {e}")
            return None
    
    def _process_trigger(self, frame: np.ndarray, trigger_data: Dict):
        """Process a single trigger"""
        try:
            trigger_id = trigger_data['trigger_id']
            zones = trigger_data.get('zones', [])
            
            if not zones:
                return
            
            # Run detection
            detection_results = self.detector.detect(frame, zones)
            self.detections_processed += 1
            
            # Evaluate trigger condition
            evaluation = self.evaluator.evaluate_trigger(trigger_data, detection_results)
            
            # Update status
            status = "triggered" if evaluation.triggered else "detecting"
            self.ipc.write_vision_event(status, trigger_id if evaluation.triggered else None, None)
            
            # If triggered, create event
            if evaluation.triggered:
                self.last_detection_time = time.time()
                
                event = {
                    "timestamp": time.time(),
                    "result": "PRESENT",
                    "reason": evaluation.reason,
                    "details": evaluation.details,
                    "action": trigger_data.get('action', {}).get('type', 'advance_sequence')
                }
                
                self.ipc.write_vision_event("triggered", trigger_id, event)
                
                print(f"[DAEMON] 🎯 Trigger '{trigger_data['name']}' FIRED!")
                print(f"         Reason: {evaluation.reason}")
                
                # Speed up after detection
                if self.config['performance']['adaptive_framerate']:
                    self._adjust_framerate(detected=True)
        
        except Exception as e:
            print(f"[DAEMON] Error processing trigger: {e}")
    
    def _adjust_framerate(self, detected: bool):
        """Adjust frame rate based on detection activity"""
        perf_cfg = self.config['performance']
        
        if detected:
            # Speed up after detection
            self.current_fps = perf_cfg['active_fps']
        else:
            # Check if we should slow down
            if self.last_detection_time:
                elapsed = time.time() - self.last_detection_time
                if elapsed > perf_cfg['return_to_slow_after_seconds']:
                    self.current_fps = perf_cfg['idle_fps']
    
    def _cleanup_memory(self):
        """Periodic memory cleanup"""
        try:
            # Get memory usage
            mem_info = self.process.memory_info()
            memory_mb = mem_info.rss / (1024 * 1024)
            
            # Force garbage collection
            if self.config['memory']['force_gc']:
                gc.collect()
            
            # Check memory limit
            if memory_mb > self.max_memory_mb:
                print(f"[DAEMON] ⚠ Memory limit exceeded: {memory_mb:.1f}MB / {self.max_memory_mb}MB")
                print("[DAEMON] Requesting restart...")
                self.stop_requested = True
            
            # Log stats periodically
            if self.frames_processed % 100 == 0:
                print(f"[DAEMON] Stats: {self.frames_processed} frames, "
                      f"{self.detections_processed} detections, "
                      f"{memory_mb:.1f}MB memory, "
                      f"{self.current_fps:.2f} FPS")
        
        except Exception as e:
            print(f"[DAEMON] Memory cleanup error: {e}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"\n[DAEMON] Received signal {signum}, shutting down...")
        self.stop_requested = True
        self.running = False
    
    def cleanup(self):
        """Cleanup all resources"""
        print("[DAEMON] Cleaning up...")
        
        try:
            # Release camera
            if self.camera:
                self.camera.release()
                print("[DAEMON] Camera released")
            
            # Cleanup detector
            if self.detector:
                self.detector.cleanup()
            
            # Cleanup IPC
            self.ipc.cleanup()
            
            print("[DAEMON] ✓ Cleanup complete")
        
        except Exception as e:
            print(f"[DAEMON] Cleanup error: {e}")
    
    def stop(self):
        """Stop the daemon"""
        print("[DAEMON] Stop requested")
        self.stop_requested = True
        self.running = False


def main():
    """Main entry point"""
    print("=" * 60)
    print("Vision Triggers Daemon")
    print("=" * 60)
    print()
    
    # Get paths
    base_dir = Path(__file__).parent.parent
    config_path = base_dir / "config" / "vision_config.yaml"
    runtime_dir = base_dir / "runtime"
    
    # Ensure runtime dir exists
    runtime_dir.mkdir(parents=True, exist_ok=True)
    
    # Create and run daemon
    daemon = VisionDaemon(config_path, runtime_dir)
    exit_code = daemon.run()
    
    print()
    print(f"[DAEMON] Exited with code {exit_code}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

