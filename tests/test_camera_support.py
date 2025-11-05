from utils.camera_support import (
    build_jetson_csi_pipeline,
    choose_backend,
    coerce_backend,
    looks_like_gstreamer_pipeline,
    prepare_camera_source,
    resolve_jetson_csi_source,
)


def test_coerce_backend_normalises_values():
    assert coerce_backend(" GStreamer ") == "gstreamer"
    assert coerce_backend("V4L2") == "v4l2"
    assert coerce_backend("auto") is None
    assert coerce_backend(None) is None


def test_looks_like_gstreamer_pipeline():
    assert looks_like_gstreamer_pipeline("nvarguscamerasrc ! appsink")
    assert looks_like_gstreamer_pipeline("rtsp://camera/stream")
    assert not looks_like_gstreamer_pipeline(0)
    assert not looks_like_gstreamer_pipeline("  ")


def test_build_csi_pipeline_contains_expected_segments():
    pipeline = build_jetson_csi_pipeline(sensor_id=1, width=1920, height=1080, fps=60)
    assert "nvarguscamerasrc sensor-id=1" in pipeline
    assert "width=1920" in pipeline
    assert "height=1080" in pipeline
    assert "framerate=60/1" in pipeline


def test_resolve_jetson_csi_source_converts_string():
    source, backend = resolve_jetson_csi_source("csi://0", 1280, 720, 30)
    assert "nvarguscamerasrc" in source
    assert backend == "gstreamer"

    unchanged_source, backend_none = resolve_jetson_csi_source(0, 640, 480, 30)
    assert unchanged_source == 0
    assert backend_none is None


def test_choose_backend_prefers_pipeline_detection():
    assert choose_backend(None, "nvarguscamerasrc ! appsink") == "gstreamer"
    assert choose_backend(None, "0") == "v4l2"
    assert choose_backend("ffmpeg", "video.mp4") == "ffmpeg"


def test_prepare_camera_source_handles_defaults():
    cfg = {"index_or_path": "1"}
    source, backend = prepare_camera_source(cfg, width=640, height=480, fps=30)
    assert source == 1
    assert backend == "v4l2"

    cfg_pipeline = {
        "gstreamer_pipeline": "nvarguscamerasrc ! appsink",
        "backend": "gst",
    }
    source, backend = prepare_camera_source(cfg_pipeline, width=640, height=480, fps=30)
    assert "nvarguscamerasrc" in source
    assert backend == "gstreamer"
