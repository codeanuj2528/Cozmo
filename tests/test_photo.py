"""Tests for photo tier capture loading and per-room folder ingestion."""

from __future__ import annotations

from pathlib import Path
import cv2
import numpy as np
import pytest

from cozmo.io.photo import PhotoCapture
from cozmo.schema import Tier


def test_photo_capture_loading(tmp_path: Path):
    room1 = tmp_path / "room_01"
    room1.mkdir()

    img = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.imwrite(str(room1 / "img1.jpg"), img)
    cv2.imwrite(str(room1 / "img2.jpg"), img)

    cap = PhotoCapture(tmp_path, capture_id="test_photo")
    assert cap.meta.tier == Tier.PHOTO
    assert cap.meta.frame_count == 2

    frames = list(cap.frames())
    assert len(frames) == 2
    assert frames[0].rgb_size == (100, 100)
