# Calibration ID Selection

## Overview

The NiceBot UI now includes calibration ID dropdowns in the Settings tab, allowing you to select different calibration profiles for your robots.

## Usage

### In the Settings Tab

1. **Robot Configuration Section** (🤖)
   - **Calib ID**: Select or enter the calibration ID for your follower/robot arm
   - Default options: `follower_arm`, `follower_white`, `follower_black`, `follower_left`, `follower_right`
   - You can also type custom IDs

2. **Teleoperation Section** (🎮)
   - **Calib ID**: Select or enter the calibration ID for your leader/teleop device
   - Default options: `leader_arm`, `leader_white`, `leader_black`, `leader_left`, `leader_right`
   - You can also type custom IDs

### Creating Calibration Files

To create a new calibration file, use the lerobot command-line tool:

```bash
# Calibrate a follower robot
lerobot-calibrate \
    --robot.type=so100_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=follower_white

# Calibrate a leader/teleop device
lerobot-calibrate \
    --teleop.type=so101_leader \
    --teleop.port=/dev/ttyACM0 \
    --teleop.id=leader_white
```

The calibration data is saved in:
- `~/.cache/calibration/{robot_type}/{id}.json`

For example:
- `~/.cache/calibration/so100_follower/follower_white.json`
- `~/.cache/calibration/so101_leader/leader_white.json`

### Using Multiple Robots

The calibration ID system is especially useful when you have:
- Multiple robot arms with different calibrations
- Different leader devices (e.g., left/right arm leaders)
- Test vs production setups
- Different color-coded robots in your workspace

Simply select the appropriate calibration ID from the dropdown before connecting to your robot!

## How It Works

1. When you select a calibration ID in the UI, it's saved to `config.json`
2. The robot initialization code reads the `id` field from the config
3. LeRobot automatically loads the corresponding calibration file from `~/.cache/calibration/`
4. The robot uses the calibrated offsets for accurate motor positioning

## Example config.json

```json
{
  "robot": {
    "type": "so100_follower",
    "port": "/dev/ttyACM0",
    "id": "follower_white",
    ...
  },
  "teleop": {
    "type": "so100_leader",
    "port": "/dev/ttyACM1",
    "id": "leader_white"
  }
}
```

