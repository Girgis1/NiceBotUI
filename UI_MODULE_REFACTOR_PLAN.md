# UI Modularization Refactor Plan

This document outlines TODOs for decomposing the largest UI and execution modules into maintainable packages **without changing the existing UI layout or behaviors**. The plan favors incremental extraction into helper modules and widgets so regressions can be caught quickly.

## Guiding Principles
- Preserve all current widgets, signals, and configuration flows—refactors should be strictly structural.
- Keep public APIs stable at first. Introduce adapters where necessary so tabs continue to import the same names.
- Add unit or smoke coverage where practical before moving logic, so behavior is locked down prior to extraction.
- Favor packages (folders with `__init__.py`) for each complex tab to isolate related helpers.
- Remove `sys.path` mutations during the reorganization; rely on proper package-relative imports.

---

## tabs/settings_tab.py
**Goal:** Split the monolithic tab into cohesive submodules while preserving the overall widget hierarchy.

- [ ] Create a `tabs/settings/` package to host extracted helpers. Export `SettingsTab` via `tabs/settings/__init__.py` to keep imports stable.
- [ ] Extract camera discovery/preview utilities into `camera_panel.py`. Move all OpenCV/Numpy usage and `CameraStreamHub` plumbing here.
- [ ] Move multi-arm configuration widgets and mode selectors into `multi_arm.py`; keep only high-level orchestration inside `SettingsTab`.
- [ ] Pull diagnostics helpers (status circles, simulated tests) into `diagnostics_panel.py`, relying on signals to communicate back to the main tab.
- [ ] Introduce a lightweight `data_access.py` module for loading/saving config JSON and ensuring compatibility helpers.
- [ ] After extraction, thin `SettingsTab` to: build the layout from new widgets, wire signals, and perform validation.
- [ ] Add regression tests (Qt bot or headless) for critical flows: config save, mode switch, diagnostics trigger.

## tabs/dashboard_tab.py
**Goal:** Decompose runtime controls, camera orchestration, and logging.

- [ ] Create `tabs/dashboard/` package exporting `DashboardTab`.
- [ ] Extract camera management (preview widgets, capture threads) into `camera_controller.py` with a clear interface for start/stop/status.
- [ ] Move run-selector and worker thread wiring into `run_control.py`, isolating command dispatch and status updates.
- [ ] Relocate log/history management into `log_panel.py`, including UI elements for filtering and persistence.
- [ ] Consolidate helper functions currently defined inline into a `services.py` module (e.g., path handling, file I/O, data transforms).
- [ ] Ensure the tab class only coordinates the subcomponents and maintains UI layout via composition.

## tabs/record_tab.py
**Goal:** Separate playback state, transport controls, and serialization.

- [ ] Create `tabs/record/` package exporting `RecordTab`.
- [ ] Extract the transport toolbar (play/pause/step) into `transport_controls.py`, exposing Qt signals for actions.
- [ ] Move table models, schema validation, and file serialization into `record_store.py`.
- [ ] Pull inter-tab coordination (refresh hooks, cross-tab signals) into `tab_bridge.py` so `RecordTab` no longer manages external dependencies directly.
- [ ] Introduce unit tests for serialization round-trips and playback state transitions.

## utils/execution_manager.py
**Goal:** Introduce strategy objects for each execution mode and isolate safety utilities.

- [ ] Add `utils/execution/` package to hold new strategy classes.
- [ ] Implement separate strategy modules (`positions_strategy.py`, `live_strategy.py`, `composite_strategy.py`, `sequence_strategy.py`) encapsulating the mode-specific loops.
- [ ] Extract shared safety utilities (E-stop, guard conditions) into `safety.py`.
- [ ] Introduce an `ExecutionContext` data class for shared runtime state (queues, status flags) to reduce parameter passing.
- [ ] Refactor `ExecutionManager` to delegate to the strategies and maintain thread lifecycle only.
- [ ] Backfill tests mocking the strategies to verify thread start/stop and error propagation remain intact.

## vision_ui/designer.py
**Goal:** Factor the dialog into modular widgets and backend services.

- [ ] Create `vision_ui/designer/` package exporting `VisionDesignerDialog` for compatibility.
- [ ] Move preset persistence and file I/O into `presets.py`.
- [ ] Extract camera probing/discovery (including Windows-specific logic) into `camera_backends.py`, abstracting OpenCV/DirectShow handling.
- [ ] Relocate polygon editing and ROI tools into `roi_editor.py`, offering reusable widgets shared with other dialogs if needed.
- [ ] Pull standalone launch helpers and CLI entrypoints into `__main__.py` or `launcher.py`.
- [ ] Ensure `designer.py` only constructs the dialog using the new helpers and wires signals to maintain layout.

## vision_triggers/daemon.py
**Goal:** Separate IPC, detector lifecycle, and CLI concerns.

- [ ] Create `vision_triggers/daemon/` package.
- [ ] Move IPC/socket server setup into `ipc.py` with a clean API for starting/stopping listeners.
- [ ] Extract detector lifecycle and watchdog logic into `detector_runner.py`.
- [ ] Relocate CLI/entrypoint parsing into `cli.py`, keeping `__main__` thin.
- [ ] Add integration tests that exercise the daemon startup/shutdown sequence using mocks.

## app.py
**Goal:** Prevent further bloat in the main entrypoint.

- [ ] Extract argument parsing and logging setup into `app/bootstrap.py`.
- [ ] Move palette/theme configuration into `app/theme.py`.
- [ ] Encapsulate single-instance locking into `app/instance_guard.py`.
- [ ] Leave `app.py` responsible for high-level startup only: parse args, init Qt app, create `MainWindow`, and exec.

## Cross-cutting Cleanup
- [ ] Replace ad-hoc `sys.path` mutations across tabs with package-relative imports once packages are in place.
- [ ] Update `__init__.py` files to re-export legacy names, minimizing immediate call-site changes.
- [ ] Ensure documentation (`README`, setup guides) reflects any new package paths for standalone tools.
