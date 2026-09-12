"""Synthetic data generators for testing.

These generators produce reproducible point clouds, depth maps and room
geometries that exercise the pipeline without requiring real sensor data.

Every generator accepts a ``seed`` parameter so that tests are deterministic.
"""

from __future__ import annotations

import numpy as np
from typing import Optional


def generate_box_room(
    width: float = 4.0,
    depth: float = 5.0,
    height: float = 2.5,
    n_points: int = 50_000,
    noise_m: float = 0.005,
    seed: int = 42,
) -> np.ndarray:
    """Generate a synthetic point cloud for a rectangular room.

    Points are distributed across the floor, ceiling and four walls with
    uniform density and Gaussian noise.

    Returns (N, 3) float32 points.
    """
    rng = np.random.default_rng(seed)

    def _sample_plane(origin, u_axis, v_axis, u_range, v_range, n):
        us = rng.uniform(*u_range, n)
        vs = rng.uniform(*v_range, n)
        pts = origin + np.outer(us, u_axis) + np.outer(vs, v_axis)
        pts += rng.normal(0, noise_m, pts.shape)
        return pts.astype(np.float32)

    pts_per_face = n_points // 6
    clouds = []

    # Floor (y = 0).
    clouds.append(_sample_plane(
        np.array([0, 0, 0]), np.array([1, 0, 0]), np.array([0, 0, 1]),
        (0, width), (0, depth), pts_per_face
    ))

    # Ceiling (y = height).
    clouds.append(_sample_plane(
        np.array([0, height, 0]), np.array([1, 0, 0]), np.array([0, 0, 1]),
        (0, width), (0, depth), pts_per_face
    ))

    # Wall x=0.
    clouds.append(_sample_plane(
        np.array([0, 0, 0]), np.array([0, 1, 0]), np.array([0, 0, 1]),
        (0, height), (0, depth), pts_per_face
    ))

    # Wall x=width.
    clouds.append(_sample_plane(
        np.array([width, 0, 0]), np.array([0, 1, 0]), np.array([0, 0, 1]),
        (0, height), (0, depth), pts_per_face
    ))

    # Wall z=0.
    clouds.append(_sample_plane(
        np.array([0, 0, 0]), np.array([1, 0, 0]), np.array([0, 1, 0]),
        (0, width), (0, height), pts_per_face
    ))

    # Wall z=depth.
    clouds.append(_sample_plane(
        np.array([0, 0, depth]), np.array([1, 0, 0]), np.array([0, 1, 0]),
        (0, width), (0, height), pts_per_face
    ))

    return np.concatenate(clouds)


def generate_l_shaped_room(
    wing_a_width: float = 3.0,
    wing_a_depth: float = 5.0,
    wing_b_width: float = 4.0,
    wing_b_depth: float = 3.0,
    height: float = 2.5,
    n_points: int = 80_000,
    seed: int = 42,
) -> np.ndarray:
    """Generate a synthetic L-shaped room point cloud.

    The L is formed by two rectangular wings joined at one corner.
    """
    pts_a = generate_box_room(wing_a_width, wing_a_depth, height, n_points // 2, seed=seed)
    pts_b = generate_box_room(wing_b_width, wing_b_depth, height, n_points // 2, seed=seed + 1)
    # Offset wing B.
    pts_b[:, 0] += wing_a_width
    return np.concatenate([pts_a, pts_b])


def generate_synthetic_depth_map(
    h: int = 480,
    w: int = 640,
    near: float = 0.5,
    far: float = 5.0,
    seed: int = 42,
) -> np.ndarray:
    """Generate a synthetic depth map with realistic structure.

    The depth map has a floor, ceiling and walls at realistic distances.
    """
    rng = np.random.default_rng(seed)

    depth = np.full((h, w), far, dtype=np.float32)

    # Floor gradient (bottom half).
    for row in range(h // 2, h):
        t = (row - h // 2) / (h // 2)
        depth[row, :] = near + (far - near) * (1 - t) * 0.5

    # Ceiling (top quarter).
    for row in range(h // 4):
        depth[row, :] = far * 0.8

    # Add noise.
    depth += rng.normal(0, 0.05, depth.shape).astype(np.float32)
    depth = np.clip(depth, 0.1, far * 1.5)

    return depth


def generate_camera_trajectory(
    n_frames: int = 100,
    room_width: float = 4.0,
    room_depth: float = 5.0,
    height: float = 1.5,
    seed: int = 42,
) -> np.ndarray:
    """Generate a realistic camera trajectory through a room.

    The trajectory is a smooth path that visits most of the room.
    Returns (N, 4, 4) float64 pose matrices.
    """
    rng = np.random.default_rng(seed)

    poses = np.zeros((n_frames, 4, 4), dtype=np.float64)

    # Walk in a rectangle inside the room.
    cx, cz = room_width / 2, room_depth / 2
    radius_x, radius_z = room_width * 0.35, room_depth * 0.35

    for i in range(n_frames):
        t = 2 * np.pi * i / n_frames
        x = cx + radius_x * np.cos(t)
        z = cz + radius_z * np.sin(t)
        y = height + rng.normal(0, 0.02)

        # Look towards the center.
        forward = np.array([cx - x, 0, cz - z])
        forward /= np.linalg.norm(forward) + 1e-8
        up = np.array([0, 1, 0])
        right = np.cross(forward, up)
        right /= np.linalg.norm(right) + 1e-8
        up = np.cross(right, forward)

        poses[i, :3, 0] = right
        poses[i, :3, 1] = up
        poses[i, :3, 2] = -forward  # camera looks along -z
        poses[i, :3, 3] = [x, y, z]
        poses[i, 3, 3] = 1.0

    return poses
