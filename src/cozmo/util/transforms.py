"""Rigid transforms, camera conventions and small geometric helpers.

Convention used everywhere in this codebase:

  * Camera frame is OpenCV: +x right, +y down, +z forward along the optical axis.
  * World frame is gravity aligned with +y up. This matches ARKit's world frame, which
    Stray Scanner writes into `odometry.csv`.
  * A pose `T_wc` is a 4x4 matrix mapping a point in the camera frame to the world frame.

The camera convention was not assumed. It was established by reconstructing a capture
under both the OpenCV and the OpenGL interpretation of the stored quaternion and keeping
the one that produces a gravity-consistent structure (see `tests/test_transforms.py` and
`docs/conventions.md`).
"""

from __future__ import annotations

import numpy as np

UP = np.array([0.0, 1.0, 0.0])


def quat_to_matrix(qx: float, qy: float, qz: float, qw: float) -> np.ndarray:
    """Rotation matrix from a scalar-last quaternion."""
    q = np.array([qx, qy, qz, qw], dtype=np.float64)
    n = np.linalg.norm(q)
    if n < 1e-12:
        raise ValueError("degenerate quaternion")
    x, y, z, w = q / n
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def matrix_to_quat(r: np.ndarray) -> np.ndarray:
    """Scalar-last quaternion from a rotation matrix, branch-selected for stability."""
    m = np.asarray(r, dtype=np.float64)
    trace = m[0, 0] + m[1, 1] + m[2, 2]
    if trace > 0.0:
        s = 0.5 / np.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (m[2, 1] - m[1, 2]) * s
        y = (m[0, 2] - m[2, 0]) * s
        z = (m[1, 0] - m[0, 1]) * s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = 2.0 * np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2])
        w = (m[2, 1] - m[1, 2]) / s
        x = 0.25 * s
        y = (m[0, 1] + m[1, 0]) / s
        z = (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = 2.0 * np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2])
        w = (m[0, 2] - m[2, 0]) / s
        x = (m[0, 1] + m[1, 0]) / s
        y = 0.25 * s
        z = (m[1, 2] + m[2, 1]) / s
    else:
        s = 2.0 * np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1])
        w = (m[1, 0] - m[0, 1]) / s
        x = (m[0, 2] + m[2, 0]) / s
        y = (m[1, 2] + m[2, 1]) / s
        z = 0.25 * s
    q = np.array([x, y, z, w])
    return q / np.linalg.norm(q)


def make_pose(rotation: np.ndarray, translation: np.ndarray) -> np.ndarray:
    t = np.eye(4)
    t[:3, :3] = rotation
    t[:3, 3] = translation
    return t


def invert_pose(t: np.ndarray) -> np.ndarray:
    out = np.eye(4)
    r = t[:3, :3]
    out[:3, :3] = r.T
    out[:3, 3] = -r.T @ t[:3, 3]
    return out


def transform_points(t: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Apply a 4x4 transform to an (N, 3) array."""
    return points @ t[:3, :3].T + t[:3, 3]


def scale_intrinsics(k: np.ndarray, from_size: tuple[int, int], to_size: tuple[int, int]) -> np.ndarray:
    """Rescale a pinhole intrinsic matrix between two image resolutions.

    `from_size` and `to_size` are (width, height). ARKit's depth map is a downscaled crop
    of the same frustum as the colour image, so a pure scale is the correct adjustment.
    """
    sx = to_size[0] / from_size[0]
    sy = to_size[1] / from_size[1]
    out = k.astype(np.float64).copy()
    out[0, 0] *= sx
    out[0, 2] *= sx
    out[1, 1] *= sy
    out[1, 2] *= sy
    return out


def backproject(depth: np.ndarray, k: np.ndarray, mask: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Back-project a depth image into camera-frame points.

    Returns (points, pixel_index) where `pixel_index` is the flat index of each point in
    the depth image, so per-pixel attributes can be carried along without re-deriving them.
    """
    h, w = depth.shape
    vs, us = np.mgrid[0:h, 0:w]
    if mask is None:
        mask = depth > 0
    us = us[mask].astype(np.float64)
    vs = vs[mask].astype(np.float64)
    z = depth[mask].astype(np.float64)
    x = (us - k[0, 2]) * z / k[0, 0]
    y = (vs - k[1, 2]) * z / k[1, 1]
    flat = (vs * w + us).astype(np.int64)
    return np.stack([x, y, z], axis=1), flat


def project(points: np.ndarray, k: np.ndarray) -> np.ndarray:
    """Project camera-frame points to pixels. Points behind the camera give NaN."""
    z = points[:, 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        u = points[:, 0] / z * k[0, 0] + k[0, 2]
        v = points[:, 1] / z * k[1, 1] + k[1, 2]
    uv = np.stack([u, v], axis=1)
    uv[z <= 1e-6] = np.nan
    return uv


def pose_distance(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """Translation (metres) and rotation (radians) between two poses."""
    dt = float(np.linalg.norm(a[:3, 3] - b[:3, 3]))
    r = a[:3, :3].T @ b[:3, :3]
    cos = np.clip((np.trace(r) - 1.0) / 2.0, -1.0, 1.0)
    return dt, float(np.arccos(cos))


def gravity_align(points: np.ndarray, up: np.ndarray) -> np.ndarray:
    """Rotation that takes `up` onto +y, leaving the yaw of the scene untouched."""
    up = up / np.linalg.norm(up)
    axis = np.cross(up, UP)
    s = np.linalg.norm(axis)
    if s < 1e-9:
        return np.eye(3) if up @ UP > 0 else np.diag([1.0, -1.0, -1.0])
    axis = axis / s
    angle = np.arccos(np.clip(up @ UP, -1.0, 1.0))
    kx = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    r = np.eye(3) + np.sin(angle) * kx + (1 - np.cos(angle)) * (kx @ kx)
    _ = points
    return r
