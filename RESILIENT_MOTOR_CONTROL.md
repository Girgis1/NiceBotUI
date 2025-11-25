# Resilient Motor Control System

## Overview

The Resilient Motor Control system handles transient power brownout errors gracefully, ensuring your robot operations continue even when individual motors experience brief voltage drops or communication errors.

## The Problem

**Before:** 
- Motor gets "Input voltage error" from 5V power brownout
- System retries only once
- Action fails and skips to next step
- No automatic recovery

**After:**
- Motor gets voltage error
- System retries up to 5 times with exponential backoff
- Other motors continue operating normally
- Failed motor automatically recovers when power stabilizes
- Action continues smoothly - dropout is "invisible"

## How It Works

### 1. Resilient Bus Wrapper

All motor bus communication now goes through `ResilientMotorBus` which provides:

```
Read/Write Attempt
       ↓
   Success? → Continue
       ↓ No
   Retryable Error?
   (voltage, packet, etc)
       ↓ Yes
   Wait 50ms → Retry #1
       ↓ Fail
   Wait 75ms → Retry #2
       ↓ Fail
   Wait 112ms → Retry #3
       ↓ Fail
   Wait 168ms → Retry #4
       ↓ Fail
   Wait 250ms → Retry #5
       ↓ Fail
   Mark motor as failed
   Continue with others
```

### 2. Graceful Degradation

If a motor fails after all retries:
- **Other motors keep working** - Action continues
- **Last known position used** - No wild movements
- **Automatic recovery detection** - Failed motor retried periodically
- **Action completes** - No cancellation

### 3. Automatic Recovery

```
Motor 5 fails (voltage brownout)
   ↓
System: "Motor 5 failed after 5 attempts"
   ↓
Continue with motors 1,2,3,4,6
   ↓
Check motor 5 again in 1 second
   ↓
Motor 5 responds!
   ↓
System: "✅ Motor 5 recovered after 3 failures"
   ↓
All motors operating normally
```

## Configuration

### Adjust Retry Parameters

Edit `/home/daniel/NiceBotUI/utils/resilient_motor_bus.py`:

```python
class ResilientMotorBus:
    # Retry configuration
    MAX_RETRIES = 5  # Number of retry attempts
    RETRY_DELAY_BASE = 0.05  # Initial delay (50ms)
    RETRY_DELAY_MAX = 0.5  # Maximum delay (500ms)
    BACKOFF_MULTIPLIER = 1.5  # Exponential backoff factor
    
    # Recovery tracking
    RECOVERY_CHECK_INTERVAL = 1.0  # How often to retry failed motors
    MAX_CONSECUTIVE_FAILURES = 10  # After this, motor rarely retried
```

### Common Configurations

#### Aggressive Recovery (Fast operations, frequent retries)
```python
MAX_RETRIES = 8
RETRY_DELAY_BASE = 0.03  # 30ms
BACKOFF_MULTIPLIER = 1.3
RECOVERY_CHECK_INTERVAL = 0.5  # Check every 500ms
```

#### Conservative (Minimize bus traffic)
```python
MAX_RETRIES = 3
RETRY_DELAY_BASE = 0.1  # 100ms
BACKOFF_MULTIPLIER = 2.0
RECOVERY_CHECK_INTERVAL = 2.0  # Check every 2 seconds
```

#### Balanced (Default - Good for most cases)
```python
MAX_RETRIES = 5
RETRY_DELAY_BASE = 0.05  # 50ms
BACKOFF_MULTIPLIER = 1.5
RECOVERY_CHECK_INTERVAL = 1.0
```

## What Errors Are Handled

The system automatically retries these transient errors:

✅ **"Input voltage error"** - Power brownout (your main issue)  
✅ **"Incorrect status packet"** - Communication glitch  
✅ **"Port is in use"** - Bus contention  
✅ **"RxPacketError"** - Packet receive error  
✅ **"TxRxResult"** - Transmission/receive error  

Errors that are **NOT** retried (permanent failures):
❌ Motor not found  
❌ Invalid register  
❌ Disconnected USB

## Monitoring & Statistics

### Real-Time Monitoring

Watch for these log messages:

```
[RESILIENT] ✓ Motor shoulder_pan.Present_Position succeeded after 2 retries
[RESILIENT] ⚠️ Motor wrist_rotate failed, using last known position: 2047
[RESILIENT] ✅ Motor wrist_rotate recovered after 3 failures
```

### Statistics Report

When disconnecting from motors, you'll see:

```
============================================================
🛡️  RESILIENT MOTOR BUS STATISTICS
============================================================
Total Retries: 47
Successful Recoveries: 12
Currently Failed Motors: 0
============================================================
```

**What this means:**
- **Total Retries:** Number of transient errors that were successfully retried
- **Successful Recoveries:** Motors that failed but came back online
- **Currently Failed:** Motors that are still failing (should be 0)

