#!/usr/bin/env python3
"""
Motor Dropout Diagnostic Tool for Jetson
Monitors USB events, system power, and motor status to diagnose random dropouts
"""

import subprocess
import threading
import time
import json
import sys
from datetime import datetime
from pathlib import Path
from collections import deque

class MotorDropoutMonitor:
    def __init__(self, log_dir="logs", duration_seconds=None):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        self.duration = duration_seconds
        self.start_time = time.time()
        self.running = True
        
        # Create timestamped log file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"motor_dropout_diag_{timestamp}.log"
        
        # Buffers for recent events (helps correlate)
        self.usb_events = deque(maxlen=100)
        self.power_readings = deque(maxlen=100)
        self.motor_events = deque(maxlen=100)
        
        print(f"🔍 Motor Dropout Diagnostics Started")
        print(f"📝 Logging to: {self.log_file}")
        print(f"⏱️  Duration: {'∞ (until Ctrl+C)' if duration_seconds is None else f'{duration_seconds}s'}")
        print(f"\n{'='*70}")
        print("Monitoring:")
        print("  • USB device events (dmesg)")
        print("  • System power consumption (tegrastats)")
        print("  • Motor controller ports (/dev/ttyACM*)")
        print(f"{'='*70}\n")
        
        self.log("=== MOTOR DROPOUT DIAGNOSTICS SESSION STARTED ===")
        self.log(f"Start Time: {datetime.now().isoformat()}")
        self.log(f"Monitor Duration: {'Unlimited' if duration_seconds is None else f'{duration_seconds}s'}")
        self.log("")
        
        # Log initial system state
        self._log_initial_state()
    
    def log(self, message, event_type="INFO"):
        """Write timestamped message to log file"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_line = f"[{timestamp}] [{event_type}] {message}"
        
        with open(self.log_file, 'a') as f:
            f.write(log_line + "\n")
        
        # Also print to console for important events
        if event_type in ["MOTOR_EVENT", "USB_EVENT", "POWER_SPIKE", "ERROR"]:
            print(log_line)
    
    def _log_initial_state(self):
        """Log initial system configuration"""
        self.log("--- Initial System State ---", "SYSTEM")
        
        # List USB devices
        try:
            result = subprocess.run(
                ["lsusb"], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            self.log("USB Devices:", "SYSTEM")
            for line in result.stdout.strip().split('\n'):
                self.log(f"  {line}", "SYSTEM")
        except Exception as e:
            self.log(f"Failed to list USB devices: {e}", "ERROR")
        
        # List ttyACM ports
        try:
            tty_devices = list(Path("/dev").glob("ttyACM*"))
            self.log(f"Motor Controller Ports: {len(tty_devices)} found", "SYSTEM")
            for dev in sorted(tty_devices):
                self.log(f"  {dev}", "SYSTEM")
        except Exception as e:
            self.log(f"Failed to list ttyACM devices: {e}", "ERROR")
        
        # Check USB power settings
        try:
            result = subprocess.run(
                ["lsusb", "-v"],
                capture_output=True,
                text=True,
                timeout=10
            )
            self.log("USB Power Requirements:", "SYSTEM")
            for line in result.stdout.split('\n'):
                if 'MaxPower' in line:
                    self.log(f"  {line.strip()}", "SYSTEM")
        except Exception as e:
            self.log(f"Failed to get USB power info: {e}", "ERROR")
        
        self.log("--- End Initial State ---\n", "SYSTEM")
    
    def monitor_usb_events(self):
        """Monitor kernel messages for USB events"""
        self.log("Starting USB event monitor", "MONITOR")
        
        try:
            # Use dmesg with follow mode
            proc = subprocess.Popen(
                ["dmesg", "-w", "--time-format", "iso"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            for line in iter(proc.stdout.readline, ''):
                if not self.running:
                    proc.terminate()
                    break
                
                line = line.strip()
                if not line:
                    continue
                
                # Look for USB-related messages
                usb_keywords = [
                    'usb', 'USB', 'ttyACM', 'disconnect', 'connect',
                    'device not accepting', 'reset', 'unable to enumerate',
                    'device descriptor', 'Port disabled'
                ]
                
                if any(keyword in line for keyword in usb_keywords):
                    event = {
                        'timestamp': time.time(),
                        'message': line
                    }
                    self.usb_events.append(event)
                    self.log(line, "USB_EVENT")
                    
                    # Check if this looks like a dropout
                    critical_keywords = ['disconnect', 'reset', 'unable to enumerate', 'Port disabled']
                    if any(keyword in line for keyword in critical_keywords):
                        self.log("⚠️  POTENTIAL DROPOUT EVENT DETECTED", "USB_EVENT")
                        self._analyze_recent_events()
        
        except Exception as e:
            self.log(f"USB monitor error: {e}", "ERROR")
    
    def monitor_tegrastats(self):
        """Monitor system power and resources using tegrastats"""
        self.log("Starting tegrastats power monitor", "MONITOR")
        
        try:
            # Check if tegrastats exists
            tegrastats_path = "/usr/bin/tegrastats"
            if not Path(tegrastats_path).exists():
                self.log("tegrastats not found - skipping power monitoring", "WARNING")
                return
            
            proc = subprocess.Popen(
                ["tegrastats", "--interval", "500"],  # 500ms interval
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            for line in iter(proc.stdout.readline, ''):
                if not self.running:
                    proc.terminate()
                    break
                
                line = line.strip()
                if not line:
                    continue
                
                # Parse tegrastats output for power info
                # Example: POM_5V_IN 5123/5123 POM_5V_GPU 563/563 POM_5V_CPU 2812/2812
                reading = {
                    'timestamp': time.time(),
                    'raw': line
                }
                
                # Extract power values
                if 'POM_5V' in line or 'VDD' in line or 'mW' in line:
                    self.power_readings.append(reading)
                    
                    # Log power info periodically (every 10 seconds)
                    if len(self.power_readings) % 20 == 0:
                        self.log(line, "POWER")
                    
                    # Detect power spikes (if we can parse the values)
                    try:
                        # Simple spike detection - log full reading if any value > 5000mW
                        if any(int(val) > 5000 for val in line.split() if val.isdigit()):
                            self.log(f"⚡ POWER SPIKE: {line}", "POWER_SPIKE")
                    except:
                        pass
        
        except Exception as e:
            self.log(f"Tegrastats monitor error: {e}", "ERROR")
    
    def monitor_motor_ports(self):
        """Monitor /dev/ttyACM* ports for changes"""
        self.log("Starting motor port monitor", "MONITOR")
        
        known_ports = set()
        
        while self.running:
            try:
                current_ports = set(Path("/dev").glob("ttyACM*"))
                
                # Detect new ports
                new_ports = current_ports - known_ports
                if new_ports:
                    for port in new_ports:
                        event = {
                            'timestamp': time.time(),
                            'port': str(port),
                            'action': 'appeared'
                        }
                        self.motor_events.append(event)
                        self.log(f"✅ Motor port appeared: {port}", "MOTOR_EVENT")
                
                # Detect removed ports
                removed_ports = known_ports - current_ports
                if removed_ports:
                    for port in removed_ports:
                        event = {
                            'timestamp': time.time(),
                            'port': str(port),
                            'action': 'disappeared'
                        }
                        self.motor_events.append(event)
                        self.log(f"❌ Motor port DISAPPEARED: {port}", "MOTOR_EVENT")
                        self.log("🚨 MOTOR DROPOUT DETECTED!", "MOTOR_EVENT")
                        self._analyze_recent_events()
                
                known_ports = current_ports
                time.sleep(0.1)  # Check every 100ms
                
            except Exception as e:
                self.log(f"Motor port monitor error: {e}", "ERROR")
                time.sleep(1)
    
    def _analyze_recent_events(self):
        """Analyze recent events when a dropout is detected"""
        self.log("\n" + "="*70, "ANALYSIS")
        self.log("📊 ANALYZING EVENTS AROUND DROPOUT", "ANALYSIS")
        self.log("="*70, "ANALYSIS")
        
        current_time = time.time()
        window = 5.0  # Look at 5 second window
        
        # Recent USB events
        recent_usb = [e for e in self.usb_events if current_time - e['timestamp'] < window]
        if recent_usb:
            self.log(f"\n🔌 Recent USB Events ({len(recent_usb)}):", "ANALYSIS")
            for event in recent_usb:
                self.log(f"  {event['message']}", "ANALYSIS")
        
        # Recent power readings
        recent_power = [e for e in self.power_readings if current_time - e['timestamp'] < window]
        if recent_power:
            self.log(f"\n⚡ Recent Power Readings ({len(recent_power)}):", "ANALYSIS")
            for reading in recent_power[-3:]:  # Last 3 readings
                self.log(f"  {reading['raw']}", "ANALYSIS")
        
        # Recent motor events
        recent_motors = [e for e in self.motor_events if current_time - e['timestamp'] < window]
        if recent_motors:
            self.log(f"\n🤖 Recent Motor Events ({len(recent_motors)}):", "ANALYSIS")
            for event in recent_motors:
                self.log(f"  {event['port']} - {event['action']}", "ANALYSIS")
        
        self.log("="*70 + "\n", "ANALYSIS")
    
    def run(self):
        """Start all monitoring threads"""
        threads = [
            threading.Thread(target=self.monitor_usb_events, daemon=True, name="USB-Monitor"),
            threading.Thread(target=self.monitor_tegrastats, daemon=True, name="Power-Monitor"),
            threading.Thread(target=self.monitor_motor_ports, daemon=True, name="Motor-Monitor"),
        ]
        
        for thread in threads:
            thread.start()
            time.sleep(0.1)
        
        # Main loop
        try:
            while self.running:
                # Check if duration has elapsed
                if self.duration and (time.time() - self.start_time) >= self.duration:
                    print("\n⏰ Monitoring duration elapsed")
                    break
                
                time.sleep(1)
        
        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user")
        
        finally:
            self.running = False
            print("\n🛑 Stopping monitors...")
            time.sleep(1)  # Give threads time to clean up
            
            self.log("\n=== DIAGNOSTICS SESSION ENDED ===", "SYSTEM")
            self.log(f"End Time: {datetime.now().isoformat()}", "SYSTEM")
            self.log(f"Total USB Events: {len(self.usb_events)}", "SYSTEM")
            self.log(f"Total Motor Events: {len(self.motor_events)}", "SYSTEM")
            self.log(f"Total Power Readings: {len(self.power_readings)}", "SYSTEM")
            
            print(f"\n✅ Diagnostic log saved to: {self.log_file}")
            print(f"📊 Captured {len(self.usb_events)} USB events, {len(self.motor_events)} motor events")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Monitor motor dropouts on Jetson with USB and power diagnostics"
    )
    parser.add_argument(
        "--duration",
        type=int,
        help="Monitoring duration in seconds (default: run until Ctrl+C)"
    )
    parser.add_argument(
        "--log-dir",
        default="logs",
        help="Directory for log files (default: logs/)"
    )
    
    args = parser.parse_args()
    
    monitor = MotorDropoutMonitor(
        log_dir=args.log_dir,
        duration_seconds=args.duration
    )
    
    monitor.run()

if __name__ == "__main__":
    main()

