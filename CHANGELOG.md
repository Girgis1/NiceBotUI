# Changelog - LerobotGUI

All notable changes to this project will be documented in this file.

## [0.01] - 2025-10-18

### 🎉 Initial Release - Modular Composite Recording System

#### Major Features
- **Modular Composite Recording System**
  - Folder-based storage with manifest.json orchestration
  - Separate component files for live recordings and position sets
  - Per-step speed and delay control
  - Mix live recordings and position waypoints freely

- **Crash Prevention System**
  - Triple-layer safety net (global exception handler, worker protection, cleanup protection)
  - Application never shuts down unexpectedly
  - All errors caught and logged

- **Industrial-Grade Architecture**
  - Individual JSON files for each recording
  - Automatic timestamped backups
  - Safe filename sanitization
  - Robust error handling throughout

#### Core Components
- `utils/recording_component.py` - Base classes for modular components
- `utils/composite_recording.py` - Composite recording manager
- `utils/actions_manager.py` - Folder-based recording management (rewritten)
- `utils/execution_manager.py` - Composite recording execution
- `utils/sequences_manager.py` - Sequence management with backups

#### UI Features
- Dashboard Tab - Execute models, recordings, and sequences
- Record Tab - Capture live motions and position waypoints
- Sequence Tab - Build complex multi-step workflows
- Settings Tab - Configure robot, cameras, and policies

#### Bug Fixes
- ✅ Fixed `KeyError: 'positions'` when saving live recordings
- ✅ Fixed live record button becoming inactive after first use
- ✅ Fixed nested QThread crash when running models
- ✅ Fixed recordings not appearing in Dashboard after save
- ✅ Fixed data loss bug - live recordings now preserve all points

#### Technical Details
- Python 3.13 + PySide6 (Qt6)
- LeRobot integration for SO-100/SO-101 arms
- Sydney timezone support
- Robust file system operations with backups

#### Known Limitations
- No backward compatibility with pre-0.01 single-file recordings
- Requires fresh start with new composite format
- Designed for Linux (tested on Ubuntu)

---

## Version Format
`MAJOR.MINOR`
- MAJOR: Breaking changes or major feature releases
- MINOR: Bug fixes, improvements, new features (backward compatible)

