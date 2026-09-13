"""Monocular depth backbones for the photo and video tiers.

One learned backbone is supported: Depth Anything V2 Metric Indoor (Small), fetched by
`scripts/fetch_weights.sh` into `weights/depth-anything-v2-metric-indoor-small`. Without it the
pipeline falls back to a constant 2.5 m depth, which keeps room topology but carries no metric
scale, and the plan's quality report names whichever backbone ran.

Earlier versions also listed a ViT-L relative model, ZoeDepth and VGGT-1B here. None of them
loaded its own weights: each asked a shared helper that returned no depth, and so a constant
2.5 m, unless a ZoeDepth checkpoint happened to sit in a second directory. They are removed
rather than kept as names.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

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


class DepthAnythingV2MetricBackbone(DepthBackbone):
    """Depth Anything V2 Metric Indoor, loaded from a local snapshot.

    Metric rather than relative on purpose. The relative model predicts affine-invariant
    inverse depth (a/z + b), so inverting its output is not proportional to depth unless b
    is known, and recovering scale from a single cue would then be fitting one unknown to a
    two-parameter family -- producing a room whose shape is wrong in a way no scale factor
    can correct. The metric model predicts z, leaving one multiplicative unknown that the
    camera-height prior can honestly pin.
    """

    name = "depth_anything_v2_metric_indoor"

    def __init__(self, model_dir: Path) -> None:
        import torch
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation

        self._torch = torch
        self._processor = AutoImageProcessor.from_pretrained(str(model_dir))
        self._model = AutoModelForDepthEstimation.from_pretrained(str(model_dir))
        self._model.eval()
        # MPS on Apple silicon is roughly an order of magnitude faster than CPU here and
        # the walk-in test is timed.
        self._device = "mps" if torch.backends.mps.is_available() else "cpu"
        self._model.to(self._device)

    def estimate(self, image: np.ndarray) -> np.ndarray:
        torch = self._torch
        inputs = self._processor(images=image, return_tensors="pt").to(self._device)
        with torch.no_grad():
            outputs = self._model(**inputs)
        depth = outputs.predicted_depth
        if depth.ndim == 3:
            depth = depth.unsqueeze(1)
        depth = torch.nn.functional.interpolate(
            depth, size=image.shape[:2], mode="bicubic", align_corners=False
        )
        return depth.squeeze().float().cpu().numpy().astype(np.float32)

    def is_metric(self) -> bool:
        return True


_BACKBONE_REGISTRY = [
    ("depth-anything-v2-metric-indoor-small", DepthAnythingV2MetricBackbone),
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
