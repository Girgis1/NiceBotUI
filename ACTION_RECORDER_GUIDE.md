# 🎬 Action Recorder System - Complete Guide

## ✅ IMPLEMENTATION COMPLETE!

Your LeRobot GUI now has a comprehensive **3-tab system** with action recording, sequence building, and the original dashboard interface - all optimized for your **1024x600px 7-inch touchscreen**.

---

## 📱 NEW TAB SYSTEM

### **Left-Side Navigation (70px wide)**
```
┌──────┐
│Dash- │ ← Dashboard (original UI)
│board │
├──────┤
│Seque-│ ← Sequence Builder
│nce   │
├──────┤
│Recor-│ ← Action Recorder
│d     │
└──────┘
```

**Keyboard Shortcuts:**
- `Ctrl+1` → Dashboard
- `Ctrl+2` → Sequence
- `Ctrl+3` → Record
- `F11` or `Escape` → Toggle Fullscreen

---

## 🎯 TAB 1: DASHBOARD

**Your original robot control interface** - unchanged functionality:
- Model selection (task + checkpoint dropdowns)
- Episode and time controls
- START/STOP button
- HOME button
- Settings button
- Status indicators (robot, cameras)
- Log display

**Key Features:**
- All existing functionality preserved
- Compact layout for 1024x600px screen
- Touch-optimized button sizes (45-80px heights)

---

## 🎬 TAB 2: RECORD (Action Recorder)

### **Layout**
```
┌─────────────────────────────────────────────────┐
│ ACTION: [NewAction01 ▼]  [💾 SAVE]              │
├─────────────────────────────────────────────────┤
│ [SET] [▶ PLAY/⏹STOP] [🔁 Loop] [+ Delay]        │
├─────────────────────────────────────────────────┤
│ ┌───────────────────────────────────────────┐   │
│ │ TABLE: Name | Motors | Vel | Edit | Del  │   │
│ │ ─────────────────────────────────────────│   │
│ │ Pos 1  │ [2082,1106...]│ 600 │ ✏️ │ 🗑️  │   │
│ │ ⏱️  Delay: 1.5s                            │   │
│ │ Pos 2  │ [2100,1200...]│ 400 │ ✏️ │ 🗑️  │   │
│ └───────────────────────────────────────────┘   │
│ Status: Ready to record...                      │
└─────────────────────────────────────────────────┘
```

### **How to Use**

#### **1. Record a Position**
1. Manually move robot to desired position
2. Press **SET** button
3. Position is captured and added to table as "Pos 1", "Pos 2", etc.
4. Motor positions are read from `/dev/ttyACM0`

#### **2. Add a Delay**
1. Select a position row (or let it add at end)
2. Press **+ Delay** button
3. Enter delay duration (0.1-60 seconds)
4. Delay row appears with orange background

#### **3. Edit Position Name**
1. Click **✏️ Edit** button on any position
2. Enter new name (e.g., "Grab Cup", "Release")
3. Name updates in table

#### **4. Delete Position**
1. Click **🗑️ Delete** button
2. Confirm deletion
3. Position removed from table

#### **5. Reorder Positions (Touch Drag-Drop)**
1. Touch and hold any row
2. Drag up or down
3. Drop at desired location
4. Positions automatically renumber

#### **6. Save Action**
1. Enter action name in top dropdown (or type new name)
2. Press **💾 SAVE** button
3. Action saved to `data/actions.json`
4. Can load later from dropdown

#### **7. Play Action**
1. Press **▶ PLAY** button
2. Robot executes all positions in order
3. Respects delays between positions
4. Press **⏹ STOP** to halt (button changes when playing)

#### **8. Loop Action**
1. Toggle **🔁 Loop** button (turns orange when on)
2. Press **▶ PLAY**
3. Action repeats continuously until stopped

### **Data Storage**

Actions saved to `data/actions.json`:
```json
{
  "actions": {
    "GrabCup_v1": {
      "positions": [
        {
          "name": "Pos 1",
          "motor_positions": [2082, 1106, 2994, 2421, 1044, 2054],
          "velocity": 600
        },
        {
          "name": "Pos 2",
          "motor_positions": [2100, 1200, 3000, 2400, 1050, 2100],
          "velocity": 400
        }
      ],
      "delays": {
        "0": 1.5
      },
      "created": "2025-10-15T10:30:00",
      "modified": "2025-10-15T11:45:00"
    }
  }
}
```

### **Motor Control Details**

