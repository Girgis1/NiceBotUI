# Solo/Bimanual Testing Checklist 🧪

## Quick Start

### Check Current Mode
```bash
python switch_mode.py status
```

### Switch Modes
```bash
# Switch to solo mode (single arm)
python switch_mode.py solo

# Switch to bimanual mode (dual arms)
python switch_mode.py bimanual
```

---

## Solo Mode Testing (Default)

### ✅ Configuration
- [ ] Run `python switch_mode.py status`
- [ ] Verify shows "Robot Mode: SOLO"
- [ ] Verify "Enabled Arms: 1/2"

### ✅ UI Display
- [ ] Open app → Recording tab
- [ ] Check mode indicator shows "Recording Mode: 👤 Solo"
- [ ] Dashboard → Check action dropdown
- [ ] Verify existing actions show 👤 icon

### ✅ Recording
- [ ] Record a new action
- [ ] Save it with a name (e.g., "test_solo")
- [ ] Check it appears with 👤 icon in dropdown
- [ ] Reload app → verify icon persists

### ✅ Playback
- [ ] Dashboard → Select a solo action (👤)
- [ ] Click "Play"
- [ ] Verify it executes correctly
- [ ] Check logs for "so100_follower" (not "bi_so100_follower")

### ✅ Sequences
- [ ] Sequence tab → Add action step
- [ ] Add a solo action
- [ ] Verify shows "👤 🎬 Action: test_solo"
- [ ] Save sequence
- [ ] Play sequence from Dashboard

### ✅ Policy Playback (if trained)
- [ ] Train a policy on solo data
- [ ] Dashboard → Select model
- [ ] Click "Play"
- [ ] Verify uses single arm (`--robot.port`)

---

## Bimanual Mode Testing

### ⚙️ Prerequisites
- [ ] Both robot arms physically connected
- [ ] Ports configured in config.json:
  - Arm 1: `/dev/ttyACM0`
  - Arm 2: `/dev/ttyACM1`
- [ ] (Optional) Both teleop arms connected if recording with teleop

### ✅ Configuration
```bash
python switch_mode.py bimanual
```
- [ ] Verify output shows both arms enabled
- [ ] Check "Bimanual ready" messages
- [ ] Run `python switch_mode.py status` to confirm

### ✅ UI Display
- [ ] Open app → Recording tab
- [ ] Check mode indicator shows "Recording Mode: 👥 Bimanual"
- [ ] Verify both arms are enabled in Settings → Robot Arms

### ✅ Recording
- [ ] Record a bimanual action (both arms moving)
- [ ] Save it (e.g., "test_bimanual")
- [ ] Check it appears with 👥 icon
- [ ] Dashboard → Verify shows "👥 🎬 Action: test_bimanual"

### ✅ Playback
- [ ] Dashboard → Select bimanual action (👥)
- [ ] Click "Play"
- [ ] Verify BOTH arms move
- [ ] Check logs for "bi_so100_follower"
- [ ] Verify mentions `left_arm_port` and `right_arm_port`

### ✅ Sequences
- [ ] Sequence tab → Add action step
- [ ] Add bimanual action
- [ ] Verify shows "👥 🎬 Action: test_bimanual"
- [ ] Save and play sequence
- [ ] Both arms should execute

### ✅ Policy Playback (Advanced)
- [ ] Train policy with bimanual data (`lerobot-record --robot.type=bi_so100_follower`)
- [ ] Load policy in Dashboard
- [ ] Play policy
- [ ] Verify both arms controlled simultaneously

---

## Mode Switching Tests

### ✅ Solo → Bimanual
- [ ] Start in solo mode with recordings
- [ ] Switch: `python switch_mode.py bimanual`
- [ ] Open app → Both recording modes work
- [ ] Old solo actions still show 👤
- [ ] New recordings show 👥

### ✅ Bimanual → Solo
- [ ] Start in bimanual mode
- [ ] Switch: `python switch_mode.py solo`
- [ ] Open app → Check mode indicator
- [ ] Old bimanual actions still show 👥
- [ ] New recordings show 👤
- [ ] Verify only Arm 1 is enabled

---

## Edge Cases & Validation

### ✅ Mode Mismatch Handling
- [ ] Record solo action in solo mode
- [ ] Switch to bimanual mode
- [ ] Try playing solo action → Should still work (uses Arm 1)
- [ ] Check no errors in console

### ✅ Config Persistence
- [ ] Set bimanual mode
- [ ] Close app
- [ ] Reopen → Verify still bimanual
- [ ] Mode indicator correct
- [ ] Icons correct

### ✅ Mixed Sequences
- [ ] Create sequence with both solo and bimanual actions
- [ ] Icons should show 👤 vs 👥 for each step
- [ ] Playback works for both types

### ✅ Settings Tab
- [ ] Open Settings → Robot tab
- [ ] Check both arms visible
- [ ] Can configure each independently
- [ ] Save settings → Mode persists

---

## Expected Behaviors

### Solo Mode Command Structure
```bash
# Recording (example)
lerobot-record --robot.type=so100_follower --robot.port=/dev/ttyACM0

# Policy playback (internal)
robot_client --robot.type=so100_follower --robot.port=/dev/ttyACM0
```

### Bimanual Mode Command Structure
```bash
# Recording (example)
lerobot-record --robot.type=bi_so100_follower \
  --robot.left_arm_port=/dev/ttyACM0 \
  --robot.right_arm_port=/dev/ttyACM1

# Policy playback (internal)
robot_client --robot.type=bi_so100_follower \
  --robot.left_arm_port=/dev/ttyACM0 \
  --robot.right_arm_port=/dev/ttyACM1
```

---

## Troubleshooting

### Issue: Mode indicator doesn't update
**Fix**: Close and reopen app after switching modes

### Issue: Bimanual playback only moves one arm
**Check**:
1. Both arms enabled in config?
2. Both ports correct?
3. Physical connections OK?
4. Console logs show `bi_so100_follower`?

### Issue: Icons don't show
**Fix**: Refresh action list (reload app or switch tabs)

### Issue: "No arms configured" error
**Fix**: 
```bash
python switch_mode.py status  # Check config
# If needed:
python switch_mode.py bimanual  # Re-enable arms
```

---

## Success Criteria

### Solo Mode ✓
- [x] Config shows solo
- [x] UI shows 👤 icons
- [x] Recording saves with mode
- [x] Playback uses single arm
- [x] Backward compatible

### Bimanual Mode ✓
- [x] Config shows bimanual
- [x] UI shows 👥 icons
- [x] Recording saves with mode
- [x] Playback uses both arms
- [x] Correct LeRobot robot type

### Overall ✓
- [x] Mode switching works
- [x] Icons persist across restarts
- [x] No errors in console
- [x] Both modes coexist peacefully

---

## Quick Test Script

```bash
# 1. Test solo mode
python switch_mode.py solo
python app.py  # Record and play solo action

# 2. Test bimanual mode
python switch_mode.py bimanual
python app.py  # Record and play bimanual action

# 3. Verify both work
python switch_mode.py status
python app.py  # Check both action types visible
```

---

**Last Updated**: Phase 3 Complete
**Status**: Ready for User Testing 🚀

