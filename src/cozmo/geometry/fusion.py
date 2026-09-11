"""Depth fusion: frames to a single weighted point cloud in the property frame.

Two decisions here carry most of the downstream accuracy.

Normals are computed in image space from neighbouring back-projected pixels rather than by
a k-nearest-neighbour PCA over the fused cloud. Image-space normals are O(N), they respect
the sensor's own sampling pattern, and a depth discontinuity is a cheap local test rather
than something a radius search has to be tuned to avoid straddling.

Points are reduced on a voxel grid with inverse-variance weighting, so a 3 m return at
ARKit confidence 0 does not drag a voxel that a 1 m confidence-2 return already pins down.
The per-voxel variance that falls out of that weighting is carried forward and becomes the
weight in every plane fit, which is where the wall and ceiling numbers come from.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from cozmo.io.base import CaptureSource, Frame
from cozmo.util.transforms import backproject, pose_distance, transform_points

KEYFRAME_TRANSLATION_M = 0.08
KEYFRAME_ROTATION_RAD = np.deg2rad(6.0)
MAX_KEYFRAMES = 600
DEPTH_DISCONTINUITY_M = 0.06


@dataclass
class FusedCloud:
    """Voxel-reduced world points with the uncertainty that produced them."""

    points: np.ndarray
    normals: np.ndarray
    sigma: np.ndarray
    weight: np.ndarray
    view_dir: np.ndarray
    range_m: np.ndarray
    frame_index: np.ndarray
    voxel_m: float = 0.02

    def __len__(self) -> int:
        return len(self.points)

    @property
    def height(self) -> np.ndarray:
        """World y, which is the gravity axis."""
        return self.points[:, 1]

    @property
    def cameras(self) -> np.ndarray:
        """Position of the camera that observed each point.

        Reconstructed from the point, its view ray and its range rather than plumbed
        through from the pose list, so any consumer of a cloud can recover the ray that
        produced a point without also needing the capture it came from. Occlusion
        reasoning and see-through detection both need that ray.
        """
        return self.points + self.view_dir * self.range_m[:, None]

    def select(self, mask: np.ndarray) -> FusedCloud:
        return FusedCloud(
            points=self.points[mask],
            normals=self.normals[mask],
            sigma=self.sigma[mask],
            weight=self.weight[mask],
            view_dir=self.view_dir[mask],
            range_m=self.range_m[mask],
            frame_index=self.frame_index[mask],
            voxel_m=self.voxel_m,
        )

    def rotated(self, rotation: np.ndarray) -> FusedCloud:
        """Rigidly rotate the cloud about the origin, normals and view rays included."""
        return FusedCloud(
            points=(self.points @ rotation.T).astype(np.float32),
            normals=(self.normals @ rotation.T).astype(np.float32),
            sigma=self.sigma,
            weight=self.weight,
            view_dir=(self.view_dir @ rotation.T).astype(np.float32),
            range_m=self.range_m,
            frame_index=self.frame_index,
            voxel_m=self.voxel_m,
        )

    @property
    def verticality(self) -> np.ndarray:
        """1 for a perfectly vertical surface (wall), 0 for a horizontal one."""
        return 1.0 - np.abs(self.normals[:, 1])


def select_keyframes(
    poses: np.ndarray,
    translation_m: float = KEYFRAME_TRANSLATION_M,
    rotation_rad: float = KEYFRAME_ROTATION_RAD,
    max_frames: int = MAX_KEYFRAMES,
) -> list[int]:
    """Pick frames that actually add viewpoint, not frames that add file size.

    A handheld walkthrough spends much of its duration nearly stationary. Fusing every
    frame multiplies redundant returns from one viewpoint, which biases a plane fit toward
    wherever the operator paused rather than toward the surface.
    """
    if len(poses) == 0:
        return []
    chosen = [0]
    last = poses[0]
    for i in range(1, len(poses)):
        dt, dr = pose_distance(last, poses[i])
        if dt >= translation_m or dr >= rotation_rad:
            chosen.append(i)
            last = poses[i]
    if len(chosen) > max_frames:
        step = len(chosen) / max_frames
        chosen = [chosen[int(i * step)] for i in range(max_frames)]
    return chosen


def image_normals(points_img: np.ndarray, valid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Normals from a back-projected depth image, held in image layout.

    Returns (normals, ok) both in image layout. A pixel is rejected when either of its
    neighbour pairs straddles a depth discontinuity, because a normal computed across an
    occlusion boundary points nowhere real and is exactly the kind of point that later
    votes for a wall that does not exist.
    """
    h, w, _ = points_img.shape
    normals = np.zeros((h, w, 3), dtype=np.float32)
    ok = np.zeros((h, w), dtype=bool)

    right = np.zeros_like(points_img)
    down = np.zeros_like(points_img)
    right[:, :-1] = points_img[:, 1:] - points_img[:, :-1]
    down[:-1, :] = points_img[1:, :] - points_img[:-1, :]

    z = points_img[:, :, 2]
    dz_r = np.zeros((h, w), dtype=np.float32)
    dz_d = np.zeros((h, w), dtype=np.float32)
    dz_r[:, :-1] = np.abs(z[:, 1:] - z[:, :-1])
    dz_d[:-1, :] = np.abs(z[1:, :] - z[:-1, :])

    neighbours_valid = np.zeros((h, w), dtype=bool)
    neighbours_valid[:-1, :-1] = valid[:-1, :-1] & valid[:-1, 1:] & valid[1:, :-1]
    # Scale the discontinuity tolerance with range: the same surface slant produces a
    # larger inter-pixel depth step further away.
    tol = DEPTH_DISCONTINUITY_M * np.maximum(1.0, z)
    smooth = (dz_r < tol) & (dz_d < tol)

    cand = neighbours_valid & smooth
    n = np.cross(right, down)
    norm = np.linalg.norm(n, axis=2)
    good = cand & (norm > 1e-9)
    normals[good] = n[good] / norm[good][:, None]
    ok[good] = True
    return normals, ok


