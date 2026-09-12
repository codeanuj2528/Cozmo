"""Per-tier reconstruction, behind one entry point.

Three tiers share one core: each resolves to frames carrying intrinsics, metric depth and a
pose, and they differ only in how those fields were obtained and how far they can be
trusted. What differs is the front half.

* :mod:`~cozmo.pipeline.lidar` fuses ARKit depth from a Stray Scanner export. Depth and
  pose are measured, so this is the reference tier.
* :mod:`~cozmo.pipeline.photo` reconstructs from unposed stills, one folder per room.
  Depth is predicted and pose is estimated, so metric scale has to be recovered.
* :mod:`~cozmo.pipeline.video` samples keyframes from a walkthrough and hands them to the
  photo path, adding the one thing a photo folder does not have: temporal continuity.

There is exactly one public `reconstruct`, and it always returns a `PipelineResult`.

That last sentence is load-bearing. This package previously exported a `reconstruct(path,
tier)` returning a bare plan, which shadowed `lidar.reconstruct(source, config)` returning
a result, while every call site used the second signature. The CLI therefore raised
TypeError on every input and had never produced a plan, and the failure was invisible from
reading either function because each was internally consistent. Two functions with one
name and two contracts is the defect; the per-tier builders are now named for what they
build, and only this module exports `reconstruct`.
"""

from __future__ import annotations

from pathlib import Path

from cozmo.config import PipelineConfig
from cozmo.io.base import CaptureSource
from cozmo.pipeline.common import PipelineArtifacts, PipelineResult
from cozmo.pipeline.lidar import build_lidar_plan
from cozmo.pipeline.photo import build_photo_plan
from cozmo.pipeline.video import build_video_plan
from cozmo.schema import Tier
from cozmo.uncertainty.calibration import IntervalBook

_BUILDERS = {
    Tier.LIDAR: build_lidar_plan,
    Tier.PHOTO: build_photo_plan,
    Tier.VIDEO: build_video_plan,
}


def reconstruct(
    source: CaptureSource | Path | str,
    config: PipelineConfig | None = None,
    book: IntervalBook | None = None,
    tier: Tier | str | None = None,
) -> PipelineResult:
    """Reconstruct one capture, dispatching on its tier.

    `source` may be a loaded capture or a path to one; a path is loaded and its tier
    detected from what the directory contains. `tier` overrides that detection, which is
    what the benchmark uses to run the same rooms through a tier other than the one the
    files came from.
    """
    if isinstance(source, (str, Path)):
        from cozmo.io import load_capture

        source = load_capture(Path(source))

    resolved = source.meta.tier if tier is None else (Tier(tier) if isinstance(tier, str) else tier)
    builder = _BUILDERS.get(resolved)
    if builder is None:
        raise ValueError(f"no builder registered for tier {resolved!r}")
    return builder(source, config, book)


__all__ = [
    "reconstruct",
    "build_lidar_plan",
    "build_photo_plan",
    "build_video_plan",
    "PipelineResult",
    "PipelineArtifacts",
]
