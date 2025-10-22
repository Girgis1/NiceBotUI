# Kiosk Mode - Robot Control Interface

## Overview

Production-ready kiosk application for industrial robot control, designed for 1024x600px touchscreen displays on Nvidia Jetson Orin.

## Features

### Safety-First Design
- **Always-responsive STOP button** (<100ms response time)
- Robot operations run in separate thread
- UI never blocks
- Emergency stop with signal escalation (SIGINT → SIGTERM → SIGKILL)
- Clean shutdown on SIGTERM (Docker/systemd compatible)

### Touch-Optimized Interface
- Minimum button size: 80x80px
- No text input (no virtual keyboard)
- Large dropdowns and spinboxes
- Minimalist dark mode design

### Core Functionality
- **START/STOP**: Execute trained models or live recordings
- **HOME**: Move robot Home
- **Settings**: Configure robot, cameras, and episodes
- **Live Record**: Record robot movements at 20Hz
- **Status Indicators**: Real-time robot and camera connection status

## Quick Start

### 1. Run Kiosk Mode

**Fullscreen (default):**
```bash
python kiosk_app.py
```

**Windowed (for testing):**
```bash
python kiosk_app.py --windowed
```

### 2. Keyboard Shortcuts

- `Escape` - Exit application
- `Ctrl+Q` - Exit application  
- `Alt+F4` - Exit application

## Using the Kiosk

### Main Dashboard

#### Status Bar (Top)
- **Robot Indicators**: 2 green dots = robot connected
- **Camera Indicators**: Green dots = cameras detected
- **Elapsed Time**: Shows operation duration
- **Status Text**: Current operation status

#### RUN Selector
Select what to execute:
- 🤖 **Models**: Trained AI models from `outputs/train/`
- 🔴 **Recordings**: Live recordings from previous sessions

#### Main Controls
- **START**: Begin selected operation
- **STOP**: Emergency stop (always responsive)
- **HOME (⌂)**: Move robot to home position

#### Bottom Buttons
- **⚙️ Settings**: Open configuration
- **🔴 Live Record**: Record new movements

### Settings

Configure robot parameters:
- **Robot Port**: Auto-detected serial ports
- **Robot FPS**: Control loop frequency (10-60 Hz)
- **Front Camera**: Camera index (-1 = disabled)
- **Episodes**: Number of episodes to run
- **Episode Time**: Duration per episode (seconds)

Changes are saved to `config.json`.

### Live Recording

Record robot movements:
1. Click **🔴 Live Record**
2. Click **🔴 START RECORDING**
3. Manually move the robot arm
4. Click **⏹ STOP RECORDING** when done
5. Click **💾 SAVE** to save recording

Recordings are saved with timestamp: `Recording_YYYYMMDD_HHMMSS`

Recording specs:
- **Frequency**: 20 Hz (50ms interval)
- **Precision**: 3 motor units threshold
- **Data**: Position + timestamp + velocity

## Configuration

### config.json Structure

```json
{
  "robot": {
    "type": "so101_follower",
    "port": "/dev/ttyACM0",
    "id": "follower_arm",
    "fps": 30
  },
  "cameras": {
    "front": {
      "type": "opencv",
      "index_or_path": 0,
      "width": 640,
      "height": 480,
      "fps": 30
    }
  },
  "policy": {
    "path": "outputs/train/.../pretrained_model",
    "base_path": "outputs/train",
    "device": "cpu"
  },
  "control": {
    "warmup_time_s": 3,
    "episode_time_s": 25,
    "reset_time_s": 8,
    "num_episodes": 3
  },
  "rest_position": {
    "positions": [2082, 1106, 2994, 2421, 1044, 2054],
    "velocity": 600,
    "disable_torque_on_arrival": true
  }
}
```

## Architecture

### Files

- **kiosk_app.py** - Main application entry point
- **kiosk_dashboard.py** - Main dashboard interface
- **kiosk_settings.py** - Settings modal
- **kiosk_live_record.py** - Live recording modal
- **kiosk_styles.py** - Centralized styling
- **robot_worker.py** - Thread worker for robot operations
- **config.json** - Configuration storage

### Threading Model

```
Main Thread (UI)
├─ Always responsive
├─ Updates display
└─ Handles user input

Worker Thread (Robot Operations)
├─ Subprocess management
├─ Status updates via signals
└─ Emergency stop handling
```

### Safety Mechanism

STOP button triggers:
1. **Immediate** - Set stop flag
2. **1 second** - Send SIGINT to subprocess
3. **0.5 seconds** - Escalate to SIGTERM
4. **Final** - Force SIGKILL if needed

## Deployment

### Nvidia Jetson Orin

#### 1. Install Dependencies
```bash
pip install PySide6 opencv-python
```

#### 2. Hardware Acceleration
```bash
export QT_QPA_EGLFS_INTEGRATION=eglfs_kms
```

#### 3. Auto-Start (systemd)

Create `/etc/systemd/system/robot-kiosk.service`:
```ini
[Unit]
Description=Robot Control Kiosk
After=network.target

[Service]
Type=simple
User=robot
WorkingDirectory=/home/robot/NiceBotUI
ExecStart=/home/robot/NiceBotUI/.venv/bin/python kiosk_app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable:
```bash
sudo systemctl enable robot-kiosk
sudo systemctl start robot-kiosk
```

### Docker Deployment

#### Dockerfile
```dockerfile
FROM python:3.10-slim

# Install Qt dependencies
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libxcb-xinerama0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose display
ENV QT_QPA_PLATFORM=offscreen
ENV DISPLAY=:0

CMD ["python", "kiosk_app.py"]
```

#### Run with X11 forwarding
```bash
docker run -it --rm \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -e DISPLAY=$DISPLAY \
  --device /dev/ttyACM0 \
  robot-kiosk
```

## Troubleshooting

### STOP Button Not Responding
- Check if worker thread is alive
- Verify subprocess is running
- Check system resources (CPU/memory)

### Cannot Find Serial Port
- Run `ls -l /dev/ttyACM*` to list ports
- Check permissions: `sudo usermod -aG dialout $USER`
- Verify USB connection and power supply

### Camera Not Detected
- Run `ls -l /dev/video*` to list cameras
- Test with: `python -c "import cv2; print(cv2.VideoCapture(0).isOpened())"`
- Check camera index in settings

### Models Not Showing
- Verify models exist in `outputs/train/*/checkpoints/last/pretrained_model`
- Check permissions on model directories
- Set correct `base_path` in config.json

### Live Recording Failed
- Verify robot connection
- Check motor controller initialization
- Ensure motors have power and torque enabled

## Safety Notes

⚠️ **IMPORTANT SAFETY INFORMATION**

1. **Physical E-Stop Required**: Software stop is not sufficient for safety. Always have a physical emergency stop button that cuts power to motors.

2. **Operator Training**: Ensure operators are trained on:
   - Emergency stop procedures
   - Robot movement limitations
   - Safe operating distances

3. **Workspace**: Keep workspace clear of obstacles and personnel during operation.

4. **Testing**: Always test in a safe environment before production use.

5. **Monitoring**: Monitor robot operation continuously. Do not leave unattended.

## Performance Specifications

- **UI Response Time**: <100ms for STOP button
- **Recording Frequency**: 20 Hz (50ms interval)
- **Connection Check**: Every 5 seconds
- **Display Update**: 1 second for elapsed time

## Support

For issues or questions:
1. Check this README
2. Review LeRobot documentation: https://huggingface.co/docs/lerobot/en/so101
3. Check logs in application
4. Verify hardware connections

## License

This kiosk interface is part of the NiceBotUI project for LeRobot control.


