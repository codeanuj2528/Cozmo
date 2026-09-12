"""Tests for the reconstruction backbone, scale recovery, and frame selection."""

from pathlib import Path
import numpy as np
import pytest

from cozmo.recon.backbone import DepthBackboneAdapter, estimate_depth_monocular
from cozmo.recon.scale import MetricScaleEstimator, ScaleStrategy
from cozmo.recon.frames import FrameQualitySelector


def test_depth_backbone_adapter():
    """Test depth backbone interface and mock inference."""
    adapter = DepthBackboneAdapter(model_name="depth_anything_v2")
    img = np.random.randint(0, 255, size=(100, 100, 3), dtype=np.uint8)
    depth = adapter.estimate_depth(img)
    assert depth.shape == (100, 100)
    assert depth.dtype == np.float32
    assert np.all(depth >= 0)


def test_depth_monocular_convenience():
    """Test convenience wrapper function."""
    img = np.random.randint(0, 255, size=(120, 160, 3), dtype=np.uint8)
    depth = estimate_depth_monocular(img)
    assert depth.shape == (120, 160)


def test_scale_recovery_strategies():
    """Test scale recovery under different strategy configurations."""
    estimator = MetricScaleEstimator(primary_strategy=ScaleStrategy.STRUCTURAL_PRIOR)
    img = np.random.randint(0, 255, size=(200, 200, 3), dtype=np.uint8)
    depth_rel = np.ones((200, 200), dtype=np.float32)

    result = estimator.recover_scale(rel_depth=depth_rel, image=img)
    assert result.scale_factor > 0.0
    assert 0.0 <= result.confidence <= 1.0
    assert result.metric_depth.shape == depth_rel.shape


def test_frame_quality_selector(temp_dir):
    """Test quality frame filtering and blur detection."""
    from PIL import Image

    frame_dir = temp_dir / "frames"
    frame_dir.mkdir()

    # Create sharp and blurry images
    sharp_path = frame_dir / "sharp.png"
    blurry_path = frame_dir / "blurry.png"

    sharp = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    blurry = np.full((100, 100, 3), 128, dtype=np.uint8)  # zero variance

    Image.fromarray(sharp).save(sharp_path)
    Image.fromarray(blurry).save(blurry_path)

    selector = FrameQualitySelector(blur_threshold=10.0)
    selected = selector.filter_frames([sharp_path, blurry_path])

    # Blurry image should be rejected
    assert sharp_path in selected
    assert blurry_path not in selected
