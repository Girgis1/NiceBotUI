# 🔍 SEQUENCER ANALYSIS & REBUILD PLAN

**Current Status:** Sequencer has NEVER worked  
**Branch:** `dev`  
**Target:** Robust, tested, working sequencer integrated with composite recordings

---

## 🐛 CRITICAL ISSUES FOUND

### Issue 1: SequenceTab RUN Button Does Nothing ❌

**Location:** `tabs/sequence_tab.py` line 568-570

```python
# TODO: Implement actual sequence execution
# This would need to coordinate with the main app to execute actions and models
QTimer.singleShot(2000, self.stop_sequence)  # Placeholder
```

**Problem:** Button just waits 2 seconds then stops. No execution happens!

---

### Issue 2: Type Mismatch Between Save and Execute ❌

**What SequenceTab Saves:** `{"type": "action", "name": "MyRecording"}`  
**What ExecutionManager Expects:** `{"type": "recording", "name": "MyRecording"}`

**Location:**
- Saving: `tabs/sequence_tab.py` line 406
- Execution: `utils/execution_manager.py` line 380

**Impact:** Even if execution ran, it wouldn't recognize the steps!

---

### Issue 3: No Dashboard Integration ❌

**Problem:** SequenceTab has NO way to trigger Dashboard execution  
**Current Flow:** Button click → does nothing → stops after 2 seconds  
**Needed Flow:** Button click → tell Dashboard → Dashboard starts ExecutionWorker

---

### Issue 4: Model Execution Not Implemented ❌

**Location:** `utils/execution_manager.py` line 392-395

```python
elif step_type == "model":
    # Execute model
    self.log_message.emit('warning', "Model execution not yet implemented in sequences")
    # TODO: Implement model execution
```

**Problem:** Can't run AI models from sequences

---

## ✅ WHAT ACTUALLY WORKS

### ExecutionManager Has Good Foundation ✓

The `_execute_sequence()` method (lines 348-411) is well-structured:
- ✅ Loads sequence from SequencesManager
- ✅ Loops through steps
- ✅ Handles loop mode correctly
- ✅ Executes recordings via `_execute_recording_inline()`
- ✅ Handles delays
- ✅ Progress updates and logging
- ✅ Works with composite recordings!

### SequencesManager Works ✓

- ✅ Saves sequences to individual JSON files
- ✅ Loads sequences correctly
- ✅ Lists all sequences
- ✅ Automatic backups

### UI Is Well Designed ✓

- ✅ Clean interface for building sequences
- ✅ Drag-and-drop reordering
- ✅ Add actions, models, delays
- ✅ Visual feedback with colors
- ✅ Loop toggle

---

## 🏗️ ROBUST REBUILD PLAN

### Phase 1: Fix Data Format (Type Consistency)

**Goal:** Make SequenceTab save data that ExecutionManager understands

**Changes in `sequence_tab.py`:**

```python
# OLD (line 406):
step = {"type": "action", "name": action}

# NEW:
step = {"type": "recording", "name": action}  # Match ExecutionManager expectation
```

**Also update:**
- Display text logic (line 368-383) to show "recording" type correctly
- Step coloring to be consistent

---

### Phase 2: Connect SequenceTab to Dashboard Execution

**Goal:** Wire up RUN SEQUENCE button to actually execute

**Option A: Signal to Parent (Recommended)**
```python
# In sequence_tab.py:
class SequenceTab(QWidget):
    execute_sequence_signal = Signal(str, bool)  # (sequence_name, loop)
    
    def start_sequence(self):
        """Emit signal to parent to execute"""
        sequence_name = self.current_sequence_name
        loop = self.loop_btn.isChecked()
        
        if sequence_name and sequence_name != "NewSequence01":
            self.execute_sequence_signal.emit(sequence_name, loop)
        else:
            self.status_label.setText("❌ Save sequence first!")
```

**In app.py:**
```python
# Connect sequence tab signal to dashboard
self.sequence_tab.execute_sequence_signal.connect(
    lambda name, loop: self.dashboard_tab.run_sequence(name, loop)
)
```

**In dashboard_tab.py:**
```python
def run_sequence(self, sequence_name: str, loop: bool):
    """Execute a sequence (called from SequenceTab)"""
    # Switch to dashboard tab
    # Start ExecutionWorker with type="sequence"
    self._start_execution_worker("sequence", sequence_name)
```

