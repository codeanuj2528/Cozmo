"""Ceiling returns as interior evidence.

Floor evidence is the direct proof a cell is standable, and it is exactly what furniture
destroys: the floor under a wardrobe or a bed is never observed. On the benchmark flat that
bounded the bedroom at the wardrobe front, 5.28 m2 against a taped 9.29 m2, while the ceiling
observed above the same room covered 9.10 m2. These tests pin the raster that recovers it.
"""

from __future__ import annotations

import numpy as np

from cozmo.geometry.fusion import FusedCloud
from cozmo.geometry.occupancy import CEILING_EVIDENCE_MIN_HEIGHT_M, build_occupancy

FLOOR_Y = 0.0
CEILING_Y = 2.6


def _patch(x0, x1, z0, z1, y, normal_y, step=0.02):
    xs, zs = np.meshgrid(np.arange(x0, x1, step), np.arange(z0, z1, step))
    pts = np.stack([xs.ravel(), np.full(xs.size, y), zs.ravel()], axis=1)
    nrm = np.tile([0.0, normal_y, 0.0], (len(pts), 1))
    return pts, nrm


def _cloud(parts):
    pts = np.vstack([p for p, _ in parts]).astype(np.float32)
    nrm = np.vstack([n for _, n in parts]).astype(np.float32)
    n = len(pts)
    view = np.tile([0.0, 1.0, 0.0], (n, 1)).astype(np.float32)
    return FusedCloud(
        points=pts,
        normals=nrm,
        sigma=np.full(n, 0.01, np.float32),
        weight=np.full(n, 1e4, np.float32),
        view_dir=view,
        range_m=np.full(n, 1.5, np.float32),
        frame_index=np.zeros(n, np.int32),
        voxel_m=0.02,
    )


def _cell(occ, x, z):
    rc = occ.grid.to_cell(np.array([[x, z]]))[0]
    return bool(occ.ceiling_hits[rc[0], rc[1]])


def test_ceiling_over_hidden_floor_is_marked():
    """Floor observed only on the left half; ceiling observed over the whole room."""
    floor = _patch(0.0, 1.5, 0.0, 3.0, FLOOR_Y, +1.0)
    ceiling = _patch(0.0, 3.0, 0.0, 3.0, CEILING_Y, -1.0)
    occ = build_occupancy(_cloud([floor, ceiling]), FLOOR_Y, CEILING_Y, resolution=0.05)

    assert occ.ceiling_hits is not None
    assert _cell(occ, 2.4, 1.5), "the ceiling above the unseen floor must be evidence"
    rc = occ.grid.to_cell(np.array([[2.4, 1.5]]))[0]
    assert not occ.floor_hits[rc[0], rc[1]], "and that cell genuinely has no floor return"


def test_low_downward_surfaces_are_not_ceiling():
    """A table or shelf underside faces down but sits well below head height."""
    table_underside = _patch(1.0, 1.6, 1.0, 1.6, 0.72, -1.0)
    occ = build_occupancy(_cloud([table_underside]), FLOOR_Y, CEILING_Y, resolution=0.05)
    assert not _cell(occ, 1.3, 1.3)
    assert 0.72 < CEILING_EVIDENCE_MIN_HEIGHT_M


def test_upward_surfaces_at_ceiling_height_are_not_ceiling():
    """The top of a tall wardrobe faces up; only downward-facing returns count."""
    wardrobe_top = _patch(0.0, 0.6, 0.0, 2.0, 2.2, +1.0)
    occ = build_occupancy(_cloud([wardrobe_top]), FLOOR_Y, CEILING_Y, resolution=0.05)
    assert not _cell(occ, 0.3, 1.0)


def test_returns_above_the_ceiling_are_rejected():
    """Nothing real sits above the measured ceiling; such returns are noise or a void."""
    above = _patch(0.0, 1.0, 0.0, 1.0, CEILING_Y + 0.6, -1.0)
    occ = build_occupancy(_cloud([above]), FLOOR_Y, CEILING_Y, resolution=0.05)
    assert not _cell(occ, 0.5, 0.5)
