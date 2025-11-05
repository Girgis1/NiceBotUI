# Safety System Status

## Current State (Jetson-Oriented Build)

The previous computer-vision based **hand safety monitor** has been **fully removed** from this release to prioritise determinism and stability on the NVIDIA Jetson Orin Nano. No YOLO/MediaPipe models are loaded, there is no background safety thread, and the Settings UI no longer exposes any hand-detection controls.

Only the following safety features remain active in software:

- Configurable joint soft-limits (from `config.json`)
- Motor temperature monitoring (optional)
- Torque spike monitoring (optional)

All other safety enforcement must come from external hardware (certified e-stop circuits, guards, light curtains, etc.) and operator procedures.

## Operator Guidance

- Maintain a **physical emergency-stop** inline with the robot power path.
- Keep the workcell guarded according to your site’s safety assessment.
- Treat the software as *non-safety-rated*; it should never be your only protection layer.

## Why It Was Removed

1. **Reliability** – The prior implementation depended on optional Python wheels (ultralytics, mediapipe) that are fragile on JetPack and could fail silently.
2. **Resource Contention** – Continuous vision inference competed with the robot stack for GPU and camera access, causing jitter.
3. **Safety Integrity** – Without deterministic performance guarantees, we could not justify retaining the feature in an industrial deployment.

## Future Work

- If a vision-based safety layer is reintroduced it will target a separate MCU/PLC or fail-safe compute path with certified components.
- Until then, any new safety functionality should focus on leveraging reliable sensors (hardware light curtains, torque sensing, external vision systems) that integrate with the industrial e-stop chain.
