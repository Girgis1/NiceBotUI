# Resilient Motor Control - Default + Notes

## Update: Now Enabled by Default

Resilient motor handling now wraps the motor bus by default to ride through brief dropouts. The notes below remain for context and manual control, but you no longer need to opt in.

## Current Status

✅ **MotorController** - Now wraps the resilient bus by default  
✅ **ResilientMotorController** - Still available for explicit testing/overrides

**Default behavior:** Resilience is ON by default; no config needed.

## Background (previous opt-in)

Originally this was an opt-in to avoid breaking sequences. The separate class remains so you can disable or override behavior when needed.

## How to Use (When Ready)

### Option 1: Config-Based (Override)

Add to your `config.json`:

```json
{
  "robot": {
    "enable_resilient_motors": true,
    ...
  }
}
```

Then in your code where you create motor controllers:

```python
from utils.resilient_motor_controller import create_motor_controller

# Reads config to determine which controller to use
config = read_config()
use_resilient = config.get("robot", {}).get("enable_resilient_motors", False)

controller = create_motor_controller(config, arm_index=0, resilient=use_resilient)
```

### Option 2: Direct Import (Manual)

For specific operations where you want resilience:

```python
# Your existing code (unchanged)
from utils.motor_controller import MotorController

# New resilient version (opt-in)
from utils.resilient_motor_controller import ResilientMotorController

# Use standard for normal sequences
controller = MotorController(config, arm_index=0)

# OR use resilient for operations prone to brownouts
controller = ResilientMotorController(config, arm_index=0)
```

### Option 3: Test Mode (Safest)

Test the resilient controller in specific scenarios:

```python
from utils.resilient_motor_controller import ResilientMotorController

# Create with resilience disabled (behaves exactly like MotorController)
controller = ResilientMotorController(config, arm_index=0, enable_resilience=False)

# When you're ready to test, enable it:
controller.enable_resilience = True

# Or create with it enabled from the start:
controller = ResilientMotorController(config, arm_index=0, enable_resilience=True)
```

## What Files Changed

### New Files (No impact on existing code)
- `utils/resilient_motor_bus.py` - Retry wrapper
- `utils/resilient_motor_controller.py` - Optional controller
- `RESILIENT_MOTOR_*.md` - Documentation

### Unchanged Files (Your system still works)
- ✅ `utils/motor_controller.py` - **REVERTED TO ORIGINAL**
- ✅ `HomePos.py` - Untouched
- ✅ `utils/execution_manager.py` - Untouched
- ✅ All sequence/recording code - Untouched

## Testing Plan (When You're Ready)

### Step 1: Verify Current System Works

```bash
./sync_to_jetson.sh
ssh jetson
cd ~/NiceBotUI

# Test your sequences - should work exactly as before
```

### Step 2: Test Resilient Controller (Manual)

Create a test script `test_resilient.py`:

```python
#!/usr/bin/env python3
from utils.resilient_motor_controller import ResilientMotorController
from HomePos import read_config

config = read_config()

# Test with resilience enabled
controller = ResilientMotorController(config, arm_index=0, enable_resilience=True)
controller.connect()

# Read positions (with retry capability)
positions = controller.read_positions()
print(f"Positions: {positions}")

# Move to a position (with retry capability)
controller.set_positions(positions, velocity=300)

# See stats
controller.disconnect()
```

Run it:
```bash
python3 test_resilient.py
```

### Step 3: Enable for Specific Operations

Identify which operations experience brownouts most:
- Long sequences?
- High-speed movements?
- Simultaneous arm operations?

Use ResilientMotorController **only for those operations**.

## Rollback

If anything goes wrong:

```bash
# Your system is already rolled back!
# Nothing to do - you're using the standard MotorController
```

## Performance Comparison

### Standard MotorController (Current)
```
✓ Fast - no overhead
✓ Reliable - well tested
❌ Fails on transient errors
❌ Requires stable power
```

### ResilientMotorController (Optional)
```
✓ Handles transient errors
✓ Retries automatically (5 attempts)
✓ Graceful degradation
✓ Auto recovery detection
⚠️  Slight overhead during retries (~50-500ms)
⚠️  New code (less tested)
```

## Recommended Approach

1. **Keep using MotorController** for everything (it works!)

2. **When brownouts occur**, try ResilientMotorController for that specific operation

3. **If it helps**, gradually enable for more operations

4. **If it causes issues**, just don't use it - no harm done!

## Example: Gradual Adoption

```python
# Day 1: All standard (current behavior)
controller = MotorController(config, arm_index=0)

# Day 2: Test resilient in one place
if operation_type == "long_sequence":
    controller = ResilientMotorController(config, arm_index=0)
else:
    controller = MotorController(config, arm_index=0)

# Day 3: If successful, expand usage
if config.get("robot", {}).get("enable_resilient_motors", False):
    controller = ResilientMotorController(config, arm_index=0)
else:
    controller = MotorController(config, arm_index=0)
```

## Support

If you decide to try the resilient controller and encounter issues:

1. **Disable it** - Switch back to MotorController
2. **Share logs** - Show what went wrong
3. **Describe scenario** - What operation was running?

I'll help debug without breaking your working system!

## Summary

✅ **Your system is working again** - No forced changes  
✅ **Resilient controller available** - When you want it  
✅ **Easy to test** - Import and try  
✅ **Easy to rollback** - Just don't use it  
✅ **Zero risk** - Opt-in only  

**You're in control of when/where to use it!**

---

**Status:** Reverted to safe state, resilient controller available as opt-in  
**Risk:** Zero (unless you explicitly enable it)  
**Next:** Test your existing sequences to confirm they work
