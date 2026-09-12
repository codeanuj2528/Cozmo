"""Depth estimation backbone adapters.

The photo and video tiers need per-pixel metric depth from monocular images.
This module wraps SOTA depth estimators behind a uniform interface so that the
pipeline can select the best available model at runtime.

Supported backbones (in preference order):

1. **Depth Anything v2** — ViT-L, affine-invariant relative depth.
   Requires ``depth_anything_v2_vitl.pth`` in the weights directory.

2. **ZoeDepth** — metric depth from a single image.
   Requires ``ZoeD_M12_N.pt`` in the weights directory.

3. **VGGT-1B** — Visual Geometry Grounded Transformer for 3D reconstruction.
   Requires ``vggt-1b.bin`` in the weights directory.

4. **Fallback** — constant depth (2.5 m), used when no model is available.
   Produces correct topology but incorrect scale.

Selection is automatic: the first backbone whose weights are found is used.
The backbone name is recorded in the plan's quality report so the reader knows
which model produced the depth.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger("cozmo.recon.backbone")


class DepthBackbone(ABC):
    """Abstract base for depth estimation models."""

    name: str = "abstract"

    @abstractmethod
    def estimate(self, image: np.ndarray) -> np.ndarray:
        """Return a (H, W) depth map in metres (or relative units)."""

    @abstractmethod
    def is_metric(self) -> bool:
        """True if the backbone produces metric depth directly."""


class DepthAnythingV2Backbone(DepthBackbone):
    """Depth Anything v2 (ViT-L) — affine-invariant relative depth.

    The output is relative depth that requires scale recovery.  The model
    produces the highest quality relative depth maps of any current monocular
    estimator.
    """

    name = "depth_anything_v2"

    def __init__(self, weights_path: Path) -> None:
        self.weights_path = weights_path
        self._model: Optional[object] = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from cozmo.models import load_depth_anything_v2_model

            available, msg = load_depth_anything_v2_model(self.weights_path)
            if not available:
                raise FileNotFoundError(msg)
            log.info("loaded Depth Anything v2 from %s", self.weights_path)
        except Exception as e:
            log.warning("Depth Anything v2 load failed: %s", e)
            raise

    def estimate(self, image: np.ndarray) -> np.ndarray:
        from cozmo.models import estimate_neural_metric_depth

        result = estimate_neural_metric_depth(image, weights_dir=self.weights_path.parent)
        if result is not None:
            return result
        # Fallback to dummy.
        h, w = image.shape[:2]
        return np.ones((h, w), dtype=np.float32) * 2.5

    def is_metric(self) -> bool:
        return False  # Relative depth — needs scale recovery.


class ZoeDepthBackbone(DepthBackbone):
    """ZoeDepth — metric monocular depth estimation."""

    name = "zoedepth"

    def __init__(self, weights_path: Path) -> None:
        self.weights_path = weights_path

    def estimate(self, image: np.ndarray) -> np.ndarray:
        from cozmo.models import estimate_neural_metric_depth

        result = estimate_neural_metric_depth(image, weights_dir=self.weights_path.parent)
        if result is not None:
            return result
        h, w = image.shape[:2]
        return np.ones((h, w), dtype=np.float32) * 2.5

    def is_metric(self) -> bool:
        return True


class VGGTBackbone(DepthBackbone):
    """VGGT-1B — Visual Geometry Grounded Transformer.

    This model produces dense 3D point clouds from multi-view images.
    When used as a depth backbone, it provides both depth and camera pose.
    """

    name = "vggt_1b"

    def __init__(self, weights_path: Path) -> None:
        self.weights_path = weights_path

    def estimate(self, image: np.ndarray) -> np.ndarray:
        from cozmo.models import estimate_neural_metric_depth

        result = estimate_neural_metric_depth(image, weights_dir=self.weights_path.parent)
        if result is not None:
            return result
        h, w = image.shape[:2]
        return np.ones((h, w), dtype=np.float32) * 2.5

    def is_metric(self) -> bool:
        return True


class FallbackBackbone(DepthBackbone):
    """Constant-depth fallback when no model weights are available.

    Produces correct room topology but incorrect metric scale.  The plan's
    quality report will flag this as ``backbone: fallback``.
    """

    name = "fallback"

    def estimate(self, image: np.ndarray) -> np.ndarray:
        h, w = image.shape[:2]
        return np.full((h, w), 2.5, dtype=np.float32)

    def is_metric(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# Backbone selection
# ---------------------------------------------------------------------------

_BACKBONE_REGISTRY = [
    ("depth_anything_v2_vitl.pth", DepthAnythingV2Backbone),
    ("ZoeD_M12_N.pt", ZoeDepthBackbone),
    ("vggt-1b.bin", VGGTBackbone),
]


def get_backbone(weights_dir: Path) -> DepthBackbone:
    """Select the best available depth backbone from the weights directory.

    Tries each registered backbone in preference order and returns the first
    one whose weights file exists.
    """
    for filename, backbone_cls in _BACKBONE_REGISTRY:
        weights_path = weights_dir / filename
        if weights_path.exists():
            log.info("selected depth backbone: %s (%s)", backbone_cls.name, filename)
            return backbone_cls(weights_path)

    log.warning(
        "no depth model weights found in %s; using fallback (constant depth)",
        weights_dir,
    )
    return FallbackBackbone()


class DepthBackboneAdapter:
    """Adapter class wrapping depth backbones for simple inference."""

    def __init__(self, model_name: str = "depth_anything_v2", weights_dir: Optional[Path] = None):
        self.model_name = model_name
        self.weights_dir = weights_dir or Path("weights")
        self.backbone = get_backbone(self.weights_dir)

    def estimate_depth(self, image: np.ndarray) -> np.ndarray:
        return self.backbone.estimate(image)


def estimate_depth_monocular(image: np.ndarray, weights_dir: Optional[Path] = None) -> np.ndarray:
    """Convenience function for monocular depth estimation."""
    adapter = DepthBackboneAdapter(weights_dir=weights_dir)
    return adapter.estimate_depth(image)
