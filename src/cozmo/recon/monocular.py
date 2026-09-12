"""Turning unposed stills into metric, gravity-aligned, posed frames.

The whole design of this codebase is that a tier's job is to produce frames carrying
intrinsics, metric depth and a pose, after which one shared reconstruction core does the
rest. The LiDAR tier is handed all three. The photo tier has to manufacture them, and this
module is where that happens. Everything downstream -- walls, the cell complex, openings,
ceiling heights, the stitched plan -- is then literally the same code, which is the only
way three tiers stay comparable rather than becoming three products.

Three problems have to be solved per image, in order, because each depends on the last.

**Intrinsics.** Recovered from EXIF. An iPhone records `FocalLengthIn35mmFilm`, and
`fx = width * f35 / 36` follows from the definition of 35 mm equivalence. This is exact
when EXIF survives, which is why the capture protocol says not to send photos through
messaging apps: they strip it, and then focal length has to be assumed.

**Gravity.** A monocular depth map is a surface in camera coordinates with no notion of
up. The floor supplies it: the dominant near-horizontal plane below the camera has a normal
that is, by definition, up. Estimating gravity from the geometry rather than assuming the
photographer held the phone level is what lets a photo taken at a downward tilt still
produce a level plan.

**Scale.** The depth model used is the metric variant, so it already predicts metres. What
it does not do is predict them consistently: measured against LiDAR on the sample capture,
its per-frame scale factor ranges from 0.71 to 1.48 and its mean absolute relative error is
0.28, so a single global correction barely helps (0.280 to 0.241). A per-image physical
constraint is the obvious answer, and the camera's own height above the floor is the one
metric quantity present in every indoor photograph ever taken.

It is applied as a *correction to* the model, not a *replacement of* it, and only when the
two roughly agree. Applied unconditionally it made things three times worse -- 0.297 to
0.755 -- because the floor is not reliably the lowest strong horizontal plane in a
furnished room, and when the detected "floor" is really a bed or a countertop the implied
camera height is wrong and the correction propagates that error into every dimension. The
agreement gate keeps the correction where it helps and defers to the model where the floor
estimate is not credible, and the plan records which happened.

This is the dominant term in the photo tier's error budget, and it is why that tier's
intervals are wide. Note that the numbers above were measured on frames pulled from a video
walkthrough, which are motion-blurred; native stills should do better, and that will be
re-measured against the benchmark captures rather than assumed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from cozmo.geometry.planes import fit_plane, ransac_plane
from cozmo.util.transforms import UP

log = logging.getLogger(__name__)

# The capture protocol says "both hands at chest height, roughly 1.4 m off the floor".
# The spread across adult operators is what sets the photo tier's scale uncertainty, and
# it is the dominant term in that tier's error budget.
ASSUMED_CAMERA_HEIGHT_M = 1.40
CAMERA_HEIGHT_SIGMA_M = 0.14

# The camera-height correction is bounded only to reject a floor estimate that is
# physically impossible, not to keep it near the model's own answer.
#
# The band was [0.75, 1.35] and that was wrong. It was set while the intrinsics were being
# read from the wrong EXIF IFD, which distorted the cloud and made the floor fit unreliable,
# so keeping the correction near 1.0 was protective. With intrinsics correct the prior
# became both consistent and large: across the benchmark photographs it implies a camera
# height of 2.50-2.90 m where the operator held the phone at about 1.45 m, a correction
# near 0.57 -- and the old band rejected every one of them.
#
# The size is not a surprise once stated. A metric monocular model infers depth from
# apparent size, which requires an assumed focal length, and Depth Anything V2 Metric Indoor
# is trained on normal-field-of-view indoor imagery. These photographs are 0.5x ultra-wide
# at 88 degrees, well outside that, and the model over-predicts depth by about 1.76x as a
# result -- independently corroborated at 1.57x against LiDAR depth on the same property.
# Rejecting the correction meant shipping that factor straight into the floor area.
#
# The remaining bounds only exclude the physically absurd: a phone is not held at 30 cm and
# not at 4 m.
SCALE_CORRECTION_MIN = 0.25
SCALE_CORRECTION_MAX = 4.0
PLAUSIBLE_CAMERA_HEIGHT_M = (0.6, 2.4)

# 35 mm film is 36 mm wide. This is the definition of "35 mm equivalent focal length",
# not an approximation.
FILM_WIDTH_MM = 36.0
# Fallback for an image with no EXIF: the iPhone main camera is close to a 26 mm
# equivalent, which is a horizontal field of view of about 70 degrees.
DEFAULT_EQUIVALENT_FOCAL_MM = 26.0


@dataclass
class ScaleEstimate:
    factor: float
    source: str
    relative_uncertainty: float


@dataclass
class FrameGeometry:
    """One photograph, made metric and level."""

    depth_m: np.ndarray
    intrinsics: np.ndarray
    gravity_rotation: np.ndarray
    camera_height_m: float
    scale: ScaleEstimate
    floor_found: bool


# EXIF stores the photographic tags in a sub-IFD that IFD0 merely points at. Pillow's
# `getexif()` returns IFD0, so a lookup for a focal length there finds nothing on an iPhone
# JPEG and silently falls through to whatever default follows.
EXIF_SUB_IFD = 0x8769


def _focal_from_exif(path: Optional[Path]) -> tuple[float | None, str]:
    """The 35 mm equivalent focal length, and where it was found.

    The sub-IFD is checked first because that is where it actually is. Reading only IFD0
    cost this pipeline a factor of 1.86 on every photo-tier frame: all 58 photographs of the
    benchmark property carry `FocalLengthIn35mmFilm = 14`, taken on the 0.5x ultra-wide, and
    none of them was ever read, so every frame ran at the 26 mm main-camera prior.

    That error does not appear as a clean scale factor in the output. Back-projection is
    `X = (u - cx) Z / fx` with Z from the depth model and untouched by fx, so too long a
    focal length compresses the cloud laterally while leaving depth alone. The result is an
    anisotropic distortion rather than a similarity: the floor stops being planar, the floor
    fit that recovers camera height is then fitted to a curved surface, and the scale
    correction computed from that height is wrong in its own right. The 1.86 became +422% on
    the whole-property footprint by compounding through those three stages.

    Returning the provenance rather than logging it matters for the same reason the
    interval method does: a measured focal length and an assumed one carry very different
    uncertainty, and the plan should say which it had.
    """
    if path is None:
        return None, "no_file"
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
    except ImportError:
        return None, "pillow_unavailable"

    try:
        with Image.open(path) as image:
            base = image.getexif()
            if not base:
                return None, "no_exif"
            for ifd, label in ((base.get_ifd(EXIF_SUB_IFD), "exif_sub_ifd"), (base, "exif_ifd0")):
                if not ifd:
                    continue
                tags = {TAGS.get(k, k): v for k, v in ifd.items()}
                value = tags.get("FocalLengthIn35mmFilm")
                if value:
                    return float(value), f"{label}_35mm_equivalent"
    except Exception as exc:
        log.debug("EXIF unreadable for %s: %s", path, exc)
        return None, "exif_unreadable"
    return None, "exif_has_no_focal_length"


def intrinsics_from_exif(path: Optional[Path], width: int, height: int) -> tuple[np.ndarray, str]:
    """Pinhole intrinsics for a still, from EXIF where available.

    Returns the matrix and the provenance of the focal length, because a focal length that
    was assumed and one that was read carry different uncertainty and the plan says which.
    """
    equivalent_mm, source = _focal_from_exif(path)
    if not equivalent_mm or equivalent_mm <= 0:
        equivalent_mm = DEFAULT_EQUIVALENT_FOCAL_MM
        source = "assumed_iphone_main_camera"

    # The 35 mm equivalence is defined on the long edge of the frame.
    long_edge = max(width, height)
    focal_px = long_edge * equivalent_mm / FILM_WIDTH_MM
    k = np.array(
        [[focal_px, 0.0, width / 2.0], [0.0, focal_px, height / 2.0], [0.0, 0.0, 1.0]]
    )
    return k, source


def _backproject(depth: np.ndarray, k: np.ndarray, stride: int = 4) -> np.ndarray:
    h, w = depth.shape
    vs, us = np.mgrid[0:h:stride, 0:w:stride]
    z = depth[::stride, ::stride]
    good = np.isfinite(z) & (z > 1e-4)
    z = z[good].astype(np.float64)
    us = us[good].astype(np.float64)
    vs = vs[good].astype(np.float64)
    x = (us - k[0, 2]) * z / k[0, 0]
    y = (vs - k[1, 2]) * z / k[1, 1]
    return np.stack([x, y, z], axis=1)


def estimate_gravity_and_height(
    points: np.ndarray, seed: int = 0
) -> tuple[np.ndarray, float, bool]:
    """Find the floor and return (rotation to y-up, camera height above it, found).

    In the OpenCV camera frame the camera sits at the origin with +y pointing down, so the
    floor is the strong plane at positive y whose normal is close to vertical. Taking the
    lowest such plane rather than the strongest matters in a furnished room, where a bed or
    a table can present more visible horizontal surface than the floor does.
    """
    if len(points) < 200:
        return np.eye(3), ASSUMED_CAMERA_HEIGHT_M, False

    below = points[points[:, 1] > 0.05 * np.percentile(points[:, 1], 95)]
    if len(below) < 150:
        below = points

    weights = np.ones(len(below))
    best: tuple[float, np.ndarray, float] | None = None
    remaining = np.arange(len(below))
    rng = np.random.default_rng(seed)

    for _ in range(4):
        if len(remaining) < 100:
            break
        result = ransac_plane(
            below[remaining], weights[remaining], threshold_m=0.04, iterations=120, rng=rng
        )
        if result is None:
            break
        plane, inliers = result
        normal = plane.normal
        # Camera-frame "down" is +y, so a floor normal points at -y once oriented toward
        # the camera.
        if normal[1] > 0:
            normal, offset = -normal, -plane.offset
        else:
            offset = plane.offset
        verticality = abs(float(normal @ np.array([0.0, -1.0, 0.0])))
        height = abs(offset)
        if verticality > 0.86 and 0.4 < height < 3.0:
            support = float(inliers.sum())
            # Prefer the lowest qualifying plane; break ties by support.
            score = -height * 1000.0 + support
            if best is None or score > best[0]:
                best = (score, normal, height)
        remaining = remaining[~inliers]

    if best is None:
        return np.eye(3), ASSUMED_CAMERA_HEIGHT_M, False

    _, normal, height = best
    # Rotate so the floor normal becomes world up.
    axis = np.cross(-normal, UP)
    sin = float(np.linalg.norm(axis))
    if sin < 1e-9:
        rotation = np.eye(3)
    else:
        axis = axis / sin
        angle = float(np.arccos(np.clip((-normal) @ UP, -1.0, 1.0)))
        kx = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
        rotation = np.eye(3) + np.sin(angle) * kx + (1 - np.cos(angle)) * (kx @ kx)
    return rotation, float(height), True


def recover_scale(
    measured_camera_height: float, floor_found: bool, backbone_is_metric: bool = True
) -> ScaleEstimate:
    """Scale correction from the camera's own height above the detected floor.

    `measured_camera_height` is the height the depth map itself implies, in whatever units
    it is in. For a metric backbone those are already metres and the returned factor is a
    correction near 1; for a relative backbone it is the whole scale.
    """
    if not floor_found or measured_camera_height <= 1e-6:
        return ScaleEstimate(
            factor=1.0,
            source="model_metric_no_floor_found" if backbone_is_metric else "none_unscaled",
            relative_uncertainty=0.25 if backbone_is_metric else 0.50,
        )

    factor = ASSUMED_CAMERA_HEIGHT_M / measured_camera_height

    if not (SCALE_CORRECTION_MIN <= factor <= SCALE_CORRECTION_MAX):
        return ScaleEstimate(
            factor=1.0,
            source=f"floor_implausible_correction_{factor:.2f}",
            relative_uncertainty=0.35,
        )

    return ScaleEstimate(
        factor=float(factor),
        source="camera_height_correction",
        relative_uncertainty=float(CAMERA_HEIGHT_SIGMA_M / ASSUMED_CAMERA_HEIGHT_M),
    )


def make_metric(
    predicted_depth: np.ndarray,
    intrinsics: np.ndarray,
    seed: int = 0,
    backbone_is_metric: bool = True,
) -> FrameGeometry:
    """Full per-image pipeline: predicted depth in, metric level geometry out."""
    points = _backproject(predicted_depth, intrinsics)
    rotation, relative_height, floor_found = estimate_gravity_and_height(points, seed=seed)
    scale = recover_scale(relative_height, floor_found, backbone_is_metric)
    return FrameGeometry(
        depth_m=(predicted_depth * scale.factor).astype(np.float32),
        intrinsics=intrinsics,
        gravity_rotation=rotation,
        camera_height_m=float(relative_height * scale.factor),
        scale=scale,
        floor_found=floor_found,
    )


def refine_floor_after_scaling(points_world: np.ndarray) -> float:
    """Camera height above the floor of an already gravity-aligned metric cloud."""
    if len(points_world) < 100:
        return ASSUMED_CAMERA_HEIGHT_M
    low = np.percentile(points_world[:, 1], 2)
    near_floor = points_world[points_world[:, 1] < low + 0.08]
    if len(near_floor) < 30:
        return float(-low)
    plane = fit_plane(near_floor).flip_to(UP)
    return float(abs(plane.offset))
