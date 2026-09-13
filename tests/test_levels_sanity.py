"""Where a ceiling height is read, and what is allowed to count as a ceiling.

The long walk of the benchmark flat has a bay whose only upward surface is a window ledge
0.52 m above the floor. The pipeline published that bay with a 1.860 m ceiling measured from
the ledge; once surfaces under 2.20 m were excluded, it published a 3.04 m ceiling instead,
read at the world origin from a patch tilted 15 degrees. It now abstains. These tests pin
each of those steps.
"""

from __future__ import annotations

import numpy as np
import pytest

from cozmo.geometry.fusion import FusedCloud
from cozmo.geometry.levels import MIN_CEILING_CLEARANCE_M, detect_levels


def _patch(x0, x1, z0, z1, y, normal_y, step=0.03):
    xs, zs = np.meshgrid(np.arange(x0, x1, step), np.arange(z0, z1, step))
    pts = np.stack([xs.ravel(), np.full(xs.size, y), zs.ravel()], axis=1)
    return pts, np.tile([0.0, normal_y, 0.0], (len(pts), 1))


def _cloud(parts):
    pts = np.vstack([p for p, _ in parts]).astype(np.float32)
    nrm = np.vstack([n for _, n in parts]).astype(np.float32)
    n = len(pts)
    return FusedCloud(
        points=pts,
        normals=nrm,
        sigma=np.full(n, 0.01, np.float32),
        weight=np.full(n, 1e4, np.float32),
        view_dir=np.tile([0.0, 1.0, 0.0], (n, 1)).astype(np.float32),
        range_m=np.full(n, 1.5, np.float32),
        frame_index=np.zeros(n, np.int32),
        voxel_m=0.02,
    )


def test_loft_underside_is_not_a_ceiling():
    floor = _patch(0.0, 2.4, 0.0, 1.2, 0.0, +1.0)
    loft = _patch(0.0, 2.4, 0.0, 1.2, 1.86, -1.0)
    levels = detect_levels(_cloud([floor, loft]))
    assert levels.ceiling is None
    assert levels.height is None, "an unobserved ceiling must abstain, not report the loft"


def test_real_ceiling_above_a_loft_is_still_measured():
    floor = _patch(0.0, 2.4, 0.0, 1.2, 0.0, +1.0)
    loft = _patch(0.0, 1.2, 0.0, 1.2, 1.86, -1.0)
    ceiling = _patch(0.0, 2.4, 0.0, 1.2, 2.60, -1.0)
    levels = detect_levels(_cloud([floor, loft, ceiling]))
    assert levels.height == pytest.approx(2.60, abs=0.02)


def test_the_bound_sits_above_door_heads_and_below_finished_ceilings():
    seven_foot_door_head = 7 * 0.3048
    lowest_measured_ceiling_in_benchmark = 2.40
    assert seven_foot_door_head < MIN_CEILING_CLEARANCE_M < lowest_measured_ceiling_in_benchmark


def test_levels_are_read_where_the_room_is_not_where_the_world_origin_is():
    # A floor patch fitted with 1.5 degrees of tilt, seven metres from the origin, under a level
    # ceiling. Read at the origin, the floor sits 18 cm low and the room gains 18 cm of height.
    floor_pts, floor_normals = _patch(6.0, 8.0, 6.0, 8.0, 0.0, +1.0)
    floor_pts[:, 1] = np.tan(np.deg2rad(1.5)) * (floor_pts[:, 0] - 7.0)
    ceiling = _patch(6.0, 8.0, 6.0, 8.0, 2.60, -1.0)
    levels = detect_levels(_cloud([(floor_pts, floor_normals), ceiling]))
    assert levels.height == pytest.approx(2.60, abs=0.02)


def test_a_trace_above_a_window_head_is_not_a_ceiling():
    # The long walk's window bay: a ledge is the only upward surface, a window head 1.47 m above
    # it is the strongest thing overhead, and a few returns sit higher still.
    ledge = _patch(0.0, 2.4, 0.0, 1.2, 0.52, +1.0)
    window_head = _patch(0.0, 2.4, 0.0, 1.2, 1.99, -1.0)
    trace = _patch(1.0, 1.25, 0.4, 0.65, 2.95, -1.0)
    levels = detect_levels(_cloud([ledge, window_head, trace]))
    assert levels.height is None


def test_a_light_fitting_alone_is_not_a_ceiling():
    floor = _patch(0.0, 3.0, 0.0, 3.0, 0.0, +1.0)
    fitting = _patch(1.32, 1.66, 1.32, 1.66, 2.45, -1.0)
    levels = detect_levels(_cloud([floor, fitting]))
    assert levels.height is None
    assert "unmeasured" in levels.warnings[0]
