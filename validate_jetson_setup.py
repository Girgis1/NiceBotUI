#!/usr/bin/env python3
"""
Jetson Setup Validation Script

Validates that the LeRobot GUI is properly configured for NVIDIA Jetson hardware,
specifically optimized for Jetson Orin Nano 8GB.
"""

import sys
import platform
from pathlib import Path
import subprocess
import importlib.util

def print_section(title):
    print(f"\n{'='*60}")
    print(f"🔍 {title}")
    print(f"{'='*60}")

def print_success(message):
    print(f"✅ {message}")

def print_warning(message):
    print(f"⚠️  {message}")

def print_error(message):
    print(f"❌ {message}")

def print_info(message):
    print(f"ℹ️  {message}")

def check_jetson_hardware():
    """Check if running on Jetson hardware"""
    print_section("Jetson Hardware Detection")

    machine = platform.machine().lower()
    print_info(f"Architecture: {machine}")

    is_jetson = False
    jetson_model = "Unknown"

    # Check architecture
    if machine not in {"aarch64", "armv8", "arm64"}:
        print_error("Not running on ARM64 architecture - this is not a Jetson device")
        return False

    # Check for Jetson-specific files
    tegra_release = Path("/etc/nv_tegra_release")
    if tegra_release.exists():
        is_jetson = True
        try:
            with open(tegra_release, 'r') as f:
                jetson_info = f.read().strip()
                print_success(f"Jetson detected via /etc/nv_tegra_release: {jetson_info}")
        except Exception as e:
            print_warning(f"Could not read Jetson info: {e}")

    # Check device tree model
    try:
        model_path = Path("/sys/firmware/devicetree/base/model")
        if model_path.exists():
            model = model_path.read_text(errors="ignore").strip()
            print_info(f"Device tree model: {model}")
            if "nvidia jetson" in model.lower():
                is_jetson = True
                jetson_model = model
    except Exception as e:
        print_warning(f"Could not read device tree model: {e}")

    if is_jetson:
        print_success(f"Confirmed: Running on {jetson_model}")
        return True
    else:
        print_error("Jetson hardware not detected")
        return False

def check_jetson_memory():
    """Check available memory"""
    print_section("Memory Check")

    try:
        import psutil
        memory = psutil.virtual_memory()
        total_gb = memory.total // (1024**3)
        available_gb = memory.available // (1024**3)

        print_info(f"Total Memory: {total_gb}GB")
        print_info(f"Available Memory: {available_gb}GB")

        if total_gb >= 8:
            print_success("Sufficient memory for Jetson Orin Nano 8GB operations")
        elif total_gb >= 4:
            print_warning("Memory is limited - consider using lower resolution settings")
        else:
            print_error("Memory is very limited - performance may be poor")

        return total_gb

    except ImportError:
        print_warning("psutil not available - cannot check memory")
        return None

def check_python_environment():
    """Check Python environment and key packages"""
    print_section("Python Environment")

    print_info(f"Python version: {sys.version}")
    print_info(f"Python executable: {sys.executable}")

    # Check virtual environment
    in_venv = sys.prefix != sys.base_prefix
    if in_venv:
        print_success("Running in virtual environment")
    else:
        print_warning("Not running in virtual environment - consider using one")

    # Check key packages
    required_packages = [
        ("torch", "PyTorch"),
        ("torchvision", "PyTorch Vision"),
        ("cv2", "OpenCV"),
        ("PySide6", "Qt GUI Framework"),
        ("numpy", "NumPy"),
    ]

    for module_name, display_name in required_packages:
        try:
            if module_name == "cv2":
                import cv2
            else:
                importlib.import_module(module_name)
            print_success(f"{display_name} available")
        except ImportError:
            print_error(f"{display_name} not available - install with pip")

def check_jetson_optimizations():
    """Check Jetson-specific optimizations"""
    print_section("Jetson Optimizations")

    # Check if Jetson-optimized PyTorch is available
    try:
        import torch
        print_info(f"PyTorch version: {torch.__version__}")

        if torch.cuda.is_available():
            print_success("CUDA available")
            device_count = torch.cuda.device_count()
            print_info(f"CUDA devices: {device_count}")

            if device_count > 0:
                device_name = torch.cuda.get_device_name(0)
                print_info(f"CUDA device: {device_name}")

                # Check if it's a Jetson GPU
                if "orin" in device_name.lower():
                    print_success("Jetson Orin GPU detected")
                elif "nano" in device_name.lower():
                    print_success("Jetson Nano GPU detected")
                else:
                    print_info(f"GPU detected: {device_name}")
        else:
            print_warning("CUDA not available - using CPU only")

    except ImportError:
        print_error("PyTorch not available")

