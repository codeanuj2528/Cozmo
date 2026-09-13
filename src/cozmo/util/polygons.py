"""Polygon cleanup for room outlines.

Merging the faces of a cell complex leaves a polygon that is geometrically right and
structurally awful: a wall that crossed three faces arrives as four collinear vertices,
and the tiny buffers used to make the union robust leave slivers a few tenths of a
millimetre long. Neither affects area, and both make the plan unreadable and the wall list
meaningless, since a "wall" would be reported once per face it happened to cross.

Cleanup is ordered so that each step's assumptions hold. Sliver edges go first, because a
collinearity test on an edge two tenths of a millimetre long measures floating-point noise
rather than direction. Collinear runs go second. Douglas-Peucker goes last and with a tight
tolerance, since by that point the only remaining vertices are real corners.
"""

from __future__ import annotations

import numpy as np
from shapely.geometry import Polygon

MIN_EDGE_M = 0.04
COLLINEAR_TOLERANCE_RAD = np.deg2rad(4.0)
# Largest perpendicular step treated as an artefact of the cell complex rather than a real
# feature of the room. Above this a step is kept, because bays and alcoves exist.
MAX_JOG_M = 0.55


def _drop_short_edges(ring: np.ndarray, min_edge_m: float) -> np.ndarray:
    """Collapse consecutive vertices closer together than `min_edge_m`."""
    if len(ring) < 4:
        return ring
    out = [ring[0]]
    for point in ring[1:]:
        if np.linalg.norm(point - out[-1]) >= min_edge_m:
            out.append(point)
    if len(out) >= 3 and np.linalg.norm(out[0] - out[-1]) < min_edge_m:
        out.pop()
    return np.array(out)


def _drop_collinear(ring: np.ndarray, tolerance_rad: float) -> np.ndarray:
    """Remove vertices whose two edges run in nearly the same direction."""
    n = len(ring)
    if n < 4:
        return ring
    keep = np.ones(n, dtype=bool)
    for i in range(n):
        prev_i = (i - 1) % n
        while not keep[prev_i] and prev_i != i:
            prev_i = (prev_i - 1) % n
        next_i = (i + 1) % n
        a = ring[i] - ring[prev_i]
        b = ring[next_i] - ring[i]
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na < 1e-9 or nb < 1e-9:
            keep[i] = False
            continue
        cos = np.clip(a @ b / (na * nb), -1.0, 1.0)
        if np.arccos(cos) < tolerance_rad:
            keep[i] = False
    if keep.sum() < 3:
        return ring
    return ring[keep]


def _collapse_jogs(ring: np.ndarray, max_jog_m: float, flank_ratio: float = 2.0) -> np.ndarray:
    """Merge a staircase back into the single wall it came from.

    The cell complex partitions the floor with every wall line in the property, including
    lines belonging to other rooms. Where one of those crosses a room, the room's outline
    picks up a short perpendicular step in the middle of what is physically one flat wall.
    Measured against tape, a 4.88 m hall wall came out as 2.72 + 0.41 + 2.07 -- the length
    is right (2.72 + 2.07 = 4.79) but it is reported as two walls with a 0.41 m jog between
    them, and the wall-length gate then compares a 2.07 m fragment against a 4.88 m tape
    reading and calls it a 58% error.

    A jog is collapsed only when both flanking edges are at least `flank_ratio` times its
    length. That is what separates an artefact from a real feature: a genuine alcove or bay
    is comparable in size to the wall it interrupts, while these steps are a fraction of it.
    """
    n = len(ring)
    if n < 5:
        return ring

    keep = np.ones(n, dtype=bool)
    for i in range(n):
        prev_i, next_i, after_i = (i - 1) % n, (i + 1) % n, (i + 2) % n
        if not (keep[prev_i] and keep[i] and keep[next_i] and keep[after_i]):
            continue

        before = ring[i] - ring[prev_i]
        jog = ring[next_i] - ring[i]
        after = ring[after_i] - ring[next_i]
        len_before, len_jog, len_after = (float(np.linalg.norm(v)) for v in (before, jog, after))
        if not (0 < len_jog <= max_jog_m):
            continue
        if len_before < flank_ratio * len_jog or len_after < flank_ratio * len_jog:
            continue

        # The two flanking edges must be nearly parallel and pointing the same way, or this
        # is a corner rather than a step in one wall.
        cos = float(before @ after / (len_before * len_after))
        if cos < np.cos(np.deg2rad(12.0)):
            continue

        keep[i] = False
        keep[next_i] = False

    if keep.sum() < 4:
        return ring
    return ring[keep]


def clean_polygon(
    polygon: Polygon,
    min_edge_m: float = MIN_EDGE_M,
    collinear_tolerance_rad: float = COLLINEAR_TOLERANCE_RAD,
    simplify_m: float = 0.015,
    max_jog_m: float = MAX_JOG_M,
) -> Polygon:
    """Reduce a merged polygon to its real corners without moving them."""
    if polygon.is_empty:
        return polygon
    polygon = polygon.buffer(0)
    if polygon.geom_type == "MultiPolygon":
        polygon = max(polygon.geoms, key=lambda g: g.area)
    if polygon.is_empty or polygon.geom_type != "Polygon":
        return polygon

    ring = np.asarray(polygon.exterior.coords)[:-1]
    before = polygon.area
    ring = _drop_short_edges(ring, min_edge_m)
    ring = _collapse_jogs(ring, max_jog_m=max_jog_m)
    ring = _drop_collinear(ring, collinear_tolerance_rad)
    if len(ring) < 3:
        return polygon

    cleaned = Polygon(ring).buffer(0)
    if cleaned.geom_type == "MultiPolygon":
        cleaned = max(cleaned.geoms, key=lambda g: g.area)
    if cleaned.is_empty:
        return polygon
    cleaned = cleaned.simplify(simplify_m, preserve_topology=True)
    if cleaned.is_empty or cleaned.geom_type != "Polygon":
        return polygon
    # Cleanup must not change what the room measures. A cleaned outline that moved the
    # area by more than a couple of percent means a real corner was cut, so keep the
    # original rather than report a number the geometry no longer supports.
    if before > 0 and abs(cleaned.area - before) / before > 0.06:
        return polygon
    return cleaned


def rotation_2d(angle_rad: float) -> np.ndarray:
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array([[c, -s], [s, c]])


def rotation_about_up(angle_rad: float) -> np.ndarray:
    """3x3 rotation about the gravity axis, for putting a property on its own axes."""
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])
