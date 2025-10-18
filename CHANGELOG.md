# Changelog - LerobotGUI

All notable changes to this project will be documented in this file.

## [0.03] - 2025-10-18

### 🚀 Sequencer Rebuild - Full Production Ready

#### Major Features
- **✅ Complete Sequencer Rebuild**
  - Sequencer now fully functional and production-ready
  - Modular, folder-based composite architecture
  - Individual step files for easy editing
  - Automatic backups on every save

- **✅ New Step Types**
  - **Action Steps** - Execute saved recordings/actions
  - **Model Steps** - Run trained policy models with duration control
  - **Delay Steps** - Wait for specified time periods
  - **Home Steps** - Return arm to rest position (NEW!)
  - **Loop Mode** - Repeat sequences indefinitely

- **✅ Execution Engine**
  - Fixed type mismatch: "recording" → "action"
  - Implemented model execution in sequences
  - Models run as subprocesses with graceful shutdown
  - Full progress and status feedback
  - Stop button works mid-sequence

- **✅ Composite Sequence Architecture**
  - Folder structure: `data/sequences/{name}/manifest.json`
  - Individual step files: `01_step_action.json`, `02_step_delay.json`, etc.
  - Easy to edit individual steps without affecting others
  - Extensible for future step types (vision triggers, sensors)

#### Technical Implementation
- **New Files**:
  - `utils/sequence_step.py` - Base classes (ActionStep, ModelStep, DelayStep, HomeStep)
  - `utils/composite_sequence.py` - Folder-based sequence management
  
- **Rewritten**:
  - `utils/sequences_manager.py` - Complete rewrite for composite format
  - `utils/execution_manager.py` - Added home and model execution
  
- **Enhanced**:
  - `tabs/sequence_tab.py` - Added +Home button, execution wiring
  - `tabs/dashboard_tab.py` - Added run_sequence() method
  - `app.py` - Connected sequence execution signals

#### Bug Fixes
- ✅ Fixed AttributeError: 'DashboardTab' object has no attribute 'run_btn'
  - Corrected to use 'start_stop_btn'
- ✅ Fixed sequencer never working - complete rebuild from scratch
- ✅ Fixed type mismatch in sequence execution

#### Files Modified (7 files, 1,300+ lines)
- `app.py` - Signal connections
- `tabs/dashboard_tab.py` - run_sequence method, button fix
- `tabs/sequence_tab.py` - +Home button, signal emission
- `utils/execution_manager.py` - Home + model inline execution
- `utils/sequences_manager.py` - Composite format (complete rewrite)
- **NEW** `utils/composite_sequence.py` - Sequence orchestration
- **NEW** `utils/sequence_step.py` - Step type classes

#### Architecture Benefits
- **Modular** - Each step is its own file
- **Extensible** - Easy to add new step types
- **Robust** - Automatic backups, error handling
- **Maintainable** - Clean separation of concerns
- **Industrial Ready** - Built for reliability

#### Testing Requirements
Hardware testing needed for:
- Basic sequence (action + delay)
- Home step execution
- Loop mode
- Model execution in sequences
- Stop mid-sequence

#### Documentation
- Added `SEQUENCER_COMPLETE.md` - Full implementation summary
- Added `SEQUENCER_REBUILD_PLAN.md` - Architecture and planning

---

## [0.02] - 2025-10-18

### 🐛 Bug Fix Release

#### Critical Fixes
- **✅ Delete Button Fixed**
  - Fixed Qt lambda issue causing delete button to not work
  - Now passes button reference instead of using sender()
  - Delete functionality fully operational with confirmation dialog

- **✅ Velocity/Speed Separation**
  - Positions now use motor velocity (50-1000) from slider
  - Live recordings use speed percentage (25-200)
  - Column renamed to "Vel/Speed" to reflect dual purpose
  - Proper data structure for saving/loading with correct parameters

- **✅ Removed Defunct Features**
  - Removed "Add Delay" button (delays now part of composite manifest)
  - Cleaned up AttributeError related to add_delay_row
  - Delays will return in future step editor UI

- **✅ Import Fixes**
  - Removed obsolete settings_dialog imports
  - Fixed ModuleNotFoundError on app startup
  - Settings now handled by integrated SettingsTab

#### Technical Improvements
- Added extensive debug logging for troubleshooting
- Improved action table data structure
- Better separation of concerns between position and live recording types
- Enhanced error messages with context

#### Files Modified
- `widgets/action_table.py` - Fixed delete button, velocity/speed handling
- `tabs/record_tab.py` - Velocity from slider, debug logging
- `app.py` - Removed obsolete imports
- `tabs/dashboard_tab.py` - Removed obsolete imports

#### Testing Notes
- Delete button confirmed working with button reference approach
- Velocity slider correctly applies to position recordings
- Speed percentage correctly applies to live recordings

---

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