---

### Phase 3: Implement Model Execution in Sequences

**Goal:** Allow AI models to run as sequence steps

**In `execution_manager.py` (line 392-395):**

```python
elif step_type == "model":
    # Execute model
    task = step.get("task")
    checkpoint = step.get("checkpoint", "last")
    duration = step.get("duration", 25.0)
    
    self.log_message.emit('info', f"→ Executing model: {task} ({checkpoint}) for {duration}s")
    self._execute_model_inline(task, checkpoint, duration)
```

**Add new method:**
```python
def _execute_model_inline(self, task: str, checkpoint: str, duration: float):
    """Execute a trained model as part of sequence"""
    # Import RobotWorker
    from robot_worker import RobotWorker
    
    # Build checkpoint path
    train_dir = Path(self.config["policy"].get("base_path", ""))
    checkpoint_path = train_dir / task / "checkpoints" / checkpoint / "pretrained_model"
    
    # Create config for this model
    model_config = self.config.copy()
    model_config["policy"]["path"] = str(checkpoint_path)
    
    # Create and start worker
    worker = RobotWorker(model_config)
    
    # Connect signals for logging
    worker.log_message.connect(lambda level, msg: self.log_message.emit(level, msg))
    worker.status_update.connect(lambda msg: self.status_update.emit(msg))
    
    # Start worker
    worker.start()
    
    # Wait for duration
    start_time = time.time()
    while time.time() - start_time < duration:
        if self._stop_requested:
            worker.stop()
            break
        time.sleep(0.1)
    
    # Stop worker
    worker.stop()
    worker.wait(5000)
```

---

### Phase 4: Enhance UI with Real-Time Feedback

**Goal:** Show sequence execution progress in SequenceTab

**Add to sequence_tab.py:**

```python
def start_sequence(self):
    """Start running the sequence"""
    steps = self.get_all_steps()
    
    if not steps:
        self.status_label.setText("❌ No steps to run")
        self.run_btn.setChecked(False)
        return
    
    # Save sequence first if needed
    if self.current_sequence_name == "NewSequence01":
        self.status_label.setText("❌ Please save sequence before running")
        self.run_btn.setChecked(False)
        return
    
    self.is_running = True
    self.run_btn.setText("⏹ STOP")
    
    # Disable editing while running
    self.add_action_btn.setEnabled(False)
    self.add_model_btn.setEnabled(False)
    self.add_delay_btn.setEnabled(False)
    self.save_btn.setEnabled(False)
    self.new_btn.setEnabled(False)
    
    # Emit signal to start execution
    loop = self.loop_btn.isChecked()
    self.execute_sequence_signal.emit(self.current_sequence_name, loop)
    
    self.status_label.setText(f"▶ Running: {self.current_sequence_name}")

def on_execution_completed(self, success: bool, message: str):
    """Called when sequence execution completes"""
    self.stop_sequence()
    if success:
        self.status_label.setText(f"✓ {message}")
    else:
        self.status_label.setText(f"❌ {message}")
```

---

### Phase 5: Add Sequence Validation

**Goal:** Validate sequence before running

**Add validation method:**

```python
def validate_sequence(self) -> tuple[bool, str]:
    """Validate sequence can be executed
    
    Returns:
        (is_valid, error_message)
    """
    steps = self.get_all_steps()
    
    if not steps:
        return False, "No steps in sequence"
    
    # Check all recordings exist
    for step in steps:
        if step.get("type") == "recording":
            name = step.get("name")
            if not self.actions_manager.action_exists(name):
                return False, f"Recording not found: {name}"
        
        elif step.get("type") == "model":
            task = step.get("task")
            train_dir = Path(self.config["policy"].get("base_path", ""))
            checkpoint_path = train_dir / task / "checkpoints"
            if not checkpoint_path.exists():
                return False, f"Model not found: {task}"
    
    return True, "Valid"
```

---

### Phase 6: Add Error Recovery

**Goal:** Handle errors gracefully without crashing

**In execution_manager.py:**

