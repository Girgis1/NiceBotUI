# Solo/Bimanual Mode Implementation

## Overview
Redesigning NiceBotUI to support proper LeRobot bimanual robot types (`bi_so100_follower`) vs solo arms (`so100_follower`).

## Key Changes

### 1. Config Structure ✅ DONE
```json
{
  "robot": {
    "mode": "solo",  // or "bimanual"
    "arms": [
      { "arm_id": 1, "port": "/dev/ttyACM0", ... },
      { "arm_id": 2, "port": "/dev/ttyACM1", ... }
    ]
  },
  "teleop": {
    "mode": "solo",  // or "bimanual"  
    "arms": [...]
  }
}
```

### 2. Settings Tab UI - TODO
**Replace** dynamic add/remove arms **with**:
- Radio buttons: `( ) Solo  ( ) Bimanual`
- **Solo mode**: Dropdown to select Arm 1 or Arm 2, configure that arm
- **Bimanual mode**: Show both arms side-by-side (Left=Arm1, Right=Arm2)
- Apply same to Teleop section

### 3. Robot Worker - TODO
Must build different lerobot-record commands:

**Solo Mode:**
```bash
lerobot-record \
  --robot.type=so100_follower \
  --robot.port=/dev/ttyACM0 \
  --robot.id=follower_arm
```

**Bimanual Mode:**
```bash
lerobot-record \
  --robot.type=bi_so100_follower \
  --robot.left_arm_port=/dev/ttyACM0 \
  --robot.right_arm_port=/dev/ttyACM1 \
  --robot.id=bimanual_follower \
  --teleop.type=bi_so100_leader \
  --teleop.left_arm_port=/dev/ttyACM2 \
  --teleop.right_arm_port=/dev/ttyACM3
```

### 4. Action/Sequence Metadata - TODO
Add `mode` field to ActionStep:
```python
class ActionStep:
    mode: str = "solo"  # or "bimanual"
```

### 5. Display Icons - TODO
- Solo actions: 👤 icon
- Bimanual actions: 👥 icon
- Show in:
  - Recording tab action list
  - Sequence tab step list
  - Dashboard run selector

### 6. Recording Tab - TODO
- Show current mode at top
- Validate: Bimanual requires both robot arms + both teleop arms enabled
- Save mode with action metadata

### 7. Composite Sequences - TODO
- Save mode with each action step
- Display mode icon in sequence viewer
- Validate mode compatibility when adding steps

## Implementation Status

### Phase 1: Settings & Config ✅
- [x] Config structure with mode field
- [x] Migration logic for old configs  
- [x] Mode saving in settings (auto-defaults to "solo")
- [x] Mode widgets created (ModeSelector, SingleArmConfig)
- [ ] Settings UI fully redesigned (deferred - works with defaults)

### Phase 2: Robot Worker & Recording 🚧 IN PROGRESS
- [ ] Robot worker command builder (NEXT)
- [ ] Recording tab mode indicator
- [ ] Action metadata with mode

### Phase 3: Polish & Icons
- [ ] Display icons throughout UI
- [ ] Sequence mode handling
- [ ] Testing solo mode
- [ ] Testing bimanual mode

## Critical Rules

1. **Cannot mix modes in a single recording**
   - A dataset is EITHER solo OR bimanual
   - Policy trained on solo won't work with bimanual hardware

2. **Bimanual requires ALL arms**
   - Both robot arms must be enabled + configured
   - Both teleop arms must be enabled + configured (if using teleop)

3. **Motor key prefixes**
   - Solo: `shoulder_pan.pos`
   - Bimanual: `left_shoulder_pan.pos`, `right_shoulder_pan.pos`

4. **Calibration IDs**
   - Solo: Uses arm's `id` field directly
   - Bimanual: Appends `_left` and `_right` automatically

## Next Steps

1. Create simplified Settings tab UI with mode toggle
2. Update robot_worker.py to detect mode and build correct commands
3. Add mode icons to all action/sequence displays
4. Test end-to-end: record solo, record bimanual, replay both

