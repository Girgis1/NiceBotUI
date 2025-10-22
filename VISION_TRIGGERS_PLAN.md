# Vision Triggers System - Implementation Plan

**Branch:** Vision (from dev)  
**Target:** Modular vision-based automation for robot sequencing  
**Screen:** 1024×600 touchscreen optimized  

---

## 🎯 Goals

1. **Idle Standby Mode** - Robot waits for objects to appear before starting work
2. **Multi-Zone Detection** - Trigger based on objects in specific areas
3. **Conditional Logic** - Count-based, presence-based, multi-zone AND/OR triggers
4. **Sequence Integration** - Vision triggers as optional sequence step conditions
5. **24/7 Reliability** - Memory-safe daemon, auto-restart, no leaks

---

## 📁 Architecture Overview

### **Modular Design (Following Existing Patterns)**

```
LerobotGUI/
├── vision_triggers/              # NEW: Vision system module
│   ├── __init__.py
│   ├── daemon.py                 # Main long-running process
│   ├── triggers_manager.py       # Manager class (like ActionsManager)
│   ├── composite_trigger.py      # Composite pattern (like CompositeRecording)
│   ├── zone_manager.py           # Zone storage and validation
│   ├── trigger_rules.py          # Condition evaluation engine
│   ├── ipc.py                    # File-based IPC with sequencer
│   ├── detectors/
│   │   ├── __init__.py
│   │   ├── presence.py           # Background subtraction detector
│   │   └── base.py               # Base detector interface
│   └── ui/
│       ├── __init__.py
│       ├── zone_editor.py        # 1024x600 touch zone drawing
│       └── trigger_config.py     # Trigger setup UI
│
├── data/
│   ├── vision_triggers/          # NEW: Trigger storage (folder-based)
│   │   ├── idle_standby/
│   │   │   ├── manifest.json
│   │   │   ├── zones.json
│   │   │   └── conditions.json
│   │   └── dual_box_check/
│   │       ├── manifest.json
│   │       ├── zones.json
│   │       └── conditions.json
│   └── backups/
│       └── vision_triggers/      # Timestamped backups
│
├── runtime/                      # NEW: Process state files
│   ├── vision_events.json        # Daemon → Sequencer
│   ├── robot_state.json          # Sequencer → Daemon
│   └── vision_daemon.pid
│
├── config/
│   └── vision_config.yaml        # Camera, detection, watchdog settings
│
└── tabs/
    └── vision_tab.py             # NEW: Vision triggers UI tab
```

---

## 🔧 Core Components

### **1. Data Models**

#### **Zone Model**
```python
{
    "zone_id": "zone_001",
    "name": "Box 1",
    "type": "trigger",  # trigger | count | quality_check
    "polygon": [[100, 200], [400, 200], [400, 500], [100, 500]],
    "enabled": true,
    "notes": ""
}
```

#### **Trigger Model (Composite Pattern)**
```
data/vision_triggers/idle_standby/
├── manifest.json          # Orchestration
├── zones.json             # Zone definitions
└── conditions.json        # Trigger logic
```

**manifest.json:**
```json
{
    "name": "Idle Standby Check",
    "trigger_id": "idle_standby",
    "type": "presence",
    "created_at": "2025-10-22T10:00:00",
    "modified_at": "2025-10-22T10:00:00",
    "description": "Wait for any object in work area",
    "enabled": true,
    "check_interval_seconds": 5.0,
    "active_when": {"robot_state": "home"},
    "action": {
        "type": "advance_sequence",
        "sequence_id": null
    },
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
            "zone_id": "work_area",
            "name": "Work Area",
            "type": "trigger",
            "polygon": [[200, 120], [1080, 120], [1080, 560], [200, 560]],
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
        "min_objects": 1,
        "zone": "work_area",
        "stability_frames": 2
    }
}
```

---

### **2. Manager Classes (Following Existing Pattern)**

#### **TriggersManager** (mirrors ActionsManager/SequencesManager)
```python
class TriggersManager:
    def __init__(self):
        self.triggers_dir = Path("data/vision_triggers")
        self.backups_dir = Path("data/backups/vision_triggers")
        self._ensure_directories()
    
    def list_triggers(self) -> List[str]:
        """Scan for folders with manifest.json"""
        
    def load_trigger(self, name: str) -> Optional[Dict]:
        """Load trigger with all components"""
        
    def save_trigger(self, name: str, trigger_data: dict) -> bool:
        """Save trigger with automatic backup"""
        
    def delete_trigger(self, name: str) -> bool:
        """Delete with backup"""
        
    def get_composite_trigger(self, name: str) -> Optional[CompositeTrigger]:
        """Get CompositeTrigger object for editing"""
```

