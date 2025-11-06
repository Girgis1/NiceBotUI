# Fix: Setting Home for Arm 2 in Bimanual Mode

## Problem
When trying to set home position for the second arm (Arm 2) in bimanual mode, the system was encountering errors because it referenced old UI widget structures that no longer exist after the Solo/Bimanual UI redesign.

## Root Cause
The `set_home_arm(arm_index)` method was still trying to access:
- `self.robot_arm_widgets[arm_index]` - This array was removed in the UI redesign
- `.get_home_velocity()` - This method was removed when we centralized velocity control

## Changes Made

### 1. Updated `set_home_arm()` Method
**File**: `tabs/settings_tab.py`

- ✅ Removed references to old `robot_arm_widgets` array
- ✅ Now uses `robot_arm1_config` and `robot_arm2_config` directly
- ✅ Uses master velocity from `rest_velocity_spin` instead of per-arm velocity
- ✅ Properly updates UI widgets based on:
  - Current mode (solo/bimanual)
  - Which arm index is being set
  - Which arm is currently displayed in solo mode

### 2. Updated `on_solo_arm_changed()` Method
- ✅ Removed obsolete `set_velocity()` call
- ✅ Now only sets port, ID, and home positions

## How It Works Now

### Bimanual Mode
1. User clicks "Set Home" on Left Arm (Arm 1):
   - Calls `set_home_arm(0)`
   - Reads positions from Arm 1
   - Saves to `config["robot"]["arms"][0]["home_positions"]`
   - Updates `robot_arm1_config` widget display
   - Saves config to disk

2. User clicks "Set Home" on Right Arm (Arm 2):
   - Calls `set_home_arm(1)`
   - Reads positions from Arm 2
   - Saves to `config["robot"]["arms"][1]["home_positions"]`
   - Updates `robot_arm2_config` widget display
   - Saves config to disk

### Solo Mode
1. User selects Arm 1 or Arm 2 from dropdown
2. UI loads that arm's current settings
3. User clicks "Set Home"
   - Calls `set_home_arm(0)` or `set_home_arm(1)` based on selection
   - Saves to correct arm index in config
   - Updates `solo_arm_config` widget if that arm is currently displayed

## Testing Steps

### Test 1: Bimanual Mode - Set Home for Both Arms
1. Open Settings tab
2. Select "Bimanual" mode
3. Manually position Arm 1 to desired home position
4. Click "Set Home" on Left Arm (Arm 1)
5. Verify: Success message shows saved positions
6. Manually position Arm 2 to desired home position
7. Click "Set Home" on Right Arm (Arm 2)
8. Verify: Success message shows saved positions
9. Click "🏠 Home All Arms" button at top
10. Verify: Both arms move to their respective home positions

### Test 2: Solo Mode - Set Home for Each Arm
1. Open Settings tab
2. Select "Solo" mode
3. Select "Arm 1" from dropdown
4. Manually position Arm 1 to desired home position
5. Click "Set Home"
6. Verify: Success message and home positions update in UI
7. Select "Arm 2" from dropdown
8. Verify: UI switches to show Arm 2's settings
9. Manually position Arm 2 to desired home position
10. Click "Set Home"
11. Verify: Success message and home positions update in UI

### Test 3: Config Persistence
1. Set home for both arms (using either method above)
2. Click "Save Settings" button
3. Close the application
4. Reopen the application
5. Go to Settings tab
6. Verify: Both arms show their correct home positions
7. Test homing each arm individually
8. Verify: Arms move to correct saved positions

## What's Fixed
- ✅ Setting home for Arm 2 no longer crashes
- ✅ Home positions are properly saved for both arms
- ✅ UI correctly updates when home is set
- ✅ Config is properly written to disk
- ✅ Homing works correctly for both arms

## Technical Details

### Config Structure
```json
{
  "robot": {
    "mode": "bimanual",
    "arms": [
      {
        "arm_id": 1,
        "enabled": true,
        "home_positions": [2048, 2048, 2048, 2048, 2048, 2048],
        "home_velocity": 600
      },
      {
        "arm_id": 2,
        "enabled": true,
        "home_positions": [2100, 2000, 2950, 2400, 1050, 2060],
        "home_velocity": 600
      }
    ]
  }
}
```

### Key Functions
- `set_home_arm(arm_index)` - Sets home position for specific arm
- `home_arm(arm_index)` - Moves specific arm to its home position
- `home_all_arms()` - Homes all enabled arms sequentially

### Master Velocity
All home movements now use the master velocity value from the top of the Settings tab. This value is saved to each arm's `home_velocity` field in the config for consistency.

## Related Files
- `tabs/settings_tab.py` - Main settings UI with fixed methods
- `utils/config_compat.py` - Config helpers (no changes needed)
- `utils/mode_widgets.py` - SingleArmConfig widget (velocity removed)
- `config.json` - Stores home positions per arm

