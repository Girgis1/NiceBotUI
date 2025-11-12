# Bimanual SO100/SO101 Teleoperation - Working Configuration

**Last Updated:** 2025-11-12  
**Status:** ✅ Fully Working

## Overview

This document contains the working configuration for bimanual teleoperation with mixed SO100/SO101 arms.

## Hardware Configuration

### Port Mapping (VERIFIED WORKING)

| Arm Type | Position | Port | ID | Robot Type |
|----------|----------|------|-----|------------|
| Follower | Left | `/dev/ttyACM0` | `follower_left` | SO101 |
| Follower | Right | `/dev/ttyACM2` | `follower_right` | SO101 |
| Leader | Left | `/dev/ttyACM1` | `leader_left` | SO100 |
| Leader | Right | `/dev/ttyACM3` | `leader_right` | SO101 |

### Important Notes
- **Both follower arms are SO101** → Use `bi_so101_follower`
- **Leaders are mixed (SO100 + SO101)** → Use `bi_so100_leader`
- The left leader is SO100, right leader is SO101

## Calibration Files

Calibrations are stored in: `~/.cache/huggingface/lerobot/calibration/`

### Required Calibration Files

For bimanual operation, calibration files must follow the naming pattern: `{id}_{side}.json`

**Follower Arms (in `robots/so101_follower/`):**
- `follower_left.json` - Left follower arm
- `follower_right.json` - Right follower arm

**Leader Arms (in `teleoperators/bi_so100_leader/`):**
- `leader_left.json` - Left leader arm (SO100)
- `leader_right.json` - Right leader arm (SO101)

### Calibrating Arms

If you need to recalibrate any arm:

```bash
# Calibrate left follower
lerobot-calibrate \
  --robot.type=so101_follower \
  --robot.port=/dev/ttyACM0 \
  --robot.id=follower_left

# Calibrate right follower
lerobot-calibrate \
  --robot.type=so101_follower \
  --robot.port=/dev/ttyACM2 \
  --robot.id=follower_right

# Calibrate left leader (SO100)
lerobot-calibrate \
  --teleop.type=so100_leader \
  --teleop.port=/dev/ttyACM1 \
  --teleop.id=leader_left

# Calibrate right leader (SO101)
lerobot-calibrate \
  --teleop.type=so101_leader \
  --teleop.port=/dev/ttyACM3 \
  --teleop.id=leader_right
```

## Running Bimanual Teleoperation

### Quick Start

```bash
ssh jetson
cd ~/NiceBotUI
./run_bimanual_teleop.sh
```

### Manual Command

If you need to run it manually:

```bash
cd ~/NiceBotUI
source .venv/bin/activate

# Set USB permissions (required after reboot/reconnect)
echo '447447' | sudo -S chmod 666 /dev/ttyACM0 /dev/ttyACM1 /dev/ttyACM2 /dev/ttyACM3

# Run teleoperation
lerobot-teleoperate \
  --robot.type=bi_so101_follower \
  --robot.left_arm_port=/dev/ttyACM0 \
  --robot.right_arm_port=/dev/ttyACM2 \
  --robot.id=follower \
  --teleop.type=bi_so100_leader \
  --teleop.left_arm_port=/dev/ttyACM1 \
  --teleop.right_arm_port=/dev/ttyACM3 \
  --teleop.id=leader \
  --display_data=false
```

### Stopping Teleoperation

```bash
# From local machine
ssh jetson "pkill -f lerobot-teleoperate"

# Or from Jetson
pkill -f lerobot-teleoperate
```

## Recording Demonstrations

To record bimanual demonstrations for training:

```bash
cd ~/NiceBotUI
source .venv/bin/activate

lerobot-record \
  --robot.type=bi_so101_follower \
  --robot.left_arm_port=/dev/ttyACM0 \
  --robot.right_arm_port=/dev/ttyACM2 \
  --robot.id=follower \
  --teleop.type=bi_so100_leader \
  --teleop.left_arm_port=/dev/ttyACM1 \
  --teleop.right_arm_port=/dev/ttyACM3 \
  --teleop.id=leader \
  --repo-id=your-dataset-name \
  --num-episodes=50 \
  --run-compute-stats=true
```

## Troubleshooting

### Issue: "Permission denied" on USB devices

