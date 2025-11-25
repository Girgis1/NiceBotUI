# Motor Dropout Diagnostics Guide

This guide explains how to use the motor dropout diagnostic tool to investigate USB power issues on the Jetson.

## Overview

The diagnostic tool monitors three key areas simultaneously:
1. **USB Events** - Kernel messages about device connects/disconnects
2. **System Power** - Tegrastats readings for power consumption correlation
3. **Motor Ports** - Real-time monitoring of `/dev/ttyACM*` devices

## Quick Start

### On the Jetson

```bash
# SSH into Jetson
ssh jetson

# Navigate to project
cd ~/NiceBotUI

# Start diagnostics (run until Ctrl+C)
./tools/start_motor_diagnostics.sh

# OR run for specific duration (e.g., 300 seconds = 5 minutes)
./tools/start_motor_diagnostics.sh 300
```

### During Monitoring

1. **Run your normal operations** - Use the motors as you typically would
2. **When dropout occurs** - Just note the approximate time
3. **Let it run ~30 seconds longer** - Capture any recovery events
4. **Stop with Ctrl+C** - The log file path will be displayed

### Retrieve and Analyze Logs

```bash
# Back on your local machine
./sync_from_jetson.sh --logs-only

# View the diagnostic log
cat logs/motor_dropout_diag_*.log | less

# Or view most recent
ls -t logs/motor_dropout_diag_*.log | head -1 | xargs cat | less
```

## Understanding the Log Output

### Event Types

- `[USB_EVENT]` - USB device activity from kernel
- `[MOTOR_EVENT]` - Motor port appearing/disappearing
- `[POWER]` - System power readings
- `[POWER_SPIKE]` - Detected power consumption spike
- `[ANALYSIS]` - Automatic analysis when dropout detected
- `[SYSTEM]` - System state and configuration
- `[ERROR]` - Errors during monitoring

### Key Indicators

#### Power Issue
```
[POWER_SPIKE] ⚡ POWER SPIKE: POM_5V_IN 6543/6543 ...
[USB_EVENT] usb 1-3: USB disconnect, device number 5
[MOTOR_EVENT] ❌ Motor port DISAPPEARED: /dev/ttyACM2
```

#### USB Enumeration Issue
```
[USB_EVENT] usb 1-3: device descriptor read/64, error -71
[USB_EVENT] usb 1-3: device not accepting address 5, error -71
```

#### Clean Disconnect/Reconnect
```
[USB_EVENT] usb 1-3: USB disconnect, device number 5
[USB_EVENT] usb 1-3: new full-speed USB device number 6 using tegra-xusb
```

### Automatic Analysis

When a dropout is detected, the tool automatically analyzes the 5 seconds surrounding the event:

```
================================
📊 ANALYZING EVENTS AROUND DROPOUT
================================

🔌 Recent USB Events (3):
  [2025-11-25 10:23:45] usb 1-3: reset full-speed USB device number 5
  [2025-11-25 10:23:45] usb 1-3: USB disconnect, device number 5
  [2025-11-25 10:23:46] usb 1-3: new full-speed USB device number 6

⚡ Recent Power Readings (3):
  RAM 2156/7468MB CPU [12%@1420,12%@1420,...] POM_5V_IN 5842/5842
  RAM 2158/7468MB CPU [15%@1420,15%@1420,...] POM_5V_IN 6234/6234
  RAM 2156/7468MB CPU [18%@1420,18%@1420,...] POM_5V_IN 5123/5123

🤖 Recent Motor Events (1):
  /dev/ttyACM2 - disappeared
================================
```

## What to Look For

### Scenario 1: Power Draw Issue
**Symptoms:**
- Power spike before dropout
- Multiple motors affected
- System-wide power increase

**Next Steps:**
- Use powered USB hub
- Check power supply capacity
- Reduce number of motors active simultaneously

### Scenario 2: Loose Connection
**Symptoms:**
- Random single motor dropout
- No power correlation
- USB disconnect/reconnect messages
- Physical movement triggers it

**Next Steps:**
- Check cable connections
- Try different USB port
- Replace cable

### Scenario 3: USB Bandwidth
**Symptoms:**
- Dropout during high activity
- "unable to enumerate" errors
- Multiple devices on same USB hub

**Next Steps:**
- Spread devices across USB buses
- Use USB hub with separate power
- Reduce communication frequency

### Scenario 4: Electrical Noise
**Symptoms:**
- Dropout during motor acceleration
- "device descriptor read" errors
- Random timing

**Next Steps:**
- Add ferrite beads to USB cables
- Separate power and data lines
- Check grounding

## Advanced Usage

### Running Diagnostics in Background

```bash
# On Jetson, run in background with nohup
nohup ./tools/start_motor_diagnostics.sh 3600 &

# Check if running
ps aux | grep motor_dropout

# Kill when done
pkill -f motor_dropout_diagnostics
```

### Monitoring Live

```bash
# On Jetson, tail the log while it runs
tail -f logs/motor_dropout_diag_*.log
```

### Multiple Sessions

```bash
# Each run creates a timestamped log
# Format: motor_dropout_diag_YYYYMMDD_HHMMSS.log

# Compare multiple sessions
ls -lh logs/motor_dropout_diag_*.log
```

## Integration with Motor Controllers

### Checking Which Motor Dropped

The tool logs the initial port mapping. Cross-reference with your config:

From `config.json`:
```json
{
  "follower_left": "/dev/ttyACM0",
  "follower_right": "/dev/ttyACM2",
  "leader_left": "/dev/ttyACM1",
  "leader_right": "/dev/ttyACM3"
}
```

If log shows `/dev/ttyACM2` disappeared → **Follower Right** dropped out

## Troubleshooting the Diagnostic Tool

### "tegrastats not found"
- Tool will still work, but power monitoring disabled
- Only affects power correlation, USB and motor monitoring still active

### "Permission denied" for dmesg
- The start script uses `sudo` automatically
- If prompted, enter your password

### No USB events appearing
- May need to run with sudo: `sudo python3 tools/motor_dropout_diagnostics.py`
- Check if dmesg is working: `dmesg | tail`

### Tool not detecting dropout
- Dropout may be at software level, not USB level
- Check application logs separately
- Try monitoring motor communication directly

## Related Tools

- `tools/diagnose_motor_velocity.py` - Motor velocity diagnostics
- `tools/test_motor_velocity_reset.py` - Motor reset testing
- `jetson_helpers.sh` - General Jetson utilities

## Questions to Answer

After reviewing the logs, you should be able to answer:

1. **Does the dropout coincide with a USB disconnect?**
   - Yes → Hardware/power issue
   - No → Software issue

2. **Is there a power spike before the dropout?**
   - Yes → Power supply insufficient
   - No → Look at other factors

3. **Is it always the same motor?**
   - Yes → That specific connection/device
   - No → System-wide issue

4. **Are there kernel errors?**
   - Yes → Check error type
   - No → May be application-level

5. **Does it correlate with motor activity?**
   - Yes → Power draw from motors
   - No → External factor

---

**Created:** 2025-11-25  
**For:** Diagnosing random motor ID dropouts on Nvidia Jetson

