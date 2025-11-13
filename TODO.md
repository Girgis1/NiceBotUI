# TODO

## High Priority
- [x] Windows support removed - project now Linux/Jetson only
- [x] Finalise the Jetson-first installation path: ensure `setup.sh` delegates cleanly to one Jetson-aware flow and filters out unsupported wheels (e.g., `opencv-python` on aarch64).

## Medium Priority
- [x] Unify camera backend selection by adopting the shared Jetson-aware helper module across `camera_hub`, `device_manager`, and safety tooling.
- [ ] Migrate policy/pipeline device resolution to use the shared hardware helper so GPU vs CPU selection stays consistent.

## Low Priority
- [x] Remove the Safety Camera / Hand Detection (YOLO) feature until a certified replacement is available.
