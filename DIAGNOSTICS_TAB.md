# 🔧 Diagnostics Tab - Real-time Motor Monitoring

## Overview

The Diagnostics tab provides real-time monitoring of all motor parameters in a compact, easy-to-read table format. Perfect for troubleshooting, monitoring system health, and identifying issues before they become problems.

## Features

### 📊 Compact Table View
- **All 6 motors visible at once** - No scrolling needed
- **9 data columns per motor**:
  1. Motor name (Shoulder Pan, Shoulder Lift, etc.)
  2. Position (current/max 4095)
  3. Goal position
  4. Velocity (units/s)
  5. Load (percentage with color coding)
  6. Temperature (°C with color coding)
  7. Current (mA)
  8. Voltage (V with color coding)
  9. Moving status (Yes/No)

### 🎨 Color Coding

**Temperature:**
- 🟢 Green: < 45°C (Safe)
- 🟠 Orange: 45-60°C (Warning)
- 🔴 Red: > 60°C (Critical)

**Load:**
- 🟢 Green: < 80% (Normal)
- 🟠 Orange: 80-95% (High)
- 🔴 Red: > 95% (Critical)

**Voltage:**
- 🟢 Green: 11-13V (Normal)
- 🟠 Orange: Outside range (Check power supply)

**Moving:**
- 🔵 Blue: Motor is currently moving
- Gray: Motor is stationary

### ⚙️ Controls

**Arm Selection:**
- Toggle between Arm 1 and Arm 2
- Automatically reconnects when switching

**Refresh Rate:**
- Manual: Click "Refresh Now" button only
- 0.5s: Fast updates (2 Hz)
- 1.0s: Normal updates (1 Hz) - Default
- 2.0s: Slow updates (0.5 Hz)

**Connection:**
- 🔌 Connect: Establish connection to motors
- 🔌 Disconnect: Close connection

**Data Logging:**
- 📊 Start Logging: Begin recording diagnostic data
- 📊 Stop Logging: End recording session
- Logs stored in memory until exported

**Export:**
- 💾 Export CSV: Save logged data to `logs/diagnostics/`
- Filename format: `diagnostics_arm{N}_{timestamp}.csv`
- Includes all motor parameters with timestamps

## Usage Guide

### Basic Monitoring

1. **Open Settings → Diagnostics tab**
2. **Select your arm** (Arm 1 or Arm 2)
3. **Click "🔌 Connect"**
4. Data updates automatically based on refresh rate

### Troubleshooting a Problem

1. **Connect to the arm**
2. **Set refresh to 0.5s** for fast updates
3. **Manually move the robot** or run an action
4. **Watch for:**
   - Temperature spikes (orange/red cells)
   - High load (orange/red cells)
   - Voltage drops (orange cells)
   - Motors not reaching goal position
   - Unexpected moving status

### Recording a Diagnostic Session

1. **Connect to the arm**
2. **Click "📊 Start Logging"**
3. **Run your test** (manual movement, sequence, etc.)
4. **Click "📊 Stop Logging"** when done
5. **Click "💾 Export CSV"** to save the data

### Analyzing CSV Data

The exported CSV contains:
```csv
Timestamp,Arm,Motor,Position,Goal,Velocity,Load,Temperature,Current,Voltage,Moving
2024-01-15T10:30:45.123,1,1,2048,2050,0,15,32,145,122,0
2024-01-15T10:30:45.623,1,2,1106,1100,12,22,35,178,121,1
...
```

Import into Excel, Python, or any data analysis tool.

## Summary Bar

At the bottom of the table, key metrics are displayed:

- **Max Temp**: Highest temperature across all motors
- **Total Current**: Sum of all motor currents
- **Avg Voltage**: Average voltage across all motors
- **Status**: Overall system health
  - ✓ OK: All parameters normal
  - 🟡 WARNING: Some parameters in warning range
  - 🔴 CRITICAL: Critical thresholds exceeded

## Connection Status

Top bar shows:
- **Connection state**: Connected (green) / Disconnected (red)
- **Port**: Serial port being used (e.g., /dev/ttyACM0)
- **Last update**: Timestamp of most recent data refresh

## Common Issues

### "Failed to connect"
- Check that motors are powered on
- Verify correct port in Robot settings
- Ensure no other program is using the port
- Try the other arm to verify it's not a hardware issue

### "No data" or "--" in cells
- Motor may not be responding
- Check physical connections
- Verify motor IDs in calibration
- Try reconnecting

### High temperature warnings
- Normal during extended use
- Allow motors to cool down
- Check for mechanical binding
- Reduce load or speed if persistent

### Voltage warnings
- Check power supply connection
- Verify power supply voltage (should be 12V)
- Check for voltage drop under load
- May indicate power supply insufficient for load

## Tips

1. **Baseline Recording**: Take a diagnostic recording of normal operation for comparison
2. **Regular Monitoring**: Check temperatures after long sessions
3. **Pre-flight Check**: Quick connect to verify all motors responding before important tasks
4. **Troubleshooting**: Use 0.5s refresh when diagnosing intermittent issues
5. **Documentation**: Export and save CSV files when reporting issues

## Technical Details

### Data Sources

All data comes from the Feetech motor control tables:
- `Present_Position`: Current motor position (0-4095)
- `Present_Velocity`: Current velocity in units/s
- `Present_Load`: Load/torque on motor (converted to %)
- `Present_Temperature`: Internal temperature sensor (°C)
- `Present_Current`: Current draw (mA)
- `Present_Voltage`: Supply voltage (V * 10)
- `Goal_Position`: Target position for motor
- `Moving`: Boolean flag indicating motion

### Update Rate

The refresh rate determines how often the entire table is updated. Lower refresh rates reduce bus traffic and CPU usage but provide less frequent data.

For most uses, 1.0s is sufficient. Use 0.5s for troubleshooting active issues.

### Motor Bus

Each connection opens a serial bus to the motors. Only one connection per port is allowed at a time. Disconnect from diagnostics before using motors elsewhere (e.g., running actions).

## Safety

- 🔥 **Monitor temperatures** - Motors can overheat if overloaded
- ⚡ **Watch load percentages** - Sustained high load can damage motors
- 🔋 **Check voltages** - Low voltage indicates power issues
- ⚠️ **Heed warnings** - Orange/red indicators mean action needed

The diagnostics tab is a monitoring tool - it does not control motors. Use it alongside the Robot tab, Dashboard, and other controls for comprehensive system management.

## Export File Locations

Diagnostic CSV files are saved to:
```
logs/diagnostics/diagnostics_arm1_YYYYMMDD_HHMMSS.csv
logs/diagnostics/diagnostics_arm2_YYYYMMDD_HHMMSS.csv
```

The `logs/diagnostics/` directory is created automatically if it doesn't exist.

## Integration

The Diagnostics tab integrates with:
- **MotorController** - Uses existing motor control infrastructure
- **Config system** - Reads port and arm configuration
- **Settings status bar** - Displays connection and export messages

It operates independently of other tabs and can be used while other features are idle.

