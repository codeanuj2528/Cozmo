"""A plan and its run manifest should say what was captured, and on what."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np
from PIL import Image

from cozmo.io.photo import PhotoCapture
from cozmo.pipeline.lidar import _hash_input


def _jpeg(path: Path, model: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exif = Image.Exif()
    if model is not None:
        exif[0x0110] = model
    Image.fromarray(np.full((48, 64, 3), 128, dtype=np.uint8)).save(path, format="JPEG", exif=exif)


def test_photo_device_model_is_read_from_the_photographs(tmp_path):
    _jpeg(tmp_path / "hall" / "a.jpg", "iPhone 17 Pro")
    _jpeg(tmp_path / "hall" / "b.jpg", "iPhone 17 Pro")
    assert PhotoCapture(tmp_path).meta.device_model == "iPhone 17 Pro"


def test_photo_device_model_without_exif_is_unknown_rather_than_a_guess(tmp_path):
    _jpeg(tmp_path / "hall" / "a.jpg", None)
    assert PhotoCapture(tmp_path).meta.device_model == "unknown"


def test_input_hash_follows_a_symlinked_folder(tmp_path):
    real = tmp_path / "real" / "bathroom"
    _jpeg(real / "a.jpg", None)
    run = tmp_path / "run"
    run.mkdir()
    os.symlink(real, run / "bathroom")
    assert _hash_input(run) != hashlib.sha256().hexdigest()[:16]
    assert _hash_input(run) == _hash_input(tmp_path / "real")
