"""Tests for neural model loader wrappers (ZoeDepth, Grounding DINO, SAM 2)."""

from __future__ import annotations

from pathlib import Path
import numpy as np

from cozmo.models import (
    load_zoedepth_model,
    load_grounding_dino_model,
    load_sam2_model,
    estimate_neural_metric_depth,
    detect_open_vocabulary,
)


def test_model_availability_checks():
    avail, msg = load_zoedepth_model(Path("non_existent_weights"))
    assert not avail
    assert "ZoeDepth weights not found" in msg

    avail_dino, msg_dino = load_grounding_dino_model(Path("non_existent_weights"))
    assert not avail_dino
    assert "Grounding DINO weights not found" in msg_dino

    avail_sam, msg_sam = load_sam2_model(Path("non_existent_weights"))
    assert not avail_sam
    assert "SAM 2 weights not found" in msg_sam


def test_estimate_neural_metric_depth_fallback():
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    depth = estimate_neural_metric_depth(dummy_img, weights_dir=Path("non_existent_weights"))
    assert depth is None


def test_detect_open_vocabulary_fallback():
    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    dets = detect_open_vocabulary(dummy_img, prompts=["door"], weights_dir=Path("non_existent_weights"))
    assert dets == []
