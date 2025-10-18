# 🔧 SEQUENCER REBUILD PLAN - Updated

**Branch:** `dev`  
**Goal:** Working, robust sequencer with modular architecture

---

## 🎯 USER REQUIREMENTS

1. **Keep "action" terminology** - NOT "recording"
   - Reason: Future extensibility (vision triggers, sensors, custom actions)
   - "Action Recorder" makes more sense

2. **Add +Home button** - Return arm to home position
   - New step type: "home"
   - Uses existing rest_pos.py functionality

3. **Make sequences modular** - Like recordings
   - Folder-based structure
   - Individual step files
   - Manifest for orchestration

---

## 📁 NEW SEQUENCE ARCHITECTURE

### Current (Flat):
```
data/sequences/
└── my_sequence.json    # Everything in one file
```

### New (Modular):
```
data/sequences/
└── production_run/
    ├── manifest.json              # Orchestration
    ├── 01_grab_part_action.json   # Action step
    ├── 02_wait_delay.json         # Delay step
    ├── 03_home.json               # Home step
    └── 04_model_inference.json    # Model step
```

---

## 📝 FILE FORMATS

### Manifest (manifest.json):
```json
{
  "format_version": "2.0",
  "name": "Production Run",
  "type": "composite_sequence",
  "description": "Complete production workflow",
  "loop": false,
  "steps": [
    {
      "step_id": "step_001",
      "step_number": 1,
      "type": "action",
      "name": "Grab Part",
      "file": "01_grab_part_action.json",
      "enabled": true,
      "notes": ""
    },
    {
      "step_id": "step_002",
      "step_number": 2,
      "type": "delay",
      "name": "Wait",
      "file": "02_wait_delay.json",
      "enabled": true,
      "notes": ""
    },
    {
      "step_id": "step_003",
      "step_number": 3,
      "type": "home",
      "name": "Return Home",
      "file": "03_home.json",
      "enabled": true,
      "notes": ""
    }
  ],
  "metadata": {
    "created": "2025-10-18T...",
    "modified": "2025-10-18T...",
    "total_steps": 3
  }
}
```

### Action Step (01_grab_part_action.json):
```json
{
  "step_type": "action",
  "action_name": "GrabPart_v1",
  "action_type": "composite_recording",
  "description": "Grab part from conveyor"
}
```

### Delay Step (02_wait_delay.json):
```json
{
  "step_type": "delay",
  "duration": 2.5,
  "description": "Wait for part to settle"
}
```

### Home Step (03_home.json):
```json
{
  "step_type": "home",
  "velocity": 600,
  "description": "Return to home position"
}
```

### Model Step (04_model_inference.json):
```json
{
  "step_type": "model",
  "task": "GrabBlock",
  "checkpoint": "last",
  "duration": 25.0,
  "description": "AI-driven block placement"
}
```

---

## 🏗️ IMPLEMENTATION PHASES

### Phase 1: New Step Types (30 min)

**Add "home" step type:**

1. **SequenceTab UI:**
```python
# Add home button next to delay
self.add_home_btn = QPushButton("🏠 Home")
self.add_home_btn.setMinimumHeight(45)
self.add_home_btn.setStyleSheet("""
    QPushButton {
        background-color: #4CAF50;
        color: white;
        border: none;
        border-radius: 6px;
        font-size: 14px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #388E3C;
    }
""")
self.add_home_btn.clicked.connect(self.add_home_step)
add_bar.addWidget(self.add_home_btn)

def add_home_step(self):
    """Add a home position step"""
    step = {"type": "home"}
    self.add_step_to_list(step)
    self.status_label.setText("✓ Added home step")
```

2. **Update display logic:**
```python
def add_step_to_list(self, step: dict, number: int = None):
    # ... existing code ...
    
    elif step_type == "home":
        text = f"{number}. 🏠 Home: Return to rest position"
        color = QColor("#4CAF50")
```

3. **ExecutionManager:**
```python
def _execute_sequence(self):
    # ... existing loop ...
    
    elif step_type == "home":
        # Execute home
        self.log_message.emit('info', "→ Returning to home position")
        self._execute_home_inline()
    
def _execute_home_inline(self):
    """Return arm to home position"""
    # Connect if not already connected
    if not self.motor_controller.bus:
        if not self.motor_controller.connect():
            self.log_message.emit('error', "Failed to connect to motors")
            return
    
    # Get home position from config
    home_positions = self.config.get("robot", {}).get("home_position", [2048, 2048, 2048, 2048, 2048, 2048])
    
    self.log_message.emit('info', f"Moving to home position: {home_positions}")
    
    # Move to home
    self.motor_controller.set_positions(
        home_positions,
        velocity=600,
        wait=True,
        keep_connection=True
    )
    
    self.log_message.emit('info', "✓ Reached home position")
```

