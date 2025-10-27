"""Runtime manager orchestrating per-camera vision pipelines."""

from __future__ import annotations

import threading
import time
from typing import Dict, List, Optional

from .base import VisionPipeline, VisionResult, np
from .config import load_vision_profile
from .events import VisionEventBus
from .registry import create_pipeline
from .training import record_training_sample

try:
    from utils.camera_hub import CameraStreamHub
except Exception:  # pragma: no cover - runtime guarded
    CameraStreamHub = None  # type: ignore


class VisionPipelineManager:
    """Manage pipeline execution for all configured cameras."""

    def __init__(self, app_config: Dict, profile: Optional[Dict] = None, camera_hub: Optional[CameraStreamHub] = None):
        self._app_config = app_config
        self._profile = profile or load_vision_profile(camera_names=list(app_config.get("cameras", {}).keys()))
        self._camera_hub = camera_hub or (CameraStreamHub.instance(app_config) if CameraStreamHub else None)
        self._threads: Dict[str, threading.Thread] = {}
        self._stops: Dict[str, threading.Event] = {}
        self._pipelines: Dict[str, List[VisionPipeline]] = {}
        self._bus = VisionEventBus.instance()
        self._lock = threading.Lock()
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._restart_threads()

    def stop(self) -> None:
        self._running = False
        with self._lock:
            for stop_event in self._stops.values():
                stop_event.set()
            for thread in self._threads.values():
                if thread.is_alive():
                    thread.join(timeout=1.5)
            self._threads.clear()
            self._stops.clear()
            self._pipelines.clear()

    # ------------------------------------------------------------------
    # Configuration management

    def update_profile(self, profile: Dict) -> None:
        with self._lock:
            self._profile = profile
        self._restart_threads()
        self._bus.handDetectionChanged.emit("*", False, 0.0)

    def _restart_threads(self) -> None:
        if not self._running:
            return
        self.stop()
        self._running = True
        cameras = self._profile.get("cameras", {})
        for camera_name, camera_cfg in cameras.items():
            pipelines = self._build_pipelines(camera_name, camera_cfg.get("pipelines", []))
            if not pipelines:
                continue
            stop_event = threading.Event()
            thread = threading.Thread(
                target=self._camera_loop,
                name=f"vision_{camera_name}",
                args=(camera_name, pipelines, stop_event),
                daemon=True,
            )
            self._stops[camera_name] = stop_event
            self._threads[camera_name] = thread
            self._pipelines[camera_name] = pipelines
            thread.start()

    def _build_pipelines(self, camera_name: str, configs: List[Dict]) -> List[VisionPipeline]:
        pipelines: List[VisionPipeline] = []
        for config in configs[: int(self._profile.get("max_pipelines_per_camera", 3))]:
            if not isinstance(config, dict) or not config.get("enabled", True):
                continue
            pipeline_type = config.get("type")
            pipeline_id = config.get("id") or f"{camera_name}_{pipeline_type}_{len(pipelines)}"
            try:
                pipeline = create_pipeline(pipeline_type, pipeline_id, camera_name, config)
            except ValueError:
                continue
            pipelines.append(pipeline)
        return pipelines

    # ------------------------------------------------------------------
    # Processing loops

    def _camera_loop(self, camera_name: str, pipelines: List[VisionPipeline], stop_event: threading.Event) -> None:
        hub = self._camera_hub
        if hub is None:
            return
        interval = 0.2
        while self._running and not stop_event.is_set():
            frame = hub.get_frame(camera_name, preview=False) if hub else None
            if frame is None:
                time.sleep(0.5)
                continue
            timestamp = time.time()
            min_interval = 0.2
            for pipeline in pipelines:
                try:
                    result = pipeline.process(frame.copy() if np is not None else frame, timestamp)
                except Exception as exc:  # pragma: no cover - safety net
                    print(f"[VISION][ERROR] Pipeline {pipeline.pipeline_id} crashed: {exc}")
                    continue
                self._handle_result(camera_name, frame, result)
                freq = getattr(pipeline, "config", {}).get("frequency_hz", 5.0)
                try:
                    interval_candidate = 1.0 / max(0.5, float(freq))
                except Exception:
                    interval_candidate = 0.2
                min_interval = min(min_interval, interval_candidate)
            time.sleep(max(0.05, min_interval))

    def _handle_result(self, camera_name: str, frame: "np.ndarray", result: VisionResult) -> None:
        if result.metadata.get("dashboard_indicator"):
            self._bus.handDetectionChanged.emit(camera_name, result.detected, result.confidence)
        self._bus.pipelineResult.emit(camera_name, result.pipeline_id, result.metadata)
        if result.metadata.get("record_training"):
            try:
                record_training_sample(camera_name, frame, result)
            except Exception as exc:  # pragma: no cover - keep runtime alive
                print(f"[VISION][WARN] Failed to persist training sample: {exc}")

    # ------------------------------------------------------------------
    # Testing helpers

    def process_single_frame(self, camera_name: str, frame: "np.ndarray") -> List[VisionResult]:
        """Process a single frame synchronously. Useful for tests."""

        configs = self._profile.get("cameras", {}).get(camera_name, {}).get("pipelines", [])
        pipelines = self._build_pipelines(camera_name, configs)
        results: List[VisionResult] = []
        timestamp = time.time()
        for pipeline in pipelines:
            result = pipeline.process(frame, timestamp)
            results.append(result)
        return results


__all__ = ["VisionPipelineManager"]