**Solution:**
```bash
echo '447447' | sudo -S chmod 666 /dev/ttyACM0 /dev/ttyACM1 /dev/ttyACM2 /dev/ttyACM3
```

This is required after every reboot or device reconnection.

### Issue: "Calibration mismatch" error

**Solution:**
The motor's stored calibration doesn't match the file. Either:

1. **Press ENTER** when prompted to use the existing calibration file
2. **Type 'c' and ENTER** to recalibrate the arm
3. **Run calibration manually** (see Calibrating Arms section above)

### Issue: "Missing motor IDs" or "No motors found"

**Possible causes:**
- Arm is not powered on
- USB cable disconnected
- Wrong port specified

**Solution:**
1. Check power supply to the arm
2. Verify USB connection
3. Run `ls -l /dev/ttyACM*` to see available devices

### Issue: Can't find calibration files

**Solution:**
Calibration files must be in the correct directory with the correct naming:

```bash
# Check if files exist
ls -la ~/.cache/huggingface/lerobot/calibration/robots/so101_follower/
ls -la ~/.cache/huggingface/lerobot/calibration/teleoperators/bi_so100_leader/

# If missing, copy from individual calibrations
cp ~/.cache/huggingface/lerobot/calibration/robots/so101_follower/left_follower.json \
   ~/.cache/huggingface/lerobot/calibration/robots/so101_follower/follower_left.json

cp ~/.cache/huggingface/lerobot/calibration/teleoperators/so100_leader/left_leader.json \
   ~/.cache/huggingface/lerobot/calibration/teleoperators/bi_so100_leader/leader_left.json
```

## Configuration Files

### config.json Setup

The `config.json` is configured with:

```json
{
  "robot": {
    "mode": "bimanual",
    "arms": [
      {
        "enabled": true,
        "name": "Follower Left",
        "type": "so101_follower",
        "port": "/dev/ttyACM0",
        "id": "left_follower",
        "arm_id": 1
      },
      {
        "enabled": true,
        "name": "Follower Right",
        "type": "so101_follower",
        "port": "/dev/ttyACM2",
        "id": "right_follower",
        "arm_id": 2
      }
    ]
  },
  "teleop": {
    "mode": "bimanual",
    "arms": [
      {
        "enabled": true,
        "name": "Leader Left",
        "type": "so100_leader",
        "port": "/dev/ttyACM1",
        "id": "left_leader",
        "arm_id": 1
      },
      {
        "enabled": true,
        "name": "Leader Right",
        "type": "so101_leader",
        "port": "/dev/ttyACM3",
        "id": "right_leader",
        "arm_id": 2
      }
    ]
  }
}
```

## Helper Scripts

### run_bimanual_teleop.sh

Located at: `~/NiceBotUI/run_bimanual_teleop.sh`

This script handles:
- Setting USB permissions
- Starting teleoperation with correct parameters
- Logging output

## Key Learnings

1. **Naming Convention:** Bimanual calibrations use `{id}_{side}.json` format, not `{side}_{id}.json`
2. **Robot Type:** Use `bi_so101_follower` even with mixed arms if followers are SO101
3. **Teleop Type:** Use `bi_so100_leader` for mixed SO100/SO101 leader arms
4. **Permissions:** USB devices need `chmod 666` after every reboot/reconnection
5. **Display Mode:** Use `--display_data=false` when running over SSH without X11 forwarding

## References

- LeRobot Bimanual SO100 PR: https://github.com/huggingface/lerobot/pull/1509
- LeRobot Documentation: https://github.com/huggingface/lerobot
- Installed packages:
  - `lerobot_teleoperator_bi_so101_leader` v0.0.9
  - `lerobot_robot_bi_so101_follower` v0.1.1

## Testing Checklist

- [x] All 4 arms powered and connected
- [x] USB permissions set correctly
- [x] Calibration files exist and named correctly
- [x] Leader arms connect successfully
- [x] Follower arms connect successfully
- [x] Teleoperation runs without errors
- [x] Follower arms follow leader movements smoothly
- [x] Both left and right arms work independently
- [x] No calibration mismatch errors

## Success Criteria

✅ **Working State Confirmed:** 2025-11-12  
- All 4 arms connect without errors
- Teleoperation runs continuously
- Follower arms track leader movements in real-time
- No motor communication issues

