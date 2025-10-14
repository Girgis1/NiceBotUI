# LeRobot Operator Console

A minimalist, touch-friendly GUI for operating SO-100/101 robot arms with Hugging Face LeRobot.

## Features

- **Large Touch-Friendly Buttons** - Designed for touchscreen operation
- **Simple Interface** - Start, Stop, Go Home controls
- **Real-Time Status** - Connection indicators, episode progress, elapsed time
- **Error Handling** - Clear problem/solution messages for common issues
- **Settings Editor** - GUI for all configuration parameters
- **Run History** - Track last 10 runs with timestamps and status
- **Object Gate** - Optional presence detection before starting
- **Timezone Aware** - Displays times in Australia/Sydney timezone

## Quick Start

### 1. Install

```bash
cd /home/daniel/LerobotGUI
./setup.sh
```

The setup script will:
- Create a virtual environment
- Install all dependencies including LeRobot
- Set up udev rules for serial access
- Add your user to the dialout group

**Important:** After setup, log out and back in for group permissions to take effect.

### 2. Configure

Edit `config.json` or use the Settings dialog in the app to set:
- Serial port for your robot (e.g., `/dev/ttyACM0`)
- Camera index (usually `0`)
- Policy checkpoint path
- Number of episodes

To find your robot's serial port:
```bash
source .venv/bin/activate
lerobot-find-port
```

### 3. Run

**Fullscreen mode (default - for touch displays):**
```bash
source .venv/bin/activate
python app.py
```

**Windowed mode (for testing):**
```bash
python app.py --windowed
```

Or directly:
```bash
.venv/bin/python app.py
```

**Keyboard shortcuts:**
- `F11` - Toggle fullscreen
- `Escape` - Exit fullscreen

## Usage

### Main Controls

- **START** - Begin recording episodes with the trained policy
- **STOP** - Interrupt the current run
- **GO HOME** - Move robot to rest position
- **⚙ Settings** - Open configuration editor

### Settings Dialog

**Robot Tab:**
- Serial port, FPS, motor parameters

**Camera Tab:**
- Camera index, resolution, FPS

**Policy Tab:**
- Trained model checkpoint path
- Compute device (CPU/CUDA)

**Control Tab:**
- Number of episodes
- Warmup, episode, and reset timings
- Task name

**Advanced Tab:**
- **SET HOME** - Capture current position as home
- Rest position angles
- Object presence gate
- Safety limits

## Hardware Setup

### SO-100 Assembly

Follow the official guide: https://huggingface.co/docs/lerobot/so100

Key steps:
1. 3D print parts
2. Configure motor IDs using `lerobot-setup-motors`
3. Assemble leader and follower arms
4. Calibrate using `lerobot-calibrate`

### Connections

- **Power:** Connect 12V power supply to motor controller
- **USB:** Connect controller to computer
- **Camera:** Connect USB camera
- **E-Stop:** Wire emergency stop to power supply (recommended)

## Error Messages

The application provides clear error messages with solutions:

| Error | Meaning | Solution |
|-------|---------|----------|
| **Motors Not Found** | Serial port not detected | Check USB cable and power supply |
| **Cannot Access Motors** | Permission denied | Run `./setup.sh` and log out/in |
| **Joint X Not Responding** | Motor timeout | Check cable at joint X |
| **Power Lost** | Unexpected disconnect | Check E-stop and power supply |
| **Camera Not Found** | Can't open camera | Check USB and camera index |
| **Policy Missing** | Checkpoint not found | Check path in Settings |

## Development

### Project Structure

```
LerobotGUI/
├── app.py                  # Main application
├── robot_worker.py         # QThread worker for subprocess
├── settings_dialog.py      # Settings UI
├── rest_pos.py             # Rest position control (stub)
├── config.json             # Configuration
├── run_history.json        # Recent runs log
├── requirements.txt        # Python dependencies
├── setup.sh                # Setup script
├── udev/
│   └── 99-so100.rules     # Serial port access rules
└── README.md              # This file
```

### Integrating Hardware

The `rest_pos.py` file is currently a stub. To integrate with real hardware:

1. Uncomment the Feetech SDK code in `rest_pos.py`
2. Update `settings_dialog.py` `_set_home_position()` method
3. Test with: `python rest_pos.py --go`

Example integration:
```python
from lerobot.common.robot_devices.motors.feetech import FeetechMotorsBus

bus = FeetechMotorsBus(
    port="/dev/ttyACM0",
    motors={
        'shoulder_pan': (1, 'sts3215'),
        'shoulder_lift': (2, 'sts3215'),
        # ... etc
    }
)
bus.connect()
# Read/write positions
bus.disconnect()
```

### Dependencies

- **PySide6** - Qt6 GUI framework
- **numpy** - Numerical operations
- **opencv-python** - Camera and presence gate
- **pytz** - Timezone support
- **python-dateutil** - Date parsing
- **lerobot** - Hugging Face LeRobot package

## Troubleshooting

### "Permission denied" on serial port
```bash
sudo usermod -aG dialout $USER
# Log out and back in
```

### Can't find lerobot-find-port
```bash
source .venv/bin/activate
pip install -e ".[feetech]"
```

### Camera not working
```bash
# Check available cameras
ls -l /dev/video*

# Test camera
python -c "import cv2; cap = cv2.VideoCapture(0); print(cap.isOpened())"
```

### Policy not found
- Ensure you've trained a model first
- Check path in Settings → Policy tab
- Path should end in `.../pretrained_model`

## Production Deployment

### Kiosk Mode

For production use on a dedicated touchscreen:

1. Create a dedicated `operator` user
2. Enable auto-login
3. Add application to autostart
4. Disable screen blanking
5. Set up physical E-stop button

### Autostart (.desktop file)

Create `~/.config/autostart/lerobot-console.desktop`:

```desktop
[Desktop Entry]
Type=Application
Name=LeRobot Console
Exec=/home/daniel/LerobotGUI/.venv/bin/python /home/daniel/LerobotGUI/app.py
Terminal=false
```

### Safety

- **Always use a physical E-stop** - Software stop is not sufficient
- Wire E-stop to cut motor power directly
- Test E-stop regularly
- Keep safety limits configured in Settings → Advanced

## Support

- **LeRobot Docs:** https://huggingface.co/docs/lerobot
- **Discord:** Hugging Face Discord server
- **Issues:** Check configuration and error messages first

## License

This operator console is provided as-is for use with LeRobot. 
Refer to the LeRobot project for licensing information.

