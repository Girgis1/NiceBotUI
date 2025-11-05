# Agent Workflow Guide: Working with Nvidia Jetson

This document provides instructions for AI coding agents on how to work with the Nvidia Jetson device as part of the development workflow for LerobotGUI.

## System Configuration

### SSH Setup
- **Host alias:** `jetson`
- **IP Address:** 192.168.1.88
- **User:** nicebot
- **SSH Key:** `~/.ssh/id_ed25519` (passwordless authentication configured)
- **SSH Config Location:** `~/.ssh/config`

### Directory Structure
- **Local workspace:** `/home/daniel/LerobotGUI/` (renamed from NiceBotUI)
- **Jetson workspace:** `/home/nicebot/NiceBotUI/` (git repository)
- **Logs directory:** `logs/` (exists in both locations)

**Note:** The local machine uses "LerobotGUI" as the folder name, but syncs to "NiceBotUI" on the Jetson to maintain the git repository structure.

## Available Tools & Scripts

### 1. Sync Scripts

#### `sync_to_jetson.sh` - Push Changes to Jetson
Syncs local changes to the Jetson device.

**Usage:**
```bash
./sync_to_jetson.sh [--dry-run]
```

**Flags:**
- `--dry-run` - Preview what would be transferred without making changes

**Excludes:**
- `.venv/` (virtual environments)
- `__pycache__/` (Python cache)
- `*.pyc` (compiled Python)
- `.git/` (git repository)
- `*.log` (log files - managed separately)
- `.DS_Store` (macOS files)
- `node_modules/` (npm packages)

#### `sync_from_jetson.sh` - Pull Changes from Jetson
Syncs changes from Jetson back to local machine.

**Usage:**
```bash
./sync_from_jetson.sh [--dry-run] [--logs-only]
```

**Flags:**
- `--dry-run` - Preview without making changes
- `--logs-only` - Only sync log files (fast, useful for checking outputs)

#### `jetson_helpers.sh` - Jetson Logging Utilities
Helper functions for running commands with logging on the Jetson.
**Location on Jetson:** `~/jetson_helpers.sh`

**Functions:**
- `run_logged <command>` - Execute command with automatic logging
- `tail_latest_log` - View most recent log in real-time
- `list_logs` - Display available log files

## Common Workflows

### Workflow 1: Develop and Test on Jetson

**When to use:** Making changes locally that need to be tested on Jetson hardware.

```bash
# 1. Make changes locally (edit code)

# 2. Preview what will be synced
./sync_to_jetson.sh --dry-run

# 3. Sync to Jetson
./sync_to_jetson.sh

# 4. SSH into Jetson
ssh jetson

# 5. Navigate to project
cd ~/LerobotGUI

# 6. Load logging helpers
source ~/jetson_helpers.sh

# 7. Run with logging
run_logged python app.py

# 8. Exit Jetson (Ctrl+D or 'exit')

# 9. Pull logs back to local
./sync_from_jetson.sh --logs-only

# 10. Review logs locally
ls -lt logs/jetson_*.log
```

### Workflow 2: Quick Log Check

**When to use:** Just want to see what's happening on the Jetson without SSHing.

```bash
# Pull latest logs
./sync_from_jetson.sh --logs-only

# View most recent Jetson log
tail -f logs/jetson_$(ls -t logs/jetson_*.log 2>/dev/null | head -1 | xargs basename)
```

### Workflow 3: Retrieve Work Done on Jetson

**When to use:** User made changes directly on Jetson that need to be pulled back.

```bash
# Preview what's different
./sync_from_jetson.sh --dry-run

# Pull all changes
./sync_from_jetson.sh
```

### Workflow 4: Initial Project Setup on Jetson

**When to use:** First time deploying project to Jetson.

```bash
# 1. Sync entire project
./sync_to_jetson.sh

# 2. SSH into Jetson
ssh jetson

# 3. Setup environment
cd ~/LerobotGUI
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. Test basic functionality
source ~/jetson_helpers.sh
run_logged python -c "import lerobot; print('LeRobot imported successfully')"

# 5. Exit and pull logs
exit
./sync_from_jetson.sh --logs-only
```

## Best Practices for Agents

### 1. Always Use Dry-Run First
When making significant changes, preview the sync operation:
```bash
./sync_to_jetson.sh --dry-run
```

### 2. Sync Before Testing
Before asking the user to test on Jetson, sync the changes:
```bash
./sync_to_jetson.sh
```

### 3. Retrieve Logs After Remote Execution
After running code on Jetson, always pull logs:
```bash
./sync_from_jetson.sh --logs-only
```

### 4. Use Logging Functions on Jetson
When providing commands to run on Jetson, always use `run_logged`:
```bash
# Good
run_logged python app.py

# Not as good (logs not captured)
python app.py
```

### 5. Check Connectivity First
If unsure about Jetson availability:
```bash
ssh jetson "echo 'Jetson is reachable'"
```

