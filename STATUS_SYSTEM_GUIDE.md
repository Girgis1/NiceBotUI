# Status Indicator System - Complete Guide

## Overview
The LerobotGUI now has a unified, centralized status indicator system that keeps Dashboard and Settings synchronized. All status indicators start blank (empty) on startup, then update automatically when devices are discovered.

## Architecture

### Central Coordinator: DeviceManager
Location: `utils/device_manager.py`

The DeviceManager is the **single source of truth** for all device status:
- Runs discovery on startup
- Emits Qt signals when status changes
- Both Dashboard and Settings listen to these signals
- Ensures status is always synchronized

### Status States

| State | Visual | Meaning |
|-------|--------|---------|
| **empty** | ⚪ (gray outline circle) | Device not configured or not found |
| **online** | 🟢 (solid green circle) | Device found and working |
| **offline** | 🔴 (solid red circle) | Device configured but not responding |

### Status Lifecycle

```
App Startup
    ↓
UI Initialized (all dots blank/empty)
    ↓
Window Shown (showEvent)
    ↓
100ms delay
    ↓
Device Discovery
    ├── Scan serial ports for robot
    ├── Scan /dev/video* for cameras
    ├── Match found devices to config
    ├── Print results to terminal
    └── Emit status signals
        ↓
        ├──> Dashboard indicators update
        └──> Settings indicators update
```

## Components

### 1. StatusIndicator Widget
Location: `tabs/dashboard_tab.py` (lines 65-131)

A custom `QLabel` subclass that displays colored circles:

```python
class StatusIndicator(QLabel):
    def __init__(self):
        self.null = False     # Blank/empty state
        self.connected = False # Green/online state
        self.warning = False   # Orange/warning state
    
    def set_null(self):      # → Gray outline
    def set_connected(bool)  # → Green (True) or Red (False)
    def set_warning(self)    # → Orange
```

**Key Features:**
- Initializes `null=False` to prevent attribute errors
- `update_style()` checks `hasattr(self, 'null')` for safety
- Clears conflicting states when setting new state
- Fixed size: 20x20px for consistency

### 2. CircularProgress (Throbber)
Location: `tabs/dashboard_tab.py` (lines 32-61)

Activity indicator that shows when robot is executing:

```python
class CircularProgress(QWidget):
    def __init__(self):
        self.setVisible(False)  # Hidden by default!
```

**Behavior:**
- **Startup:** Hidden, timer not running
- **Execution starts:** `setVisible(True)`, timer starts
- **Execution ends:** `setVisible(False)`, timer stops, progress reset to 0

### 3. Device Discovery
Location: `utils/device_manager.py` (lines 36-110)

```python
def discover_all_devices() -> Dict[str, any]:
    """
    1. Scan serial ports (/dev/ttyACM*, /dev/ttyUSB*)
    2. Scan cameras (/dev/video0-9)
    3. Match to config
    4. Emit signals
    5. Return results dict
    """
```

**Output:**
```python
{
    "robot": {
        "port": "/dev/ttyACM0",
        "motor_count": 6,
        "description": "LeRobot SO-100",
        "positions": [...]
    },
    "cameras": [
        {"index": 0, "path": "/dev/video0", "width": 640, "height": 480},
        {"index": 2, "path": "/dev/video2", "width": 640, "height": 480}
    ],
    "errors": []
}
```

## Signal Flow

```
DeviceManager.discover_all_devices()
    ↓
Found robot? → robot_status_changed.emit("online")
    ↓
    ├──> DashboardTab.on_robot_status_changed("online")
    │       └── robot_indicator1.set_connected(True)
    └──> SettingsTab.on_robot_status_changed("online")
            └── robot_status_circle.set_connected(True)

Found cameras? → camera_status_changed.emit("front", "online")
    ↓
    ├──> DashboardTab.on_camera_status_changed("front", "online")
    │       └── camera_indicator1.set_connected(True)
    └──> SettingsTab.on_camera_status_changed("front", "online")
            └── camera_front_circle.set_connected(True)
```

## Dashboard Integration

### Initialization
```python
def __init__(self, config, parent, device_manager):
    self.device_manager = device_manager
    
    # Create indicators (start as null/empty)
    self.robot_indicator1 = StatusIndicator()
    self.robot_indicator1.set_null()
    
    self.camera_indicator1 = StatusIndicator()
    self.camera_indicator1.set_null()
    
    # Connect signals
    if self.device_manager:
        device_manager.robot_status_changed.connect(self.on_robot_status_changed)
        device_manager.camera_status_changed.connect(self.on_camera_status_changed)
```

### Signal Handlers
```python
def on_robot_status_changed(self, status: str):
    if status == "empty":
        self.robot_status_circle.set_null()
    elif status == "online":
        self.robot_status_circle.set_connected(True)
    else:  # offline
        self.robot_status_circle.set_connected(False)
```

