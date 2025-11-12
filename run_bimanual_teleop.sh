#!/bin/bash
# Bimanual SO100/SO101 Teleoperation Script
# Auto-generated for NiceBotUI

set -e

echo "🤖 Starting Bimanual Teleoperation"
echo "=================================="
echo ""
echo "Robot Configuration:"
echo "  Left arm (follower):  /dev/ttyACM0 (left_follower, SO101)"
echo "  Right arm (follower): /dev/ttyACM2 (right_follower, SO101)"
echo ""
echo "Teleop Configuration:"
echo "  Left arm (leader):  /dev/ttyACM1 (left_leader, SO100)"
echo "  Right arm (leader): /dev/ttyACM3 (right_leader, SO101)"
echo ""
echo "Press Ctrl+C to stop teleoperation"
echo ""

# Give permissions to USB devices
sudo chmod 666 /dev/ttyACM0 /dev/ttyACM1 /dev/ttyACM2 /dev/ttyACM3

# Run bimanual teleoperation
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