---

### **3. Vision Daemon (Long-Running Process)**

#### **Key Features:**
- **Home-Gated:** Only runs detection when `robot_state == "home"`
- **Adaptive Frame Rate:** 0.2 fps idle → 2 fps active
- **Memory Limits:** Fixed buffers, periodic GC, hard caps
- **Watchdog:** Auto-restart on hang or memory exceed
- **Background Model:** Only updates when no objects present

#### **Main Loop:**
```python
while not stop_requested:
    # 1. Read robot state
    robot_state = read_state_file("runtime/robot_state.json")
    
    # 2. Gate by state
    if robot_state != "home":
        sleep(1.0)
        continue
    
    # 3. Capture frame at current fps
    frame = capture_frame()
    
    # 4. Run detection on active triggers
    for trigger in active_triggers:
        result = evaluate_trigger(frame, trigger)
        if result.triggered:
            write_event("runtime/vision_events.json", result)
            pause_for_cooldown()
    
    # 5. Memory check (every 100 frames)
    if frame_count % 100 == 0:
        check_memory_usage()
    
    # 6. Adaptive sleep
    sleep(current_interval)
```

---

### **4. IPC Layer (File-Based)**

#### **robot_state.json** (Sequencer → Daemon)
```json
{
    "state": "home",           # home | moving | working | error
    "moving": false,
    "current_sequence": "production_run",
    "accepting_triggers": true,
    "timestamp": 1730000000.123
}
```

#### **vision_events.json** (Daemon → Sequencer)
```json
{
    "last_check": 1730000000.5,
    "status": "triggered",     # idle | detecting | triggered | error
    "trigger_id": "idle_standby",
    "event": {
        "timestamp": 1730000000.5,
        "result": "PRESENT",
        "zone": "work_area",
        "confidence": 0.95,
        "boxes": [[420, 180, 120, 160]],
        "action": "advance_sequence"
    }
}
```

---

### **5. Sequence Integration**

#### **Extended Sequence Step Format:**
```json
{
    "step_type": "action",
    "action_name": "PickupBlock",
    "vision_trigger": {              # NEW: Optional
        "enabled": true,
        "trigger_id": "idle_standby",
        "timeout_seconds": 300,
        "on_timeout": "error"        # error | skip | continue
    }
}
```

#### **Sequencer Behavior:**
```python
for step in sequence.steps:
    if step.has_vision_trigger():
        # Wait for trigger
        result = wait_for_vision_trigger(
            trigger_id=step.vision_trigger.trigger_id,
            timeout=step.vision_trigger.timeout_seconds
        )
        
        if result == "timeout":
            handle_timeout(step.vision_trigger.on_timeout)
            continue
    
    # Execute step normally
    execute_step(step)
```

---

## 🎨 UI Components (1024×600 Touch-Optimized)

### **Vision Tab (New Main Tab)**

#### **Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│ Vision Triggers                          [Live View] [Edit] │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────────────┐  ┌─────────────────────────┐  │
│  │                         │  │  Active Triggers (3)    │  │
│  │   Live Camera Preview   │  │                         │  │
│  │   (640×480 scaled)      │  │  ☑ Idle Standby        │  │
│  │   [zones overlaid]      │  │    ● Waiting...        │  │
│  │                         │  │    Last: Never         │  │
│  │                         │  │                         │  │
│  │                         │  │  ☑ Dual Box Check      │  │
│  │                         │  │    ○ Inactive          │  │
│  │                         │  │                         │  │
│  │                         │  │  ☐ Count Exit          │  │
│  │                         │  │    (disabled)          │  │
│  └─────────────────────────┘  │                         │  │
│                                │  [+ Add Trigger]       │  │
│  Status: ● Running             └─────────────────────────┘  │
│  FPS: 0.2 (idle mode)                                       │
│  Memory: 124 MB / 512 MB                                    │
│                                                               │
│  [Start Daemon]  [Stop Daemon]  [Calibrate]  [Settings]    │
└─────────────────────────────────────────────────────────────┘
```

#### **Button Sizes:**
- Minimum: 72×72 px (touch target)
- Font: 20px minimum
- Margins: 12px safe area

---

### **Zone Editor UI**

#### **Touch Interactions:**
- **Tap** to add polygon vertex
- **Drag** vertex to reposition (24px handle radius)
- **Long-press** edge to insert vertex
- **Two-finger pinch** to zoom (future)

#### **Bottom Toolbar:**
```
[Add Point] [Undo] [Clear] [Save] [Cancel]
  72×72      72×72   72×72   72×72   72×72