def check_camera_setup():
    """Check camera configuration"""
    print_section("Camera Configuration")

    try:
        from utils.camera_support import is_jetson_platform, prepare_camera_source
        print_success("Camera support module available")

        if is_jetson_platform():
            print_success("Jetson platform detected by camera support")

            # Test CSI camera configuration
            try:
                source, backend = prepare_camera_source({
                    "index_or_path": "CSI://0",
                    "width": 640,
                    "height": 480,
                    "fps": 15
                }, 640, 480, 15.0)

                if "nvarguscamerasrc" in source:
                    print_success("CSI camera pipeline configured correctly")
                else:
                    print_info(f"Camera source: {source[:100]}...")

            except Exception as e:
                print_warning(f"Camera configuration test failed: {e}")
        else:
            print_info("Not on Jetson platform - camera optimizations not active")

    except ImportError:
        print_error("Camera support module not available")

def check_vision_config():
    """Check vision configuration"""
    print_section("Vision Configuration")

    config_dir = Path("config")
    if not config_dir.exists():
        print_error("Config directory not found")
        return

    # Check for Jetson-specific configs
    jetson_configs = [
        "jetson_orin_nano_8gb.yaml",
        "jetson_orin.yaml",
        "jetson_nano.yaml",
        "jetson.yaml"
    ]

    found_jetson_config = False
    for config_file in jetson_configs:
        config_path = config_dir / config_file
        if config_path.exists():
            print_success(f"Jetson config found: {config_file}")
            found_jetson_config = True
            break

    if not found_jetson_config:
        print_warning("No Jetson-specific config found - using defaults")
        default_config = config_dir / "vision_config.yaml"
        if default_config.exists():
            print_info("Default vision config available")
        else:
            print_error("No vision config found")

def check_system_services():
    """Check system services and permissions"""
    print_section("System Services")

    # Check udev rules
    udev_dir = Path("udev")
    if udev_dir.exists():
        so100_rules = udev_dir / "99-so100.rules"
        if so100_rules.exists():
            print_success("SO-100 udev rules available")

            # Check if installed
            system_udev = Path("/etc/udev/rules.d/99-so100.rules")
            if system_udev.exists():
                print_success("SO-100 udev rules installed")
            else:
                print_warning("SO-100 udev rules not installed - run setup.sh")
        else:
            print_error("SO-100 udev rules not found")
    else:
        print_warning("udev directory not found")

    # Check user groups
    try:
        result = subprocess.run(["groups"], capture_output=True, text=True)
        if "dialout" in result.stdout:
            print_success("User in dialout group (serial port access)")
        else:
            print_warning("User not in dialout group - run setup.sh and logout/login")
    except Exception as e:
        print_warning(f"Could not check user groups: {e}")

def main():
    """Main validation function"""
    print("🤖 LeRobot GUI - Jetson Setup Validation")
    print("Validating setup for NVIDIA Jetson Orin Nano 8GB")
    print()

    all_checks_pass = True

    # Run all checks
    checks = [
        check_jetson_hardware,
        check_jetson_memory,
        check_python_environment,
        check_jetson_optimizations,
        check_camera_setup,
        check_vision_config,
        check_system_services,
    ]

    for check_func in checks:
        try:
            result = check_func()
            if result is False:  # Explicit False means failure
                all_checks_pass = False
        except Exception as e:
            print_error(f"Check failed with exception: {e}")
            all_checks_pass = False

    # Summary
    print_section("Validation Summary")

    if all_checks_pass:
        print_success("All checks passed! Your Jetson setup looks good.")
        print()
        print("🚀 Ready to run:")
        print("   source .venv/bin/activate")
        print("   python app.py")
    else:
        print_warning("Some checks failed. Review the output above and fix issues.")
        print()
        print("🔧 To fix common issues:")
        print("   ./setup.sh              # Run the setup script")
        print("   sudo reboot            # Reboot after setup")
        print("   source .venv/bin/activate && pip install -r requirements.txt")

    return 0 if all_checks_pass else 1

if __name__ == "__main__":
    sys.exit(main())
