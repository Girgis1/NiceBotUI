# 🏗️ COMPOSITE RECORDING SYSTEM - COMPLETE IMPLEMENTATION PLAN

**Goal:** Transform recordings from single JSON files into modular folder-based composite recordings with reusable, editable sub-components.

---

## 📊 OVERVIEW

### Current System
```
data/recordings/
├── grab_cup.json          # Single file with all data
└── pick_place.json        # Single file with all data
```

### New System
```
data/recordings/
├── grab_cup/
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

## 🎯 PHASE 1: NEW DATA STRUCTURES & FILE FORMAT

### 1.1 Manifest File Structure
**File:** `data/recordings/{recording_name}/manifest.json`

```json
{
  "format_version": "2.0",
  "name": "Grab Cup v1",
  "type": "composite_recording",
  "description": "Pick up cup from table with smooth approach",
  "steps": [
    {
      "step_id": "step_001",
      "step_number": 1,
      "type": "live_recording",
      "name": "Smooth Approach",
      "file": "01_approach_live.json",
      "speed": 80,
      "enabled": true,
      "delay_before": 0.0,
      "delay_after": 0.0,
      "notes": "Slow approach to avoid collision"
    },
    {
      "step_id": "step_002",
      "step_number": 2,
      "type": "position_set",
      "name": "Grasp Waypoints",
      "file": "02_grasp_positions.json",
      "speed": 100,
      "enabled": true,
      "delay_before": 0.5,
      "delay_after": 1.0,
      "notes": "Pause before grasping"
    },
    {
      "step_id": "step_003",
      "step_number": 3,
      "type": "live_recording",
      "name": "Retreat Motion",
      "file": "03_retreat_live.json",
      "speed": 60,
      "enabled": true,
      "delay_before": 0.0,
      "delay_after": 0.0,
      "notes": "Slow retreat with object"
    }
  ],
  "metadata": {
    "created": "2025-10-18T10:30:00+11:00",
    "modified": "2025-10-18T15:45:00+11:00",
    "author": "user",
    "robot_model": "SO-100",
    "total_steps": 3,
    "total_duration_estimate": 12.5
  }
}
```

### 1.2 Live Recording Component File
**File:** `data/recordings/{recording_name}/01_approach_live.json`

```json
{
  "format_version": "2.0",
  "component_type": "live_recording",
  "name": "Smooth Approach",
  "description": "Smooth approach motion to cup",
  "recorded_data": [
    {
      "timestamp": 0.0,
      "positions": [0, 0, 0, 0, 0, 0],
      "velocity": 600
    },
    {
      "timestamp": 0.1,
      "positions": [1, 2, 3, 4, 5, 6],
      "velocity": 600
    }
    // ... hundreds more points
  ],
  "metadata": {
    "point_count": 500,
    "duration": 5.0,
    "recorded_at": "2025-10-18T10:30:00+11:00",
    "recording_fps": 10
  }
}
```

### 1.3 Position Set Component File
**File:** `data/recordings/{recording_name}/02_grasp_positions.json`

```json
{
  "format_version": "2.0",
  "component_type": "position_set",
  "name": "Grasp Waypoints",
  "description": "Key positions for grasping",
  "positions": [
    {
      "position_id": "pos_001",
      "name": "Pre-Grasp",
      "motor_positions": [10, 20, 30, 40, 50, 60],
      "velocity": 800,
      "wait_for_completion": true,
      "notes": "Hover above cup"
    },
    {
      "position_id": "pos_002",
      "name": "Grasp",
      "motor_positions": [15, 25, 35, 45, 55, 65],
      "velocity": 400,
      "wait_for_completion": true,
      "notes": "Close gripper"
    },
    {
      "position_id": "pos_003",
      "name": "Lift",
      "motor_positions": [15, 25, 35, 45, 55, 85],
      "velocity": 600,
      "wait_for_completion": true,
      "notes": "Lift up with cup"
    }
  ],
  "metadata": {
    "position_count": 3,
    "created_at": "2025-10-18T10:35:00+11:00"
  }
}
```

---

## 🔧 PHASE 2: NEW CLASSES & MODULES

### 2.1 Create `utils/composite_recording.py`

**Purpose:** Main class for managing composite recordings

**Key Methods:**
```python
class CompositeRecording:
    def __init__(self, name: str, recordings_dir: Path)
    def create_new(self, name: str, description: str = "") -> bool
    def load(self, name: str) -> Optional['CompositeRecording']
    def save(self) -> bool
    def add_step(self, step_data: dict) -> str  # Returns step_id
    def remove_step(self, step_id: str) -> bool
    def reorder_step(self, step_id: str, new_position: int) -> bool
    def update_step(self, step_id: str, updates: dict) -> bool
    def get_step(self, step_id: str) -> Optional[dict]
    def get_all_steps(self) -> List[dict]
    def add_live_recording_component(self, name: str, recorded_data: List[dict]) -> str
    def add_position_set_component(self, name: str, positions: List[dict]) -> str
    def get_component(self, filename: str) -> Optional[dict]
    def delete_component(self, filename: str) -> bool
    def get_full_recording_data(self) -> dict  # For execution
    def get_info(self) -> dict  # Summary info
    def delete_recording(self) -> bool
    
    # Properties
    @property
    def manifest_path(self) -> Path
    @property
    def recording_dir(self) -> Path
    @property
    def step_count(self) -> int
    @property
    def total_duration_estimate(self) -> float
