"""Reconstruction backbone, scale recovery and frame selection.

These test the API that exists. An earlier version of this file imported
`MetricScaleEstimator` and `ScaleStrategy`, which are not defined anywhere in the package,
so the whole suite failed at collection and every other test in the repository stopped
running with it. A test that names something that does not exist is worse than no test: it
takes the rest of the suite down with it, and the suite is what would otherwise have caught
the broken CLI.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cozmo.recon.backbone import DepthBackbone, FallbackBackbone, get_backbone
from cozmo.recon.frames import select_diverse_frames


def test_backbone_resolves_without_weights(tmp_path: Path):
    """With no weights on disk the backbone still resolves, and says what it is.

    The pipeline must run cold on a machine that has never downloaded a model, because the
    walk-in test is a cold run. What it must not do is pretend the fallback is a learned
    depth model.
    """
    backbone = get_backbone(tmp_path)
    assert isinstance(backbone, DepthBackbone)
    assert backbone.name == "fallback", "with no weights present the fallback must be selected, and named"
    assert backbone.is_metric() is False, "the fallback is not a metric depth model and must not claim to be"


def test_fallback_backbone_returns_usable_depth():
    image = np.random.default_rng(0).integers(0, 255, (120, 160, 3), dtype=np.uint8)
    depth = FallbackBackbone().estimate(image)
    assert depth.shape == (120, 160)
    assert np.isfinite(depth).all()
    assert (depth > 0).all()


def test_frame_selection_prefers_sharp_and_diverse():
    """A blurred duplicate of a sharp frame should not be selected over a new viewpoint."""
    rng = np.random.default_rng(1)
    sharp = rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)
    blurred = np.full((64, 64, 3), 128, dtype=np.uint8)
    other = rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)

    picked = select_diverse_frames([sharp, blurred, other], max_frames=2)
    assert len(picked) == 2
    assert 1 not in picked, "the flat, blurred frame should not survive selection"


@pytest.mark.parametrize("count", [0, 1, 5])
def test_frame_selection_handles_degenerate_counts(count: int):
    rng = np.random.default_rng(2)
    frames = [rng.integers(0, 255, (32, 32, 3), dtype=np.uint8) for _ in range(count)]
    picked = select_diverse_frames(frames, max_frames=3)
    assert len(picked) <= min(count, 3)
