# Code Review Summary

## Overview
I walked through the run-time critical pieces of the GUI (the async inference worker, the execution manager, and configuration plumbing) with an eye toward how the console will behave on a production robot kiosk. The UI work is quite polished, but there are a few high-severity runtime issues that will make the system fragile once it is attached to real hardware.

## Findings

### 1. Async inference worker can block forever on server logs
The async worker starts the policy server with both `stdout` and `stderr` piped, but never consumes those pipes. Once the server prints enough output to fill its OS pipe buffer, `Popen`'s child will block on the next write and the console will hang even though nothing is wrong with the robot.

*Evidence: `robot_worker.py` lines 43-75 show the server process created with `stdout=subprocess.PIPE`/`stderr=subprocess.PIPE` and no corresponding reader.*

**Fix recommendation:** Either forward the server's streams to `subprocess.DEVNULL`/`sys.stdout`, or spin up a reader thread (exactly like `_monitor_process` does for the client stdout) so the pipes are drained continuously.

### 2. Client stderr is also left unread during runs
While `_monitor_process` consumes the client's `stdout`, the client's `stderr` is only read after the process exits. Any sustained stderr logging (warnings, tracebacks, etc.) will fill the pipe buffer and stall the robot mid-run – the worker has no timeout or fallback to recover.

*Evidence: `robot_worker.py` lines 63-155 start the client with `stderr=subprocess.PIPE`, but `_monitor_process` (lines 157-205) never drains that pipe until after the loop completes.*

**Fix recommendation:** Handle `stderr` exactly like `stdout` (merge them with `stderr=subprocess.STDOUT`, or start a second reader thread) so the buffer cannot fill up during a recording.

### 3. Local model execution ignores the configured checkpoint path
The default configuration populates `policy.path` with the full `.../checkpoints/last/pretrained_model` directory, but `_run_single_episode` only ever looks for `policy.base_path` and constructs `train_dir / task / ...` from it. With the defaults, `base_path` is missing, so local-mode runs always fail with "Model not found" even when the checkpoint directory exists.

*Evidence: `utils/execution_manager.py` lines 815-822 compute `checkpoint_path` from `policy.base_path` and never fall back to `policy.path`.*

**Fix recommendation:** If `policy.base_path` is absent, reuse the already configured `policy.path` (or split it into base/checkpoint parts). Otherwise the shipped `config.json` can never execute a policy in local mode.

## Suggested Next Steps
1. Drain or redirect all subprocess pipes in `RobotWorker` to prevent OS-level deadlocks.
2. Add stderr draining (or merge stdout/stderr) in `_monitor_process`.
3. Teach `_run_single_episode` to honour the `policy.path` setting as a fallback for the checkpoint directory.

Once these are addressed we can run another pass focusing on kiosk robustness (watchdogging the subprocesses, better readiness detection, etc.).