```

### 2.2 Create `utils/recording_component.py`

**Purpose:** Base classes for recording components

```python
class RecordingComponent:
    """Base class for recording components"""
    def __init__(self, component_type: str, name: str)
    def to_dict(self) -> dict
    def save(self, filepath: Path) -> bool
    @staticmethod
    def load(filepath: Path) -> Optional['RecordingComponent']

class LiveRecordingComponent(RecordingComponent):
    """Live recording with time-series data"""
    def __init__(self, name: str, recorded_data: List[dict])
    def add_point(self, timestamp: float, positions: List[int], velocity: int)
    def get_point_count(self) -> int
    def get_duration(self) -> float
    
class PositionSetComponent(RecordingComponent):
    """Set of discrete waypoints"""
    def __init__(self, name: str, positions: List[dict] = None)
    def add_position(self, name: str, motor_positions: List[int], velocity: int)
    def remove_position(self, position_id: str) -> bool
    def get_position_count(self) -> int
```

### 2.3 Update `utils/actions_manager.py`

**Purpose:** Extend to handle both legacy and composite recordings

**Key Changes:**
- Add `format` detection (v1.0 = single JSON, v2.0 = composite folder)
- Add `save_composite_recording()` method
- Add `load_composite_recording()` method
- Keep backward compatibility with old `save_action()` / `load_action()`
- Add `list_actions()` to return both formats
- Add `get_recording_format(name)` to check which format a recording uses

**New Methods:**
```python
def is_composite_recording(self, name: str) -> bool
def convert_to_composite(self, name: str) -> bool  # Upgrade legacy to composite
def get_composite_recording(self, name: str) -> Optional[CompositeRecording]
```

---

## 🖥️ PHASE 3: UI UPDATES

### 3.1 Update `widgets/action_table.py`

**Current:** Simple table with rows for each position/recording

**New:** Tree-style table showing composite structure

```
[Composite Recording: "Grab Cup"]
  ├─ [1] Live Recording: Approach (500 pts, 5.0s) [Speed: 80%]
  ├─ [2] Position Set: Grasp Waypoints (3 positions) [Speed: 100%]
  └─ [3] Live Recording: Retreat (300 pts, 3.0s) [Speed: 60%]