### 6. Respect Excluded Files
Don't sync virtual environments or cache files. The exclusion list is:
- `.venv/`, `__pycache__/`, `*.pyc`, `.git/`, `*.log`, `.DS_Store`, `node_modules/`

### 7. Handle Long-Running Processes
For processes that run continuously on Jetson:
```bash
# Use nohup and background
ssh jetson "cd ~/LerobotGUI && nohup python app.py > logs/jetson_app_$(date +%Y%m%d_%H%M%S).log 2>&1 &"
```

## Troubleshooting Commands

### Check Jetson Connection
```bash
ssh jetson "hostname && uptime"
```

### Verify Sync Paths Exist
```bash
ssh jetson "ls -la ~/LerobotGUI/"
```

### Check Disk Space on Jetson
```bash
ssh jetson "df -h ~"
```

### View Remote Logs Without Pulling
```bash
ssh jetson "tail -f ~/LerobotGUI/logs/jetson_*.log"
```

### Kill Stuck Processes on Jetson
```bash
ssh jetson "pkill -f app.py"
ssh jetson "pkill -f vision_app.py"
```

### Compare File Counts (Debug Sync Issues)
```bash
# Local
find ~/LerobotGUI -type f | wc -l

# Remote
ssh jetson "find ~/LerobotGUI -type f | wc -l"
```

## Log File Naming Convention

### Jetson Logs
- **Pattern:** `jetson_YYYYMMDD_HHMMSS.log`
- **Location:** `logs/`
- **Created by:** `run_logged` function
- **Contains:** Full terminal output, start/end times, exit codes

### Application Logs
- **Pattern:** `policy_server_*.log`, `robot_client_*.log`
- **Location:** `logs/`
- **Created by:** Application code
- **Contains:** Application-specific logging

## User Timezone
- **Timezone:** Australia/Sydney (AEDT/AEST)
- When displaying timestamps, convert to this timezone if possible

## Quick Reference Table

| Task | Command |
|------|---------|
| Push changes to Jetson | `./sync_to_jetson.sh` |
| Pull changes from Jetson | `./sync_from_jetson.sh` |
| Pull only logs | `./sync_from_jetson.sh --logs-only` |
| Preview sync | `./sync_to_jetson.sh --dry-run` |
| SSH into Jetson | `ssh jetson` |
| Run with logging on Jetson | `run_logged <command>` |
| View latest log on Jetson | `tail_latest_log` |
| Check Jetson status | `ssh jetson "uptime"` |

## Integration with Development Tasks

### When Making Code Changes
1. Edit files locally
2. Run local tests if applicable
3. Sync to Jetson: `./sync_to_jetson.sh`
4. Test on Jetson hardware
5. Pull logs: `./sync_from_jetson.sh --logs-only`
6. Review results

### When Debugging Issues
1. Check local logs: `ls -lt logs/`
2. Pull Jetson logs: `./sync_from_jetson.sh --logs-only`
3. Compare outputs
4. Make fixes locally
5. Repeat test cycle

### When Deploying Changes
1. Ensure all changes are committed (if using git)
2. Sync to Jetson: `./sync_to_jetson.sh`
3. SSH and restart services
4. Monitor logs: `./sync_from_jetson.sh --logs-only`

## Notes for Agents

- The user (daniel) prefers seeing actual terminal output from the Jetson
- Always offer to pull logs after remote execution
- Assume Jetson is for hardware testing (motors, cameras, real robot control)
- Local machine is for development and editing
- The Jetson has limited resources compared to the local machine
- Don't suggest running heavy computation on Jetson unless necessary
- If a task requires GPU/inference, the Jetson Orin Nano has 8GB memory available

## Environment Differences

### Local Machine
- **OS:** Linux (Ubuntu-based)
- **Python:** Multiple versions available
- **Use for:** Development, editing, git operations, heavy computation

### Jetson Orin Nano 8GB
- **OS:** JetPack (Ubuntu-based)
- **Arch:** aarch64 (ARM)
- **GPU:** Integrated NVIDIA GPU (CUDA capable)
- **RAM:** 8GB shared memory
- **Use for:** Robot control, motor operations, real-time inference, camera operations

### Compatibility Notes
- Some packages may need ARM-specific builds
- PyTorch/TensorFlow may have different installation methods
- CUDA version is fixed by JetPack version
- Not all Python packages available on ARM architecture

## File Management

### Files That Should Stay Local
- Development documentation (unless needed on Jetson)
- Large model files (unless needed for inference)
- Git repository metadata
- Virtual environment directories

### Files That Should Sync
- Application code (Python files)
- Configuration files (JSON, YAML)
- Scripts
- Small data files
- Requirements files

### Files That Sync Back
- Logs (primary use case)
- Recorded data from robot operations
- Configuration changes made on Jetson
- Results from Jetson-specific operations

---

**Last Updated:** 2025-11-05  
**Maintained for:** AI coding agents working on LerobotGUI project

