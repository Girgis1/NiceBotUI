# Train Tab Plan (ACT Dataset Recording & Launch)

## Goals
- Provide a touch-first ACT dataset recorder UI with the same status/camera bar as Dashboard.
- Support left/right/bimanual arm selection and teleop “sanity check” before recording.
- Map Reset/Next controls to the ACT reset flow (left = reset env/episode, right = next episode).
- Enforce resume semantics (`resume=true` to append if data exists; block/confirm overwrite otherwise).
- Keep all heavy training off the Jetson; allow launching local-GPU training from this tab.

## UI Layout
- **Header**: Reuse Dashboard status bar (robot/camera indicators, Model: label, camera preview + Cameras popup).
- **Main controls (large buttons)**:
  - Idle: `START`, `Modify` (opens side panel), (Next hidden).
  - Recording: `STOP` (red), `⏮ Redo` (orange = reset/left), `⏭ Next` (blue = next/right).
  - Status line under header for concise messages (e.g., “At home position”, “Recording ep 3/30”, “Resetting env…”).
- **Side panel (slide-out, tappable arrow, dark overlay)**:
  - Thick edge/handle for resizing.
  - Fields (touch-friendly):
    - Run/Model name (pre-filled `act_run_YYYYMMDD_HHMMSS`).
    - Episodes (min 30) with big ▲/▼.
    - Episode length (seconds) with big ▲/▼.
    - Arm mode: Left / Right / Bimanual buttons.
    - Resume toggle (default ON).
    - Notes textbox.
    - Existing dataset dropdown (shows episodes count, trained flag).
  - Save/Apply close the panel; tapping outside closes.
- **Log panel**: concise, training-specific messages; filter spam.

## Dataset Management & Validation
- Dataset root: `outputs/datasets/act/<name>` (configurable later).
- On START:
  - If folder missing → create.
  - If exists and empty → purge then start fresh.
  - If exists and resume=true → append (resume flag passed through).
  - If exists and resume=false → prompt overwrite; on confirm, delete and start fresh; otherwise cancel.
- Show computed path + existence state in header/info line.
- Track episodes completed, target episodes, episode length.
- Enforce minimum episodes = 30 (per requirement).

## ACT Recording Hooks (per HF docs)
- Parameters to pass when wiring:
  - `resume` (bool)
  - `episode_length` (seconds)
  - `num_episodes`
  - `dataset_name/path`
  - Sensors: cameras/proprio as per ACT defaults (plan to map from config).
- Reset/Next behavior:
  - Left action = enter “reset environment” state; second left confirms and restarts episode timer.
  - Right action = “next episode” (end current early).
  - Auto-start recording after reset timeout if no input (per ACT expectation).
- Capture metadata:
  - Arm mode, notes, timestamp, device info.
  - Mark `trained.flag` (or similar) after training finishes (on local machine).

## Arm/Teleop Check
- Provide Left/Right/Bimanual selection tied to the manager.
- Quick “Check motion” trigger (optional) before recording to verify ports/torque.
- Show arm status in header indicators; error if ports unavailable.

## Training Launch (Local GPU, not Jetson)
- “Train” button (small, orange) triggers a local script/notebook on this machine:
  - Inputs: dataset path, run name, resume, epochs, batch size, lr, seed, output dir.
  - No training on Jetson; just start process locally (future wiring).
- Show training status in log (started/finished/failed) and set `trained.flag` on success.

## Logging & Status Messages (examples)
- Split log into **two conceptual streams**:
  - **ACT Session Log (on screen)** – concise, human-readable status:
    - Info: “Recording ep X/Y”, “Resetting environment… (left)”, “Advancing to next episode… (right)”, “Appending to existing dataset (resume)”.
    - Warnings: “Dataset exists; resume enabled”, “Overwrite cancelled”, “Arm(s) offline”, “Camera missing”.
    - Errors: “Failed to connect motors”, “Failed to open dataset path”, “Recording aborted”.
    - Completion: “Recording complete: X episodes saved to <path>”.
  - **Raw lerobot output (background)** – streamed to stdout/log files only; Train tab surfaces *only* selected lines prefixed with `[lerobot] …` to avoid spam.
- Bottom log panel shows a rolling summary:
  - Latest dataset summary line (e.g. `pick_v2_bi — 12/40 episodes, 30s, BI`).
  - Last N key events (episode start/stop, errors, teleop checks).
  - When idle, shows quick hints (“Press START to record ep N/Total for <dataset>”).

## Keybindings & Touch Actions
- On-screen buttons drive reset/next; future: map to key events (Left/Right) for ACT recorder.
- Tap outside panel closes it; arrow shows/hides panel.
- Keep Start visible only when idle; hide during recording.

## Optimizations (future wiring)
- Use MotorManager handles to avoid port contention; parallel arm checks.
- Debounce log spam; rate-limit status updates.
- Preflight resource check: disk space, camera availability, motor ports RW.
- Non-blocking recording worker; keep UI responsive.

## Command & Naming Strategy (Recording + Training)

### Dataset & Model Naming
- **Dataset IDs**:
  - Internal slug: `dataset_id = sanitize(run_name)` (e.g. `pick_v2_bi`).
  - Stored under: `outputs/datasets/act/<dataset_id>/metadata.json`.
  - HF local repo: `local/act_<dataset_id>_<YYYYMMDD_%H%M%S>` (unique per run).
