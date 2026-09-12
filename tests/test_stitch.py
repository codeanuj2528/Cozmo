"""Tests for multi-room stitching, pose graph optimization, and drift correction."""

from __future__ import annotations

import numpy as np
import pytest

from cozmo.geometry.drift import correct_drift, propose_loops


def _synthetic_loop_trajectory(n_frames: int = 100):
    """Generate a trajectory walking out and returning to origin with drift."""
    poses = []
    half = n_frames // 2
    for i in range(n_frames):
        pose = np.eye(4)
        if i < half:
            tx = i * 0.05
            tz = 0.0
        else:
            steps_back = i - half
            tx = (half - steps_back) * 0.05
            tz = steps_back * 0.005  # Drift
        pose[:3, 3] = [tx, 1.2, tz]
        poses.append(pose)
    return np.array(poses)


def test_find_loop_closures():
    poses = _synthetic_loop_trajectory(100)
    keyframes = list(range(0, len(poses), 2))

    closures = propose_loops(poses, keyframes, radius_m=2.5, min_gap=10)
    assert isinstance(closures, list)


def test_no_loop_closure_one_way():
    poses = [np.eye(4) for _ in range(50)]
    for i, p in enumerate(poses):
        p[:3, 3] = [i * 0.1, 1.2, 0.0]
    kf_poses = np.array(poses)
    keyframes = list(range(50))

    closures = propose_loops(kf_poses, keyframes, radius_m=0.3, min_gap=15)
    assert len(closures) == 0


def _box_room(room_id: str, origin: tuple[float, float], size: tuple[float, float], area: float) -> Room:
    from cozmo.schema import Measure, Room

    x0, y0 = origin
    w, h = size
    return Room(
        room_id=room_id,
        label="room",
        polygon=[(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)],
        walls=[],
        surfaces=[],
        openings=[],
        ceiling_height=None,
        floor_area=Measure(value=area, lo=area * 0.95, hi=area * 1.05, unit="m2"),
        perimeter=Measure(value=2 * (w + h), lo=2 * (w + h) - 0.1, hi=2 * (w + h) + 0.1, unit="m"),
        observation_quality=0.9,
    )


def test_close_declared_gaps_pulls_rooms_together():
    from shapely.geometry import Polygon

    from cozmo.geometry.assemble import close_declared_gaps
    from cozmo.schema import Adjacency

    a = _box_room("room_01", (0.0, 0.0), (4.0, 3.0), 12.0)
    b = _box_room("room_02", (4.4, 0.0), (3.0, 3.0), 9.0)  # 40 cm void
    assert Polygon(a.polygon).distance(Polygon(b.polygon)) == pytest.approx(0.4)
    warnings = close_declared_gaps(
        [a, b],
        [Adjacency(room_a="room_01", room_b="room_02", opening_a="", opening_b=None, confidence=0.8, evidence="walked")],
    )
    assert warnings
    assert Polygon(a.polygon).distance(Polygon(b.polygon)) < 0.02
    # The larger room stays put; the smaller one moves.
    assert a.polygon[0] == (0.0, 0.0)
    assert b.floor_area.value == 9.0


def test_close_declared_gaps_does_not_reopen_the_first_pair():
    from shapely.geometry import Polygon

    from cozmo.geometry.assemble import close_declared_gaps
    from cozmo.schema import Adjacency

    a = _box_room("room_01", (0.0, 0.0), (3.0, 3.0), 9.0)
    b = _box_room("room_02", (3.0, 0.0), (3.0, 3.0), 9.0)  # already touching a
    c = _box_room("room_03", (6.4, 0.0), (2.0, 3.0), 6.0)  # 40 cm from b
    close_declared_gaps(
        [a, b, c],
        [
            Adjacency(room_a="room_01", room_b="room_02", opening_a="", opening_b=None, confidence=0.8, evidence="w"),
            Adjacency(room_a="room_02", room_b="room_03", opening_a="", opening_b=None, confidence=0.8, evidence="w"),
        ],
    )
    pa, pb, pc = Polygon(a.polygon), Polygon(b.polygon), Polygon(c.polygon)
    assert pa.distance(pb) < 0.02
    assert pb.distance(pc) < 0.02


def test_merge_diagonal_splits_joins_fat_overlap_not_a_thin_wall():
    from shapely.geometry import box

    from cozmo.geometry.cellcomplex import _merge_diagonal_splits

    # Two halves of one L, overlapping in a fat 2.2 x 1.8 m region.
    left = box(0, 0, 4, 4)
    right = box(2, 2, 7, 6)
    merged = _merge_diagonal_splits({0: left, 1: right})
    assert len(merged) == 1

    # Two rooms that only overlap in a 3.0 x 0.12 m partition strip must stay two.
    a = box(0, 0, 3.06, 4)
    b = box(2.94, 0, 6, 4)
    stayed = _merge_diagonal_splits({0: a, 1: b})
    assert len(stayed) == 2
