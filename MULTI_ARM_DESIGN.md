# Multi-Arm Robot Support Design Document

## Overview
This document outlines the design for adding multi-arm (bimanual) robot support to NiceBot UI.

## LeRobot Support
LeRobot has built-in support for bimanual robots:
- `bi_so100_follower` - Bimanual follower (2 robot arms)
- `bi_so100_leader` - Bimanual leader (2 teleop arms)
- `bi_so101_follower` / `bi_so101_leader` - SO-101 variants

### Key Differences for Bimanual:
1. **Separate Ports**: Each arm gets its own serial port
   - `left_arm_port` and `right_arm_port` instead of `port`
2. **Auto-prefixed IDs**: Calibration IDs get "_left" and "_right" appended
   - If `id="my_robot"`, it becomes `my_robot_left` and `my_robot_right`
3. **Prefixed Motor Keys**: All observations/actions get "left_" and "right_" prefixes
   - `shoulder_pan.pos` becomes `left_shoulder_pan.pos` and `right_shoulder_pan.pos`

## New Config Structure

###before (Single Arm):
```json
{
  "robot": {
    "type": "so100_follower",
    "port": "/dev/ttyACM0",
    "id": "follower_arm",
    "fps": 60,
    ...
  },
  "teleop": {
    "type": "so100_leader",
    "port": "/dev/ttyACM1",
    "id": "leader_arm"
  }
}
```

### After (Supporting Both):
```json
{
  "robot": {
    "mode": "single",  // or "dual"
    "type": "so100_follower",  // changes to "bi_so100_follower" when mode="dual"
    
    // Single arm settings (used when mode="single")
    "port": "/dev/ttyACM0",
    "id": "follower_arm",
    
    // Dual arm settings (used when mode="dual")
    "left_arm_port": "/dev/ttyACM0",
    "left_arm_id": "follower_left",
    "right_arm_port": "/dev/ttyACM2",
    "right_arm_id": "follower_right",
    
    // Common settings (shared regardless of mode)
    "fps": 60,
    "min_time_to_move_multiplier": 3.0,
    "enable_motor_torque": true,
    "position_tolerance": 45,
    "position_verification_enabled": true
  },
  "teleop": {
    "mode": "single",
    "type": "so100_leader",
    
    "port": "/dev/ttyACM1",
    "id": "leader_arm",
    
    "left_arm_port": "/dev/ttyACM1",
    "left_arm_id": "leader_left",
    "right_arm_port": "/dev/ttyACM3",
    "right_arm_id": "leader_right"
  },
  "rest_position": {
    // For single arm (when robot.mode="single")
    "positions": [2082, 1106, 2994, 2421, 1044, 2054],
    "velocity": 600,
    
    // For dual arms (when robot.mode="dual")
    "left_positions": [2082, 1106, 2994, 2421, 1044, 2054],
    "left_velocity": 600,
    "right_positions": [2082, 1106, 2994, 2421, 1044, 2054],
    "right_velocity": 600,
    
    "disable_torque_on_arrival": true
  }
}
```

## UI Changes - Settings Tab

### Current Layout:
- Single robot configuration section
- One set of controls: Port, Calib ID, Hertz
- One "Home" button, one "Calibrate" button

### New Layout:
```
🤖 Robot Configuration
  [ ] Single Arm  (•) Dual Arms
  
  [When Single Arm selected:]
  ○ Port: /dev/ttyACM0
  ○ Calib ID: [follower_arm ▼]
  ○ Hertz: 60
  [🏠 Home] [Set Home] [⚙️ Calibrate]
  
  [When Dual Arms selected:]
  ┌─ Left Arm ──────────────────────┐
  │ ○ Port: /dev/ttyACM0            │
  │ ○ Calib ID: [follower_left ▼]  │
  │ [🏠 Home] [Set Home] [⚙️ Calib] │
  └─────────────────────────────────┘
  
  ┌─ Right Arm ─────────────────────┐
  │ ○ Port: /dev/ttyACM2            │
  │ ○ Calib ID: [follower_right ▼] │
  │ [🏠 Home] [Set Home] [⚙️ Calib] │
  └─────────────────────────────────┘
  
  ○ Hertz: 60 (shared)
  [🏠 Home All]

🎮 Teleoperation
  [ ] Single Arm  (•) Dual Arms
  [Same layout as robot section]
```

## Code Changes Required

### 1. Config Migration
- Add `mode` field with default "single" for backward compatibility
- Auto-detect old configs and add "mode": "single"
- Validate dual-arm configs have all required fields

### 2. Settings Tab (`tabs/settings_tab.py`)
- Add mode toggle (radio buttons or toggle switch)
- Show/hide appropriate fields based on mode
- Per-arm controls for calibration and homing
- "Home All" button when in dual mode
- Save/load logic for both modes

### 3. Motor Controller (`utils/motor_controller.py`)
- Support both single and dual arm modes
- When dual: create two motor buses (one per arm)
- Handle prefixed motor names (left_*, right_*)
- Home position logic for individual arms

### 4. Device Manager (`utils/device_manager.py`)
- Detect multiple robot arms on different ports
- Track status per arm (left online, right offline, etc.)
- Discovery should find all available arms

### 5. Dashboard Tab
- "Home All" button at top should home all arms
- Status indicators for each arm (if dual mode)

## Implementation Steps

1. ✅ Research LeRobot bimanual support
2. ✅ Design config structure and UI layout
3. Update config.json with new structure (add defaults)
4. Refactor Settings Tab UI
   - Add mode toggles
   - Create collapsible arm sections
   - Per-arm controls
5. Update Motor Controller
   - Support dual mode
   - Multiple motor buses
6. Update Device Manager
   - Multi-arm discovery
   - Per-arm status tracking
7. Update Dashboard
   - Home All button
   - Multi-arm status display
8. Test single mode (backward compatibility)
9. Test dual mode
10. Documentation and push

## Backward Compatibility

All existing single-arm configs will work without modification:
- `mode` defaults to "single"
- Single-arm fields (`port`, `id`) are preserved
- Old configs auto-upgrade on first load

## Future Enhancements

- Support for more than 2 arms (e.g., 3 or 4 arms)
- Individual arm enable/disable
- Per-arm speed multipliers
- Synchronized vs independent homing

