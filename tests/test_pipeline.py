"""Tests for end-to-end pipeline execution and configuration overrides."""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest

from cozmo.config import PipelineConfig
from cozmo.io import load_capture
from cozmo.pipeline import reconstruct


def test_pipeline_reconstruct_real_sample():
    sample_path = Path("data/raw/1a8384c3f6")
    if not sample_path.exists():
        sample_path = Path("../data/raw/1a8384c3f6")
    if not sample_path.exists():
        pytest.skip("Sample raw capture not present")

    source = load_capture(sample_path)
    config = PipelineConfig(max_keyframes=20, voxel_m=0.10)
    result = reconstruct(source, config=config)

    assert result.plan.capture_id == "1a8384c3f6"
    assert len(result.plan.rooms) >= 1
    assert result.plan.total_floor_area.value > 0.0
