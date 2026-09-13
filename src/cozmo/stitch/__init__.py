"""Multi-room stitching.

When a capture spans multiple rooms, each room may be reconstructed independently (photo and
video tiers) or jointly (LiDAR tier). Either way the rooms have to share one coordinate frame.
:mod:`~cozmo.stitch.graph` builds and optimises the pose graph, and :mod:`~cozmo.stitch.rooms`
joins rooms that were reconstructed separately. Trajectory drift detection and correction lives
in :mod:`cozmo.geometry.drift`, with the geometry it depends on.
"""

from cozmo.stitch.graph import PoseGraph, optimise_pose_graph  # noqa: F401

__all__ = ["PoseGraph", "optimise_pose_graph"]
