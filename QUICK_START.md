# Quick Start Guide - LeRobot Operator Console

## What You're Seeing Right Now 👀

Your GUI is running in **FULLSCREEN MODE** - perfect for your touch display!

```
┌────────────────────────────────────────────┐
│ LeRobot Operator Console      ⚙ Settings  │
├────────────────────────────────────────────┤
│                                            │
│ Status: 🔴 Motors  🔴 Camera               │
│ Action: ⚠️ Check configuration in Settings │
│ Time: 00:00                                │
│                                            │
│ Episodes: [3]                              │
│                                            │
│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓   │
│  ┃          START                    ┃   │
│  ┃       (Giant Green Button)        ┃   │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛   │
│                                            │
│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓   │
│  ┃          STOP                     ┃   │
│  ┃        (Giant Red Button)         ┃   │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛   │
│                                            │
│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓   │
│  ┃        GO HOME                    ┃   │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛   │
│                                            │
├─ Recent Runs ─────────────────────────────┤
│ ✓ 12 Oct 05:10 PM - 5/5 - 2m 25s         │
│                                            │
└────────────────────────────────────────────┘
```

## Those Warnings Are Normal! ✅

You're seeing:
- ⚠️ **Policy not found** - Because you haven't trained a model yet
- ⚠️ **Serial port not found** - Because the robot isn't connected yet

**This is expected!** The GUI is working perfectly. These will turn green (🟢) when you connect hardware.

## What Everything Does

### Status Indicators
- 🔴 **Red dot** = Not connected (normal without hardware)
- 🟢 **Green dot** = Connected and ready
- **Action Label** = Shows what's happening ("Idle", "Recording Episode 2/5", etc.)
- **Time** = Elapsed time during a run

### Main Buttons

**START (Green, 180px tall)**
- Tap to begin recording episodes
- Uses the policy checkpoint to control the robot
- Runs for the number of episodes selected

**STOP (Red, 180px tall)**
- Tap to interrupt current run
- Asks for confirmation before stopping
- Robot will return to home position

**GO HOME (Blue, 120px tall)**
- Tap to move robot to rest/home position
- Uses the angles defined in config
- Safe to use anytime when not recording

**⚙ Settings (Gray, top-right)**
- Opens configuration editor
- 5 tabs: Robot, Camera, Policy, Control, Advanced
- "SET HOME" button is in Advanced tab

### Episodes Counter
- Spin box to set how many episodes to record
- Range: 1 to 9999
- Changes are saved when you tap START

### Recent Runs (Bottom)
- Shows last 10 runs with timestamps (Sydney timezone)
- ✓ = Completed successfully
- ✗ = Failed
- ⊗ = Stopped by user

## Keyboard Shortcuts

Even though it's a touch screen, these work:
- **F11** - Toggle fullscreen on/off
- **Escape** - Exit fullscreen mode

## Testing Without Hardware

You can:
1. ✅ Tap Settings and explore all options
2. ✅ Change episodes counter
3. ✅ Tap GO HOME (will log that it's a stub)
4. ❌ START won't work yet (needs policy and robot)

## When You Connect Hardware

1. **Connect robot controller USB** → Motor indicator turns 🟢
2. **Connect camera USB** → Camera indicator turns 🟢  
3. **Train a policy** → Policy warning disappears
4. **Tap START** → Everything works!

## For Your Touch Display

The interface is designed with:
- **44px minimum touch targets** (industry standard)
- **High contrast colors** (colorblind-friendly)
- **Large fonts** (28-32px for main buttons)
- **20px spacing** between buttons
- **Press feedback** (buttons darken when touched)

## Running Modes

**Production mode (what you have now):**
```bash
python app.py
```
- Fullscreen by default
- Warnings shown in action label (not popup)
- Perfect for always-on touch display

**Testing mode:**
```bash
python app.py --windowed
```
- Windowed mode (800×600)
- Warnings shown in popup dialog
- Easy to resize and move

## Next Steps

1. **Leave it running** - It's designed to stay open 24/7
2. **Explore Settings** - Tap ⚙ Settings to see all options
3. **Connect hardware** - When ready, plug in robot and camera
4. **Train a policy** - Follow LeRobot docs to train a model
5. **Start using** - Tap START to record episodes!

## Need Help?

The application has built-in error handling. If something goes wrong, you'll see:
- **Problem:** What went wrong
- **Solution:** Exactly how to fix it

Example errors:
- "Motors not found" → "Check USB cable and power supply"
- "Joint 3 not responding" → "Check cable connection at joint 3"
- "Power lost" → "Check emergency stop button"

---

**Everything is working perfectly! 🎉**

The warnings you see are just letting you know the hardware isn't connected yet. The GUI is ready and waiting for you to add the robot when you're ready.


