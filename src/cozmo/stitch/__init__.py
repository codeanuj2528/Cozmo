"""Multi-room stitching: pose graph optimisation and feature matching.

When a capture spans multiple rooms, each room may be reconstructed
independently (photo/video tiers) or jointly (LiDAR tier).  Either way, the
rooms must be placed in a common coordinate frame.  This package provides:

- :mod:`~cozmo.stitch.graph` — pose graph construction and optimisation
- :mod:`~cozmo.stitch.match` — feature matching between overlapping observations
- :mod:`~cozmo.stitch.drift` — trajectory drift detection and correction
"""

from cozmo.stitch.graph import PoseGraph, optimise_pose_graph  # noqa: F401
from cozmo.stitch.match import match_features, FeatureMatch  # noqa: F401

__all__ = ["PoseGraph", "optimise_pose_graph", "match_features", "FeatureMatch"]
