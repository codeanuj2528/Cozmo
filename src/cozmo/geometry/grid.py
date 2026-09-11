"""A metric 2D raster over the property footprint, and conversions to and from it."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Grid2D:
    """Axis-aligned raster on the world xz plane. Row index follows z, column follows x."""

    origin: np.ndarray
    resolution: float
    shape: tuple[int, int]

    @classmethod
    def covering(cls, points_xz: np.ndarray, resolution: float, margin_m: float = 0.5) -> Grid2D:
        lo = points_xz.min(axis=0) - margin_m
        hi = points_xz.max(axis=0) + margin_m
        size = np.ceil((hi - lo) / resolution).astype(int) + 1
        return cls(origin=lo, resolution=resolution, shape=(int(size[1]), int(size[0])))

    def to_cell(self, points_xz: np.ndarray) -> np.ndarray:
        """World xz to integer (row, col). Values may fall outside the raster."""
        rel = (np.atleast_2d(points_xz) - self.origin) / self.resolution
        return np.stack([rel[:, 1], rel[:, 0]], axis=1).round().astype(np.int64)

    def to_cell_float(self, points_xz: np.ndarray) -> np.ndarray:
        rel = (np.atleast_2d(points_xz) - self.origin) / self.resolution
        return np.stack([rel[:, 1], rel[:, 0]], axis=1)

    def to_world(self, cells_rc: np.ndarray) -> np.ndarray:
        cells_rc = np.atleast_2d(np.asarray(cells_rc, dtype=np.float64))
        x = cells_rc[:, 1] * self.resolution + self.origin[0]
        z = cells_rc[:, 0] * self.resolution + self.origin[1]
        return np.stack([x, z], axis=1)

    def inside(self, cells_rc: np.ndarray) -> np.ndarray:
        return (
            (cells_rc[:, 0] >= 0)
            & (cells_rc[:, 0] < self.shape[0])
            & (cells_rc[:, 1] >= 0)
            & (cells_rc[:, 1] < self.shape[1])
        )

    @property
    def cell_area(self) -> float:
        return self.resolution**2

    def empty(self, dtype=np.float32) -> np.ndarray:
        return np.zeros(self.shape, dtype=dtype)
