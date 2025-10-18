# 🏗️ COMPOSITE RECORDING SYSTEM - STREAMLINED IMPLEMENTATION

**CLEAN START - No Legacy Compatibility Required**

User will handle real robot testing. Focus: Build clean, modular, industrial-grade system.

---

## 📊 NEW FILE STRUCTURE

```
data/recordings/
├── grab_cup_v1/
│   ├── manifest.json              # Master orchestration file
│   ├── 01_approach_live.json      # Live recording component
│   ├── 02_grasp_positions.json    # Position waypoints component
│   └── 03_retreat_live.json       # Live recording component
└── pick_place/
    ├── manifest.json
    ├── 01_pickup_live.json
    └── 02_place_positions.json
```

---

## 🎯 SIMPLIFIED PHASES

### PHASE 1: Core Data Structures ✅ Starting Now
- `utils/recording_component.py` - Component base classes
- `utils/composite_recording.py` - Main composite manager
- No tests needed (user will test with robot)

### PHASE 2: Replace ActionsManager
- Completely rewrite `ActionsManager` to ONLY handle composite format
- Remove all legacy code
- Clean, simple API

### PHASE 3: Update Execution Engine
- Modify `ExecutionManager` to execute composite recordings
- Add per-step speed/delay support

### PHASE 4: Update RecordTab UI
- Modify to create/edit composite recordings
- Show steps in table
- Add/remove/reorder steps
- Edit step properties

### PHASE 5: Update Dashboard
- Ensure composite recordings show in dropdown
- Execute from Dashboard

### PHASE 6: Real Robot Testing
- User tests with actual robot
- Fix any issues found
- Iterate based on feedback

---

## 📝 FILE FORMATS (Simplified)

### Manifest File
```json
{
  "format_version": "2.0",
  "name": "Grab Cup v1",
  "type": "composite_recording",
  "steps": [
    {
      "step_id": "step_001",
      "type": "live_recording",
      "name": "Approach",
      "file": "01_approach_live.json",
      "speed": 80,
      "enabled": true,
      "delay_after": 0.0
    },
    {
      "step_id": "step_002",
      "type": "position_set",
      "name": "Grasp",
      "file": "02_grasp_positions.json",
      "speed": 100,
      "enabled": true,
      "delay_after": 1.0
    }
  ],
  "metadata": {
    "created": "2025-10-18T10:30:00+11:00",
    "modified": "2025-10-18T15:45:00+11:00"
  }
}
```

### Live Recording Component
```json
{
  "component_type": "live_recording",
  "name": "Approach",
  "recorded_data": [
    {"timestamp": 0.0, "positions": [0,0,0,0,0,0], "velocity": 600},
    {"timestamp": 0.1, "positions": [1,2,3,4,5,6], "velocity": 600}
  ]
}
```

### Position Set Component
```json
{
  "component_type": "position_set",
  "name": "Grasp",
  "positions": [
    {"name": "Pre-Grasp", "motor_positions": [10,20,30,40,50,60], "velocity": 800},
    {"name": "Grasp", "motor_positions": [15,25,35,45,55,65], "velocity": 400}
  ]
}
```

---

## 🚀 IMPLEMENTATION ORDER

1. ✅ **Create component classes** (30 min)
2. ✅ **Create composite recording manager** (45 min)
3. ✅ **Rewrite ActionsManager** (30 min)
4. ✅ **Update ExecutionManager** (45 min)
5. ✅ **Update RecordTab UI** (1-2 hours)
6. ✅ **Update Dashboard** (15 min)
7. ✅ **User tests with robot** (iterative)

**Total estimated dev time: 4-5 hours**

---

## 🎯 SUCCESS CRITERIA

✅ Can record live motion and save as component  
✅ Can record positions and save as component  
✅ Can combine components into composite recording  
✅ Can reorder/edit steps  
✅ Can execute composite from Dashboard  
✅ Per-step speed control works  
✅ Delays between steps work  
✅ Can enable/disable steps  
✅ Robot executes correctly (user validates)  

---

Ready to build! 🚀

