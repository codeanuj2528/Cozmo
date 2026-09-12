"""Per-tier reconstruction pipeline package.

Three tiers, one core: every tier resolves to frames carrying intrinsics, metric
depth and a pose.  The tiers differ only in how those fields were obtained and how
much they can be trusted.

* :mod:`~cozmo.pipeline.lidar` — fuses depth frames from a LiDAR-capable device
  (iPhone Pro / iPad Pro) via Stray Scanner export.  This is the reference tier.
* :mod:`~cozmo.pipeline.photo` — reconstructs from unposed stills per room, using
  monocular depth estimation and learned feature matching.
* :mod:`~cozmo.pipeline.video` — samples keyframes from a walkthrough clip and
  delegates to the photo path.

All three produce the same validated ``PropertyPlan``.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional, Union, Tuple, Any

from cozmo.schema import PropertyPlan, Tier
from cozmo.pipeline.lidar import reconstruct as reconstruct_lidar
from cozmo.pipeline.photo import reconstruct as reconstruct_photo
from cozmo.pipeline.video import reconstruct as reconstruct_video
from cozmo.pipeline.common import PipelineResult, PipelineArtifacts


def reconstruct(
    path: Path,
    tier: Optional[Union[Tier, str]] = None,
    weights_dir: Optional[Path] = None,
) -> PropertyPlan:
    """Canonical multi-tier entry point for property reconstruction.

    Args:
        path: Path to capture directory (LiDAR / Photo / Video).
        tier: Optional explicit tier override. Inferred from directory structure if omitted.
        weights_dir: Optional path to ML model weights directory.

    Returns:
        Validated PropertyPlan dataclass instance.
    """
    if tier is not None:
        tier_enum = Tier(tier) if isinstance(tier, str) else tier
    else:
        tier_enum = Tier.LIDAR

    if tier_enum == Tier.PHOTO:
        res = reconstruct_photo(path)
    elif tier_enum == Tier.VIDEO:
        res = reconstruct_video(path)
    else:
        res = reconstruct_lidar(path)

    return res.plan if hasattr(res, "plan") else res


__all__ = ["reconstruct", "PipelineResult", "PipelineArtifacts"]