def _frame_points(frame: Frame, pixel_stride: int, min_confidence: int, max_range_m: float):
    depth = frame.depth
    if depth is None:
        return None
    h, w = depth.shape
    valid = (depth > 0.15) & (depth < max_range_m) & np.isfinite(depth)
    if frame.confidence is not None and min_confidence > 0:
        valid &= frame.confidence >= min_confidence
    if not valid.any():
        return None

    vs, us = np.mgrid[0:h, 0:w]
    k = frame.k_depth
    z = depth.astype(np.float32)
    x = (us - k[0, 2]) * z / k[0, 0]
    y = (vs - k[1, 2]) * z / k[1, 1]
    points_img = np.stack([x, y, z], axis=2).astype(np.float32)

    normals_img, normal_ok = image_normals(points_img, valid)
    keep = valid & normal_ok
    if pixel_stride > 1:
        sub = np.zeros_like(keep)
        sub[::pixel_stride, ::pixel_stride] = True
        keep &= sub
    if not keep.any():
        return None

    pts_cam = points_img[keep]
    nrm_cam = normals_img[keep]
    sigma = (
        frame.depth_sigma[keep]
        if frame.depth_sigma is not None
        else np.full(len(pts_cam), 0.02, dtype=np.float32)
    )

    # Orient each normal toward the camera. A surface normal that points away from the
    # sensor that measured it is a sign convention error, not a physical observation.
    flip = np.einsum("ij,ij->i", nrm_cam, pts_cam) > 0
    nrm_cam[flip] *= -1.0

    pose = frame.pose
    pts_w = transform_points(pose, pts_cam.astype(np.float64)).astype(np.float32)
    nrm_w = (nrm_cam.astype(np.float64) @ pose[:3, :3].T).astype(np.float32)
    cam_w = pose[:3, 3].astype(np.float32)
    view = cam_w[None, :] - pts_w
    ranges = np.linalg.norm(view, axis=1)
    view /= np.maximum(ranges, 1e-9)[:, None]
    return pts_w, nrm_w, sigma, view, ranges.astype(np.float32)


