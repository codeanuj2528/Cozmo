"""Tests for geometric algorithms and wall fitting."""

from __future__ import annotations

import numpy as np
from cozmo.util.polygons import rotation_about_up


def test_rotation_about_up():
    angle = np.pi / 4.0
    rot = rotation_about_up(angle)
    assert rot.shape == (3, 3)
    assert np.allclose(rot @ rot.T, np.eye(3))
    # Vector pointing along X should rotate in XZ plane
    v = np.array([1.0, 0.0, 0.0])
    v_rot = v @ rot.T
    assert v_rot[1] == 0.0
