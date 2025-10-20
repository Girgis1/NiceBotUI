#!/bin/bash
# Download SO101 URDF file for IK solver

echo "Downloading SO101 URDF file..."

# Create directory
mkdir -p SO101

# Download URDF from GitHub
curl -L -o SO101/so101_new_calib.urdf \
  "https://raw.githubusercontent.com/TheRobotStudio/SO-ARM100/main/Simulation/SO101/so101_new_calib.urdf"

if [ $? -eq 0 ]; then
    echo "✓ URDF downloaded successfully to SO101/so101_new_calib.urdf"
    echo "IK solver will now use proper kinematics!"
else
    echo "✗ Failed to download URDF file"
    echo "Please download manually from:"
    echo "https://github.com/TheRobotStudio/SO-ARM100/blob/main/Simulation/SO101/so101_new_calib.urdf"
fi