```

**Key Changes:**
- Add tree/hierarchy view capability (QTreeWidget instead of QTableWidget?)
- Add expand/collapse for steps
- Add drag-and-drop for reordering
- Add context menu for step operations (edit, delete, enable/disable)
- Show component type icons (🎬 for live, 📍 for positions)

### 3.2 Update `tabs/record_tab.py`

**New UI Elements:**
- **Composite Recording Info Panel:**
  - Name field
  - Description field
  - Total steps count
  - Estimated duration
  
- **Step Controls:**
  - "Add Current as Step" button (converts table contents to a component)
  - Step type selector (Live Recording / Position Set)
  - "Clear Table" button (for starting fresh component)
  
- **Component Editor:**
  - Edit step properties (speed, delays, enabled)
  - Edit individual positions within a position set
  - View/edit live recording metadata (can't edit points, only metadata)

**New Methods:**
```python
def create_composite_recording(self, name: str)
def load_composite_recording(self, name: str)
def save_current_as_component(self, component_type: str)
def add_component_to_composite(self)
def remove_step_from_composite(self, step_id: str)
def reorder_composite_steps(self)
def update_composite_ui()
```

### 3.3 Update `tabs/dashboard_tab.py`

**Changes:**
- Detection of recording format in `run_selector`
- Display format indicator in dropdown (🗂️ for composite, 📄 for legacy)
- No major execution changes (ExecutionWorker handles both)

---

## ⚙️ PHASE 4: EXECUTION ENGINE UPDATES

### 4.1 Update `utils/execution_manager.py`

**Key Changes:**
```python
def _execute_recording(self):
    """Execute a recording (legacy or composite)"""
    # Load recording
    recording_format = self.actions_mgr.get_recording_format(self.execution_name)
    
    if recording_format == "composite":
        composite = self.actions_mgr.get_composite_recording(self.execution_name)
        self._execute_composite_recording(composite)
    else:
        # Legacy execution (existing code)
        recording = self.actions_mgr.load_action(self.execution_name)
        self._execute_legacy_recording(recording)

def _execute_composite_recording(self, composite: CompositeRecording):
    """Execute a composite recording step-by-step"""
    steps = composite.get_all_steps()
    
    for step in steps:
        if self._stop_requested:
            break
        
        # Check if step is enabled
        if not step.get('enabled', True):
            self.log_message.emit('info', f"Skipping disabled step: {step['name']}")
            continue
        
        # Delay before
        delay_before = step.get('delay_before', 0.0)
        if delay_before > 0:
            self.log_message.emit('info', f"Waiting {delay_before}s before step...")
            time.sleep(delay_before)
        
        # Execute step based on type
        if step['type'] == 'live_recording':
            component = composite.get_component(step['file'])
            self._execute_live_component(component, step['speed'])
        elif step['type'] == 'position_set':
            component = composite.get_component(step['file'])
            self._execute_position_component(component, step['speed'])
        
        # Delay after
        delay_after = step.get('delay_after', 0.0)
        if delay_after > 0:
            self.log_message.emit('info', f"Waiting {delay_after}s after step...")
            time.sleep(delay_after)

def _execute_live_component(self, component: dict, speed_override: int):
    """Execute a live recording component"""
    # Similar to existing _playback_live_recording but with speed override
    
def _execute_position_component(self, component: dict, speed_override: int):
    """Execute a position set component"""
    # Similar to existing _playback_position_recording but with speed override
```

---

## 🔄 PHASE 5: MIGRATION & BACKWARD COMPATIBILITY

### 5.1 Create `utils/migrate_to_composite.py`

**Purpose:** Migrate existing recordings to composite format

```python
def migrate_recording_to_composite(name: str, actions_mgr: ActionsManager) -> bool:
    """
    Migrate a legacy recording to composite format
    
    Steps:
    1. Load legacy recording
    2. Create composite recording folder
    3. Analyze recording type (live vs position)
    4. Create appropriate component file(s)
    5. Create manifest
    6. Backup legacy file
    7. Mark as migrated (optional: delete legacy)
    """
    
