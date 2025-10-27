"""Utilities for managing downloadable vision models and metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional


@dataclass
class VisionModelInfo:
    """Description of a downloadable vision model."""

    task: str
    model_id: str
    label: str
    description: str
    filename: str
    url: Optional[str]
    size_mb: float
    default_confidence: float
    extras: Dict[str, object] = field(default_factory=dict)

    @property
    def supports_masks(self) -> bool:
        return bool(self.extras.get("supports_masks", False))

    @property
    def default_threshold(self) -> float:
        value = self.extras.get("default_threshold")
        if isinstance(value, (int, float)):
            return float(value)
        return 0.5

    @property
    def default_classes(self) -> Optional[Iterable[int]]:
        classes = self.extras.get("classes")
        if classes is None:
            return None
        if isinstance(classes, (list, tuple, set)):
            return list(int(c) for c in classes)
        return None


_CATALOG: Dict[str, List[VisionModelInfo]] = {
    "hand_detection": [
        VisionModelInfo(
            task="hand_detection",
            model_id="yolov8n-person",
            label="YOLOv8n Person Detector (fast)",
            description="Fast COCO model ideal for background person/hand guard zones.",
            filename="yolov8n.pt",
            url="https://github.com/ultralytics/assets/releases/download/v8.1.0/yolov8n.pt",
            size_mb=12.4,
            default_confidence=0.35,
            extras={"classes": [0]},
        ),
        VisionModelInfo(
            task="hand_detection",
            model_id="yolov8s-person",
            label="YOLOv8s Person Detector (balanced)",
            description="Balanced detector with higher recall for complex hand interactions.",
            filename="yolov8s.pt",
            url="https://github.com/ultralytics/assets/releases/download/v8.1.0/yolov8s.pt",
            size_mb=22.5,
            default_confidence=0.4,
            extras={"classes": [0]},
        ),
    ],
    "product_detection": [
        VisionModelInfo(
            task="product_detection",
            model_id="yolov8n-seg",
            label="YOLOv8n Segmentation (light)",
            description="Segmenter for masking bottles/cosmetics with minimal compute load.",
            filename="yolov8n-seg.pt",
            url="https://github.com/ultralytics/assets/releases/download/v8.1.0/yolov8n-seg.pt",
            size_mb=25.5,
            default_confidence=0.35,
            extras={"supports_masks": True},
        ),
        VisionModelInfo(
            task="product_detection",
            model_id="yolov8s-seg",
            label="YOLOv8s Segmentation (high fidelity)",
            description="Higher fidelity segmentation for beauty-product picking accuracy.",
            filename="yolov8s-seg.pt",
            url="https://github.com/ultralytics/assets/releases/download/v8.1.0/yolov8s-seg.pt",
            size_mb=47.8,
            default_confidence=0.33,
            extras={"supports_masks": True},
        ),
    ],
    "defect_detection": [
        VisionModelInfo(
            task="defect_detection",
            model_id="yolov8n-cls",
            label="YOLOv8n Surface Classifier",
            description="Classifier tuned for surface anomalies – great starting baseline.",
            filename="yolov8n-cls.pt",
            url="https://github.com/ultralytics/assets/releases/download/v8.1.0/yolov8n-cls.pt",
            size_mb=11.2,
            default_confidence=0.5,
            extras={"default_threshold": 0.55},
        ),
        VisionModelInfo(
            task="defect_detection",
            model_id="yolov8s-cls",
            label="YOLOv8s Surface Classifier",
            description="More robust classifier for intricate defect signals.",
            filename="yolov8s-cls.pt",
            url="https://github.com/ultralytics/assets/releases/download/v8.1.0/yolov8s-cls.pt",
            size_mb=21.9,
            default_confidence=0.5,
            extras={"default_threshold": 0.6},
        ),
    ],
    "label_reading": [
        VisionModelInfo(
            task="label_reading",
            model_id="yolov8n-ocr",
            label="YOLOv8n Text Detector",
            description="Lightweight detector for label text regions (pairs well with OCR).",
            filename="yolov8n-obb.pt",
            url="https://github.com/ultralytics/assets/releases/download/v8.1.0/yolov8n-obb.pt",
            size_mb=14.8,
            default_confidence=0.32,
            extras={"supports_masks": False},
        ),
        VisionModelInfo(
            task="label_reading",
            model_id="paddle-ocr-lite",
            label="PaddleOCR PP-OCRv4 Lite",
            description="High accuracy OCR backbone for crisp or angled labels.",
            filename="ppocrv4lite.onnx",
            url="https://paddleocr.bj.bcebos.com/ppocr/mobile/latest/rec/en_PP-OCRv4_rec_infer.onnx",
            size_mb=10.6,
            default_confidence=0.3,
        ),
    ],
}


def get_tasks() -> List[str]:
    """Return the list of supported vision tasks."""

    return list(_CATALOG.keys())


def get_models_for_task(task: str) -> List[VisionModelInfo]:
    """Retrieve available models for a given task."""

    return list(_CATALOG.get(task, []))


def get_model_info(task: str, model_id: Optional[str]) -> Optional[VisionModelInfo]:
    """Return model info for the provided identifier."""

    if model_id is None:
        return None
    for info in get_models_for_task(task):
        if info.model_id == model_id:
            return info
    return None


def get_models_root(base_dir: Optional[Path] = None) -> Path:
    """Return the directory that stores downloaded models."""

    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent
    root = base_dir / "runtime" / "models"
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_model_path(model: VisionModelInfo, base_dir: Optional[Path] = None) -> Path:
    """Compute the on-disk path for a model."""

    return get_models_root(base_dir) / model.filename


def download_model(
    model: VisionModelInfo,
    base_dir: Optional[Path] = None,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> Path:
    """Ensure a model is present locally, downloading it if required."""

    destination = resolve_model_path(model, base_dir)
    if destination.exists():
        if progress_callback:
            progress_callback(100)
        return destination

    if not model.url:
        raise RuntimeError(f"Model '{model.model_id}' does not define a download URL.")

    tmp_path = destination.with_suffix(destination.suffix + ".part")
    tmp_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        try:
            import requests  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "requests package is required to download models. Install with 'pip install requests'."
            ) from exc

        with requests.get(model.url, stream=True, timeout=90) as response:  # type: ignore
            response.raise_for_status()
            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0

            with open(tmp_path, "wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total:
                        progress_callback(min(100, int(downloaded * 100 / total)))

        tmp_path.replace(destination)

        if progress_callback:
            progress_callback(100)
        return destination

    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def format_size(megabytes: float) -> str:
    """Return a user-friendly size string."""

    if megabytes >= 1024:
        return f"{megabytes / 1024:.1f} GB"
    return f"{megabytes:.1f} MB"

