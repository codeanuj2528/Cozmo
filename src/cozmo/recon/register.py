"""Registering several unposed photographs of one room into a common frame.

Once each photograph has been made metric and level, the pose that remains unknown is only
three degrees of freedom: a yaw about the vertical, and a translation in the floor plane.
Roll and pitch are gone because gravity fixed them, and scale is gone because the camera
height fixed that. Solving three parameters instead of seven is what makes registration
from four handheld stills tractable at all.

The three are solved in the order that each one makes the next well posed.

Yaw comes from the walls. A room's vertical surfaces have normals clustered in a few
directions, so the circular histogram of wall-normal azimuths is a signature of the room's
orientation, and the offset between two images' histograms is the yaw between them. This
is a global one-dimensional search with no initial guess needed, which is exactly what
nothing else here can offer.

Translation comes from the floor plan. With yaw fixed, the top-down occupancy of the two
clouds differ by a pure 2D shift, and cross-correlation finds a shift without needing
correspondences. Feature matching would need overlapping texture; two photographs taken
from opposite corners of a room often share almost none, while they always share the room's
shape.

ICP then refines all three together. It is deliberately last: point-to-plane ICP has a
small basin of convergence and would fall into the nearest wrong minimum if handed the
identity, which is what makes "just run ICP" fail on this problem.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import fftconvolve

from cozmo.geometry.icp import point_to_plane_icp
from cozmo.util.transforms import make_pose

log = logging.getLogger(__name__)

AZIMUTH_BINS = 180
OCCUPANCY_RESOLUTION_M = 0.06
MAX_TRANSLATION_M = 6.0
ICP_CORRESPONDENCE_M = 0.30
MIN_REGISTRATION_FITNESS = 0.25


@dataclass
class RegisteredFrame:
    index: int
    points: np.ndarray
    normals: np.ndarray
    pose: np.ndarray
    fitness: float
    method: str


@dataclass
class RegistrationReport:
    frames: list[RegisteredFrame] = field(default_factory=list)
    failed: list[int] = field(default_factory=list)
    mean_fitness: float = 0.0

    @property
    def registered_count(self) -> int:
        return len(self.frames)


def wall_azimuth_histogram(points: np.ndarray, normals: np.ndarray, floor_y: float) -> np.ndarray:
    """Circular histogram of vertical-surface normal directions, weighted by area."""
    vertical = np.abs(normals[:, 1]) < 0.35
    above_floor = points[:, 1] > floor_y + 0.25
    selected = vertical & above_floor
    histogram = np.zeros(AZIMUTH_BINS)
    if selected.sum() < 30:
        return histogram
    azimuth = np.degrees(np.arctan2(normals[selected, 2], normals[selected, 0])) % 360.0
    bins = (azimuth / (360.0 / AZIMUTH_BINS)).astype(int) % AZIMUTH_BINS
    np.add.at(histogram, bins, 1.0)
    return gaussian_filter1d(histogram, sigma=1.5, mode="wrap")


def yaw_candidates(reference: np.ndarray, target: np.ndarray, top_k: int = 4) -> list[float]:
    """Yaw angles, in radians, that align the target's wall directions to the reference."""
    if reference.sum() < 1 or target.sum() < 1:
        return [0.0]
    # Circular cross-correlation: correlating with a doubled signal and slicing is the
    # cheapest way to get every rotation without an FFT wrap-around mistake.
    doubled = np.concatenate([target, target])
    scores = np.array(
        [float(reference @ doubled[shift : shift + AZIMUTH_BINS]) for shift in range(AZIMUTH_BINS)]
    )
    order = np.argsort(scores)[::-1]
    step = 2 * np.pi / AZIMUTH_BINS
    picked: list[float] = []
    for index in order:
        angle = float(index * step)
        if all(abs((angle - other + np.pi) % (2 * np.pi) - np.pi) > np.deg2rad(12) for other in picked):
            picked.append(angle)
        if len(picked) >= top_k:
            break
    return picked or [0.0]