### Throbber Control
```python
def start_run(self):
    # Show throbber
    self.throbber.setVisible(True)
    self.throbber_update_timer.start(100)

def _reset_ui_after_run(self):
    # Hide throbber
    self.throbber.setVisible(False)
    self.throbber_update_timer.stop()
    self.throbber_progress = 0
```

## Settings Integration

### Manual Device Finding
When user clicks "Find Robot Ports" or "Find Cameras":

```python
def find_robot_ports(self):
    # Scan and show dialog
    selected_port = user_selection
    
    # Update local status
    self.robot_status = "online"
    self.update_status_circle(self.robot_status_circle, "online")
    
    # Update device_manager (propagates to Dashboard)
    if self.device_manager:
        self.device_manager.update_robot_status("online")
```

This ensures:
1. Settings tab shows updated status
2. Dashboard automatically updates via signal
3. Single source of truth maintained

## Disabled Legacy Code

To prevent conflicts with the new system:

### Dashboard
```python
def validate_config(self):
    """Now a no-op - device_manager handles validation"""
    pass

# Commented out:
# self.connection_check_timer = QTimer()
# self.connection_check_timer.start(10000)
```

### Why?
- Old code checked devices every 10 seconds
- Would override device_manager status
- Caused indicators to flicker or show wrong state
- Device_manager is now the only status updater

## Terminal Output

When app starts, you'll see:

```
============================================================
🔍 DEVICE DISCOVERY - Starting...
============================================================

⚪ ROBOT ARM: Not found

✅ CAMERAS FOUND: 2
   /dev/video0 - 640x480
   /dev/video2 - 640x480
   ✓ Wrist camera matched: /dev/video0
   ✓ Front camera matched: /dev/video2

============================================================
🔍 DEVICE DISCOVERY - Complete
============================================================
```

## Testing

### Standalone Test
```bash
cd /home/daniel/LerobotGUI
python test_device_discovery.py
```

This runs discovery without GUI, useful for debugging.

### Visual Test
1. Start app: `python app.py`
2. Check terminal output for discovery results
3. Check Dashboard status bar:
   - Should show blank circles initially
   - Updates to green/red after discovery
4. Go to Settings tab:
   - Status circles should match Dashboard
5. Click "Find Cameras" in Settings:
   - Settings updates
   - Dashboard should also update

## Extending the System

### Add New Device Type

1. **Update DeviceManager:**
```python
class DeviceManager:
    def __init__(self):
        self.sensor_status = "empty"
    
    sensor_status_changed = Signal(str)
    
    def _discover_sensors(self):
        # Scan logic
        if found:
            self.sensor_status = "online"
            self.sensor_status_changed.emit("online")
```

2. **Add to Dashboard:**
```python
def __init__(self):
    self.sensor_indicator = StatusIndicator()
    self.sensor_indicator.set_null()
    
    device_manager.sensor_status_changed.connect(self.on_sensor_status_changed)

def on_sensor_status_changed(self, status: str):
    if status == "empty":
        self.sensor_indicator.set_null()
    elif status == "online":
        self.sensor_indicator.set_connected(True)
```

3. **Add to Settings:**
```python
def find_sensors(self):
    # Scan logic
    if found:
        self.sensor_status = "online"
        if self.device_manager:
            self.device_manager.update_sensor_status("online")
```

## Benefits

✅ **Single Source of Truth**
- DeviceManager owns all status
- No conflicting updates
- Predictable behavior

✅ **Automatic Synchronization**
- Dashboard ↔ Settings always match
- Real-time updates via Qt signals
- No manual polling needed

✅ **Clean Startup**
- All indicators start blank
- No red errors before discovery
- Professional appearance

✅ **Extensible**
- Easy to add new device types
- Clean separation of concerns
- Testable components

✅ **User Friendly**
- Throbber only when needed
- Clear visual feedback
- Terminal output for debugging

## Troubleshooting

### Indicators Not Updating
1. Check device_manager is passed to tabs
2. Verify signal connections in `__init__`
3. Check terminal for discovery output
4. Test with `test_device_discovery.py`

### Throbber Always Spinning
1. Check `CircularProgress.__init__` sets `setVisible(False)`
2. Verify `_reset_ui_after_run()` stops timer
3. Ensure timer doesn't start in `__init__`

### Conflicting Status Updates
1. Ensure `validate_config()` is disabled
2. Check no other code calls `set_connected()` directly
3. Only device_manager should update status

### Discovery Not Running
1. Check `showEvent()` is defined in MainWindow
2. Verify `QTimer.singleShot(100, discover_devices_on_startup)`
3. Check for exceptions in device_manager methods

