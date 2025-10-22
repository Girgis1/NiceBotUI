# Quick Start - Kiosk Mode

Get up and running with kiosk mode in 5 minutes.

## Prerequisites

- Python 3.8+ installed
- Robot arm connected and powered
- Camera connected (optional)
- LeRobot installed

## Step 1: Install PySide6

```bash
pip install PySide6
```

## Step 2: Test the UI

```bash
python test_kiosk_ui.py
```

You should see:
```
[OK] All imports work
[OK] All files found
[OK] Application creates
```

## Step 3: Run in Windowed Mode

```bash
python NiceBot.py --windowed
```

Or use the startup script:

**Linux/Mac:**
```bash
chmod +x start_kiosk.sh
./start_kiosk.sh --windowed
```

**Windows:**
```bash
start_kiosk.bat --windowed
```

## Step 4: Configure Settings

1. Click the **⚙️ Settings** button (bottom-left)
2. Select your **Robot Port** from dropdown
3. Set **Robot FPS** (default: 30)
4. Set **Front Camera** index (0 for first camera, -1 to disable)
5. Set **Episodes** count
6. Set **Episode Time** in seconds
7. Click **💾 Save**

## Step 5: Verify Connections

Look at the status bar (top of screen):
- **Robot**: 2 dots should be green
- **Cameras**: Dots should be green for connected cameras

If dots are red:
- Robot: Check USB cable and power supply
- Cameras: Check `ls -l /dev/video*` and adjust index

## Step 6: Run Your First Model

1. Select a model from the **RUN** dropdown
   - Format: 🤖 Model: model_name
2. Click the giant **START** button
3. Watch the status updates
4. Click **STOP** anytime to emergency stop

## Step 7: Test HOME Button

Click the **⌂** (HOME) button.

Robot should move Home as defined in `config.json`.

## Step 8: Try Live Recording

1. Click **🔴 Live Record** (bottom-right)
2. Click **🔴 START RECORDING**
3. Manually move the robot arm
4. Click **⏹ STOP RECORDING**
5. Click **💾 SAVE**

Recording is saved with timestamp and appears in RUN dropdown.

## Step 9: Run Fullscreen

Once comfortable, run in fullscreen:

```bash
python NiceBot.py
```

**Exit:** Press `Escape`, `Ctrl+Q`, or `Alt+F4`

## Step 10: Deploy to Production

### Option A: Systemd Service

Create `/etc/systemd/system/robot-kiosk.service`:

```ini
[Unit]
Description=Robot Control Kiosk
After=network.target

[Service]
Type=simple
User=robot
WorkingDirectory=/home/robot/NiceBotUI
ExecStart=/home/robot/NiceBotUI/.venv/bin/python NiceBot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable:
```bash
sudo systemctl enable robot-kiosk
sudo systemctl start robot-kiosk
```

### Option B: Auto-Start on Login

**Linux (Desktop Entry):**

Create `~/.config/autostart/robot-kiosk.desktop`:
```ini
[Desktop Entry]
Type=Application
Name=Robot Kiosk
Exec=/home/robot/NiceBotUI/.venv/bin/python /home/robot/NiceBotUI/NiceBot.py
Terminal=false
```

## Troubleshooting

### "Module not found: PySide6"
```bash
pip install PySide6
```

### "Cannot find robot port"
```bash
# List ports
ls -l /dev/ttyACM*

# Test port
python -c "import serial; print(serial.Serial('/dev/ttyACM0'))"

# Fix permissions
sudo usermod -aG dialout $USER
# Log out and back in
```

### "Camera not detected"
```bash
# List cameras
ls -l /dev/video*

# Test camera
python -c "import cv2; cap = cv2.VideoCapture(0); print(cap.isOpened())"
```

### "No models in RUN dropdown"
- Verify models exist in `outputs/train/*/checkpoints/last/pretrained_model`
- Check `config.json` has correct `policy.base_path`
- Permissions: `chmod -R +r outputs/train/`

### "STOP button doesn't work"
- This is a bug - report immediately
- Use physical E-stop
- Check if process is frozen: `top` or Task Manager

### "UI is laggy"
- Check CPU usage
- Close other applications
- Reduce recording frequency (modify code)
- Check for background processes

## Tips

### Performance
- Close unnecessary applications
- Disable screen blanking
- Use wired network (not WiFi)
- Monitor CPU/memory usage

### Safety
- Always have physical E-stop accessible
- Test STOP button regularly
- Never leave unattended
- Keep workspace clear

### Workflow
- Use Settings to configure once
- Create recordings for common tasks
- Run models for trained behaviors
- HOME button between operations

## Next Steps

- Read **KIOSK_README.md** for full documentation
- Read **MIGRATION_GUIDE.md** if migrating from old UI
- Read **IMPLEMENTATION_SUMMARY.md** for technical details
- Check LeRobot docs: https://huggingface.co/docs/lerobot/en/so101

## Support

If you encounter issues:

1. Run test script: `python test_kiosk_ui.py`
2. Check configuration: `cat config.json`
3. Check logs in terminal output
4. Verify hardware connections
5. Consult documentation

## Success Checklist

- [x] PySide6 installed
- [x] UI loads without errors
- [x] Connections show green dots
- [x] Settings save correctly
- [x] Can run a model or recording
- [x] HOME button works
- [x] STOP button responds immediately
- [x] Live recording works
- [x] Comfortable with touch controls
- [x] Ready for production

**Congratulations! You're ready to use kiosk mode in production.**

For safety-critical operations, always:
- ✅ Use physical E-stop
- ✅ Monitor continuously
- ✅ Keep workspace clear
- ✅ Train operators properly


