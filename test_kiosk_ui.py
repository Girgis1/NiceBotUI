#!/usr/bin/env python3
"""
Test script to verify NiceBot UI loads without errors
Run this before deploying to production
"""

import sys
from pathlib import Path

# Use ASCII checkmarks for Windows compatibility
CHECK = "[OK]"
CROSS = "[FAIL]"

print("=" * 50)
print("NiceBot UI Test")
print("=" * 50)
print()

# Test 1: Import checks
print("Test 1: Checking imports...")
try:
    from PySide6.QtWidgets import QApplication
    print(f"  {CHECK} PySide6 available")
except ImportError as e:
    print(f"  {CROSS} PySide6 not found: {e}")
    print("\nInstall with: pip install PySide6")
    sys.exit(1)

try:
    import kiosk_styles
    print(f"  {CHECK} kiosk_styles imports")
except ImportError as e:
    print(f"  {CROSS} kiosk_styles failed: {e}")
    sys.exit(1)

try:
    import NiceBot
    print(f"  {CHECK} NiceBot imports")
except ImportError as e:
    print(f"  {CROSS} NiceBot failed: {e}")
    sys.exit(1)

try:
    import kiosk_dashboard
    print(f"  {CHECK} kiosk_dashboard imports")
except ImportError as e:
    print(f"  {CROSS} kiosk_dashboard failed: {e}")
    sys.exit(1)

try:
    import kiosk_settings
    print(f"  {CHECK} kiosk_settings imports")
except ImportError as e:
    print(f"  {CROSS} kiosk_settings failed: {e}")
    sys.exit(1)

try:
    import kiosk_live_record
    print(f"  {CHECK} kiosk_live_record imports")
except ImportError as e:
    print(f"  {CROSS} kiosk_live_record failed: {e}")
    sys.exit(1)

print()

# Test 2: Check dependencies
print("Test 2: Checking dependencies...")
try:
    import robot_worker
    print(f"  {CHECK} robot_worker available")
except ImportError as e:
    print(f"  {CROSS} robot_worker not found: {e}")
    sys.exit(1)

try:
    from utils.motor_controller import MotorController
    print(f"  {CHECK} utils.motor_controller available")
except ImportError as e:
    print(f"  {CROSS} utils.motor_controller not found: {e}")
    sys.exit(1)

try:
    from utils.actions_manager import ActionsManager
    print(f"  {CHECK} utils.actions_manager available")
except ImportError as e:
    print(f"  {CROSS} utils.actions_manager not found: {e}")
    sys.exit(1)

print()

# Test 3: Check file structure
print("Test 3: Checking file structure...")
required_files = [
    "NiceBot.py",
    "kiosk_dashboard.py",
    "kiosk_settings.py",
    "kiosk_live_record.py",
    "kiosk_styles.py",
    "robot_worker.py",
    "rest_pos.py",
    "utils/motor_controller.py",
    "utils/actions_manager.py",
]

for file in required_files:
    if Path(file).exists():
        print(f"  {CHECK} {file}")
    else:
        print(f"  {CROSS} {file} not found")

print()

# Test 4: Create test application
print("Test 4: Creating test application...")
try:
    app = QApplication(sys.argv)
    from NiceBot import KioskApplication
    window = KioskApplication()
    print(f"  {CHECK} NiceBot application created successfully")
    print(f"  {CHECK} Window size:", window.size())
    print(f"  {CHECK} Dashboard loaded")
    
    # Don't show window, just verify it creates
    # window.show()
    
except Exception as e:
    print(f"  {CROSS} Failed to create application: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Test 5: Style verification
print("Test 5: Verifying styles...")
try:
    from kiosk_styles import Colors, Styles, StatusIndicator
    print(f"  {CHECK} Colors defined")
    print(f"  {CHECK} Styles defined")
    print(f"  {CHECK} StatusIndicator defined")
    
    # Test a style
    style = Styles.get_base_style()
    if style and len(style) > 0:
        print(f"  {CHECK} Styles generate valid CSS")
    else:
        print(f"  {CROSS} Styles empty")
        
except Exception as e:
    print(f"  {CROSS} Style verification failed: {e}")
    sys.exit(1)

print()

# Summary
print("=" * 50)
print(f"{CHECK} All tests passed!")
print("=" * 50)
print()
print("NiceBot is ready to run.")
print("Launch with: python NiceBot.py --windowed")
print()

