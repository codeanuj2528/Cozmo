"""Weighted plane fitting and sequential plane extraction.

Plane fits are weighted by each point's inverse variance, which is what carries the LiDAR
confidence channel and the range-dependent noise model into the wall and ceiling numbers.

The offset uncertainty reported by `fit_plane` is the larger of two estimates: the one the
sensor noise model predicts, and the one the observed residual scatter implies. Real walls
are not perfectly planar, they are plastered, papered and occasionally bowed, so trusting
the sensor model alone produces intervals that are too narrow and a calibration table that
under-covers. Taking the larger of the two is the conservative choice and it is what keeps
the reported coverage close to nominal.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class PlaneFit:
    """A plane n . x + d = 0 with the uncertainty of its offset."""

    normal: np.ndarray
    offset: float
    sigma_offset: float
    sigma_angle_rad: float
    inlier_count: int
    residual_rms: float
    effective_n: float

    def distance(self, points: np.ndarray) -> np.ndarray:
        return points @ self.normal + self.offset

    def project(self, points: np.ndarray) -> np.ndarray:
        return points - np.outer(self.distance(points), self.normal)

    def flip_to(self, reference: np.ndarray) -> PlaneFit:
        """Return the same plane with its normal on the side of `reference`."""
        if self.normal @ reference < 0:
            return PlaneFit(
                -self.normal, -self.offset, self.sigma_offset, self.sigma_angle_rad,
                self.inlier_count, self.residual_rms, self.effective_n,
            )
        return self


def fit_plane(points: np.ndarray, weights: np.ndarray | None = None) -> PlaneFit:
    """Weighted total-least-squares plane through `points`."""
    points = np.asarray(points, dtype=np.float64)
    if len(points) < 3:
        raise ValueError("a plane needs at least three points")
    w = np.ones(len(points)) if weights is None else np.asarray(weights, dtype=np.float64)
    w = np.maximum(w, 1e-12)
    wsum = w.sum()

    centroid = (points * w[:, None]).sum(axis=0) / wsum
    centred = points - centroid
    scatter = (centred * w[:, None]).T @ centred / wsum
    evals, evecs = np.linalg.eigh(scatter)
    normal = evecs[:, 0]
    offset = float(-normal @ centroid)

    residual = centred @ normal
    residual_rms = float(np.sqrt((w * residual**2).sum() / wsum))

    # Effective sample size: a thousand returns from one viewpoint are not a thousand
    # independent looks at the wall, and Kish's formula is the standard discount for that.
    effective_n = float(wsum**2 / np.maximum((w**2).sum(), 1e-12))

    sigma_from_model = float(np.sqrt(1.0 / wsum))
    sigma_from_residual = float(residual_rms / np.sqrt(max(effective_n, 1.0)))
    sigma_offset = max(sigma_from_model, sigma_from_residual)

    # Angular uncertainty from the ratio of the out-of-plane spread to the in-plane spread.
    spread = float(np.sqrt(max(evals[1], 1e-12)))
    sigma_angle = float(np.arctan2(residual_rms / np.sqrt(max(effective_n, 1.0)), max(spread, 1e-6)))

    return PlaneFit(
        normal=normal,
        offset=offset,
        sigma_offset=sigma_offset,
        sigma_angle_rad=sigma_angle,
        inlier_count=len(points),
        residual_rms=residual_rms,
        effective_n=effective_n,
    )


def refit_with_inliers(
    points: np.ndarray,
    weights: np.ndarray,
    plane: PlaneFit,
    threshold_m: float,
    iterations: int = 3,
) -> tuple[PlaneFit, np.ndarray]:
    """Alternate between selecting inliers and refitting. Converges in a few passes."""
    inliers = np.abs(plane.distance(points)) < threshold_m
    for _ in range(iterations):
        if inliers.sum() < 3:
            break
        plane = fit_plane(points[inliers], weights[inliers])
        new = np.abs(plane.distance(points)) < threshold_m
        if new.sum() == inliers.sum():
            inliers = new
            break
        inliers = new
    return plane, inliers


def ransac_plane(
    points: np.ndarray,
    weights: np.ndarray,
    normals: np.ndarray | None = None,
    threshold_m: float = 0.03,
    iterations: int = 200,
    normal_tolerance_rad: float = np.deg2rad(20.0),
    rng: np.random.Generator | None = None,
) -> tuple[PlaneFit, np.ndarray] | None:
    """Single-plane RANSAC, scored by summed inlier weight rather than inlier count.

    Weight-based scoring matters because an unweighted count lets a dense cluster of noisy
    close-range returns outvote a sparse but precise observation of the actual wall.
    """
    n = len(points)
    if n < 3:
        return None
    rng = rng or np.random.default_rng(0)

    best_score = -np.inf
    best: tuple[PlaneFit, np.ndarray] | None = None
    probs = weights / weights.sum()

    for _ in range(iterations):
        idx = rng.choice(n, size=3, replace=False, p=probs)
        trio = points[idx]
        normal = np.cross(trio[1] - trio[0], trio[2] - trio[0])
        length = np.linalg.norm(normal)
        if length < 1e-9:
            continue
        normal = normal / length
        offset = -normal @ trio[0]
        dist = np.abs(points @ normal + offset)
        inliers = dist < threshold_m
        if normals is not None:
            agree = np.abs(normals @ normal) > np.cos(normal_tolerance_rad)
            inliers &= agree
        score = weights[inliers].sum()
        if score > best_score:
            best_score = score
            best = (fit_plane(points[inliers], weights[inliers]), inliers) if inliers.sum() >= 3 else None

    if best is None:
        return None
    plane, _ = best
    plane, inliers = refit_with_inliers(points, weights, plane, threshold_m)
    if normals is not None:
        inliers &= np.abs(normals @ plane.normal) > np.cos(normal_tolerance_rad)
    if inliers.sum() < 3:
        return None
    return fit_plane(points[inliers], weights[inliers]), inliers


def extract_planes(
    points: np.ndarray,
    weights: np.ndarray,
    normals: np.ndarray,
    max_planes: int = 40,
    threshold_m: float = 0.03,
    min_inlier_weight_fraction: float = 0.004,
    iterations: int = 160,
    seed: int = 0,
) -> list[tuple[PlaneFit, np.ndarray]]:
    """Sequential RANSAC: fit the strongest plane, remove its inliers, repeat.

    Returns (plane, index array into the original points) pairs, strongest first.
    """
    rng = np.random.default_rng(seed)
    remaining = np.arange(len(points))
    total_weight = float(weights.sum())
    found: list[tuple[PlaneFit, np.ndarray]] = []

    for _ in range(max_planes):
        if len(remaining) < 50:
            break
        result = ransac_plane(
            points[remaining], weights[remaining], normals[remaining],
            threshold_m=threshold_m, iterations=iterations, rng=rng,
        )
        if result is None:
            break
        plane, inliers = result
        if weights[remaining][inliers].sum() < min_inlier_weight_fraction * total_weight:
            break
        found.append((plane, remaining[inliers]))
        remaining = remaining[~inliers]

    return found
