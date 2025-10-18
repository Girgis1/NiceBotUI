# Robust & Modular Architecture

## 🏗️ **Overview**

The LerobotGUI has been refactored to use a robust, modular, file-based architecture designed for industrial reliability.

---

## 📁 **New File Structure**

```
LerobotGUI/
├── data/
│   ├── recordings/           # Individual recording files (NEW)
│   │   ├── grab_cup_v1.json
│   │   ├── place_block.json
│   │   └── inspection_scan.json
│   ├── sequences/            # Individual sequence files (NEW)
│   │   ├── production_run_v2.json
│   │   ├── quality_check.json
│   │   └── assembly_task.json
│   └── backups/              # Automatic backups (NEW)
│       ├── recordings/
│       │   ├── grab_cup_v1_20251018_143022.json
│       │   └── ...
│       ├── sequences/
│       │   └── ...
│       └── migration/
│           ├── actions_20251018_120000.json
│           └── sequences_20251018_120000.json
├── utils/
│   ├── actions_manager.py    # Manages individual recording files
│   ├── sequences_manager.py  # Manages individual sequence files
│   ├── execution_manager.py  # Unified execution system (NEW)
│   ├── motor_controller.py   # Motor control with position verification
│   └── migrate_data.py       # Migration script (NEW)
└── tabs/
    └── dashboard_tab.py      # Unified dashboard (UPDATED)
```

---

## 🎯 **Key Improvements**

### **1. Individual File Storage**

**OLD (Fragile):**
```json
// data/actions.json - ALL recordings in one file
{
  "actions": {
    "GrabCup_v1": {...},
    "PlaceBlock": {...},
    "InspectionScan": {...}
  }
}
```

**NEW (Robust):**
```
data/recordings/
  - grab_cup_v1.json
  - place_block.json
  - inspection_scan.json
```

**Benefits:**
- ✅ No single point of failure
- ✅ Version control friendly (git tracks each file)
- ✅ Parallel editing safe
- ✅ Faster load times (load only what you need)
- ✅ Easy to backup/restore individual items

### **2. Automatic Backups**

Every save creates a timestamped backup:
```
data/backups/recordings/grab_cup_v1_20251018_143022.json
                                       ↑ timestamp
```

**Backup Policy:**
- Keep last 10 backups per recording
- Automatic cleanup of old backups
- Backup before deletion (final safety net)

### **3. Safe Filename Sanitization**

User-friendly names → safe filenames:

| User Name | Safe Filename |
|-----------|--------------|
| "Grab Cup v1" | `grab_cup_v1.json` |
| "Pick & Place!" | `pick_place.json` |
| "Inspection/QC #2" | `inspection_qc_2.json` |

### **4. Rich Metadata**

Each recording includes:
```json
{
  "name": "Grab Cup v1",
  "type": "live_recording",
  "speed": 100,
  "positions": [...],
  "recorded_data": [...],
  "metadata": {
    "created": "2025-10-18T14:30:22+11:00",
    "modified": "2025-10-18T15:45:10+11:00",
    "version": "1.0",
    "file_format": "lerobot_recording"
  }
}
```

---

## 🚀 **Unified Execution System**

### **Dashboard Integration**

The Dashboard now executes **all three types** from a single interface:

```
┌─────────────────────────────────────┐
│ RUN: [🤖 Model: GrabBlock     ▼]   │  ← Dropdown with all types
│      [✓ last              ▼]       │  ← Checkpoint selector (for models)
├─────────────────────────────────────┤
│ Episodes: [10]  Time: [20s] [START]│  ← Press START to run anything
└─────────────────────────────────────┘
```

**Dropdown Options:**
- 🤖 **Model: GrabBlock** → Runs trained policy (async inference)
- 🔗 **Sequence: Production Run v2** → Runs sequence of steps
- 🎬 **Action: Grab Cup v1** → Plays back recording

### **Execution Flow**

```mermaid
User clicks START
    ↓
Parse selection (Model/Sequence/Recording)
    ↓
Create ExecutionWorker
    ↓
    ├─ Model → RobotWorker (async inference)
    ├─ Recording → MotorController (direct playback)
    └─ Sequence → Execute steps (recordings, delays, models)
    ↓
Real-time progress updates
    ↓
Completion notification
```

---

