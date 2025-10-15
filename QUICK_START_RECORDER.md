# 🚀 Action Recorder - Quick Start

## ⚡ Get Started in 60 Seconds!

### **1. Launch the App**
```bash
cd /home/daniel/LerobotGUI
python3 app.py
```

### **2. Switch to Record Tab**
- Click **"Record"** tab on the left (or press `Ctrl+3`)

### **3. Record Your First Action**
1. **Move robot manually** to first position
2. Press **SET** button → Position captured as "Pos 1"
3. **Move robot** to second position
4. Press **SET** again → Position captured as "Pos 2"
5. Add more positions as needed

### **4. Save Your Action**
1. Type action name in top dropdown (e.g., "PickPlace_v1")
2. Press **💾 SAVE** button
3. Action saved to `data/actions.json`

### **5. Play It Back**
1. Press **▶ PLAY** button
2. Watch robot execute your recorded positions!
3. Press **⏹ STOP** to halt anytime

---

## 🎯 Common Tasks

### **Add a Delay Between Positions**
1. Select a position row in table
2. Press **+ Delay** button
3. Enter seconds (e.g., 1.5)
4. Orange delay row appears

### **Rename a Position**
1. Click **✏️** button next to position
2. Enter new name (e.g., "Grab Cup")
3. Press OK

### **Reorder Positions**
1. Touch and hold any row
2. Drag up or down
3. Drop at new location

### **Loop an Action**
1. Toggle **🔁 Loop** button (turns orange)
2. Press **▶ PLAY**
3. Action repeats until stopped

### **Build a Sequence**
1. Go to **Sequence** tab (Ctrl+2)
2. Press **+ Action** → Select saved action
3. Press **+ Delay** → Add wait time
4. Press **💾 SAVE** → Name your sequence
5. Press **▶️ RUN SEQUENCE** to execute

---

## 🎨 Tab Navigation

| Tab | Shortcut | Purpose |
|-----|----------|---------|
| **Dashboard** | `Ctrl+1` | Original robot control UI |
| **Sequence** | `Ctrl+2` | Combine actions, models, delays |
| **Record** | `Ctrl+3` | Record motor positions |

---

## 📁 File Structure

```
LerobotGUI/
├── app.py                 # Launch this
├── data/
│   ├── actions.json       # Your saved actions
│   └── sequences.json     # Your saved sequences
└── ACTION_RECORDER_GUIDE.md  # Full documentation
```

---

## ⚠️ Important Notes

1. **Robot must be powered ON** to record positions
2. **USB must be connected** to `/dev/ttyACM0`
3. **Green status indicators** = Robot ready (see Dashboard tab)
4. **Original app.py backed up** as `app_backup.py`

---

## 🆘 Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| Can't read positions | Check robot power & USB connection |
| Actions won't save | Check `data/` folder permissions |
| Drag-drop not working | Try mouse first, then recalibrate touchscreen |
| App won't start | Run: `pip install PySide6` |

---

## 🎓 Watch This!

The action recorder works just like teaching a robot:
1. **Show** it what to do (move manually + SET)
2. **Save** the lesson (give it a name)
3. **Replay** anytime (PLAY button)
4. **Combine** multiple actions (Sequence tab)

That's it! Happy recording! 🎬🤖

---

**For full documentation, see [ACTION_RECORDER_GUIDE.md](ACTION_RECORDER_GUIDE.md)**

