import re

from utils import camera_support as cs


def test_looks_like_gstreamer_pipeline_detection():
    assert cs.looks_like_gstreamer_pipeline("nvarguscamerasrc ! video/x-raw ! appsink")
    assert cs.looks_like_gstreamer_pipeline("rtsp://example.com/stream")
    assert not cs.looks_like_gstreamer_pipeline("/dev/video0")


def test_prepare_camera_source_digit_index():
    source, backend = cs.prepare_camera_source({"index_or_path": "1"}, 640, 480, 30)
    assert source == 1
    assert backend == "v4l2"


def test_prepare_camera_source_csi_pipeline():
    cfg = {"index_or_path": "csi://2", "width": 1280, "height": 720, "fps": 30}
    source, backend = cs.prepare_camera_source(cfg, 1280, 720, 30)
    assert "nvarguscamerasrc" in source
    assert re.search(r"sensor-id=2", source)
    assert backend == "gstreamer"
