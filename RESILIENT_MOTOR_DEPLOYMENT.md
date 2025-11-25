# Resilient Motor Control - Deployment Guide

## Quick Deploy to Jetson

```bash
# 1. Sync to Jetson
./sync_to_jetson.sh

# 2. SSH in
ssh jetson
cd ~/NiceBotUI

# 3. Test it
# Run your normal operations (app, teleoperation, sequences, etc.)
```

## What Changed

### New Files
- `utils/resilient_motor_bus.py` - Retry wrapper for motor bus
- `RESILIENT_MOTOR_CONTROL.md` - Full documentation
- `RESILIENT_MOTOR_DEPLOYMENT.md` - This file

### Modified Files
- `utils/motor_controller.py` - Now wraps bus with resilient layer

**All changes are backwards compatible** - your existing code works unchanged!

## Expected Behavior

### Before This Update
```
[WARNING] Failed to read 'Present_Load' on id_=5 after 1 tries. [RxPacketError] Input voltage error!
[WARNING] Failed to read 'Present_Voltage' on id_=6 after 1 tries. [RxPacketError] Input voltage error!
❌ Action cancelled
```

### After This Update
```
[RESILIENT] ⟳ Motor shoulder_pan.Present_Position retry 2/5 after 75ms
[RESILIENT] ✓ Motor shoulder_pan.Present_Position succeeded after 2 retries
✅ Action continues normally
```

Or if motor temporarily drops:
```
[RESILIENT] ⚠️ Motor 5 (wrist_rotate) failed, using last known position: 2047
... continues with other motors ...
[RESILIENT] ✅ Motor wrist_rotate recovered after 3 failures
```

## Testing Checklist

Run your normal operations and verify:

- [ ] **Normal operations work** - No new errors
- [ ] **Brownouts handled** - Actions complete despite voltage errors
- [ ] **Recovery works** - Failed motors come back online
- [ ] **Statistics shown** - See retry counts at end
- [ ] **Performance OK** - No noticeable slowdown

## Monitoring During Test

Watch terminal for these indicators:

### ✅ Good Signs
```
[MOTOR] ✓ Connected with resilient bus wrapper (max 5 retries)
[RESILIENT] ✓ Motor X succeeded after N retries
[RESILIENT] ✅ Motor X recovered after N failures
```

### ⚠️ Warning Signs (Not Critical)
```
[RESILIENT] ⚠️ Motor X failed, using last known position
# This is OK - system continues with other motors
```

### ❌ Problems (Needs Attention)
```
[RESILIENT] ❌ Motor X failed after 5 attempts: Non-retryable error
[MOTOR] ❌ All motors failed to read
# This indicates a more serious issue than brownouts
```

## Statistics Report

At the end of operations, you'll see:

```
============================================================
🛡️  RESILIENT MOTOR BUS STATISTICS
============================================================
Total Retries: 47
Successful Recoveries: 12
Currently Failed Motors: 0
============================================================
```

**Interpretation:**

| Stat | Value | Meaning |
|------|-------|---------|
| Total Retries | 47 | System handled 47 transient errors automatically |
| Successful Recoveries | 12 | 12 motors dropped out and came back online |
| Currently Failed | 0 | ✅ All motors healthy at end |
| Currently Failed | 1+ | ⚠️ Some motors still failing - check power supply |

## Tuning (If Needed)

### If brownouts still cause issues:

Edit `/home/nicebot/NiceBotUI/utils/resilient_motor_bus.py` on Jetson:

```python
# Increase retry count
MAX_RETRIES = 8  # Default: 5

# Increase delays (give more time for power recovery)
RETRY_DELAY_MAX = 1.0  # Default: 0.5
```

### If operations feel slow:

```python
# Decrease retry count
MAX_RETRIES = 3  # Default: 5

# Decrease delays
RETRY_DELAY_BASE = 0.03  # Default: 0.05
RETRY_DELAY_MAX = 0.3    # Default: 0.5
```

## Rollback (If Needed)

If you need to revert:

```bash
# On Jetson
cd ~/NiceBotUI
git diff utils/motor_controller.py

# Remove the import and wrapper
# Or restore from backup
```

The only critical change is in `motor_controller.py` where the bus is wrapped. All other functionality remains the same.

## Next Steps

1. **Deploy** - `./sync_to_jetson.sh`
2. **Test** - Run normal operations on Jetson
3. **Monitor** - Watch for resilient bus messages
4. **Verify** - Check statistics at end
5. **Report** - Let me know how it works!

## If Issues Occur

**Collect this information:**

```bash
# On Jetson, capture full log
python3 app.py 2>&1 | tee test_resilient.log

# Pull log back for analysis
# On local machine:
./sync_from_jetson.sh --logs-only
```

Then share:
- What operation you were running
- Error messages (especially "Non-retryable error" messages)
- Statistics report at end
- Whether motor physically moved or not

---

**Status:** Ready to deploy  
**Risk:** Low - backwards compatible, falls back gracefully  
**Testing:** Recommended on development setup first

