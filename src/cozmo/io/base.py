"""Tier-independent capture interface.

Every tier (photo, video, LiDAR) resolves to the same `CaptureSource`: a sequence of
`Frame` objects carrying intrinsics, an optional metric depth map and a world-from-camera
pose. What differs between tiers is where those fields come from and how much they can be
trusted, which is why each frame records the provenance of its depth and its pose rather
than pretending they are equivalent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterator, Protocol

import numpy as np

from cozmo.schema import Tier


class Provenance(str, Enum):
    """Where a quantity came from. Drives how much weight the solver gives it."""

    SENSOR = "sensor"
    ESTIMATED = "estimated"
    PREDICTED = "predicted"
    ABSENT = "absent"


@dataclass
class Frame:
    """One observation.

    `depth` is metres at the resolution of `k_depth`, with zeros marking no return.
    `depth_sigma` is a per-pixel standard deviation in metres. The LiDAR tier derives it
    from ARKit's confidence channel and the range-dependent noise model; the predicted
    tiers derive it from the depth model's own spread. Carrying it per pixel is what lets
    the plane fits be weighted rather than uniform, which is most of the difference
    between a wall estimate that holds at 2 cm and one that does not.
    """

    index: int
    timestamp: float
    k_depth: np.ndarray
    k_rgb: np.ndarray
    rgb_size: tuple[int, int]
    depth: np.ndarray | None = None
    depth_sigma: np.ndarray | None = None
    confidence: np.ndarray | None = None
    pose: np.ndarray | None = None
    depth_provenance: Provenance = Provenance.ABSENT
    pose_provenance: Provenance = Provenance.ABSENT
    rgb_path: Path | None = None
    _rgb: np.ndarray | None = field(default=None, repr=False)
    group: str = "default"

    @property
    def has_metric_depth(self) -> bool:
        return self.depth is not None

    @property
    def has_pose(self) -> bool:
        return self.pose is not None


@dataclass
class CaptureMeta:
    capture_id: str
    tier: Tier
    device_model: str
    root: Path
    frame_count: int
    groups: list[str] = field(default_factory=lambda: ["default"])
    notes: dict[str, str] = field(default_factory=dict)

    @property
    def is_grouped(self) -> bool:
        """True when the capture arrives pre-partitioned, one group per room."""
        return len(self.groups) > 1 or self.groups != ["default"]


class CaptureSource(Protocol):
    """Read side of a capture. Implementations must be safe to iterate more than once."""

    meta: CaptureMeta

    def frames(self, indices: list[int] | None = None) -> Iterator[Frame]: ...

    def load_rgb(self, frame: Frame) -> np.ndarray: ...