- **Motors:** 6 Feetech STS3215 servos (IDs 1-6)
- **Names:** shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper
- **Position Range:** 0-4095 (raw servo units)
- **Velocity Range:** 0-4000 (higher = faster)
- **Default Velocity:** 600

**Motor Reading:**
```python
from utils.motor_controller import MotorController
controller = MotorController(config)
positions = controller.read_positions()  # Returns [int, int, int, int, int, int]
```

**Motor Writing:**
```python
controller.set_positions(
    positions=[2082, 1106, 2994, 2421, 1044, 2054],
    velocity=600,
    wait=True  # Wait for movement to complete
)
```

---

## 🔗 TAB 3: SEQUENCE (Sequence Builder)

### **Layout**
```
┌─────────────────────────────────────────────────┐
│ SEQUENCE: [MySequence ▼]  [💾 SAVE]  [✨ NEW]   │
├─────────────────────────────────────────────────┤
│ [+ Action]  [+ Model]  [+ Delay]                │
├─────────────────────────────────────────────────┤
│ ┌───────────────────────────────────────────┐   │
│ │ 1. 🎬 Action: GrabCup_v1                  │   │
│ │ 2. ⏱️ Delay: 2.0s                          │   │
│ │ 3. 🤖 Model: GrabBlock (last) - 25s       │   │
│ │ 4. 🎬 Action: ReturnHome                  │   │
│ └───────────────────────────────────────────┘   │
│ [▶️ RUN SEQUENCE]  [🔁 Loop]  [🗑️ Delete]      │
│ Status: Build a sequence...                     │
└─────────────────────────────────────────────────┘
```

### **How to Use**

#### **1. Add Action Step**
1. Press **+ Action** button
2. Select saved action from dropdown
3. Action appears in list with 🎬 icon (blue background)

#### **2. Add Model Step**
1. Press **+ Model** button
2. Select trained model task (from `/outputs/train/`)
3. Enter execution duration (seconds)
4. Model step appears with 🤖 icon (purple background)

#### **3. Add Delay Step**
1. Press **+ Delay** button
2. Enter delay duration
3. Delay appears with ⏱️ icon (orange background)

#### **4. Reorder Steps (Touch Drag-Drop)**
1. Touch and hold any step
2. Drag up or down
3. Drop at new position
4. Steps automatically renumber

#### **5. Delete Step**
1. Select step in list
2. Press **🗑️ Delete** button
3. Step removed

#### **6. Save Sequence**
1. Enter sequence name in top dropdown
2. Press **💾 SAVE** button
3. Sequence saved to `data/sequences.json`

#### **7. Run Sequence**
1. Press **▶️ RUN SEQUENCE** button
2. Executes all steps in order:
   - Actions → Executes recorded positions
   - Models → Runs trained policy for duration
   - Delays → Waits specified time
3. Press **⏹ STOP** to halt

#### **8. Loop Sequence**
1. Toggle **🔁 Loop** button
2. Press **▶️ RUN SEQUENCE**
3. Sequence repeats until stopped

### **Data Storage**

Sequences saved to `data/sequences.json`:
```json
{
  "sequences": {
    "MorningRoutine": {
      "steps": [
        {"type": "action", "name": "GrabCup_v1"},
        {"type": "delay", "duration": 2.0},
        {"type": "model", "task": "GrabBlock", "checkpoint": "last", "duration": 25.0},
        {"type": "action", "name": "ReturnHome"}
      ],
      "created": "2025-10-15T10:00:00",
      "modified": "2025-10-15T12:00:00"
    }
  }
}
```

---

## 🏗️ ARCHITECTURE

### **File Structure**
```
LerobotGUI/
├── app.py                    # Main app with tab system
├── app_backup.py             # Original app.py (backup)
│
├── tabs/
│   ├── __init__.py
│   ├── dashboard_tab.py      # Dashboard (original UI)
│   ├── record_tab.py         # Action recorder
│   └── sequence_tab.py       # Sequence builder
│
├── widgets/
│   ├── __init__.py
│   ├── draggable_table.py    # Base drag-drop table
│   └── action_table.py       # Specialized action table
│
├── utils/
│   ├── __init__.py
│   ├── actions_manager.py    # Save/load actions
│   ├── sequences_manager.py  # Save/load sequences
│   └── motor_controller.py   # Motor control interface
│
├── data/
│   ├── actions.json          # Saved actions
│   └── sequences.json        # Saved sequences
│
├── rest_pos.py               # Motor control (existing)
├── robot_worker.py           # Robot worker (existing)
├── settings_dialog.py        # Settings (existing)
└── config.json               # Configuration (existing)
```

### **Classes & Modules**

