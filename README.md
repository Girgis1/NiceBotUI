# NiceBot UI

Industrial-friendly control station for SO-100/101 robots powered by Hugging Face **LeRobot**. Designed for touch panels and operators who just need a single button to get everything running.

## 1‑Click Setup

```bash
# 1. Clone (or pull latest) repository
cd /path/to/parent
git clone https://github.com/Girgis1/NiceBotUI.git
cd NiceBotUI

# 2. Run the guided installer (installs system deps + Python stack)
./Setup/install.sh

# 3. Launch the UI (windowed for testing; fullscreen by default)
.venv/bin/python app.py --windowed
```

The installer:
- Installs required Ubuntu packages (Python, build tools, OpenCV/Video4Linux, FFmpeg, etc.).
- Adds the current user to the `dialout` group for motor controllers.
- Creates/updates `.venv`, upgrades `pip`, and installs everything in `requirements.txt` (including `lerobot[feetech]`).
- Generates a fresh `config.json` via the new app bootstrap so the UI is ready on first launch.

> **Heads up:** If this is the first time your user has been added to `dialout`, log out and back in before attempting to move the robot.

## Running The UI

```bash
# Touchscreen / kiosk mode
.venv/bin/python app.py

# Development laptop
.venv/bin/python app.py --windowed

# Vision designer only
.venv/bin/python app.py --vision
```

Keyboard shortcuts:
- `Ctrl+1…4` – dashboard / sequence / record / settings
- `F11` – toggle fullscreen
- `Esc` – exit fullscreen
- `Ctrl+Q` – quit immediately

## Features

- **Dashboard**: live status, camera previews, master speed, run selector, emergency stop helpers.
- **Sequence Tab**: build composite jobs that mix recordings, model runs, home moves, delays, and vision triggers.
- **Record Tab**: modernized transport controls for capturing individual poses or live trajectories with teleop keypad.
- **Settings Tab**: full multi-arm configuration, camera discovery, policy paths, diagnostics, safety systems.
- **Execution Engine**: modular strategies for live/composite playback plus model execution with optional policy servers.
- **Vision Triggers**: zone-based camera checks integrated into sequences (idle + hold timers, Qt overlay updates).

## Repository Layout

```
NiceBotUI/
├── app.py                  # Qt entrypoint + MainWindow
├── app/                    # Bootstrap helpers (args, config, theme, single-instance guard)
├── Setup/install.sh        # 1-click installer for operators
├── tabs/                   # Dashboard / Sequence / Record / Settings packages
├── utils/
│   ├── execution_manager.py
│   └── execution/          # Strategy helpers extracted from the manager
├── widgets/                # Shared Qt widgets (tables, buttons)
├── requirements.txt        # Python dependencies (incl. lerobot[feetech])
├── config.json             # Auto-created on first launch
└── README.md               # You are here
```

## Operator Notes

- **Robot ports**: Default config assumes `/dev/ttyACM0` for follower arm 1. Use the Settings tab to update ports; the new loader will persist them automatically.
- **Dialout membership**: The installer takes care of `usermod -aG dialout $USER`; just log out/in afterwards.
- **Vision cameras**: USB webcams work out of the box. For CSI/Jetson feeds, use `Settings → Camera` to set the GStreamer string or device path.
- **Policy checkpoints**: Drop your LeRobot checkpoint into `outputs/train/...` (or point to a different directory) and select it via `Settings → Policy`.
- **Safety**: Always keep a physical e-stop inline. Software torque/temperature watchdogs live under `Settings → Safety` and can kill runs automatically.

## Support

If the installer prints an error you don’t recognize, grab the last 20 lines and share them with the robotics/software team. For hardware issues (motors not responding, camera feeds blank), use the Diagnostics tab or the status messages on the Dashboard before diving into logs.

Happy deploying! 🙌
