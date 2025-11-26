"""Helpers for ACT-style dataset metadata and paths.

This is intentionally lightweight: lerobot handles the actual dataset
storage under ``~/.cache/huggingface/lerobot/local``. We keep a small
manifest in the repo so the Train tab can list runs, show progress, and
launch training jobs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pytz

ROOT = Path(__file__).resolve().parent.parent
ACT_DATASETS_ROOT = ROOT / "outputs" / "datasets" / "act"
TIMEZONE = pytz.timezone("Australia/Sydney")


def _now_iso() -> str:
    return datetime.now(TIMEZONE).isoformat()


def _sanitize_name(name: str) -> str:
    """Normalize a user-facing run name into a safe folder id."""
    cleaned = "".join(c for c in name.strip() if c.isalnum() or c in (" ", "_", "-"))
    cleaned = "_".join(cleaned.lower().split())
    return cleaned or "act_run"


@dataclass
class ActDatasetMeta:
    """Minimal manifest we persist per ACT dataset."""

    name: str
    dataset_id: str  # sanitized id, used for folder + repo_id suffix
    repo_id: str  # e.g. "local/act_pick_v2_20250115_101500"
    target_episodes: int
    episode_time_s: int
    arm_mode: str = "bimanual"  # "left", "right", "bimanual"
    resume: bool = True
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
    completed_episodes: int = 0
    trained: bool = False
    training_output_dir: Optional[str] = None

    @property
    def folder(self) -> Path:
        return ACT_DATASETS_ROOT / self.dataset_id

    @property
    def metadata_path(self) -> Path:
        return self.folder / "metadata.json"

    @property
    def hf_local_dir(self) -> Path:
        """Local lerobot cache directory for this dataset (mirrored via jetson_auto_sync)."""
        # For repo_id like "local/act_pick_v2_2025...", take the suffix after "local/"
        suffix = self.repo_id.split("/", 1)[1] if "/" in self.repo_id else self.repo_id
        return Path.home() / ".cache" / "huggingface" / "lerobot" / "local" / suffix

    def to_dict(self) -> Dict:
        return asdict(self)

    def save(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self.updated_at = _now_iso()
        if not self.created_at:
            self.created_at = self.updated_at
        with self.metadata_path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, dataset_id: str) -> Optional["ActDatasetMeta"]:
        path = ACT_DATASETS_ROOT / dataset_id / "metadata.json"
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None
        return cls(**data)


def ensure_dataset(
    run_name: str,
    target_episodes: int,
    episode_time_s: int,
    arm_mode: str,
    resume: bool,
    notes: str = "",
    existing_id: str | None = None,
) -> ActDatasetMeta:
    """Create or update metadata for a dataset.

    Args:
        run_name: User-facing run/model name.
        target_episodes: Desired number of episodes.
        episode_time_s: Episode length (seconds).
        arm_mode: "left", "right", or "bimanual".
        resume: Whether UI prefers resume semantics.
        notes: Free-form notes string.
        existing_id: Optional explicit dataset_id (for already-known runs).
    """
    ACT_DATASETS_ROOT.mkdir(parents=True, exist_ok=True)

    dataset_id = existing_id or _sanitize_name(run_name)
    meta = ActDatasetMeta.load(dataset_id)

    if meta is None:
        # New dataset: generate a stable repo_id using timestamp for uniqueness
        ts = datetime.now(TIMEZONE).strftime("%Y%m%d_%H%M%S")
        dataset_tag = f"act_{dataset_id}_{ts}"
        repo_id = f"local/{dataset_tag}"
        meta = ActDatasetMeta(
            name=run_name.strip() or dataset_tag,
            dataset_id=dataset_id,
            repo_id=repo_id,
            target_episodes=max(int(target_episodes), 1),
            episode_time_s=max(int(episode_time_s), 1),
            arm_mode=arm_mode,
            resume=resume,
            notes=notes,
            created_at=_now_iso(),
            updated_at=_now_iso(),
            completed_episodes=0,
        )
    else:
        # Update basic settings but keep progress/training flags
        meta.name = run_name.strip() or meta.name
        meta.target_episodes = max(int(target_episodes), 1)
        meta.episode_time_s = max(int(episode_time_s), 1)
        meta.arm_mode = arm_mode
        meta.resume = resume
        meta.notes = notes

    meta.save()
    return meta


def list_datasets() -> List[ActDatasetMeta]:
    """Return all known ACT datasets (sorted by most recently updated)."""
    if not ACT_DATASETS_ROOT.exists():
        return []

    metas: List[ActDatasetMeta] = []
    for entry in ACT_DATASETS_ROOT.iterdir():
        if not entry.is_dir():
            continue
        meta = ActDatasetMeta.load(entry.name)
        if meta:
            metas.append(meta)

    metas.sort(key=lambda m: m.updated_at or m.created_at, reverse=True)
    return metas


def update_completed_episodes(dataset_id: str, delta: int) -> Optional[ActDatasetMeta]:
    """Increment completed_episodes by delta and persist.

    Returns the updated metadata, or None if dataset cannot be loaded.
    """
    meta = ActDatasetMeta.load(dataset_id)
    if not meta:
        return None
    meta.completed_episodes = max(0, meta.completed_episodes + int(delta))
    meta.save()
    return meta


def mark_trained(dataset_id: str, output_dir: str) -> Optional[ActDatasetMeta]:
    """Mark a dataset as trained and record the output directory."""
    meta = ActDatasetMeta.load(dataset_id)
    if not meta:
        return None
    meta.trained = True
    meta.training_output_dir = output_dir
    meta.save()
    return meta


__all__ = [
    "ACT_DATASETS_ROOT",
    "ActDatasetMeta",
    "ensure_dataset",
    "list_datasets",
    "update_completed_episodes",
    "mark_trained",
]