#### **utils/motor_controller.py**
```python
class MotorController:
    def __init__(config: dict)
    def read_positions() -> list[int]
    def set_positions(positions: list[int], velocity: int, wait: bool)
    def connect() -> bool
    def disconnect()
    def emergency_stop()
```

#### **utils/actions_manager.py**
```python
class ActionsManager:
    def save_action(name: str, positions: list, delays: dict) -> bool
    def load_action(name: str) -> dict
    def delete_action(name: str) -> bool
    def list_actions() -> list[str]
    def action_exists(name: str) -> bool
```

#### **utils/sequences_manager.py**
```python
class SequencesManager:
    def save_sequence(name: str, steps: list) -> bool
    def load_sequence(name: str) -> dict
    def delete_sequence(name: str) -> bool
    def list_sequences() -> list[str]
    def sequence_exists(name: str) -> bool
```

#### **widgets/draggable_table.py**
```python
class DraggableTableWidget(QTableWidget):
    # Signals
    rows_reordered = Signal()
    
    # Methods
    def move_row(source: int, target: int)
    def get_all_rows_data() -> list[dict]
```

#### **widgets/action_table.py**
```python
class ActionTableWidget(DraggableTableWidget):
    # Signals
    edit_clicked = Signal(int)
    delete_clicked = Signal(int)
    
    # Methods
    def add_position_row(name: str, positions: list, velocity: int, row: int)
    def add_delay_row(delay: float, row: int)
    def get_position_data(row: int) -> dict
    def get_all_data() -> tuple[list, dict]
    def is_delay_row(row: int) -> bool
```

---

## 🎨 TOUCH OPTIMIZATION

### **Button Sizes**
- Primary buttons: 45-55px height
- Large action buttons: 60-80px height
- Icon buttons: 50-60px square
- Table row height: 60px

### **Fonts**
- Headers: 13-14px bold
- Body text: 12-13px
- Buttons: 14-16px
- Table: 12px

### **Colors (Dark Theme)**
- Background: `#1e1e1e`
- Panels: `#2d2d2d`
- Borders: `#404040`
- Primary Blue: `#2196F3`
- Success Green: `#4CAF50`
- Danger Red: `#f44336`
- Warning Orange: `#FF9800`
- Action Purple: `#9C27B0`

### **Drag-and-Drop**
- **Touch-friendly:** 60px row height
- **Visual feedback:** Selected rows highlighted in blue
- **Drop indicator:** Shows where row will be placed
- **Auto-scroll:** When dragging near edges

---

## 🚀 USAGE EXAMPLES

### **Example 1: Record a Simple Pick-and-Place**
1. Go to **Record** tab
2. Move robot to pickup position
3. Press **SET** → "Pos 1" recorded
4. Move robot to place position
5. Press **SET** → "Pos 2" recorded
6. Enter action name: "PickPlace_v1"
7. Press **💾 SAVE**
8. Press **▶ PLAY** to test

### **Example 2: Record with Delays**
1. Record "Pos 1" (above object)
2. Record "Pos 2" (at object)
3. Select "Pos 2" row
4. Press **+ Delay** → Enter 2.0 seconds
5. Record "Pos 3" (lift object)
6. Record "Pos 4" (place object)
7. Save action

### **Example 3: Build a Complex Sequence**
1. Go to **Sequence** tab
2. Press **+ Action** → Select "GrabCup_v1"
3. Press **+ Delay** → Enter 1.0
4. Press **+ Model** → Select "GrabBlock" → Duration 25s
5. Press **+ Action** → Select "ReturnHome"
6. Enter sequence name: "MorningRoutine"
7. Press **💾 SAVE**
8. Press **▶️ RUN SEQUENCE**

### **Example 4: Loop an Action**
1. Go to **Record** tab
2. Load saved action
3. Toggle **🔁 Loop** button (turns orange)
4. Press **▶ PLAY**
5. Action repeats continuously
6. Press **⏹ STOP** to halt

---

## ⚙️ CONFIGURATION

All settings stored in `config.json`:

```json
{
  "robot": {
    "type": "so100_follower",
    "port": "/dev/ttyACM0",  // Serial port for motors
    "fps": 30
  },
  "cameras": {
    "front": {
      "index_or_path": "/dev/video1"
    },
    "wrist": {
      "index_or_path": "/dev/video3"
    }
  },
  "rest_position": {
    "positions": [2082, 1106, 2994, 2421, 1044, 2054],  // Home position
    "velocity": 600
  }
}
```

---

## 🐛 TROUBLESHOOTING

