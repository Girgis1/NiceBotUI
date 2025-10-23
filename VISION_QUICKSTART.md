# Vision Triggers - Quick Start Guide

## 🚀 Three Ways to Use Vision Triggers

### 1. **Standalone Mode** (Testing & Debugging)
```bash
python vision_app.py --vision
```

**Features:**
- 75% camera preview with zone overlays
- 25% control panel (start/stop daemon, enable triggers)
- Perfect for testing without running main app
- Can be quit separately if it crashes

---

### 2. **Integrated Mode** (From Main App)

**In Record Tab:**
1. Click **👁️ VISION** button (top bar, right of SAVE)
2. Configure zones and triggers
3. Add vision checks to your recordings

**In Sequence Tab:**
1. Click **👁️ VISION** button (top bar, right of SAVE)
2. Configure triggers for sequence steps
3. Enable/disable triggers as needed

**From terminal (if main app running):**
```bash
cd /home/daniel/LerobotGUI
python app.py
# Then click VISION button in Record or Sequence tab
```

---

### 3. **Daemon Only** (Background Service)

**Start daemon:**
```bash
python vision_triggers/daemon.py &
```

**Check if running:**
```bash
cat runtime/vision_daemon.pid
ps -p $(cat runtime/vision_daemon.pid)
```

**Stop daemon:**
```bash
kill $(cat runtime/vision_daemon.pid)
```

**View daemon status:**
```bash
cat runtime/vision_daemon_status.json
```

---

## 📝 Current Workflow

### Step 1: Create Example Triggers
```bash
python vision_triggers/create_examples.py
```

This creates 3 example triggers:
- **idle_standby** - Detect any object presence
- **dual_box_check** - Check two zones (AND logic)
- **count_exit** - Count objects passing through

### Step 2: Start Daemon
```bash
python vision_triggers/daemon.py &
```

### Step 3: Test with Test Script
```bash
python test_vision.py
```

This will:
- Set robot state to HOME
- Enable trigger acceptance
- Monitor for vision events
- Print when triggers fire

### Step 4: Or Open Vision UI
```bash
python vision_app.py --vision
```

This will:
- Show live camera feed
- Display configured zones
- Allow enabling/disabling triggers
- Start/stop daemon from UI

---

## 🎛️ Vision UI Controls

### Camera Preview (Left 75%)
- Shows live camera feed
- Overlays all enabled zones (green polygons)
- Zone names displayed on overlay
- **Draw Zone** button to create new zones

### Control Panel (Right 25%)

**Daemon Status:**
- ● Green dot = Running
- ● Red dot = Stopped
- **Start Daemon** / **Stop Daemon** buttons

**Triggers List:**
- Checkboxes to enable/disable each trigger
- Click to select and view info
- **Refresh** to reload from disk
- **+ Add** to create new (opens wizard)

**Trigger Info:**
- Shows details of selected trigger
- Type, zones, conditions, etc.

---

## ⚙️ Configuration Files

### `config/vision_config.yaml`
Edit camera settings:
```yaml
camera:
  index: 0    # Change to 1, 2, 3 for different cameras
  width: 640
  height: 480
  fps: 30
```

Edit detection settings:
```yaml
detector:
  min_blob_area: 1200   # Minimum object size in pixels
  stability_frames: 2    # How many frames to confirm
```

### `data/vision_triggers/triggers/`
Folder-based trigger storage:
```
triggers/
├── idle_standby/
│   ├── manifest.json
│   └── zones.json
├── dual_box_check/
│   └── ...
└── count_exit/
    └── ...
```

---

## 🔧 Troubleshooting

### Camera Not Opening
```bash
# List cameras
ls -l /dev/video*

# Test camera 0
python -c "import cv2; cap = cv2.VideoCapture(0); print('OK' if cap.isOpened() else 'FAIL')"

# Try different index in vision_config.yaml
```

### Daemon Won't Start
```bash
# Check if already running
ps aux | grep daemon.py

# Kill existing
kill $(cat runtime/vision_daemon.pid)

# Check logs
tail -f runtime/vision_daemon_status.json
```

### Triggers Not Firing
1. Check daemon is running (green dot in UI)
2. Verify robot state is HOME (test_vision.py sets this)
3. Check trigger is enabled (checkbox in UI)
4. Adjust detection sensitivity in vision_config.yaml
5. Place object clearly in zone, avoid shadows/glare

### Vision UI Won't Open from Main App
```bash
# Test standalone first
python vision_app.py --vision

# Check for import errors
python -c "from vision_app import VisionApp; print('OK')"
```

---

## 🎯 Next Steps (Coming Soon)

Current features are **Phase 1** - Core Engine:
- ✅ Standalone daemon
- ✅ Basic UI with camera preview
- ✅ Enable/disable triggers
- ✅ Integration buttons in main app

**Phase 2** - Full UI:
- ⏳ Draw zones with mouse/touch
- ⏳ Trigger configuration wizard
- ⏳ Add vision steps to sequences
- ⏳ Live debugging overlay
- ⏳ Calibration wizard

---

## 📚 More Information

- **Full Guide:** `VISION_TRIGGERS_GUIDE.md`
- **Implementation Plan:** `VISION_TRIGGERS_PLAN.md`
- **Status:** `VISION_STATUS.md`

---

## 💡 Tips

1. **Test standalone first** (`--vision` flag) before integrating
2. **Start with example triggers** (create_examples.py) 
3. **Use test_vision.py** to simulate sequencer communication
4. **Daemon runs independently** - main app can crash without affecting vision
5. **Zones are persistent** - saved to disk, reload on daemon restart
6. **Home-gated by default** - only checks when robot state is "home"

---

## 🐛 Known Limitations (Phase 1)

- Cannot draw zones yet (use create_examples.py to generate)
- Trigger creation is manual (edit JSON or use Python)
- No visual debugging overlay yet
- No sequence integration yet (vision steps coming in Phase 2)

These will be addressed in Phase 2!