---

### Phase 2: Create Composite Sequence Classes (1 hour)

**New file: `utils/composite_sequence.py`**

Similar to `composite_recording.py` but for sequences:

```python
class CompositeSequence:
    """Manage folder-based sequences with modular steps"""
    
    def __init__(self, name: str, sequences_dir: Path, loop: bool = False):
        self.name = name
        self.sequences_dir = sequences_dir
        self.loop = loop
        self.steps = []
        self._next_step_number = 1
    
    @property
    def sequence_dir(self) -> Path:
        """Get directory for this sequence"""
        safe_name = sanitize(self.name)
        return self.sequences_dir / safe_name
    
    @property
    def manifest_path(self) -> Path:
        return self.sequence_dir / "manifest.json"
    
    def add_action_step(self, action_name: str, name: str = None) -> str:
        """Add action step and create component file"""
        filename = f"{self._next_step_number:02d}_{sanitize(name)}_action.json"
        filepath = self.sequence_dir / filename
        
        # Save component
        component = {
            "step_type": "action",
            "action_name": action_name
        }
        with open(filepath, 'w') as f:
            json.dump(component, f, indent=2)
        
        # Add to manifest
        step_id = self.add_step("action", name or action_name, filename)
        return step_id
    
    def add_delay_step(self, duration: float, name: str = None) -> str:
        """Add delay step and create component file"""
        # Similar pattern...
    
    def add_home_step(self, name: str = "Home") -> str:
        """Add home step and create component file"""
        # Similar pattern...
    
    def add_model_step(self, task: str, checkpoint: str, duration: float, name: str = None) -> str:
        """Add model step and create component file"""
        # Similar pattern...
    
    def save(self) -> bool:
        """Save manifest"""
        # Similar to CompositeRecording.save()
    
    @staticmethod
    def load(name: str, sequences_dir: Path) -> Optional['CompositeSequence']:
        """Load sequence from folder"""
        # Similar to CompositeRecording.load()
```

---

### Phase 3: Rewrite SequencesManager (30 min)

**Update `utils/sequences_manager.py`:**

```python
from .composite_sequence import CompositeSequence

class SequencesManager:
    """Manage composite sequences (folder-based)"""
    
    def save_sequence(self, name: str, steps: List[Dict], loop: bool = False) -> bool:
        """Save sequence as folder-based composite"""
        try:
            # Create composite sequence
            composite = CompositeSequence(name, self.sequences_dir, loop)
            composite.create_new()
            
            # Add each step
            for step in steps:
                step_type = step.get("type")
                
                if step_type == "action":
                    composite.add_action_step(
                        action_name=step.get("name"),
                        name=step.get("name")
                    )
                elif step_type == "delay":
                    composite.add_delay_step(
                        duration=step.get("duration"),
                        name=f"Delay {step.get('duration')}s"
                    )
                elif step_type == "home":
                    composite.add_home_step()
                elif step_type == "model":
                    composite.add_model_step(
                        task=step.get("task"),
                        checkpoint=step.get("checkpoint", "last"),
                        duration=step.get("duration", 25.0),
                        name=step.get("task")
                    )
            
            # Save manifest
            return composite.save()
            
        except Exception as e:
            print(f"[ERROR] Failed to save sequence: {e}")
            return False
    
    def load_sequence(self, name: str) -> Optional[Dict]:
        """Load sequence and return execution-ready data"""
        composite = CompositeSequence.load(name, self.sequences_dir)
        if not composite:
            return None
        
        return composite.get_full_sequence_data()
    
    def list_sequences(self) -> List[str]:
        """List all sequences (scan for folders with manifest.json)"""
        sequences = []
        for item in self.sequences_dir.iterdir():
            if item.is_dir():
                manifest = item / "manifest.json"
                if manifest.exists():
                    with open(manifest) as f:
                        data = json.load(f)
                        sequences.append(data.get("name", item.name))
        return sorted(sequences)
```

---

### Phase 4: Wire Up Execution (30 min)

**Connect SequenceTab → Dashboard → ExecutionWorker**

1. **sequence_tab.py:**
```python
class SequenceTab(QWidget):
    execute_sequence_signal = Signal(str, bool)  # (name, loop)
    
    def start_sequence(self):
        """Start sequence execution via Dashboard"""
        if self.current_sequence_name == "NewSequence01":
            self.status_label.setText("❌ Save sequence first!")
            self.run_btn.setChecked(False)
            return
        
        # Emit signal to parent
        loop = self.loop_btn.isChecked()
        self.execute_sequence_signal.emit(self.current_sequence_name, loop)
        
        self.is_running = True
        self.run_btn.setText("⏹ STOP (Running on Dashboard)")
```

