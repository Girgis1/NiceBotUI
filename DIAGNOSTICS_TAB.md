# Diagnostics Tab - Simplified Real-time View

The Diagnostics Tab has been successfully implemented in the Settings UI, providing real-time motor data in a maximized, easy-to-read table format.

## Features

### Layout and Design
- **Maximized Table View**: Displays all 6 motors in a large, information-dense table that fills the available space
- **Fast Auto-Refresh**: Updates every 0.2 seconds (5 Hz) automatically
- **Auto-Connect**: Connects to motors automatically on tab open (500ms delay)
- **Color-Coded Indicators**: Visual warnings for temperature, load, and voltage issues
- **Arm Selection**: Simple toggle between Arm 1 and Arm 2 diagnostics
- **Clean UI**: Minimal controls - just the essentials for monitoring

### Data Displayed

For each motor (1-6), the table shows:

| Column | Description | Color Coding |
|--------|-------------|--------------|
| Motor | Motor ID and name (e.g., "1. Shoulder Pan") | - |
| Position | Current position (0-4095) | - |
| Goal | Target goal position | - |
| Velocity | Current velocity (raw value) | - |
| Load | Load percentage | 🟢 <80% / 🟡 80-100% / 🔴 >100% |
| Temp | Temperature (°C) | 🟢 <45°C / 🟡 45-60°C / 🔴 >60°C |
| Current | Current draw (mA) | - |
| Voltage | Motor voltage (V) | 🟢 11-13V / 🟡 Outside range |
| Moving | Whether motor is moving | 🔵 Yes / ⚪ No |

### Controls

- **Arm Selector**: Toggle between Arm 1 and Arm 2 using radio buttons
- All other operations are automatic (connection, refresh)

## Implementation Details

### File Structure

- **`tabs/diagnostics_tab.py`**: Main implementation file (365 lines)
  - `DiagnosticsTab` class (QWidget)
  - Auto-refresh timer at 200ms (5 Hz)
  - Motor data reading from `MotorController`
  - Color-coded table rendering
  - Auto-connect on tab open

### Integration

The Diagnostics Tab is integrated into `tabs/settings_tab.py`:

```python
# Add diagnostics tab to settings
self.diagnostics_tab = DiagnosticsTab(self.config)
self.diagnostics_tab.status_changed.connect(self.on_diagnostics_status)
self.tabs.addTab(self.diagnostics_tab, "Diagnostics")
```

Status messages from the diagnostics tab are displayed in the main settings status label.

### Data Reading

Uses `MotorController` to read the following parameters from the Feetech motor bus:
- `Present_Position`
- `Goal_Position`
- `Present_Velocity`
- `Present_Load`
- `Present_Temperature`
- `Present_Current`
- `Present_Voltage`
- `Moving`

## Usage

1. **Open Settings**: Navigate to the Settings tab
2. **Select Diagnostics**: Click on the "Diagnostics" tab
3. **Auto-Connect**: Connection happens automatically after 500ms
4. **Monitor**: Watch real-time data updating every 0.2 seconds
5. **Switch Arms**: Toggle between Arm 1 and Arm 2 using the radio buttons at the top

## Thresholds

Current warning thresholds (defined in `DiagnosticsTab` class):

```python
TEMP_WARNING = 45   # °C
TEMP_CRITICAL = 60  # °C
LOAD_WARNING = 80   # %
LOAD_CRITICAL = 100 # %
VOLTAGE_MIN = 11.0  # V
VOLTAGE_MAX = 13.0  # V
```

These can be adjusted in the class constants if needed for different motor specifications.

## UI Layout

```
┌───────────────────────────────────────────────────────────────────────────────────────┐
│  🔧 Motor Diagnostics - Real-time (5 Hz)        Arm: [●] Arm 1  [ ] Arm 2            │
├───────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐│
│  │ Motor             Position    Goal   Vel   Load  Temp   Current  Voltage  Moving ││
│  ├──────────────────────────────────────────────────────────────────────────────────┤│
│  │ 1 Shoulder Pan    2048/4095   2050    0    15%   32°C   145mA    12.2V    No    ││
│  │ 2 Shoulder Lift   1106/4095   1100   12    22%   35°C   178mA    12.1V    Yes   ││
│  │ 3 Elbow Flex      2994/4095   2994    0    18%   33°C   156mA    12.2V    No    ││
│  │ 4 Wrist Flex      2421/4095   2420    5    12%   31°C   132mA    12.1V    Yes   ││
│  │ 5 Wrist Roll      1044/4095   1044    0    08%   30°C   121mA    12.2V    No    ││
│  │ 6 Gripper         2054/4095   2060   15    45%   38°C   234mA    12.0V    Yes   ││
│  └──────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                        │
│                        (Table maximized to fill available space)                      │
│                                                                                        │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

## Status

✅ **Complete** - Simplified version implemented
- ✅ Real-time data display at 5 Hz
- ✅ Auto-connect on tab open
- ✅ Maximized table layout
- ✅ Color-coded warnings
- ✅ Arm switching
- ✅ Integrated into Settings UI
- ❌ Logging removed (not needed)
- ❌ Export removed (not needed)
- ❌ Manual controls removed (fully automatic)

## Design Philosophy

The simplified version focuses on:
1. **Immediate visibility**: Auto-connect and fast refresh
2. **Maximum information density**: Large table with all relevant data
3. **Minimal interaction**: Just arm selection, everything else is automatic
4. **Clean interface**: No unnecessary buttons or controls