```

---

## 🔄 Integration with Existing System

### **Phase 1: Standalone Daemon (Week 1)**
✅ Build core vision system independently  
✅ Test idle standby use case  
✅ Verify 24/7 reliability  

### **Phase 2: UI Integration (Week 2)**
✅ Add Vision tab to main app  
✅ Zone editor in settings  
✅ Trigger configuration UI  

### **Phase 3: Sequence Integration (Week 3)**
✅ Extend sequence step model  
✅ Update SequencesManager  
✅ Integrate with executor  

### **Phase 4: Production Ready (Week 4)**
✅ Calibration wizard  
✅ Watchdog + auto-restart  
✅ Documentation + examples  

---

## 🛡️ Memory Leak Prevention

### **Strategy:**
1. **Fixed-size buffers** (max 3 frames in memory)
2. **Periodic GC** every 100 detections
3. **Hard memory limit** (512 MB, restart if exceeded)
4. **Background model limit** (50-frame running average)
5. **Clear detection results** immediately after use
6. **Log rotation** (daily, keep 7 days)
7. **Watchdog monitoring** (external process checks health)

---

## 📝 Configuration Files

### **config/vision_config.yaml**
```yaml
# Camera
camera:
  index: 0
  width: 1280
  height: 720
  fps: 30
  exposure_auto: false
  white_balance_auto: false

# Detection
detection:
  mode: presence                  # presence | classifier (future)
  min_blob_area: 1200            # pixels²
  stability_check: true
  stability_frames: 2
  stability_delay_ms: 250

# Performance
performance:
  idle_fps: 0.2                  # 1 frame every 5 seconds
  active_fps: 2.0                # Speed up after detection
  max_fps: 10.0
  adaptive_framerate: true

# Memory
memory:
  max_memory_mb: 512
  frame_buffer_size: 3
  background_model_frames: 50
  cleanup_interval_detections: 100
  force_gc: true

# Watchdog
watchdog:
  enabled: true
  check_interval_seconds: 30
  restart_on_hang: true
  restart_on_memory_exceed: true
  max_restart_attempts: 3
  notify_on_restart: true

# State files
state:
  robot_state_file: runtime/robot_state.json
  vision_events_file: runtime/vision_events.json
  daemon_pid_file: runtime/vision_daemon.pid
```

---

## 🧪 Testing Strategy

### **Unit Tests:**
- Zone geometry (point-in-polygon, overlap detection)
- Trigger condition evaluation
- Manager save/load/delete operations

### **Integration Tests:**
- Daemon lifecycle (start, stop, restart)
- IPC communication
- Sequence integration

### **Stress Tests:**
- 24-hour continuous run
- Memory usage monitoring
- Multiple restart cycles

---

## 📚 Dependencies

### **New Packages (add to requirements.txt):**
```
opencv-contrib-python>=4.8.0
numpy>=1.24.0
pyyaml>=6.0
psutil>=5.9.0  # For memory monitoring
```

---

## 🚀 Development Workflow

### **Branch Strategy:**
- **Vision** branch (from dev)
- Regular commits after each TODO
- Test before merge to dev
- Merge to main after full Phase 4

### **Commit Message Format:**
```
vision: <description> @codex

Examples:
vision: Add TriggersManager with folder-based storage @codex
vision: Implement zone drawing UI for 1024x600 touch @codex
vision: Integrate vision triggers into sequence executor @codex
```

---

## 📖 Documentation Deliverables

1. **VISION_TRIGGERS_GUIDE.md** - User guide
2. **API.md** - Developer API reference
3. **TROUBLESHOOTING.md** - Common issues + solutions
4. **Example triggers** - Pre-configured templates

---

## ✅ Success Criteria

### **Phase 1 Complete When:**
- [ ] Daemon runs reliably for 24+ hours
- [ ] Memory usage stays under 200 MB
- [ ] Idle standby trigger works (5-second checks)
- [ ] Auto-restart on crash works

### **Phase 2 Complete When:**
- [ ] Zone editor works on 1024×600 touch
- [ ] Can create/edit/delete triggers via UI
- [ ] Live preview shows zones + detections

### **Phase 3 Complete When:**
- [ ] Sequences can use vision triggers
- [ ] "1 in box 1 AND 1 in box 2" condition works
- [ ] Count-based exit works

### **Phase 4 Complete When:**
- [ ] Calibration wizard complete
- [ ] Documentation written
- [ ] Production testing passed (8+ hour runs)

---

**Status:** ✅ Branch created, ready to begin Phase 1