## 📝 **Recording Data Format**

### **Simple Position Recording**

```json
{
  "name": "Waypoint 1",
  "type": "position",
  "speed": 100,
  "positions": [
    {
      "name": "Position 1",
      "motor_positions": [2048, 2048, 2048, 2048, 2048, 2048],
      "velocity": 600
    }
  ],
  "delays": {},
  "metadata": {...}
}
```

### **Live Recording (Time-based)**

```json
{
  "name": "Complex Motion",
  "type": "live_recording",
  "speed": 100,
  "recorded_data": [
    {
      "positions": [2048, 2048, 2048, 2048, 2048, 2048],
      "timestamp": 0.000,
      "velocity": 600
    },
    {
      "positions": [2051, 2049, 2047, 2048, 2048, 2048],
      "timestamp": 0.053,
      "velocity": 600
    },
    ...
  ],
  "metadata": {...}
}
```

---

## 🔗 **Sequence Data Format**

```json
{
  "name": "Production Run v2",
  "steps": [
    {
      "type": "recording",
      "name": "Grab Cup v1"
    },
    {
      "type": "delay",
      "duration": 2.0
    },
    {
      "type": "recording",
      "name": "Place Block"
    },
    {
      "type": "model",
      "task": "GrabBlock",
      "checkpoint": "last",
      "duration": 25.0
    }
  ],
  "loop": false,
  "metadata": {
    "created": "2025-10-18T14:30:22+11:00",
    "modified": "2025-10-18T15:45:10+11:00",
    "step_count": 4
  }
}
```

---

## 🔄 **Migration from Old Format**

### **Automatic Migration**

```bash
cd /home/daniel/LerobotGUI
python utils/migrate_data.py
```

**What it does:**
1. ✅ Reads old `data/actions.json` and `data/sequences.json`
2. ✅ Converts each item to individual file
3. ✅ Creates timestamped backups of old files
4. ✅ Shows migration summary

**Example Output:**
```
==============================================================
LeRobotGUI Data Migration
Converting to robust individual-file format
==============================================================

[MIGRATE] Reading old actions.json...
[MIGRATE] Found 5 actions to migrate
  ✓ Migrated: GrabCup_v1 -> grab_cup_v1.json
  ✓ Migrated: PlaceBlock -> place_block.json
  ✓ Migrated: InspectionScan -> inspection_scan.json
  ✓ Migrated: PickPart -> pick_part.json
  ✓ Migrated: AssemblyTask -> assembly_task.json
[MIGRATE] Backed up old actions.json to: ...

[MIGRATE] Reading old sequences.json...
[MIGRATE] Found 2 sequences to migrate
  ✓ Migrated: ProductionRun -> production_run.json
  ✓ Migrated: QualityCheck -> quality_check.json
[MIGRATE] Backed up old sequences.json to: ...

==============================================================
Migration Summary
==============================================================
Actions migrated:   5
Sequences migrated: 2

✓ Migration completed successfully!
```

---

## 🎮 **Usage Examples**

### **1. Run a Recording from Dashboard**

```python
# User Interface:
1. Select "🎬 Action: Grab Cup v1" from RUN dropdown
2. Click START
3. Recording plays back with position verification
```

### **2. Run a Sequence from Dashboard**

```python
# User Interface:
1. Select "🔗 Sequence: Production Run v2" from RUN dropdown
2. Click START
3. Sequence executes all steps in order
```

### **3. Run a Trained Model from Dashboard**

```python
# User Interface:
1. Select "🤖 Model: GrabBlock" from RUN dropdown
2. Select checkpoint (e.g., "✓ last") from checkpoint dropdown
3. Click START
4. Model runs via async inference
```

### **4. Programmatic API**

```python
from utils.actions_manager import ActionsManager
from utils.sequences_manager import SequencesManager
from utils.execution_manager import ExecutionWorker

# Save a recording
actions_mgr = ActionsManager()
actions_mgr.save_action("Grab Cup v1", {
    "type": "position",
    "speed": 100,
    "positions": [...]
})

# Save a sequence
sequences_mgr = SequencesManager()
sequences_mgr.save_sequence("Production Run", [
    {"type": "recording", "name": "Grab Cup v1"},
    {"type": "delay", "duration": 2.0},
    {"type": "recording", "name": "Place Block"}
])

# Execute a recording
worker = ExecutionWorker(config, "recording", "Grab Cup v1")
worker.execution_completed.connect(on_completed)
worker.start()
```

