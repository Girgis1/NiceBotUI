

# Vision Triggers System - User Guide

**Version:** 1.0  
**For:** NiceBotUI Robot Control System

---

## 📖 Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Core Concepts](#core-concepts)
4. [Example Use Cases](#example-use-cases)
5. [Configuration](#configuration)
6. [Daemon Management](#daemon-management)
7. [Creating Triggers](#creating-triggers)
8. [Troubleshooting](#troubleshooting)
9. [API Reference](#api-reference)

---

## Overview

The Vision Triggers System enables your robot to detect objects via camera and trigger actions automatically. Perfect for:

- **Idle Standby Mode** - Robot waits for parts to arrive before starting work
- **Multi-Zone Detection** - Trigger when objects appear in multiple locations
- **Count-Based Actions** - Exit after processing N items
- **Quality Control** - Detect defects or missing parts (future)

### Key Features

✅ **24/7 Reliable** - Memory-safe daemon, auto-restart  
✅ **Adaptive Performance** - Slow polling when idle, fast when active  
✅ **Home-Gated** - Only detects when robot is safe at home position  
✅ **Modular Storage** - Triggers saved like Actions/Sequences  
✅ **Touch-Optimized** - UI designed for 1024×600 touchscreens  

---

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Includes: `opencv-python`, `numpy`, `pyyaml`, `psutil`

### 2. Create Example Triggers

```bash
python vision_triggers/create_examples.py
```

Creates 3 pre-configured triggers:
- **Idle Standby** - Wait for any object (enabled by default)
- **Dual Box Check** - Both boxes filled (disabled)
- **Count Exit** - After 10 items (disabled)

### 3. Configure Camera

Edit `config/vision_config.yaml`:

```yaml
camera:
  index: 0          # Camera device index
  width: 1280
  height: 720
```

Find your camera index:

```bash
# List cameras
ls /dev/video*

# Test camera 0
python -c "import cv2; cap = cv2.VideoCapture(0); print(cap.isOpened())"
```

### 4. Start Vision Daemon

```bash
python vision_triggers/daemon.py
```

You should see:
```
============================================================
Vision Triggers Daemon
============================================================

[DAEMON] Initialized (PID: 12345)
[DAEMON] ✓ Loaded config from config/vision_config.yaml
[IPC] ✓ Initialized IPC system
[DAEMON] ✓ Camera 0 opened
[PRESENCE] ✓ Detector initialized
[DAEMON] Loaded 1 active triggers
  - Idle Standby (presence)
[DAEMON] ✓ Starting main loop
```

### 5. Test in Your Sequencer

Update your sequencer to write robot state:

```python
from vision_triggers.ipc import IPCManager
from pathlib import Path

ipc = IPCManager(Path("runtime"))

# When robot is at home and ready
ipc.write_robot_state(
    state="home",
    moving=False,
    accepting_triggers=True
)

# Check for vision events
event = ipc.read_vision_event()
if event and event['status'] == 'triggered':
    print(f"🎯 Trigger fired: {event['trigger_id']}")
    # Advance sequence or start action
```

---

## Core Concepts

### Zones

**Zones** are polygons (regions of interest) where objects are detected.

```python
zone = {
    "zone_id": "work_area",
    "name": "Work Area",
    "type": "trigger",  # trigger | count | quality_check
    "polygon": [[200, 120], [1080, 120], [1080, 560], [200, 560]],
    "enabled": True,
    "notes": "Main detection area"
}
```

**Zone Types:**
- `trigger` - Presence/absence detection
- `count` - Count objects inside
- `quality_check` - Future quality inspection

### Triggers

**Triggers** combine zones with conditions to fire actions.

**Trigger Types:**
1. **Presence** - Object present/absent in zone
2. **Count** - N objects in zone (with operators: `>=`, `<=`, `==`, `>`, `<`)
3. **Multi-Zone** - Multiple zones with AND/OR logic

**Actions:**
- `advance_sequence` - Move to next step
- `start_sequence` - Start specific sequence
- `stop` - Stop current operation
- `alert` - Show alert only

### Home-Gating

The daemon only detects when:
- Robot state == `"home"`
- `accepting_triggers` == `True`

This prevents false triggers while robot is moving.

---

## Example Use Cases

### Use Case 1: Idle Standby

**Scenario:** Robot waits for parts to arrive, checking once every 5 seconds.

**Trigger:** Idle Standby (included in examples)

**Config:**
```yaml
Type: presence
Zone: work_area (large area covering workspace)
Check Interval: 5.0 seconds
Action: advance_sequence
```

**Behavior:**
1. Daemon checks every 5 seconds
2. When object appears → background model detects change
3. Confirms object is stationary (2 frames)
4. Fires trigger → Sequencer advances to pickup step

### Use Case 2: Dual-Part Assembly

**Scenario:** Start assembly only when BOTH parts are present.

**Trigger:** Dual Box Check (included in examples)

**Config:**
```yaml
Type: multi_zone
Zones:
  - box_1: Left input
  - box_2: Right input
Logic: AND
Action: start_sequence (sequence_id: "dual_assembly")
```

**Behavior:**
1. Checks both zones
2. Only triggers when objects in BOTH zones
3. Starts specific assembly sequence

### Use Case 3: Batch Processing

**Scenario:** Process items until 10 are completed.

**Trigger:** Count Exit (included in examples)

**Config:**
```yaml
Type: count
Zone: output_bin
Target Count: 10
Operator: ">="
Cumulative: true
Action: advance_sequence
```

**Behavior:**
1. Counts objects in output bin
2. Accumulates count across frames
3. When count >= 10 → exits to next sequence

### Use Case 4: Object-Based Routing

**Scenario:** Different objects → different sequences.

**Setup:** Multiple presence triggers, one per product type.

```python
# Trigger 1: Small rectangular items
zones = [{"zone_id": "small_area", "polygon": [...]}]
action = {"type": "start_sequence", "sequence_id": "handle_small"}

# Trigger 2: Large circular items  
zones = [{"zone_id": "large_area", "polygon": [...]}]
action = {"type": "start_sequence", "sequence_id": "handle_large"}
```

---

## Configuration

### vision_config.yaml

Located in `config/vision_config.yaml`

#### Camera Settings

```yaml
camera:
  index: 0                    # Device index (0, 1, 2, ...)
  width: 1280                 # Capture resolution
  height: 720
  fps: 30                     # Camera FPS
  exposure_auto: false        # Lock exposure for stability
  white_balance_auto: false   # Lock white balance
```

#### Detection Settings

```yaml
detection:
  min_blob_area: 1200         # Minimum object size (pixels²)
  stability_check: true       # Require stationary objects
  stability_frames: 2         # Frames to confirm stability
  
  background:
    learning_rate: 0.001      # Background adapt speed (lower = more stable)
    var_threshold: 16         # Detection sensitivity
    detect_shadows: false     # Shadow detection (adds CPU load)
    history: 50               # Background model history
```

**Tuning Detection:**
- **Too sensitive?** Increase `min_blob_area` or `var_threshold`
- **Missing objects?** Decrease `min_blob_area` or `var_threshold`
- **False triggers from movement?** Increase `stability_frames`

#### Performance Settings

```yaml
performance:
  idle_fps: 0.2               # FPS when idle (1 frame / 5 sec)
  active_fps: 2.0             # FPS after detection
  max_fps: 10.0               # Maximum FPS cap
  adaptive_framerate: true    # Auto-adjust based on activity
  return_to_slow_after_seconds: 30
```

#### Memory Management

```yaml
memory:
  max_memory_mb: 512          # Hard limit (restarts if exceeded)
  frame_buffer_size: 3        # Max frames in memory
  cleanup_interval_detections: 100  # GC every N detections
  force_gc: true              # Force garbage collection
```

---

## Daemon Management

### Starting the Daemon

**Manual Start:**
```bash
python vision_triggers/daemon.py
```

**Background Start:**
```bash
python vision_triggers/daemon.py &
# Save PID
echo $! > runtime/vision_daemon.pid
```

**With Logging:**
```bash
python vision_triggers/daemon.py 2>&1 | tee logs/vision_daemon.log &
```

### Stopping the Daemon

**Graceful Shutdown:**
```bash
kill -SIGINT $(cat runtime/vision_daemon.pid)
```

**Or use IPC:**
```python
from vision_triggers.ipc import IPCManager
from pathlib import Path

ipc = IPCManager(Path("runtime"))
pid = ipc.read_daemon_pid()
if pid:
    os.kill(pid, signal.SIGINT)
```

### Checking Daemon Status

```python
from vision_triggers.ipc import IPCManager
from pathlib import Path

ipc = IPCManager(Path("runtime"))

if ipc.is_daemon_running():
    print("✓ Daemon is running")
    event = ipc.read_vision_event()
    print(f"Status: {event['status']}")
else:
    print("✗ Daemon is not running")
```

### Auto-Restart on Crash

The daemon will auto-restart if memory limit is exceeded. For external crashes, use a supervisor:

**systemd service example:**
```ini
[Unit]
Description=Vision Triggers Daemon
After=network.target

[Service]
Type=simple
User=daniel
WorkingDirectory=/home/daniel/LerobotGUI
ExecStart=/home/daniel/LerobotGUI/.venv/bin/python vision_triggers/daemon.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## Creating Triggers

### Method 1: Using TriggersManager (Programmatic)

```python
from vision_triggers.triggers_manager import TriggersManager

manager = TriggersManager()

# Define zones
zones = [{
    "zone_id": "my_zone",
    "name": "My Zone",
    "type": "trigger",
    "polygon": [[100, 100], [400, 100], [400, 300], [100, 300]],
    "enabled": True,
    "notes": ""
}]

# Define conditions
conditions = {
    "condition_type": "presence",
    "rules": {
        "zone": "my_zone",
        "min_objects": 1,
        "stability_frames": 2
    }
}

# Save trigger
manager.save_trigger(
    name="My Trigger",
    trigger_type="presence",
    zones=zones,
    conditions=conditions,
    check_interval=5.0,
    enabled=True,
    action={"type": "advance_sequence"},
    description="My custom trigger"
)
```

### Method 2: Manually Creating Files

Create folder structure:
```
data/vision_triggers/my_trigger/
├── manifest.json
├── zones.json
└── conditions.json
```

**manifest.json:**
```json
{
  "name": "My Trigger",
  "trigger_id": "my_trigger",
  "type": "presence",
  "enabled": true,
  "check_interval_seconds": 5.0,
  "active_when": {"robot_state": "home"},
  "action": {"type": "advance_sequence"},
  "components": {
    "zones": "zones.json",
    "conditions": "conditions.json"
  }
}
```

**zones.json:**
```json
{
  "zones": [
    {
      "zone_id": "my_zone",
      "name": "My Zone",
      "type": "trigger",
      "polygon": [[100, 100], [400, 100], [400, 300], [100, 300]],
      "enabled": true
    }
  ]
}
```

**conditions.json:**
```json
{
  "condition_type": "presence",
  "rules": {
    "zone": "my_zone",
    "min_objects": 1,
    "stability_frames": 2
  }
}
```

### Method 3: Copy and Modify Examples

```bash
# Copy existing trigger
cp -r data/vision_triggers/idle_standby data/vision_triggers/my_trigger

# Edit manifest.json to change name, zones, conditions
nano data/vision_triggers/my_trigger/manifest.json
```

---

## Troubleshooting

### Camera Not Found

**Error:** `Failed to open camera 0`

**Solutions:**
1. Check camera is connected: `ls /dev/video*`
2. Test camera: `python -c "import cv2; cap = cv2.VideoCapture(0); print(cap.isOpened())"`
3. Try different index: Edit `config/vision_config.yaml` → `camera: index: 1`
4. Check permissions: `sudo usermod -aG video $USER` (logout/login)

### No Detections

**Problem:** Objects present but no triggers firing

**Solutions:**
1. **Check lighting** - Ensure consistent, even lighting
2. **Recalibrate background** - Restart daemon to reset background model
3. **Adjust sensitivity** - Lower `min_blob_area` in config
4. **Check zones** - Verify polygon covers object location
5. **Stability too strict** - Reduce `stability_frames` to 1

### False Triggers

**Problem:** Triggers firing when nothing present

**Solutions:**
1. **Increase `min_blob_area`** - Filter out small noise
2. **Increase `var_threshold`** - Less sensitive to changes
3. **Lock exposure/white balance** - Prevents lighting drift
4. **Add exclusion zones** - Block areas with movement (future feature)

### High Memory Usage

**Problem:** Daemon memory exceeds limit

**Solutions:**
1. **Reduce `history`** - Smaller background model
2. **Increase `cleanup_interval`** - More frequent GC
3. **Lower resolution** - Reduce camera width/height
4. **Increase `max_memory_mb`** - If system has RAM available

### Slow Performance

**Problem:** Low FPS, laggy detection

**Solutions:**
1. **Disable shadows** - Set `detect_shadows: false`
2. **Lower resolution** - 720p instead of 1080p
3. **Increase `check_interval`** - Check less frequently
4. **Reduce zones** - Fewer zones = faster processing

### Daemon Crashes

**Problem:** Daemon exits unexpectedly

**Solutions:**
1. **Check logs** - `logs/vision_daemon.log` for errors
2. **Memory limit** - Daemon auto-restarts on memory exceed
3. **Camera disconnected** - Reconnect camera, restart daemon
4. **Use supervisor** - systemd or similar to auto-restart

---

## API Reference

### TriggersManager

```python
from vision_triggers.triggers_manager import TriggersManager

manager = TriggersManager()

# List all triggers
triggers = manager.list_triggers()  # Returns: List[str]

# Load trigger data
data = manager.load_trigger("Idle Standby")  # Returns: Dict

# Save trigger
success = manager.save_trigger(
    name="My Trigger",
    trigger_type="presence",  # presence | count | multi_zone
    zones=[...],
    conditions={...},
    check_interval=5.0,
    enabled=True,
    action={"type": "advance_sequence"},
    description="Description"
)  # Returns: bool

# Delete trigger
success = manager.delete_trigger("My Trigger")  # Returns: bool

# Check if exists
exists = manager.trigger_exists("My Trigger")  # Returns: bool

# Get enabled triggers
enabled = manager.get_enabled_triggers()  # Returns: List[str]
```

### IPCManager

```python
from vision_triggers.ipc import IPCManager
from pathlib import Path

ipc = IPCManager(Path("runtime"))

# Write robot state (sequencer → daemon)
ipc.write_robot_state(
    state="home",  # home | moving | working | error
    moving=False,
    current_sequence="my_sequence",
    accepting_triggers=True
)

# Read robot state (daemon reads)
state = ipc.read_robot_state()  # Returns: Dict

# Read vision event (sequencer reads)
event = ipc.read_vision_event()  # Returns: Dict | None

# Clear event after processing
ipc.clear_vision_event()

# Daemon PID management
ipc.write_daemon_pid(os.getpid())
pid = ipc.read_daemon_pid()  # Returns: int | None
is_running = ipc.is_daemon_running()  # Returns: bool
```

### Zone

```python
from vision_triggers.zone import Zone

# Create zone
zone = Zone(
    name="Work Area",
    polygon=[[100, 100], [400, 100], [400, 300], [100, 300]],
    zone_type=Zone.TYPE_TRIGGER,  # TYPE_TRIGGER | TYPE_COUNT | TYPE_QUALITY
    enabled=True
)

# Point-in-polygon test
is_inside = zone.point_in_polygon(250, 200)  # Returns: bool

# Get bounding box
x_min, y_min, x_max, y_max = zone.get_bounding_box()

# Serialize
zone_dict = zone.to_dict()
json_str = zone.to_json()

# Deserialize
zone = Zone.from_dict(zone_dict)
zone = Zone.from_json(json_str)
```

---

## Best Practices

### 1. Start Simple

Begin with a single presence trigger before adding complex multi-zone logic.

### 2. Calibrate Background

When starting, let daemon run for 10-20 frames with empty workspace to build good background model.

### 3. Use Stable Lighting

Lock camera exposure and white balance. Avoid windows with changing sunlight.

### 4. Design Clear Zones

Make zones slightly larger than objects to handle positioning variation.

### 5. Test Thoroughly

Test with actual parts in various positions before production use.

### 6. Monitor Memory

Check daemon stats periodically:
```bash
tail -f logs/vision_daemon.log | grep "Stats:"
```

### 7. Backup Triggers

Automatic backups in `data/backups/vision_triggers/` - keep them!

### 8. Version Control

Commit trigger configurations to git for tracking changes.

---

## Support & Contributing

**Issues:** Check `TROUBLESHOOTING` section above

**Documentation:** This guide + docstrings in code

**Examples:** `vision_triggers/create_examples.py`

**Testing:** All core modules have `if __name__ == "__main__"` tests

---

## Roadmap

### Phase 1 ✅ (Current)
- [x] Core detection engine
- [x] Presence, count, multi-zone triggers
- [x] Daemon with memory management
- [x] IPC system
- [x] Example triggers

### Phase 2 🚧 (Next)
- [ ] Touch-friendly Zone Editor UI
- [ ] Vision tab in main app
- [ ] Sequence integration
- [ ] Live camera preview

### Phase 3 📋 (Future)
- [ ] ML-based object classification
- [ ] Quality inspection triggers
- [ ] Barcode/QR code reading
- [ ] Multi-camera support

---

**Version:** 1.0.0  
**Last Updated:** October 22, 2025  
**Author:** NiceBotUI Vision Team

