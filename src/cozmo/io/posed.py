"""A capture source assembled in memory from frames that were posed after the fact.

The photo and video tiers do not read poses from a file; they compute them. Wrapping the
result in the same `CaptureSource` interface the LiDAR reader implements is what lets those
tiers run the identical reconstruction core rather than a parallel one. Three parallel
cores would drift apart, and the tier comparison the brief asks for would then measure
implementation differences rather than sensor differences.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import numpy as np

from cozmo.io.base import CaptureMeta, Frame
from cozmo.schema import Tier


class PosedFrameSource:
    """Serves a fixed list of frames that already carry depth and pose."""

    def __init__(
        self,
        frames: list[Frame],
        capture_id: str,
        tier: Tier,
        device_model: str = "unknown",
        root: Path | None = None,
        images: dict[int, np.ndarray] | None = None,
        notes: dict[str, str] | None = None,
    ) -> None:
        self._frames = frames
        self._images = images or {}
        self.meta = CaptureMeta(
            capture_id=capture_id,
            tier=tier,
            device_model=device_model,
            root=root or Path("."),
            frame_count=len(frames),
            notes=notes or {},
        )

    def frames(self, indices: list[int] | None = None) -> Iterator[Frame]:
        if indices is None:
            yield from self._frames
            return
        for i in indices:
            if 0 <= i < len(self._frames):
                yield self._frames[i]

    def frame_indices(self) -> list[int]:
        return [f.index for f in self._frames]

    def poses(self) -> np.ndarray:
        if not self._frames:
            return np.zeros((0, 4, 4))
        return np.stack([f.pose if f.pose is not None else np.eye(4) for f in self._frames])

    def load_rgb(self, frame: Frame) -> np.ndarray:
        return self._images.get(frame.index, np.zeros((1, 1, 3), dtype=np.uint8))

    def load_rgb_batch(self, frame_indices: list[int]) -> dict[int, np.ndarray]:
        return {i: self._images[i] for i in frame_indices if i in self._images}