---

## 🛡️ **Error Handling & Robustness**

### **File Corruption Protection**

```python
# If a file is corrupted, only that ONE file is affected
# The rest of your data is safe

try:
    recording = actions_mgr.load_action("corrupted_file")
except Exception:
    # Fallback: use filename instead
    print("File corrupted, using backup...")
```

### **Backup Recovery**

```bash
# Oops, I deleted "grab_cup_v1.json"!
# No problem, restore from backup:

cd data/backups/recordings/
cp grab_cup_v1_20251018_143022.json ../../recordings/grab_cup_v1.json
```

### **Safe Concurrent Access**

- ✅ Each file is independent
- ✅ No race conditions when saving different recordings
- ✅ Git-friendly (no merge conflicts on unrelated changes)

---

## 📊 **Performance Comparison**

| Aspect | OLD (Single File) | NEW (Individual Files) |
|--------|------------------|----------------------|
| **Load time** | Load ALL data | Load only what's needed |
| **Save time** | Write ALL data | Write only changed file |
| **Failure impact** | Entire file corrupted | Only one item affected |
| **Git diff** | Shows all changes | Shows only actual changes |
| **Backup size** | Full copy each time | Only changed files |
| **Parallel editing** | ❌ Conflicts | ✅ No conflicts |

---

## 🔧 **Maintenance**

### **Backup Management**

```python
# Automatic cleanup keeps last 10 backups per recording
# To change:

class ActionsManager:
    def _cleanup_old_backups(self, recording_name: str, keep_count: int = 20):
        # Change to 20 backups
```

### **List All Recordings**

```bash
ls -lh data/recordings/
# Each file = one recording
```

### **Export for Sharing**

```bash
# Share a single recording
scp data/recordings/grab_cup_v1.json other_robot:/path/

# Share a full collection
tar -czf my_recordings.tar.gz data/recordings/
```

---

## 🎓 **Best Practices**

### **Naming Conventions**

- ✅ Use descriptive names: "Grab Cup v1", "Production Run v2"
- ✅ Include version numbers for iterations
- ✅ Use verbs for actions: "Grab", "Place", "Inspect"
- ✅ Use nouns for sequences: "Production Run", "Quality Check"

### **Sequence Design**

```json
{
  "name": "Production Run v2",
  "steps": [
    {"type": "recording", "name": "Move to Pickup"},
    {"type": "recording", "name": "Grab Part"},
    {"type": "delay", "duration": 1.0},
    {"type": "recording", "name": "Move to Assembly"},
    {"type": "recording", "name": "Place Part"},
    {"type": "model", "task": "Tighten", "checkpoint": "last"}
  ]
}
```

### **Version Control**

```bash
# Git tracks individual files
git status
# Shows only changed recordings

git commit -m "Update grab_cup_v1 with better speed"
# Commit only what changed
```

---

## 🚨 **Troubleshooting**

### **"Recording not found"**

```bash
# Check if file exists
ls data/recordings/

# Check filename sanitization
# "Grab Cup v1" → "grab_cup_v1.json"
```

### **"Failed to load recording"**

```bash
# Check JSON syntax
python -m json.tool data/recordings/grab_cup_v1.json

# Restore from backup if corrupted
cp data/backups/recordings/grab_cup_v1_TIMESTAMP.json \
   data/recordings/grab_cup_v1.json
```

### **"Execution failed"**

- Check robot connection
- Verify motor positions are valid
- Check motor controller is connected
- Review logs in Dashboard

---

## 📈 **Future Enhancements**

- [ ] Cloud sync for recordings
- [ ] Recording compression for large files
- [ ] Recording diff/compare tool
- [ ] Recording versioning system
- [ ] Recording search/filter
- [ ] Recording tags/categories
- [ ] Recording import/export wizard

---

## 📚 **Related Documentation**

- `INDUSTRIAL_PRECISION.md` - Recording system details
- `README.md` - Main application guide
- `ACTION_RECORDER_GUIDE.md` - Recording tutorial

---

**The new architecture is production-ready and designed for reliability in industrial environments!** 🏭✨

