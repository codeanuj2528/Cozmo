"""Backward-compatibility shim.

All reconstruction logic has moved to :mod:`cozmo.pipeline.lidar`,
:mod:`cozmo.pipeline.photo` and :mod:`cozmo.pipeline.video`.  This file
re-exports the canonical entry point so that existing imports continue to work.
"""

from cozmo.pipeline.common import PipelineArtifacts, PipelineResult  # noqa: F401
from cozmo.pipeline.lidar import reconstruct  # noqa: F401

__all__ = ["reconstruct", "PipelineResult", "PipelineArtifacts"]