def migrate_all_recordings(actions_mgr: ActionsManager, delete_legacy: bool = False):
    """Migrate all legacy recordings"""
    
def can_auto_migrate(recording_data: dict) -> bool:
    """Check if recording can be auto-migrated or needs manual intervention"""
```

### 5.2 Backward Compatibility Strategy

**Read:**
- ActionsManager can read BOTH formats
- Auto-detect format by checking if path is file or folder
- Return data in unified format for execution

**Write:**
- New recordings always saved as composite (v2.0)
- Keep old `save_action()` for legacy support (mark as deprecated)
- Add `save_composite_recording()` as new primary method

**Execution:**
- ExecutionManager handles both formats transparently
- No changes needed to existing trained models or sequences

---

## 🧪 PHASE 6: TESTING STRATEGY

### 6.1 Unit Tests (`test_composite_recording.py`)

```python
def test_create_composite_recording()
def test_add_live_recording_component()
def test_add_position_set_component()
def test_reorder_steps()
def test_remove_step()
def test_update_step_properties()
def test_save_and_load_composite()
def test_execute_composite_recording()
def test_backward_compatibility_legacy_recordings()
def test_migration_legacy_to_composite()
```

### 6.2 Integration Tests

1. **Create and Save:**
   - Record live motion → Add as component → Save composite
   - Record positions → Add as component → Save composite
   - Mix both types in one composite → Save and reload

2. **Execution:**
   - Execute composite with live recording component
   - Execute composite with position set component
   - Execute composite with mixed components
   - Execute with step disabled
   - Execute with delays

3. **Migration:**
   - Migrate simple live recording
   - Migrate simple position recording
   - Migrate complex recording (mixed)

4. **UI:**
   - Create composite in UI
   - Add/remove/reorder steps in UI
   - Edit step properties in UI
   - Load and display composite in UI

---

## 📝 PHASE 7: IMPLEMENTATION ORDER

### Step-by-Step Implementation Sequence:

1. **Create Data Structures (No UI impact)**
   - [ ] Create `utils/recording_component.py` with base classes
   - [ ] Create `utils/composite_recording.py` with main logic
   - [ ] Add unit tests for composite recording classes

2. **Extend ActionsManager (Maintain compatibility)**
   - [ ] Add composite detection to `ActionsManager`
   - [ ] Add `get_composite_recording()` method
   - [ ] Add `is_composite_recording()` method
   - [ ] Keep all existing methods working
   - [ ] Add tests for ActionsManager extensions

3. **Update Execution Engine (Handle both formats)**
   - [ ] Add composite recording detection in `ExecutionManager`
   - [ ] Add `_execute_composite_recording()` method
   - [ ] Add component execution methods
   - [ ] Test execution with mock composite recordings
   - [ ] Verify legacy recordings still work

4. **Create Migration Tools (Before UI)**
   - [ ] Create `utils/migrate_to_composite.py`
   - [ ] Add migration script functionality
   - [ ] Test migration with existing recordings
   - [ ] Create backup strategy

5. **Update UI - Phase 1: Basic Composite Support**
   - [ ] Add composite recording detection to RecordTab
   - [ ] Add basic load/save for composite recordings
   - [ ] Update action_table to show composite structure (simple view first)
   - [ ] Test create → save → load workflow

6. **Update UI - Phase 2: Advanced Features**
   - [ ] Add step reordering UI
   - [ ] Add step property editor
   - [ ] Add component type icons/indicators
   - [ ] Add enable/disable toggle per step
   - [ ] Add delay controls

7. **Update UI - Phase 3: Tree View (Optional Enhancement)**
   - [ ] Replace/enhance table with tree view
   - [ ] Add drag-and-drop reordering
   - [ ] Add context menus for steps
   - [ ] Add expand/collapse for steps

8. **Dashboard Integration**
   - [ ] Add format indicator in run selector
   - [ ] Ensure composite recordings appear in dropdown
   - [ ] Test execution from Dashboard

9. **Documentation & Final Testing**
   - [ ] Create user guide for composite recordings
   - [ ] Update `ROBUST_ARCHITECTURE.md`
   - [ ] Create migration guide
   - [ ] Full end-to-end testing
   - [ ] Performance testing with large recordings

---

## ⚠️ POTENTIAL ISSUES & MITIGATION

### Issue 1: Folder vs File Management
**Risk:** File system operations more complex with folders
**Mitigation:** 
- Robust directory creation/deletion
- Atomic operations where possible
- Comprehensive error handling
- Always backup before modification

### Issue 2: Backward Compatibility
**Risk:** Breaking existing workflows
**Mitigation:**
- Keep legacy file support indefinitely
- Auto-detect format
- Opt-in migration (don't force)
- Clear format indicators in UI

### Issue 3: File System Performance
**Risk:** Many small files slower than one big file
**Mitigation:**
- Lazy loading of components
- Cache component data in memory
- Only load components when needed for execution
- Benchmark and optimize if needed

### Issue 4: UI Complexity
**Risk:** Too many features confuse users
**Mitigation:**
- Progressive disclosure (simple view first)
- Clear visual hierarchy
- Tooltips and help text
- Optional advanced features

### Issue 5: Migration Errors
**Risk:** Data loss during migration
**Mitigation:**
- Always create backups before migration
- Validate migrated data
- Keep originals until verified
- Add rollback capability

### Issue 6: Sequences Referencing Recordings
**Risk:** Sequences store recording names, might break after migration
**Mitigation:**
- Test sequence execution with both formats
- Ensure name resolution works for both
- Update SequencesManager if needed
- Document name stability

---

## 🎯 SUCCESS CRITERIA

### Must Have (MVP):
✅ Composite recordings can be created, saved, and loaded  
✅ Live recordings can be added as components  
✅ Position sets can be added as components  
✅ Composite recordings execute correctly (all steps in order)  
✅ Legacy recordings continue to work  
✅ Migration script successfully converts legacy recordings  
✅ UI shows composite structure clearly  
✅ Dashboard can execute composite recordings  

### Should Have (V1.0):
✅ Step reordering in UI  
✅ Step enable/disable  
✅ Per-step speed control  
✅ Per-step delays  
✅ Component editing (metadata, not data)  
✅ Format indicator in UI  
✅ Comprehensive error handling  

### Nice to Have (V1.1+):
⭐ Tree view with drag-and-drop  
⭐ Component reuse across recordings  
⭐ Step templates  
⭐ Visual timeline editor  
⭐ Real-time preview during creation  
⭐ Component library browser  

---

## 📊 ESTIMATED EFFORT

| Phase | Tasks | Estimated Time | Complexity |
|-------|-------|----------------|------------|
| 1. Data Structures | 3 tasks | 2-3 hours | Medium |
| 2. Core Classes | 5 tasks | 4-5 hours | High |
| 3. ActionsManager Update | 4 tasks | 2-3 hours | Medium |
| 4. Execution Engine | 5 tasks | 3-4 hours | High |
| 5. Migration Tools | 3 tasks | 2-3 hours | Medium |
| 6. UI Basic | 4 tasks | 3-4 hours | Medium |
| 7. UI Advanced | 5 tasks | 4-5 hours | High |
| 8. Testing | 10 tasks | 3-4 hours | Medium |
| 9. Documentation | 4 tasks | 1-2 hours | Low |
| **TOTAL** | **43 tasks** | **24-33 hours** | **High** |

**This is a 3-5 day full implementation with testing!**

---

## 🚀 NEXT STEPS

Ready to proceed? We should:

1. **Review this plan** - Any concerns or modifications?
2. **Start with Phase 1** - Create core data structures (no UI impact, easy to test)
3. **Iterate through phases** - One at a time with testing
4. **Maintain functionality** - Existing system keeps working throughout

**Should I proceed with implementation starting from Phase 1?**

