# Motor Manager Architecture Plan

Goal: single-owner motor access per arm, with resilient I/O, shared telemetry, and fast emergency stop — without breaking existing call sites.

## Guiding Principles
- Keep MotorController API intact; add a shared manager layer above it.
- One bus owner per arm/port; all reads/writes go through that owner.
- Diagnostics consumes telemetry; it never opens the bus during runs.
- Emergency stop and torque-off available per arm (and all), even if UI is busy.
- Roll out incrementally; avoid regressions in record/sequencer/teleop.

## Components & Steps

### 1) Per-Arm MotorManager
- **Create** `utils/motor_manager.py` with a singleton registry keyed by arm index/port.
- Holds a single connected MotorController (resilient-wrapped by default), a lock, and a worker thread for telemetry.
- Public API:
  - `get_arm(arm_index) -> MotorHandle` (or by port)
  - `set_positions(positions, velocity, wait=True)`
  - `read_positions()`
  - `emergency_stop()` / `torque_off()`
  - `subscribe(callback)` for telemetry (positions, voltage, temp)
- Internals:
  - Serialize writes with a lock; reads reuse the same bus.
  - Telemetry loop at 5–10 Hz pushing last-known positions.
  - Resilience stays inside MotorController/ResilientMotorBus.

**Watch out for:**
- Deadlocks if callbacks call back into manager; use non-reentrant locks and document it.
- Clean shutdown to release the port.

### 2) Bus Lock Guard (fast fail)
- Add a simple process-wide lock in `MotorController.connect` or in the manager to prevent multiple opens on the same port.
- Clear, single-line log when a port is already owned.

### 3) Diagnostics Tab Integration
- Change `tabs/diagnostics_tab.py` to:
  - Subscribe to telemetry from MotorManager instead of opening the bus when a run is active.
  - Only connect its own controller when idle/no active run (fallback).
- Deduplicate “Failed to read” spam; rely on resilience telemetry instead.

### 4) ExecutionWorker Integration
- In `utils/execution_manager.py`, acquire the per-arm manager instead of constructing a new MotorController.
- Swap calls to `motor_controller.set_positions/read_positions_from_bus` to manager equivalents (same signatures to minimize code diff).
- Ensure `keep_connection=True` semantics map to “reuse the same manager-held bus”.

### 5) Teleop Path
- Update teleop launcher/worker to request the manager-held controller for the target arm(s).
- Ensure bimanual teleop maps left/right to separate managers.

### 6) Emergency Stop Path
- Add `motor_manager.emergency_stop_all()` and per-arm stop; expose a callable the UI can trigger even if a run is mid-flight.
- Consider a tiny helper script/CLI for out-of-process stop (optional).

### 7) Logging & Rate Limiting
- In `utils/log_messages.py`, translate key resilience events once per dropout/recovery (avoid per-attempt spam).
- Optionally add counters in the manager (dropouts, recoveries, last error) and surface them in dashboard.

### 8) Rollout & Compatibility
- Keep `MotorController` import points intact; introduce a helper `get_motor_handle(arm_index)` so call sites change minimally.
- Ship with feature flag (config) to toggle manager use; default ON once validated.
- Fallback: if manager init fails, log and revert to direct MotorController (for safety during rollout).

### 9) Testing Checklist
- Single-arm sequence playback: no “Port is in use” spam; dashboard shows resilience events once per dropout.
- Bimanual teleop: both arms move; no contention; emergency stop hits both.
- Diagnostics while running: stays responsive, shows telemetry, does not open a new bus.
- Kill motor process mid-run: UI stays up; bus released; restart works.

### 10) Deployment Notes
- Sync to Jetson, ensure only one app instance runs (SingleInstanceGuard already in place).
- Powered USB hub still recommended; this design prevents software contention but not power sag.

---
Status: Plan drafted. Next steps: implement per-arm manager, wire ExecutionWorker/Diagnostics to it, add lock and log translations, then validate on Jetson.

Implementation status:
- [x] MotorManager/MotorHandle added with single-owner bus and telemetry cache.
- [x] ExecutionWorker now uses the shared handle per arm.
- [x] Diagnostics reads shared telemetry instead of opening the bus.
- [x] Port guard added to MotorController; dashboard translations updated for resilient logs.
- [x] Teleop path uses shared motor handles to avoid contention.
- [ ] Emergency-stop helper wiring for UI (pending).
- [ ] Rate limiting/tidy logging (pending).