```python
def _execute_sequence(self):
    """Execute a sequence of steps with error recovery"""
    # ... existing code ...
    
    for idx, step in enumerate(steps):
        if self._stop_requested:
            break
        
        try:
            step_type = step.get("type")
            
            if step_type == "recording":
                # ... execute recording ...
            elif step_type == "delay":
                # ... delay ...
            elif step_type == "model":
                # ... execute model ...
        
        except Exception as e:
            # Log error but continue to next step
            self.log_message.emit('error', f"Step {idx+1} failed: {e}")
            
            # Optional: Ask user if they want to continue
            # For now, just log and continue
            continue
```

---

## 📋 IMPLEMENTATION CHECKLIST

### Must Have (Working Sequencer):
- [ ] Fix type mismatch (action → recording)
- [ ] Wire RUN button to Dashboard execution
- [ ] Connect ExecutionWorker signals to SequenceTab
- [ ] Validate sequence before running
- [ ] Test: Record 2 actions → Build sequence → Run sequence → Verify execution
- [ ] Test: Add delay → Verify delay works
- [ ] Test: Loop mode → Verify repeats
- [ ] Test: Stop button → Verify stops mid-execution

### Should Have (Robust):
- [ ] Model execution in sequences
- [ ] Real-time progress updates in sequence list (highlight current step)
- [ ] Error recovery (continue on step failure)
- [ ] Sequence validation before run
- [ ] Visual feedback during execution
- [ ] Save button automatically saves before run

### Nice to Have (Polish):
- [ ] Edit step properties (double-click to edit)
- [ ] Pause/resume functionality
- [ ] Step-by-step execution (debug mode)
- [ ] Export/import sequences
- [ ] Duplicate steps
- [ ] Copy sequence
- [ ] Sequence templates

---

## 🧪 TESTING PLAN

### Test 1: Basic Sequence Execution
```
1. Record Tab: Record Position 1
2. Record Tab: Record Position 2
3. Record Tab: Save as "TestRecording"
4. Sequence Tab: Add action "TestRecording"
5. Sequence Tab: Add delay 2.0s
6. Sequence Tab: Add action "TestRecording" again
7. Sequence Tab: Save as "TestSequence"
8. Sequence Tab: Click RUN SEQUENCE
9. EXPECT: Executes TestRecording → waits 2s → executes TestRecording again
```

### Test 2: Loop Mode
```
1. Load "TestSequence" from Test 1
2. Enable Loop
3. Click RUN SEQUENCE
4. Let it run 2 iterations
5. Click STOP
6. EXPECT: Stops cleanly, UI returns to normal
```

### Test 3: Mixed Sequence
```
1. Create sequence with:
   - Live recording
   - Position recording
   - Delay
   - Model (if implemented)
2. Run sequence
3. EXPECT: All types execute correctly
```

### Test 4: Error Handling
```
1. Create sequence referencing non-existent recording
2. Try to run
3. EXPECT: Validation catches error, doesn't start
```

---

## 🎯 SUCCESS CRITERIA

**Minimum Viable:**
✅ Can build a sequence with multiple recordings  
✅ Can save sequence  
✅ Can run sequence from SequenceTab  
✅ Execution happens on Dashboard  
✅ Can see execution progress  
✅ Can stop mid-execution  
✅ Delays work correctly  

**Robust:**
✅ Error handling doesn't crash app  
✅ Validation before execution  
✅ Models work in sequences  
✅ Loop mode works  
✅ UI feedback is clear  
✅ All signals properly connected/disconnected  

---

## 🚀 IMPLEMENTATION ORDER

1. **Fix data format** (15 min) - Quick win, necessary for everything else
2. **Wire up execution** (30 min) - Signal from SequenceTab → Dashboard
3. **Test basic sequence** (15 min) - Validate it works
4. **Add validation** (20 min) - Prevent errors
5. **Implement model execution** (45 min) - Complete feature set
6. **Add UI feedback** (30 min) - Polish
7. **Error recovery** (30 min) - Robustness
8. **Full testing** (1 hour) - All scenarios

**Total estimated time: 3-4 hours**

---

## 📝 NOTES

- SequenceTab should NOT execute directly - always go through Dashboard/ExecutionWorker
- Keep ExecutionManager as single source of truth for execution
- Signals are better than direct calls (loose coupling)
- Save sequence before running (prevent loss of work)
- Always validate before starting execution
- Consider making sequence execution atomic (all or nothing) vs. best-effort (continue on error)

---

Ready to implement! 🛠️