def _occupancy(points: np.ndarray, floor_y: float, origin: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    grid = np.zeros(shape, dtype=np.float32)
    band = (points[:, 1] > floor_y + 0.3) & (points[:, 1] < floor_y + 2.2)
    xz = points[band][:, [0, 2]]
    if len(xz) == 0:
        return grid
    cells = np.round((xz - origin) / OCCUPANCY_RESOLUTION_M).astype(int)
    keep = (
        (cells[:, 0] >= 0) & (cells[:, 0] < shape[1]) & (cells[:, 1] >= 0) & (cells[:, 1] < shape[0])
    )
    np.add.at(grid, (cells[keep, 1], cells[keep, 0]), 1.0)
    return grid


def translation_by_correlation(
    reference: np.ndarray, target: np.ndarray, floor_y: float
) -> np.ndarray:
    """The 2D shift that best overlays the target's top-down occupancy on the reference."""
    combined = np.vstack([reference[:, [0, 2]], target[:, [0, 2]]])
    origin = combined.min(axis=0) - MAX_TRANSLATION_M
    extent = combined.max(axis=0) + MAX_TRANSLATION_M - origin
    shape = (
        int(np.ceil(extent[1] / OCCUPANCY_RESOLUTION_M)) + 1,
        int(np.ceil(extent[0] / OCCUPANCY_RESOLUTION_M)) + 1,
    )
    if shape[0] * shape[1] > 4_000_000:
        return np.zeros(2)

    a = _occupancy(reference, floor_y, origin, shape)
    b = _occupancy(target, floor_y, origin, shape)
    if a.sum() < 20 or b.sum() < 20:
        return np.zeros(2)

    correlation = fftconvolve(a, b[::-1, ::-1], mode="same")
    peak = np.unravel_index(int(np.argmax(correlation)), correlation.shape)
    centre = (shape[0] // 2, shape[1] // 2)
    shift_rows = peak[0] - centre[0]
    shift_cols = peak[1] - centre[1]
    return np.array([shift_cols * OCCUPANCY_RESOLUTION_M, shift_rows * OCCUPANCY_RESOLUTION_M])


def _yaw_pose(angle: float, translation_xz: np.ndarray) -> np.ndarray:
    cos, sin = np.cos(angle), np.sin(angle)
    rotation = np.array([[cos, 0.0, sin], [0.0, 1.0, 0.0], [-sin, 0.0, cos]])
    return make_pose(rotation, np.array([translation_xz[0], 0.0, translation_xz[1]]))


def register_room(
    clouds: list[tuple[np.ndarray, np.ndarray]],
    floor_y: float = 0.0,
) -> RegistrationReport:
    """Register a room's photographs into one frame, anchored on the richest view."""
    report = RegistrationReport()
    if not clouds:
        return report

    sizes = [len(points) for points, _ in clouds]
    anchor = int(np.argmax(sizes))
    anchor_points, anchor_normals = clouds[anchor]
    report.frames.append(
        RegisteredFrame(anchor, anchor_points, anchor_normals, np.eye(4), 1.0, "anchor")
    )

    accumulated_points = anchor_points
    accumulated_normals = anchor_normals
    reference_histogram = wall_azimuth_histogram(anchor_points, anchor_normals, floor_y)

    order = sorted((i for i in range(len(clouds)) if i != anchor), key=lambda i: -sizes[i])
    for index in order:
        points, normals = clouds[index]
        if len(points) < 200:
            report.failed.append(index)
            continue

        histogram = wall_azimuth_histogram(points, normals, floor_y)
        best: tuple[float, np.ndarray] | None = None

        for yaw in yaw_candidates(reference_histogram, histogram):
            rotated = points @ _yaw_pose(yaw, np.zeros(2))[:3, :3].T
            translation = translation_by_correlation(accumulated_points, rotated, floor_y)
            initial = _yaw_pose(yaw, translation)

            result = point_to_plane_icp(
                points.astype(np.float64),
                accumulated_points.astype(np.float64),
                accumulated_normals.astype(np.float64),
                initial=initial,
                max_correspondence_m=ICP_CORRESPONDENCE_M,
                iterations=25,
            )
            if best is None or result.fitness > best[0]:
                best = (result.fitness, result.transform)

        if best is None or best[0] < MIN_REGISTRATION_FITNESS:
            report.failed.append(index)
            log.info("photo %d did not register (fitness %.2f)", index, best[0] if best else 0.0)
            continue

        fitness, transform = best
        moved = points @ transform[:3, :3].T + transform[:3, 3]
        moved_normals = normals @ transform[:3, :3].T
        report.frames.append(
            RegisteredFrame(index, moved, moved_normals, transform, fitness, "yaw_correlation_icp")
        )
        accumulated_points = np.vstack([accumulated_points, moved])
        accumulated_normals = np.vstack([accumulated_normals, moved_normals])
        reference_histogram = wall_azimuth_histogram(
            accumulated_points, accumulated_normals, floor_y
        )

    if report.frames:
        report.mean_fitness = float(np.mean([f.fitness for f in report.frames]))
    return report


def register_sequential(
    clouds: list[tuple[np.ndarray, np.ndarray]],
    floor_y: float = 0.0,
    max_gap: int = 3,
) -> tuple[list[np.ndarray | None], list[str]]:
    """Chain a walkthrough's frames into one frame, each onto the one before it.

    Consecutive keyframes of a walkthrough overlap heavily, so each registration is a small
    correction and the yaw search that the photo tier needs is unnecessary -- the previous
    frame's pose is already a good initial guess. That makes this both faster and more
    reliable than treating the clip as unordered stills.

    A frame that fails to register is skipped rather than dropped: the next frame is tried
    against the last one that succeeded, up to `max_gap` frames back. A single blurred
    frame in the middle of a corridor should cost one frame, not the rest of the walk.
    """
    warnings: list[str] = []
    poses: list[np.ndarray | None] = [None] * len(clouds)
    if not clouds:
        return poses, warnings

    poses[0] = np.eye(4)
    anchor_index = 0
    anchor_points, anchor_normals = clouds[0]
    failures = 0

    for index in range(1, len(clouds)):
        points, normals = clouds[index]
        if len(points) < 200:
            failures += 1
            continue

        result = point_to_plane_icp(
            points.astype(np.float64),
            anchor_points.astype(np.float64),
            anchor_normals.astype(np.float64),
            initial=np.eye(4),
            max_correspondence_m=0.45,
            iterations=25,
        )
        if result.fitness < MIN_REGISTRATION_FITNESS:
            failures += 1
            if index - anchor_index >= max_gap:
                # The trajectory has broken. Restart the chain here rather than forcing a
                # bad alignment, and say so: a plan assembled across a break is wrong in a
                # way that looks plausible.
                warnings.append(
                    f"registration broke at keyframe {index}; the walk is reported as "
                    "two disconnected stretches"
                )
                poses[index] = poses[anchor_index] if poses[anchor_index] is not None else np.eye(4)
                anchor_index = index
                anchor_points, anchor_normals = points, normals
            continue

        poses[index] = poses[anchor_index] @ result.transform
        anchor_index = index
        anchor_points, anchor_normals = points, normals

    registered = sum(1 for p in poses if p is not None)
    if failures:
        warnings.append(f"{failures} keyframe(s) failed to register and were skipped")
    if registered < 0.5 * len(clouds):
        warnings.append(
            f"only {registered} of {len(clouds)} keyframes registered; the resulting plan "
            "covers part of the walk and its footprint should be read as a lower bound"
        )
    return poses, warnings
