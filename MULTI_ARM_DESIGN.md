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

### Before (Single Arm):
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

### After (Flexible Multi-Arm - Array Based):
```json
{
  "robot": {
    "arms": [
      {
        "enabled": true,
        "name": "Follower 1",
        "type": "so100_follower",
        "port": "/dev/ttyACM0",
        "id": "follower_arm",
        "home_positions": [2082, 1106, 2994, 2421, 1044, 2054],
        "home_velocity": 600
      },
      {
        "enabled": false,
        "name": "Follower 2",
        "type": "so100_follower",
        "port": "/dev/ttyACM2",
        "id": "follower_right",
        "home_positions": [2082, 1106, 2994, 2421, 1044, 2054],
        "home_velocity": 600
      }
    ],
    "fps": 60,
    "min_time_to_move_multiplier": 3.0,
    "enable_motor_torque": true,
    "position_tolerance": 45,
    "position_verification_enabled": true
  },
  "teleop": {
    "arms": [
      {
        "enabled": true,
        "name": "Leader 1",
        "type": "so100_leader",
        "port": "/dev/ttyACM1",
        "id": "leader_arm"
      },
      {
        "enabled": false,
        "name": "Leader 2",
        "type": "so100_leader",
        "port": "/dev/ttyACM3",
        "id": "leader_right"
      }
    ]
  }
}
```

### Key Features:
- **Max 2 follower arms, max 2 leader arms** (4 total max)
- **Per-arm enable/disable** toggle
- **Per-arm home positions** and velocities
- **Named arms** for easy identification
- Empty arrays mean zero arms configured
- Easy to add/remove arms from the list

## UI Changes - Settings Tab

### New Layout:
```
🤖 Robot Arms (Followers)                        [➕ Add Arm] (disabled if 2 already)

┌─ Follower 1 ────────────────────── [☑ Enabled] [🗑️] ─┐
│ ○ Port: /dev/ttyACM0                                  │
│ ○ Calib ID: [follower_arm ▼]                         │
│ ○ Home Pos: [2082, 1106, 2994, ...]  Vel: [600]      │
│ [🏠 Home] [Set Home] [⚙️ Calibrate]                  │
└───────────────────────────────────────────────────────┘

┌─ Follower 2 ────────────────────── [☐ Enabled] [🗑️] ─┐
│ ○ Port: /dev/ttyACM2                                  │
│ ○ Calib ID: [follower_right ▼]                       │
│ ○ Home Pos: [2082, 1106, 2994, ...]  Vel: [600]      │
│ [🏠 Home] [Set Home] [⚙️ Calibrate]                  │
└───────────────────────────────────────────────────────┘

[🏠 Home All Enabled Arms]

○ Hertz: 60 (shared across all arms)
○ Position Tolerance: 45

─────────────────────────────────────────────────────────

🎮 Teleop Arms (Leaders)                         [➕ Add Arm]

┌─ Leader 1 ──────────────────────── [☑ Enabled] [🗑️] ─┐
│ ○ Port: /dev/ttyACM1                                  │
│ ○ Calib ID: [leader_arm ▼]                           │
└───────────────────────────────────────────────────────┘

[Same structure, up to 2 leader arms]
```

### UI Behavior:
- **➕ Add Arm**: Adds a new arm to the list (max 2 per type)
- **☑/☐ Enabled**: Toggle to enable/disable the arm
- **🗑️ Delete**: Remove this arm from config
- **Disabled arms**: Grayed out, still visible in config
- **Home All**: Only homes enabled arms
- **Set Home**: Saves current position to that arm's home_positions

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
3. ✅ Update config.json with new structure (add defaults)
4. ✅ **Phase 1:** Core infrastructure (config_compat, motor controller, HomePos, workers)
5. ✅ **Phase 2:** Settings Tab UI with dynamic arm management
   - ✅ Add/Remove arm buttons with 2-arm limit
   - ✅ ArmConfigSection widgets for each arm
   - ✅ Per-arm home positions and velocities
   - ✅ Home All enabled arms button
   - ✅ Enable/disable toggles per arm
   - ✅ Delete arm functionality
6. ✅ Test single mode (backward compatibility)
7. ✅ Test multi-arm mode
8. ✅ Documentation and push

## Status: ✅ **PHASE 2 COMPLETE**

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

