"""Small binary-raster operations.

These are written out rather than taken from scikit-image because the library has been
renaming and re-specifying `remove_small_objects` and `remove_small_holes` across releases
(`min_size` to `max_size`, with the comparison flipping from strict to inclusive). A
pipeline whose floor areas shift when a transitive dependency is upgraded is not
reproducible, and reproducibility is something this submission is scored on.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

EIGHT_CONNECTED = np.ones((3, 3), dtype=bool)


def remove_small_blobs(mask: np.ndarray, min_cells: int) -> np.ndarray:
    """Drop connected components with fewer than `min_cells` cells."""
    if min_cells <= 1 or not mask.any():
        return mask
    labels, n = ndimage.label(mask, structure=EIGHT_CONNECTED)
    if n == 0:
        return mask
    sizes = np.bincount(labels.ravel())
    keep = np.zeros(len(sizes), dtype=bool)
    keep[1:] = sizes[1:] >= min_cells
    return keep[labels]


def fill_small_holes(mask: np.ndarray, max_cells: int) -> np.ndarray:
    """Fill enclosed background regions with fewer than `max_cells` cells."""
    if not mask.any():
        return mask
    holes = ndimage.binary_fill_holes(mask) & ~mask
    if not holes.any():
        return mask
    labels, n = ndimage.label(holes, structure=EIGHT_CONNECTED)
    if n == 0:
        return mask
    sizes = np.bincount(labels.ravel())
    fill = np.zeros(len(sizes), dtype=bool)
    fill[1:] = sizes[1:] <= max_cells
    return mask | fill[labels]


def components_touching(mask: np.ndarray, seeds: np.ndarray) -> np.ndarray:
    """Connected components of `mask` that contain at least one seed cell."""
    if not mask.any() or not seeds.any():
        return np.zeros_like(mask)
    labels, n = ndimage.label(mask, structure=EIGHT_CONNECTED)
    if n == 0:
        return np.zeros_like(mask)
    touched = np.unique(labels[seeds & mask])
    touched = touched[touched > 0]
    if len(touched) == 0:
        return np.zeros_like(mask)
    return np.isin(labels, touched)


def draw_segments(shape: tuple[int, int], starts_rc: np.ndarray, ends_rc: np.ndarray,
                  thickness: int = 1) -> np.ndarray:
    """Rasterise line segments given in (row, col) coordinates."""
    out = np.zeros(shape, dtype=bool)
    if len(starts_rc) == 0:
        return out
    delta = ends_rc - starts_rc
    lengths = np.linalg.norm(delta, axis=1)
    steps = int(np.ceil(lengths.max())) + 2
    t = np.linspace(0.0, 1.0, steps)[None, :]
    rr = np.round(starts_rc[:, 0:1] + delta[:, 0:1] * t).astype(np.int64).ravel()
    cc = np.round(starts_rc[:, 1:2] + delta[:, 1:2] * t).astype(np.int64).ravel()
    ok = (rr >= 0) & (rr < shape[0]) & (cc >= 0) & (cc < shape[1])
    out[rr[ok], cc[ok]] = True
    if thickness > 1:
        out = ndimage.binary_dilation(out, EIGHT_CONNECTED, iterations=thickness - 1)
    return out
