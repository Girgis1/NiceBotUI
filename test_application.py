#!/usr/bin/env python3
"""
Comprehensive test suite for LeRobot Operator Console
Run this to verify all components are working correctly
"""

import sys
import json
from pathlib import Path

def test_imports():
    """Test that all modules can be imported"""
    print("Testing imports...")
    try:
        from robot_worker import RobotWorker
        from settings_dialog import SettingsDialog
        import rest_pos
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        import cv2
        import numpy as np
        import pytz
        print("✓ All imports successful")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False

def test_config():
    """Test configuration loading"""
    print("\nTesting configuration...")
    try:
        config_path = Path(__file__).parent / "config.json"
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        required_sections = ['robot', 'cameras', 'policy', 'control', 'rest_position', 'ui', 'safety']
        for section in required_sections:
            assert section in config, f"Missing section: {section}"
        
        print(f"✓ Config valid with {len(config)} sections")
        return True
    except Exception as e:
        print(f"✗ Config test failed: {e}")
        return False

def test_robot_worker():
    """Test RobotWorker functionality"""
    print("\nTesting RobotWorker...")
    try:
        from robot_worker import RobotWorker
        
        config_path = Path(__file__).parent / "config.json"
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        worker = RobotWorker(config)
        
        # Test command building
        args = worker._build_lerobot_command()
        assert len(args) > 0, "Command is empty"
        assert 'lerobot.scripts.control_robot' in ' '.join(args), "Missing lerobot command"
        
        # Test error parsing
        test_cases = [
            ("permission denied /dev/ttyACM0", 'serial_permission'),
            ("No such file /dev/ttyACM0", 'serial_not_found'),
            ("motor 3 timeout", 'servo_timeout'),
            ("camera", 'camera_not_found'),
        ]
        
        for stderr, expected_key in test_cases:
            error_key, _ = worker._parse_error(stderr, 1)
            assert error_key == expected_key, f"Expected {expected_key}, got {error_key}"
        
        print("✓ RobotWorker functional")
        return True
    except Exception as e:
        print(f"✗ RobotWorker test failed: {e}")
        return False

def test_settings_dialog():
    """Test SettingsDialog"""
    print("\nTesting SettingsDialog...")
    try:
        import os
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        
        from settings_dialog import SettingsDialog
        from PySide6.QtWidgets import QApplication
        
        app = QApplication.instance() or QApplication(sys.argv)
        
        config_path = Path(__file__).parent / "config.json"
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        dialog = SettingsDialog(config)
        
        # Check tabs
        assert dialog.tabs.count() == 5, f"Expected 5 tabs, got {dialog.tabs.count()}"
        
        # Check that values loaded
        assert dialog.robot_type.text() == config['robot']['type']
        assert dialog.num_episodes.value() == config['control']['num_episodes']
        
        print("✓ SettingsDialog functional")
        return True
    except Exception as e:
        print(f"✗ SettingsDialog test failed: {e}")
        return False

def test_rest_pos():
    """Test rest_pos module"""
    print("\nTesting rest_pos...")
    try:
        import rest_pos
        
        # Test config read
        config = rest_pos.read_config()
        assert 'rest_position' in config
        assert 'angles_deg' in config['rest_position']
        
        print("✓ rest_pos functional")
        return True
    except Exception as e:
        print(f"✗ rest_pos test failed: {e}")
        return False

def test_history():
    """Test history functionality"""
    print("\nTesting history...")
    try:
        from datetime import datetime
        import pytz
        
        TIMEZONE = pytz.timezone('Australia/Sydney')
        now = datetime.now(TIMEZONE)
        
        # Test formatting
        time_str = now.strftime("%d %b %I:%M %p")
        assert len(time_str) > 0
        
        # Test history file
        history_path = Path(__file__).parent / "run_history.json"
        if history_path.exists():
            with open(history_path, 'r') as f:
                history = json.load(f)
            assert 'runs' in history
        
        print("✓ History functional")
        return True
    except Exception as e:
        print(f"✗ History test failed: {e}")
        return False

def test_error_messages():
    """Test error message catalog"""
    print("\nTesting error messages...")
    try:
        import os
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        
        from app import MainWindow
        from PySide6.QtWidgets import QApplication
        
        app = QApplication.instance() or QApplication(sys.argv)
        window = MainWindow()
        
        # Check all error messages have required fields
        for key, msg in window.ERROR_MESSAGES.items():
            assert 'title' in msg, f"{key} missing title"
            assert 'problem' in msg, f"{key} missing problem"
            assert 'solution' in msg, f"{key} missing solution"
        
        print(f"✓ {len(window.ERROR_MESSAGES)} error messages validated")
        return True
    except Exception as e:
        print(f"✗ Error messages test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("="*60)
    print("LeRobot Operator Console - Test Suite")
    print("="*60)
    
    tests = [
        test_imports,
        test_config,
        test_robot_worker,
        test_settings_dialog,
        test_rest_pos,
        test_history,
        test_error_messages,
    ]
    
    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"✗ Test crashed: {e}")
            results.append(False)
    
    print("\n" + "="*60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✓ ALL TESTS PASSED!")
        print("="*60)
        print("\nThe application is ready to run.")
        print("Note: GUI display requires X11 or Wayland.")
        print("\nTo run: python app.py")
        return 0
    else:
        print("✗ Some tests failed")
        print("="*60)
        return 1

if __name__ == "__main__":
    sys.exit(main())


