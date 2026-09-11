"""Floor and ceiling extraction, and the gravity refinement that has to precede it.

ARKit's gravity estimate is good but not exact. A residual tilt of one degree tips a 5 m
room by 8.7 cm end to end, which on its own would blow the 1.5 cm ceiling-height gate
before any other error source is considered. So the first thing this module does is refit
the world's up axis to the observed floor plane and rotate the cloud onto it. Everything
downstream, including the wall verticality test and the height band used for wall
evidence, assumes that correction has already been applied.

Floor and ceiling are found as modes of a weighted height histogram restricted by normal
direction, not as the minimum and maximum of the cloud. Extremes are where the stray
returns live: a single point that leaked under a door would otherwise set the floor.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import gaussian_filter1d

from cozmo.geometry.fusion import FusedCloud
from cozmo.geometry.planes import PlaneFit, fit_plane, refit_with_inliers
from cozmo.util.transforms import UP

HORIZONTAL_NORMAL_TOLERANCE_RAD = np.deg2rad(20.0)
HISTOGRAM_BIN_M = 0.01
MIN_CEILING_CLEARANCE_M = 1.6
MAX_CEILING_CLEARANCE_M = 4.5


@dataclass
class LevelEstimate:
    floor: PlaneFit
    ceiling: PlaneFit | None
    floor_height: float
    ceiling_height: float | None
    height: float | None
    sigma_height: float | None
    ceiling_coverage: float
    warnings: list[str]


def _weighted_histogram(values: np.ndarray, weights: np.ndarray, bin_m: float):
    lo, hi = float(values.min()), float(values.max())
    if hi - lo < bin_m:
        hi = lo + bin_m
    bins = np.arange(lo, hi + bin_m, bin_m)
    hist, edges = np.histogram(values, bins=bins, weights=weights)
    centres = 0.5 * (edges[:-1] + edges[1:])
    return gaussian_filter1d(hist, sigma=1.5), centres


def _modes(hist: np.ndarray, centres: np.ndarray, min_fraction: float) -> list[tuple[float, float]]:
    """Local maxima above a fraction of the strongest peak, as (height, strength)."""
    if hist.size == 0:
        return []
    threshold = hist.max() * min_fraction
    out: list[tuple[float, float]] = []
    for i in range(1, len(hist) - 1):
        if hist[i] >= hist[i - 1] and hist[i] > hist[i + 1] and hist[i] >= threshold:
            out.append((float(centres[i]), float(hist[i])))
    if not out and hist.max() > 0:
        i = int(np.argmax(hist))
        out.append((float(centres[i]), float(hist[i])))
    return out


def _horizontal_mask(cloud: FusedCloud, facing: int) -> np.ndarray:
    """Points on horizontal surfaces. `facing` is +1 for upward, -1 for downward normals."""
    cos_tol = np.cos(HORIZONTAL_NORMAL_TOLERANCE_RAD)
    ny = cloud.normals[:, 1]
    return (ny * facing) > cos_tol


def refine_gravity(cloud: FusedCloud) -> tuple[np.ndarray, PlaneFit, list[str]]:
    """Rotation that puts the observed floor normal on +y, plus the floor plane it used."""
    warnings: list[str] = []
    up_mask = _horizontal_mask(cloud, +1)
    if up_mask.sum() < 200:
        warnings.append("too few upward-facing points to refine gravity; using sensor gravity")
        return np.eye(3), fit_plane(cloud.points[up_mask] if up_mask.sum() >= 3 else cloud.points,
                                    cloud.weight[up_mask] if up_mask.sum() >= 3 else cloud.weight), warnings

    heights = cloud.points[up_mask, 1]
    weights = cloud.weight[up_mask]
    hist, centres = _weighted_histogram(heights, weights, HISTOGRAM_BIN_M)
    modes = _modes(hist, centres, min_fraction=0.10)
    floor_level = min(m[0] for m in modes)

    near = np.abs(heights - floor_level) < 0.06
    if near.sum() < 50:
        warnings.append("weak floor support; gravity left as sensor reported")
        return np.eye(3), fit_plane(cloud.points[up_mask][near] if near.sum() >= 3 else cloud.points[up_mask],
                                    weights[near] if near.sum() >= 3 else weights), warnings

    plane = fit_plane(cloud.points[up_mask][near], weights[near]).flip_to(UP)
    plane, inliers = refit_with_inliers(
        cloud.points[up_mask], weights, plane, threshold_m=0.04, iterations=3
    )
    plane = plane.flip_to(UP)

    tilt = float(np.arccos(np.clip(plane.normal @ UP, -1.0, 1.0)))
    if tilt > np.deg2rad(6.0):
        warnings.append(f"floor plane tilted {np.rad2deg(tilt):.1f} deg from sensor gravity; not applied")
        return np.eye(3), plane, warnings

    axis = np.cross(plane.normal, UP)
    s = float(np.linalg.norm(axis))
    if s < 1e-9:
        return np.eye(3), plane, warnings
    axis /= s
    angle = tilt
    kx = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    rotation = np.eye(3) + np.sin(angle) * kx + (1 - np.cos(angle)) * (kx @ kx)
    _ = inliers
    return rotation, plane, warnings


def detect_levels(cloud: FusedCloud, footprint_area_m2: float | None = None) -> LevelEstimate:
    """Floor and ceiling planes of an already gravity-corrected cloud."""
    warnings: list[str] = []

    up_mask = _horizontal_mask(cloud, +1)
    if up_mask.sum() < 50:
        raise ValueError("no floor surface observed")

    floor_heights = cloud.points[up_mask, 1]
    hist, centres = _weighted_histogram(floor_heights, cloud.weight[up_mask], HISTOGRAM_BIN_M)
    floor_level = min(m[0] for m in _modes(hist, centres, min_fraction=0.08))
    near_floor = np.abs(floor_heights - floor_level) < 0.05
    floor_plane = fit_plane(cloud.points[up_mask][near_floor], cloud.weight[up_mask][near_floor]).flip_to(UP)
    floor_level = float(-floor_plane.offset / floor_plane.normal[1])

    down_mask = _horizontal_mask(cloud, -1)
    above = cloud.points[:, 1] > floor_level + MIN_CEILING_CLEARANCE_M
    below = cloud.points[:, 1] < floor_level + MAX_CEILING_CLEARANCE_M
    ceiling_mask = down_mask & above & below

    ceiling_plane: PlaneFit | None = None
    ceiling_level: float | None = None
    height: float | None = None
    sigma_height: float | None = None
    coverage = 0.0

    if ceiling_mask.sum() >= 50:
        ceil_heights = cloud.points[ceiling_mask, 1]
        chist, ccentres = _weighted_histogram(ceil_heights, cloud.weight[ceiling_mask], HISTOGRAM_BIN_M)
        cmodes = _modes(chist, ccentres, min_fraction=0.20)
        # The ceiling is the highest strong mode. Lower downward-facing modes are soffits,
        # beams, cabinet undersides and door heads, which are real but are not the ceiling.
        ceiling_level = max(m[0] for m in cmodes)
        near_ceiling = np.abs(ceil_heights - ceiling_level) < 0.05
        if near_ceiling.sum() >= 20:
            ceiling_plane = fit_plane(
                cloud.points[ceiling_mask][near_ceiling], cloud.weight[ceiling_mask][near_ceiling]
            ).flip_to(-UP)
            ceiling_level = float(-ceiling_plane.offset / ceiling_plane.normal[1])

            height = float(ceiling_level - floor_level)
            # Propagate both plane offsets, plus a term for the two planes not being
            # exactly parallel evaluated over the room's own extent.
            span = float(np.ptp(cloud.points[ceiling_mask][near_ceiling][:, [0, 2]], axis=0).max())
            tilt = float(np.arccos(np.clip(abs(ceiling_plane.normal @ floor_plane.normal), -1.0, 1.0)))
            sigma_height = float(
                np.sqrt(
                    floor_plane.sigma_offset**2
                    + ceiling_plane.sigma_offset**2
                    + (0.5 * span * np.tan(tilt)) ** 2
                )
            )
            pts = cloud.points[ceiling_mask][near_ceiling][:, [0, 2]]
            observed_area = float(np.prod(np.ptp(pts, axis=0))) if len(pts) > 2 else 0.0
            if footprint_area_m2 and footprint_area_m2 > 0:
                coverage = float(np.clip(observed_area / footprint_area_m2, 0.0, 1.0))

    if ceiling_plane is None:
        warnings.append("no ceiling surface observed; ceiling height is unmeasured at this capture")
    elif coverage and coverage < 0.15:
        warnings.append(f"ceiling observed over only {coverage:.0%} of the footprint")

    return LevelEstimate(
        floor=floor_plane,
        ceiling=ceiling_plane,
        floor_height=floor_level,
        ceiling_height=ceiling_level,
        height=height,
        sigma_height=sigma_height,
        ceiling_coverage=coverage,
        warnings=warnings,
    )
