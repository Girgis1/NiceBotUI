# Train Tab UI Workshop Notes

## 🎯 **Project Overview**
Designing a train tab for NiceBotUI focused on ACT imitation learning data collection. The Jetson device handles ONLY data collection - training happens on PC/cloud.

## 📐 **Technical Constraints**
- **Screen Size:** 1024×600px touchscreen
- **Touch Targets:** Minimum 60px height for buttons
- **Platform:** Qt/PySide6 application
- **Device:** Jetson (data collection only, no training)

## 🔄 **Core Workflow**
1. **Model Setup** - Name model, configure recording parameters
2. **Episode Recording** - Collect demonstrations with navigation
3. **Dataset Management** - Sync to PC for training
4. **Training** - Disabled on device (remote only)

## 🎨 **FINAL REDESIGNED UI Layout (1024×600px - Dashboard Integration)**

**Design Philosophy:** Complete dashboard integration with big chunky buttons, status bar consistency, and model/episode status replacing log area.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  🚂 TRAIN TAB │ 00:00 │ Training: pick_and_place_v2 │ 🤖 R:2/2 C:2/2    │  ← Dashboard Status Bar
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│                    🎯 TRAINING CONTROL CENTER                           │  ← 200px Main Area
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                                                                     │ │
│  │                      [TRAIN]                                        │ │
│  │                    (Big Orange Button)                              │ │
│  │                                                                     │ │
│  │  *When training starts, splits into:*                               │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                    │ │
│  │  │     [<]     │ │   [PAUSE]   │ │     [>]     │                    │ │
│  │  │   Previous   │ │  Training   │ │    Next    │                    │ │
│  │  │   Episode    │ │             │ │   Episode  │                    │ │
│  │  └─────────────┘ └─────────────┘ └─────────────┘                    │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐ ┌─────────────────────────────────────────────────┐ │  ← Bottom Status Area
│  │  MODEL STATUS   │ │           EPISODE STATUS                        │ │
│  │                 │ │  ┌─────────────────────────────────────────────┐ │ │
│  │ Name: pick_v2   │ │  │ Episode: [▼ 23/50] ◀️ ▶️ Progress: ████░░░  │ │ │
│  │ Episodes: 50    │ │  │ Timer: 00:15 / 00:30  Status: RECORDING     │ │ │
│  │ Size: 2.4GB     │ │  │ Actions: 1,247  Quality: ✓                   │ │ │
│  │ Status: Ready   │ │  └─────────────────────────────────────────────┘ │ │
│  │ [SYNC TO PC]    │ │                                                 │ │
│  │ [TRAIN REMOTE]  │ └─────────────────────────────────────────────────┘ │
│  └─────────────────┘                                                     │
└─────────────────────────────────────────────────────────────────────────┘ ← 600px TOTAL
```

**Layout Analysis:**
- **Top Status Bar:** Dashboard-style with timer, current action, robot/camera status
- **Main Control Area:** Large, prominent training button that morphs during training
- **Bottom Status Area:** Model info + detailed episode status (replaces dashboard log)
- **Big Chunky Buttons:** 400×150px TRAIN button, morphs to 180×120px control buttons
- **Episode Dropdown:** For picking and setting episodes with navigation arrows
- **Screen Utilization:** 95% vs 47% in old vertical design

## 🔑 **Key Features**

### **Model Setup Section**
- **Model naming** - User-defined dataset names
- **Episode count** - How many demonstrations (default: 50)
- **Episode time** - Max duration per episode (default: 30s)
- **Resume capability** - Load existing partial datasets

### **Episode Navigation (Core Feature)**
- **◀️ PREV/RESET** - Navigate to previous episode OR reset current
- **▶️ NEXT** - Advance to next episode slot
- **Timer display** - Current time / total allowed time
- **State indicators** - Recording status, episode counter

### **Recording Controls**
- **[START EPISODE]** - Begin recording current episode
- **[SAVE]** - Save completed episode to dataset
- **[DISCARD]** - Delete current recording

### **Status Panels**
- **Dataset Status** - Episode count, file size, sync status
- **Training Status** - Disabled (shows sync/remote train options)

## 🎬 **Recording Workflow**

### **New Model Creation:**
1. User enters model name (e.g., "pick_and_place_v2")
2. Sets episode count (50) and time limit (30s)
3. Clicks "CREATE NEW"
4. Starts recording episodes sequentially

### **Episode Recording Process:**
1. Click "START EPISODE" → recording begins with timer
2. Perform demonstration task
3. Timer expires OR user stops → "SAVE" or "DISCARD" options
4. Use ◀️ ▶️ arrows to navigate between episodes
5. Continue until all episodes collected

### **Resume Existing Model:**
1. Select model from dropdown
2. See current progress (e.g., "23/50 episodes")
3. Continue recording from next available episode
4. Previously recorded episodes marked as complete

### **Dataset Sync:**
1. When dataset complete, click "SYNC TO PC"
2. Transfers dataset to training machine
3. Training happens remotely (PC/cloud)

## 🎨 **Design Decisions**

### **Why This Layout?**
- **Touchscreen optimized** - Large 60-80px touch targets
- **Progressive workflow** - Clear step-by-step process
- **Always-visible navigation** - Episode arrows never disappear
- **Minimal cognitive load** - One primary action visible at a time

### **Color Coding (Proposed):**
- 🟢 Green: Start/Save actions
- 🔵 Blue: Navigation/Info
- 🔴 Red: Stop/Discard/Danger
- 🟡 Yellow: Warnings/Paused states

### **Safety Features:**
- Emergency stop accessible during recording
- Clear recording state indicators
- Auto-save on timer expiration
- Manual episode validation

## 🤔 **Open Questions**

### **Navigation Logic:**
- Should ◀️ ▶️ arrows work during recording OR only during review?
- Should there be a "review mode" separate from "recording mode"?

### **Model Management:**
- How to handle model versioning (v1, v2, etc.)?
- Should we support model templates/presets?

### **Quality Assurance:**
- Auto-detection of failed episodes?
- Quality metrics display?
- Episode retry limits?

### **Sync/Transfer:**
- Compression options for large datasets?
- Resume interrupted transfers?
- Multiple destination support?

## 📋 **Implementation Notes**

### **State Management:**
- Track current model/dataset
- Episode completion status
- Recording state (idle/recording/review)
- Sync progress

### **File Structure:**
- Models stored as: `/data/models/{model_name}/`
- Episodes: `episode_{number}.json/mp4`
- Metadata: `metadata.json`

### **Qt Integration:**
- Use QTimer for recording countdown
- QProgressBar for episode progress
- QFileDialog for dataset export
- QNetworkManager for sync operations

## 🎯 **Next Steps**
1. Implement basic model setup UI
2. Add episode recording with timer
3. Implement navigation arrows
4. Add dataset sync functionality
5. Test full workflow on device

---

**Workshop Date:** January 15, 2025
**Last Updated:** January 15, 2025
**Status:** Design Complete, Ready for Implementation

