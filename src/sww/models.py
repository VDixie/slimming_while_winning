"""Locate and download MediaPipe model files.

This is the only network access in the app, and it only happens when you run
``sww download-models`` explicitly. Normal runs are fully offline.
"""

from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path

DEFAULT_MODELS_DIR = Path("models")

_BASE = "https://storage.googleapis.com/mediapipe-models"
POSE_MODEL_URLS: dict[str, str] = {
    variant: f"{_BASE}/pose_landmarker/pose_landmarker_{variant}/float16/latest/"
    f"pose_landmarker_{variant}.task"
    for variant in ("lite", "full", "heavy")
}


def pose_model_path(variant: str, models_dir: Path = DEFAULT_MODELS_DIR) -> Path:
    """Where the pose model for ``variant`` lives on disk."""
    if variant not in POSE_MODEL_URLS:
        raise ValueError(f"unknown pose model {variant!r}; choose from {sorted(POSE_MODEL_URLS)}")
    return models_dir / f"pose_landmarker_{variant}.task"


def download_pose_model(
    variant: str, models_dir: Path = DEFAULT_MODELS_DIR, force: bool = False
) -> Path:
    """Download one pose model if it isn't there yet. Returns its path."""
    dest = pose_model_path(variant, models_dir)
    if dest.is_file() and not force:
        return dest
    models_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(POSE_MODEL_URLS[variant], timeout=60) as resp, tmp.open("wb") as f:
        shutil.copyfileobj(resp, f)
    tmp.replace(dest)  # atomic: never leave a half-written model behind
    return dest