2. **app.py:**
```python
# Connect sequence tab to dashboard
self.sequence_tab.execute_sequence_signal.connect(
    self.dashboard_tab.run_sequence
)
```

3. **dashboard_tab.py:**
```python
def run_sequence(self, sequence_name: str, loop: bool = False):
    """Execute a sequence (called from SequenceTab)"""
    # Switch to dashboard tab
    parent = self.parent()
    if hasattr(parent, 'switch_tab'):
        parent.switch_tab(0)  # Switch to dashboard
    
    # Set run selector to sequence
    self.run_selector.setCurrentText(sequence_name)
    
    # Start execution
    self._start_execution_worker("sequence", sequence_name)
    
    # Update UI
    self.log_text.append(f"[info] Running sequence: {sequence_name}")
```

---

### Phase 5: ExecutionManager Updates (45 min)

**Update to handle modular sequences:**

```python
def _execute_sequence(self):
    """Execute a composite sequence"""
    # Load sequence
    sequence = self.sequences_mgr.load_sequence(self.execution_name)
    if not sequence:
        self.log_message.emit('error', f"Sequence not found")
        return
    
    # Check if composite or legacy
    if sequence.get("type") == "composite_sequence":
        self._execute_composite_sequence(sequence)
    else:
        # Legacy flat sequence
        self._execute_legacy_sequence(sequence)

def _execute_composite_sequence(self, sequence: dict):
    """Execute modular composite sequence"""
    steps = sequence.get("steps", [])
    loop = sequence.get("loop", False)
    
    iteration = 0
    while True:
        iteration += 1
        
        for idx, step in enumerate(steps):
            if self._stop_requested:
                break
            
            # Check if enabled
            if not step.get('enabled', True):
                continue
            
            step_type = step.get("type")
            
            # Load component data
            component_file = step.get("file")
            component_data = sequence.get(f"component_{step.get('step_id')}", {})
            
            if step_type == "action":
                action_name = component_data.get("action_name")
                self._execute_recording_inline(action_name)
            
            elif step_type == "delay":
                duration = component_data.get("duration", 1.0)
                time.sleep(duration)
            
            elif step_type == "home":
                self._execute_home_inline()
            
            elif step_type == "model":
                # Model execution
                self._execute_model_inline(...)
        
        if not loop or self._stop_requested:
            break
```

---

### Phase 6: Migration Tool (20 min)

**Create `utils/migrate_sequences.py`:**

```python
def migrate_sequence_to_composite(name: str, sequences_mgr: SequencesManager):
    """Convert flat JSON sequence to folder-based composite"""
    # Load old format
    old_data = load_old_format(name)
    
    # Create new composite
    composite = CompositeSequence(name, ...)
    
    # Convert steps
    for step in old_data["steps"]:
        # Add as component...
    
    # Save
    composite.save()
    
    # Backup old file
    backup_old_file(name)
```

---

## 🧪 TESTING PLAN

### Test 1: Home Step
```
1. SequenceTab: Add "🏠 Home" step
2. Save sequence
3. Run sequence
4. EXPECT: Arm returns to home position
```

### Test 2: Mixed Sequence
```
1. Add action "GrabPart"
2. Add delay 2.0s
3. Add home
4. Add action "PlacePart"
5. Run
6. EXPECT: Execute in order
```

### Test 3: Modular Edit
```
1. Create sequence "Production"
2. Save (creates folder)
3. Manually edit step component file
4. Reload sequence
5. EXPECT: Changes reflected
```

---

## ⏱️ TIME ESTIMATE

| Phase | Task | Time |
|-------|------|------|
| 1 | Add home step type | 30 min |
| 2 | Create CompositeSequence class | 1 hour |
| 3 | Rewrite SequencesManager | 30 min |
| 4 | Wire up execution | 30 min |
| 5 | Update ExecutionManager | 45 min |
| 6 | Migration tool | 20 min |
| 7 | Testing | 1 hour |
| **TOTAL** | | **4.5 hours** |

---

## 🚀 IMPLEMENTATION ORDER

1. ✅ Add home step type (quick win, immediate value)
2. ✅ Wire up basic execution (make existing sequences work)
3. ✅ Create CompositeSequence class (new architecture)
4. ✅ Rewrite SequencesManager (use new architecture)
5. ✅ Update ExecutionManager (handle both formats)
6. ✅ Migration tool (convert old sequences)
7. ✅ Full testing

---

## 📝 NOTES

- Keep "action" terminology throughout (not "recording")
- Home step uses existing rest_pos.py functionality
- Sequences will mirror recordings architecture (consistency!)
- Support both legacy flat format and new composite format during transition
- Migration is optional (both formats work)

Ready to implement! 🛠️

