# New Solo/Bimanual Settings Tab Design
# This will replace the current dynamic add/remove arm system

# Key changes:
# 1. Solo mode: Select which arm (1 or 2) + configure that arm
# 2. Bimanual mode: Configure both arms (left=arm1, right=arm2)
# 3. Same for teleop section
# 4. Remove "Add Arm" / "Remove Arm" buttons
# 5. Simpler UI with radio buttons for mode selection

"""
UI Layout:

🤖 Robot Arms (Followers)
    ( ) Solo Mode    ( ) Bimanual Mode
    
    [Solo Mode - Shown when Solo is selected]
    Select Arm: [Dropdown: Arm 1 / Arm 2]
    Port: /dev/ttyACM0
    Calib ID: follower_arm
    Home Positions: [2048, 2048, ...]
    Velocity: 600
    [🏠 Home] [Set Home] [Calibrate]
    
    [Bimanual Mode - Shown when Bimanual is selected]
    Left Arm (Arm 1):
        Port: /dev/ttyACM0
        Calib ID: follower_left
        Home Positions: [...]
        Velocity: 600
        [🏠 Home] [Set Home] [Calibrate]
    
    Right Arm (Arm 2):
        Port: /dev/ttyACM1
        Calib ID: follower_right
        Home Positions: [...]
        Velocity: 600
        [🏠 Home] [Set Home] [Calibrate]

🎮 Teleoperation
    ( ) Solo Mode    ( ) Bimanual Mode
    
    [Same structure as robot section]
"""

# Implementation notes:
# - When switching modes, validate that required arms are configured
# - In bimanual mode, both arms must have ports configured
# - Solo mode only needs one arm configured
# - Arm 1/2 IDs stay consistent (arm_id field)
# - When saving in bimanual mode, set config.robot.mode = "bimanual"
# - When saving in solo mode, set config.robot.mode = "solo"