def fuse(
    source: CaptureSource,
    keyframes: Iterable[int],
    voxel_m: float = 0.015,
    pixel_stride: int = 1,
    min_confidence: int = 1,
    max_range_m: float = 5.0,
) -> FusedCloud:
    """Fuse selected frames into one inverse-variance-weighted cloud."""
    all_pts, all_nrm, all_sig, all_view, all_rng, all_idx = [], [], [], [], [], []
    for frame in source.frames(list(keyframes)):
        if frame.pose is None:
            continue
        got = _frame_points(frame, pixel_stride, min_confidence, max_range_m)
        if got is None:
            continue
        pts, nrm, sig, view, rng = got
        all_pts.append(pts)
        all_nrm.append(nrm)
        all_sig.append(sig)
        all_view.append(view)
        all_rng.append(rng)
        all_idx.append(np.full(len(pts), frame.index, dtype=np.int32))

    if not all_pts:
        empty3 = np.zeros((0, 3), dtype=np.float32)
        empty1 = np.zeros(0, dtype=np.float32)
        return FusedCloud(
            empty3, empty3, empty1, empty1, empty3, empty1, np.zeros(0, dtype=np.int32), voxel_m
        )

    points = np.concatenate(all_pts)
    normals = np.concatenate(all_nrm)
    sigma = np.concatenate(all_sig)
    view = np.concatenate(all_view)
    ranges = np.concatenate(all_rng)
    frame_index = np.concatenate(all_idx)
    return voxel_reduce(points, normals, sigma, view, ranges, frame_index, voxel_m)


def voxel_reduce(
    points: np.ndarray,
    normals: np.ndarray,
    sigma: np.ndarray,
    view: np.ndarray,
    ranges: np.ndarray,
    frame_index: np.ndarray,
    voxel_m: float,
) -> FusedCloud:
    """Collapse points onto a voxel grid, averaging with inverse-variance weights."""
    weight = 1.0 / np.maximum(sigma.astype(np.float64) ** 2, 1e-8)
    keys = np.floor(points.astype(np.float64) / voxel_m).astype(np.int64)
    _, inverse, counts = np.unique(keys, axis=0, return_inverse=True, return_counts=True)
    inverse = inverse.ravel()
    n_vox = len(counts)

    wsum = np.bincount(inverse, weights=weight, minlength=n_vox)
    out_pts = np.stack(
        [np.bincount(inverse, weights=points[:, d] * weight, minlength=n_vox) / wsum for d in range(3)],
        axis=1,
    )
    out_nrm = np.stack(
        [np.bincount(inverse, weights=normals[:, d] * weight, minlength=n_vox) for d in range(3)], axis=1
    )
    nlen = np.linalg.norm(out_nrm, axis=1, keepdims=True)
    out_nrm = np.divide(out_nrm, np.maximum(nlen, 1e-9))
    out_view = np.stack(
        [np.bincount(inverse, weights=view[:, d] * weight, minlength=n_vox) for d in range(3)], axis=1
    )
    vlen = np.linalg.norm(out_view, axis=1, keepdims=True)
    out_view = np.divide(out_view, np.maximum(vlen, 1e-9))

    # Combining k independent observations of the same voxel shrinks the variance as the
    # reciprocal of the summed precision. Averaging the sigmas instead would throw away
    # the benefit of having looked at the same wall from several viewpoints.
    out_sigma = np.sqrt(1.0 / wsum)
    out_range = np.bincount(inverse, weights=ranges * weight, minlength=n_vox) / wsum
    first_idx = np.zeros(n_vox, dtype=np.int32)
    order = np.argsort(inverse, kind="stable")
    first_positions = np.searchsorted(inverse[order], np.arange(n_vox))
    first_idx[:] = frame_index[order][first_positions]

    return FusedCloud(
        points=out_pts.astype(np.float32),
        normals=out_nrm.astype(np.float32),
        sigma=out_sigma.astype(np.float32),
        weight=wsum.astype(np.float32),
        view_dir=out_view.astype(np.float32),
        range_m=out_range.astype(np.float32),
        frame_index=first_idx,
        voxel_m=float(voxel_m),
    )
