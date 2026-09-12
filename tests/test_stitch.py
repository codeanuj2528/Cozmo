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