### Programmatic Monitoring

```python
# In your code
stats = motor_controller.bus.get_stats()
print(f"Retries: {stats['total_retries']}")
print(f"Recoveries: {stats['successful_recoveries']}")
print(f"Failed: {stats['currently_failed_motors']}")
```

## Integration

### Automatic Integration

The resilient bus is **automatically enabled** when you connect to motors:

```python
# Your existing code works unchanged
motor_controller = MotorController(config, arm_index=0)
motor_controller.connect()  # ← Resilient bus automatically wraps this

# All operations now resilient
positions = motor_controller.read_positions_from_bus()
motor_controller.set_positions(target_positions)
```

### Manual Control (Advanced)

If you need direct access:

```python
from utils.resilient_motor_bus import ResilientMotorBus

# Check if resilient bus is active
if isinstance(motor_controller.bus, ResilientMotorBus):
    print("Resilient bus active!")
    
    # Adjust parameters on-the-fly
    motor_controller.bus.MAX_RETRIES = 10
    
    # Check specific motor status
    failures = motor_controller.bus.motor_failures
    if 'shoulder_pan' in failures:
        print(f"Shoulder pan failures: {failures['shoulder_pan']['count']}")
```

## Testing the System

### Reproduce the Issue (Before Fix)

1. Run your normal operations
2. Watch for "Input voltage error" 
3. Observe action cancellation

### Verify the Fix (After Update)

```bash
# Deploy to Jetson
./sync_to_jetson.sh

# SSH and test
ssh jetson
cd ~/NiceBotUI
# Run your normal operations
```

**What you should see:**
- Occasional retry messages if brownouts occur
- Actions complete despite transient errors
- Recovery messages when motors come back
- Stats showing successful recoveries at end

### Force a Test (Simulate Failure)

```python
# Temporarily reduce retries to make failures visible
motor_controller.bus.MAX_RETRIES = 2
motor_controller.bus.RETRY_DELAY_BASE = 0.01

# Run operations - you'll see retries working
```

## Performance Impact

### Overhead

**Normal operation (no errors):** 
- Zero overhead - direct passthrough to bus
- No performance impact

**During brownout:**
- Retry delays: ~50-500ms total
- Better than cancelling action entirely
- Allows time for power to stabilize

### Throughput

**Before:** 
- 1 error → action cancelled → restart → 5+ seconds lost

**After:**
- 1 error → 5 retries → 500ms delay → action continues
- 10x faster recovery

## Troubleshooting

### Still Getting Failures

**If motors still fail after retries:**

1. **Check power supply** - Might need higher amperage
   ```bash
   # On Jetson, measure voltage during operation
   # Should stay > 4.8V under load
   ```

2. **Increase retry count**
   ```python
   ResilientMotorBus.MAX_RETRIES = 10
   ```

3. **Increase retry delays** - Give more time for power recovery
   ```python
   ResilientMotorBus.RETRY_DELAY_MAX = 1.0  # 1 second max
   ```

4. **Check statistics** - See which motors fail most
   ```python
   motor_controller.bus.print_stats()
   # Look at failure_details for patterns
   ```

### Too Many Retry Messages

**If logs are too verbose:**

Comment out the print statements in `resilient_motor_bus.py`:

```python
# Line ~108 - Comment out retry logging
# if attempt == 0:
#     pass  # Don't spam logs on first retry
# else:
#     print(f"[RESILIENT] ⟳ Motor {motor_name}.{register} retry...")
```

### Performance Degradation

**If operations feel slow:**

Reduce retry delays:
```python
RETRY_DELAY_BASE = 0.03  # 30ms instead of 50ms
RETRY_DELAY_MAX = 0.3    # 300ms instead of 500ms
```

## Hardware Solutions

While this software solution masks the issue, **consider upgrading power supply:**

### Current Setup (Insufficient)
```
5V Adapter (?) → 12 motors → Brownouts under load
```

### Recommended Upgrade
```
5V 10A+ Power Supply → 12 motors → Stable operation
```

**Look for:**
- 5V DC power supply
- 10A or higher capacity
- Check FEETech motor specs for exact requirements
- Barrel connector matching your motors

**Calculate required amperage:**
```
12 motors × 0.5A (peak) = 6A minimum
Add 30% safety margin = 8A
Recommended: 10A supply
```

## Summary

✅ **Problem Solved:** Voltage brownouts no longer cancel actions  
✅ **Automatic:** No code changes needed in your application  
✅ **Transparent:** Failures are handled invisibly  
✅ **Observable:** Statistics show what's happening  
✅ **Configurable:** Tune retry behavior for your needs  

The dropout is now "invisible" - actions complete successfully even during transient power issues, while still providing visibility into what's happening under the hood.

---

**Created:** 2025-11-25  
**For:** Handling FEETech motor voltage brownouts on SO Arm 100

