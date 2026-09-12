"""Tests for video tier capture loading and blur filtering."""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest

from cozmo.io.video import DEFAULT_BLUR_THRESHOLD, VideoCapture


def test_video_capture_initialization(tmp_path: Path):
    # Test video capture error on missing file
    fake_video = tmp_path / "non_existent.mp4"
    with pytest.raises((FileNotFoundError, ValueError)):
        VideoCapture(fake_video)
