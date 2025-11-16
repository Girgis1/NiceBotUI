"""Model path discovery helpers used by dashboard and sequencer UI."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TRAIN_ROOT = ROOT / "outputs" / "train"


def _normalize_path(path_str: str) -> Path:
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path


def _iter_candidate_roots(policy_cfg: Dict) -> Iterable[Path]:
    base_path = policy_cfg.get("base_path")
    if base_path:
        yield _normalize_path(base_path)

    policy_path = policy_cfg.get("path")
    if policy_path:
        candidate = _normalize_path(policy_path)
        for parent in candidate.parents:
            yield parent
            # Stop once we bubble up past the repo root to avoid walking the filesystem
            if parent == ROOT or parent == parent.parent:
                break

    yield DEFAULT_TRAIN_ROOT


def _looks_like_task_dir(path: Path) -> bool:
    try:
        return path.is_dir() and (path / "checkpoints").is_dir()
    except OSError:
        return False


def list_model_task_dirs(config: Dict) -> List[Path]:
    """Return directories that contain model checkpoints.

    Handles both the new `policy.base_path` and legacy `policy.path` hints so that
    freshly cloned systems (with only a checkpoint path) can still enumerate
    available tasks.
    """

    policy_cfg = config.get("policy", {}) if isinstance(config, dict) else {}
    search_roots = list(_iter_candidate_roots(policy_cfg))

    tasks: List[Path] = []
    seen: set[str] = set()

    def _add_task(path: Path) -> None:
        key = path.name.lower()
        if key not in seen:
            tasks.append(path)
            seen.add(key)

    for root in search_roots:
        try:
            root = root.expanduser()
        except RuntimeError:
            continue

        if not root.exists():
            continue

        if _looks_like_task_dir(root):
            _add_task(root)
            # also include siblings so users can swap tasks quickly
            parent = root.parent
            if parent.exists():
                for sibling in parent.iterdir():
                    if _looks_like_task_dir(sibling):
                        _add_task(sibling)
            continue

        try:
            for item in root.iterdir():
                if _looks_like_task_dir(item):
                    _add_task(item)
        except OSError:
            continue

    tasks.sort(key=lambda p: p.name.lower())
    return tasks


def resolve_training_root(config: Dict) -> Path:
    """Resolve the base training directory where tasks live.

    Prefers a directory that actually contains model folders but gracefully
    falls back to the configured base path or `outputs/train`.
    """

    tasks = list_model_task_dirs(config)
    if tasks:
        return tasks[0].parent

    policy_cfg = config.get("policy", {}) if isinstance(config, dict) else {}
    for candidate in _iter_candidate_roots(policy_cfg):
        candidate = candidate.expanduser()
        if candidate.exists():
            return candidate

    DEFAULT_TRAIN_ROOT.mkdir(parents=True, exist_ok=True)
    return DEFAULT_TRAIN_ROOT


def build_checkpoint_path(config: Dict, task: str, checkpoint: str, *, filename: str = "pretrained_model") -> Path:
    """Return the full path to a model checkpoint."""

    root = resolve_training_root(config)
    task_dir = root / task
    return task_dir / "checkpoints" / checkpoint / filename