### **Issue: "Failed to read motor positions"**
**Cause:** Robot not connected or no power
**Solution:**
1. Check USB cable connected to `/dev/ttyACM0`
2. Verify power supply is ON
3. Check Dashboard tab status indicators (should be green)

### **Issue: "No saved actions found"**
**Cause:** No actions created yet
**Solution:**
1. Go to Record tab
2. Record at least one position with SET button
3. Save action with a name
4. Action will appear in dropdown

### **Issue: Positions won't save**
**Cause:** Permissions or disk space
**Solution:**
1. Check `data/` directory exists and is writable
2. Check disk space: `df -h`
3. View logs in Dashboard tab for errors

### **Issue: Drag-and-drop not working**
**Cause:** Touch screen calibration
**Solution:**
1. Try with mouse first to verify functionality
2. Calibrate touchscreen in system settings
3. Try longer touch/hold before dragging

### **Issue: App won't start**
**Cause:** Missing dependencies
**Solution:**
```bash
pip install PySide6
pip install -e .[feetech]  # From lerobot directory
```

---

## 🔧 ADVANCED FEATURES

### **Velocity Control**
- Default velocity: 600 (moderate speed)
- Range: 0-4000
- Higher = faster movement
- Lower = smoother, more precise

### **Emergency Stop**
- Press **⏹ STOP** during playback
- Robot immediately halts
- Torque disabled for safety
- Use **HOME** button to return safely

### **Action Versioning**
- Name actions with versions: "GrabCup_v1", "GrabCup_v2"
- Keep old versions while testing new ones
- Easy rollback if needed

### **Custom Delays**
- Insert delays anywhere in sequence
- Useful for:
  - Waiting for object to settle
  - Giving time for gripper to close
  - Synchronizing with external systems

---

## 📊 FILE FORMATS

### **actions.json Structure**
```json
{
  "actions": {
    "ActionName": {
      "positions": [
        {
          "name": "Position Name",
          "motor_positions": [int, int, int, int, int, int],
          "velocity": int
        }
      ],
      "delays": {
        "position_index": delay_seconds
      },
      "created": "ISO8601 timestamp",
      "modified": "ISO8601 timestamp"
    }
  }
}
```

### **sequences.json Structure**
```json
{
  "sequences": {
    "SequenceName": {
      "steps": [
        {"type": "action", "name": "ActionName"},
        {"type": "delay", "duration": float},
        {"type": "model", "task": "TaskName", "checkpoint": "last", "duration": float}
      ],
      "created": "ISO8601 timestamp",
      "modified": "ISO8601 timestamp"
    }
  }
}
```

---

## 🎓 BEST PRACTICES

### **Recording Actions**
1. **Test positions manually first** before recording
2. **Name positions descriptively** (not just "Pos 1")
3. **Use consistent velocity** for smooth movements
4. **Add delays** where robot needs to stabilize
5. **Save incrementally** to avoid losing work

### **Building Sequences**
1. **Test each action individually** before combining
2. **Add delays between critical steps**
3. **Name sequences clearly** (describe what they do)
4. **Start simple** then add complexity
5. **Use loop mode** for repetitive tasks

### **Safety**
1. **Always test with low velocity first**
2. **Keep STOP button accessible**
3. **Monitor robot during playback**
4. **Set proper home position** for safe returns
5. **Clear workspace** of obstacles

---

## ✨ WHAT'S NEW

### **Completed Features**
✅ Left-side vertical tab navigation
✅ Action recorder with SET button
✅ Motor position reading and playback
✅ Drag-and-drop table reordering (touch-enabled)
✅ Delay insertion between actions
✅ Action save/load system
✅ Sequence builder combining actions/models/delays
✅ Loop mode for actions and sequences
✅ Touch-optimized UI (1024x600px)
✅ Edit and delete buttons for positions
✅ Visual feedback (colored rows, icons)
✅ Keyboard shortcuts (Ctrl+1/2/3, F11)

---

## 🚀 RUNNING THE APP

```bash
# Fullscreen mode (default for 7-inch screen)
python3 app.py

# Windowed mode (for testing)
python3 app.py --windowed

# Or
python3 app.py --no-fullscreen
```

---

## 📞 SUPPORT

If you encounter issues:
1. Check Dashboard tab log for errors
2. Verify robot connection (green status indicators)
3. Check `data/actions.json` and `data/sequences.json` are valid JSON
4. Review this guide for troubleshooting steps

---

**Enjoy your new Action Recorder system! 🎬🤖**

*Built with ❤️ for 7-inch 1024x600px touchscreens*