- **Metadata fields** (per dataset):
  - `name` (user-facing), `dataset_id`, `repo_id`, `target_episodes`, `episode_time_s`.
  - `arm_mode`: `"left" | "right" | "bimanual"` (UI choice).
  - `robot_mode`: `"solo" | "bimanual"` (read from `config.json` for validation).
  - `completed_episodes`, `trained` (bool), `training_output_dir`, `notes`.
- **Training output**:
  - Default: `outputs/train/act_<dataset_id>` (mirrors ACT docs).
  - Checkpoints follow standard lerobot layout: `<output_dir>/checkpoints/{step|last}/pretrained_model`.

### Recording Commands (Jetson, behind the Train tab)
- **Common flags (all modes)**:
  ```bash
  lerobot-record \
    --display_data=false \
    --dataset.repo_id=local/act_<dataset_id>_<timestamp> \
    --dataset.single_task="<name>" \
    --dataset.num_episodes=1 \
    --dataset.episode_time_s=<episode_time_s> \
    --dataset.push_to_hub=false \
    --resume=<true|false> \
    --robot.cameras="{ front: {type: opencv, index_or_path: /dev/video0, width: 640, height: 480, fps: 30}, ... }"
  ```
- **Solo LEFT** (one follower + one leader):
  ```bash
  # follower left only
  --robot.type=so101_follower \
  --robot.port=/dev/ttyACM0 \
  --robot.id=left_follower \
  --teleop.type=so100_leader \
  --teleop.port=/dev/ttyACM1 \
  --teleop.id=left_leader
  ```
- **Solo RIGHT**:
  ```bash
  # follower right only
  --robot.type=so101_follower \
  --robot.port=/dev/ttyACM2 \
  --robot.id=right_follower \
  --teleop.type=so101_leader \
  --teleop.port=/dev/ttyACM3 \
  --teleop.id=right_leader
  ```
- **Bimanual** (matches `bimanual_working.md` layout; follower so101, leaders so100):
  ```bash
  --robot.type=bi_so101_follower \
  --robot.left_arm_port=/dev/ttyACM0 \
  --robot.right_arm_port=/dev/ttyACM2 \
  --robot.id=bimanual_follower \
  --teleop.type=bi_so100_leader \
  --teleop.left_arm_port=/dev/ttyACM1 \
  --teleop.right_arm_port=/dev/ttyACM3 \
  --teleop.id=bimanual_leader
  ```
- Train tab maps `arm_mode` + `config.json` to these patterns automatically; the CLI snippets above are for debugging/manual runs.

### Training Commands (PC / GPU, not Jetson)
- **Initial ACT training** for a dataset:
  ```bash
  lerobot-train \
    --dataset.repo_id=local/act_<dataset_id>_<timestamp> \
    --policy.type=act \
    --output_dir=outputs/train/act_<dataset_id> \
    --job_name=act_<dataset_id> \
    --policy.device=cuda
  ```
- **Resuming training**:
  - Reuse the same `output_dir` and `job_name`.
  - Use the standard lerobot resume flag (check `lerobot-train --help`, typically `--resume_from_checkpoint=<output_dir>/checkpoints/last`).
  - On success, Train tab can set `trained=true` and record `training_output_dir`.

### Evaluation / Policy Playback (Dashboard, not Train tab)
- After training, Dashboard / Sequencer use existing model workflow:
  - `list_model_task_dirs()` discovers `outputs/train/act_<dataset_id>`.
  - User selects `🤖 Model: act_<dataset_id>` from Dashboard RUN combo.
  - Checkpoints appear under `checkpoints/` with “last” and numeric steps.
  - Execution worker uses:
    ```bash
    lerobot-record \
      --dataset.repo_id=local/eval_act_<dataset_id>_<timestamp> \
      --dataset.num_episodes=1 \
      --dataset.episode_time_s=<duration> \
      --policy.path=<output_dir>/checkpoints/last/pretrained_model
    ```
  - This is already wired through `ExecutionWorker._execute_model_inline` for local mode.
## Checklist (Build Order)
1) Keep current UI shell (status bar, controls, side panel, overlay, resize handle).
2) Add dataset validation logic (exist/empty/resume/overwrite) when wiring.
3) Wire Reset/Next buttons to ACT recorder callbacks (left/right semantics + auto reset timeout).
4) Wire Start/Stop to ACT recorder lifecycle (episodes, timers, resume).
5) Populate dataset dropdown from `outputs/datasets/act`, show episodes count & trained flag.
6) Add arm-mode selection tied to MotorManager (and optional motion check). **TODO: wire Teleop button in panel to launch a quick teleop check for the selected arm(s).**
7) Add training launcher (local machine) with params form and log hookup.
8) Harden logging/status pipeline (structured messages, minimal noise; distinguish ACT log vs raw lerobot output).
9) Add preflight checks (disk, ports, cameras; warn on missing `/dev/ttyACM*` or permissions).
10) Enforce arm-mode semantics per dataset (warn on switching `arm_mode` or `robot.mode` mid-run; suggest new dataset).
11) Test: UI states, panel animation, overlay interactions, start/stop/reset/next, resume/overwrite paths, dataset selection, training launch stub, and left/right/bimanual recording commands on hardware.
