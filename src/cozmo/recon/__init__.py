"""Reconstruction backbone — depth estimation and multi-view geometry.

This package provides the core visual reconstruction modules used by the
photo and video tiers where LiDAR depth is not available:

- :mod:`~cozmo.recon.backbone` — depth estimation model adapters
- :mod:`~cozmo.recon.frames` — frame selection and quality filtering
"""

from cozmo.recon.backbone import DepthBackbone, get_backbone  # noqa: F401
from cozmo.recon.frames import select_diverse_frames  # noqa: F401

__all__ = [
    "DepthBackbone",
    "get_backbone",
    "select_diverse_frames",
]
