"""Wall extraction by normal voting, and the wall segments that come out of it.

Walls are found with a two-dimensional Hough accumulator over (normal azimuth, signed
offset), where each point votes once, into the bin its own measured normal selects. That is
much sharper than a classical Hough transform over lines, in which every point votes along
a whole sinusoid and a cluttered room smears the accumulator into mush. Having a per-point
normal from the depth image is what makes the sharper version available.

Votes are the point's inverse variance rather than one-per-point, so a wall seen precisely
from two metres is not outvoted by a noisy patch of returns at five.

Opposite faces of the same partition land in opposite azimuth bins, because normals are
oriented toward the camera that measured them. That is deliberate: the two faces of a
150 mm partition are two different surfaces, they get repaired separately, and collapsing
them would put a room's wall 75 mm out.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import gaussian_filter, maximum_filter, uniform_filter

from cozmo.geometry.fusion import FusedCloud
from cozmo.geometry.planes import PlaneFit, fit_plane

AZIMUTH_BIN_DEG = 1.0
OFFSET_BIN_M = 0.02
MIN_WALL_HEIGHT_EXTENT_M = 0.5
MIN_SEGMENT_LENGTH_M = 0.35
SEGMENT_BIN_M = 0.05
SEGMENT_GAP_TOLERANCE_M = 0.45


@dataclass
class WallSegment:
    """A straight run of wall on one plane, in the world xz plane."""

    plane: PlaneFit
    direction: np.ndarray
    normal_xz: np.ndarray
    start: np.ndarray
    end: np.ndarray
    height_low: float
    height_high: float
    support_weight: float
    point_indices: np.ndarray = field(repr=False)
    occupancy: np.ndarray = field(repr=False, default_factory=lambda: np.zeros(0))

    @property
    def length(self) -> float:
        return float(np.linalg.norm(self.end - self.start))

    @property
    def midpoint(self) -> np.ndarray:
        return 0.5 * (self.start + self.end)

    def signed_offset(self) -> float:
        return float(-self.plane.offset)

    def point_at(self, t: float) -> np.ndarray:
        return self.start + self.direction * t


@dataclass
class WallCandidate:
    plane: PlaneFit
    normal_xz: np.ndarray
    offset: float
    weight: float
    indices: np.ndarray = field(repr=False)
    segments: list[WallSegment] = field(default_factory=list)


def _vertical_mask(cloud: FusedCloud, floor_y: float, ceiling_y: float | None,
                   min_height: float = 0.12) -> np.ndarray:
    height = cloud.points[:, 1] - floor_y
    mask = (cloud.verticality > 0.90) & (height > min_height)
    if ceiling_y is not None:
        mask &= cloud.points[:, 1] < ceiling_y - 0.06
    return mask


def vote_for_walls(
    cloud: FusedCloud,
    floor_y: float,
    ceiling_y: float | None,
    peak_relative_threshold: float = 0.02,
    min_peak_area_m2: float = 0.20,
    max_walls: int = 220,
) -> list[WallCandidate]:
    """Hough peaks over (azimuth, offset), refined into plane fits.

    Acceptance is by observed wall area, not by a fraction of total vote weight. A
    forty-wall apartment divides its weight forty ways, so the strongest genuine peak in a
    real property carries well under one percent of the total and any fraction-of-total
    threshold either admits everything or nothing. Area is the quantity a reader can argue
    with: a peak is kept when enough square metres of surface voted for it.
    """
    mask = _vertical_mask(cloud, floor_y, ceiling_y)
    idx = np.flatnonzero(mask)
    if len(idx) < 100:
        return []

    n_xz = cloud.normals[idx][:, [0, 2]].astype(np.float64)
    n_len = np.linalg.norm(n_xz, axis=1)
    good = n_len > 1e-6
    idx, n_xz, n_len = idx[good], n_xz[good], n_len[good]
    n_xz /= n_len[:, None]

    p_xz = cloud.points[idx][:, [0, 2]].astype(np.float64)
    weights = cloud.weight[idx].astype(np.float64)
    # One voxel of a reduced cloud stands for one cell of observed surface, so the fusion
    # pitch is what converts a vote count into square metres. It is carried on the cloud
    # rather than inferred from it: reduction averages positions inside each voxel, so the
    # output coordinates are not quantised and the pitch is not recoverable from them.
    voxel_pitch_m = float(cloud.voxel_m)

    azimuth = np.degrees(np.arctan2(n_xz[:, 1], n_xz[:, 0])) % 360.0
    offset = np.einsum("ij,ij->i", p_xz, n_xz)

    n_az = int(round(360.0 / AZIMUTH_BIN_DEG))
    off_lo, off_hi = offset.min() - 0.1, offset.max() + 0.1
    n_off = max(int(np.ceil((off_hi - off_lo) / OFFSET_BIN_M)), 4)

    az_bin = np.clip((azimuth / AZIMUTH_BIN_DEG).astype(int), 0, n_az - 1)
    off_bin = np.clip(((offset - off_lo) / OFFSET_BIN_M).astype(int), 0, n_off - 1)

    acc = np.zeros((n_az, n_off), dtype=np.float64)
    np.add.at(acc, (az_bin, off_bin), weights)
    counts = np.zeros((n_az, n_off), dtype=np.float64)
    np.add.at(counts, (az_bin, off_bin), 1.0)

    # Smooth with wraparound in azimuth so a wall whose normal sits on a bin edge is not
    # split into two weaker peaks that both fall under the threshold.
    smooth = gaussian_filter(acc, sigma=(1.5, 1.0), mode=("wrap", "nearest"))
    count_window = uniform_filter(counts, size=(7, 5), mode=("wrap", "nearest")) * 35.0
    peaks = smooth >= maximum_filter(smooth, size=(7, 5), mode=("wrap", "nearest"))
    peaks &= smooth > smooth.max() * peak_relative_threshold
    # Each voxel stands for one cell of surface, so a minimum area converts directly to a
    # minimum vote count once the voxel pitch is known.
    voxel_area = max(voxel_pitch_m, 1e-3) ** 2
    peaks &= count_window > (min_peak_area_m2 / voxel_area)

    peak_az, peak_off = np.nonzero(peaks)
    if len(peak_az) == 0:
        return []
    order = np.argsort(smooth[peak_az, peak_off])[::-1][:max_walls]

    claimed = np.zeros(len(idx), dtype=bool)
    candidates: list[WallCandidate] = []
    for p in order:
        a, o = int(peak_az[p]), int(peak_off[p])
        az_centre = (a + 0.5) * AZIMUTH_BIN_DEG
        off_centre = off_lo + (o + 0.5) * OFFSET_BIN_M

        d_az = np.abs((azimuth - az_centre + 180.0) % 360.0 - 180.0)
        near = (d_az < 12.0) & (np.abs(offset - off_centre) < 0.06) & ~claimed
        if near.sum() * voxel_pitch_m**2 < min_peak_area_m2 * 0.5:
            continue

        plane = fit_plane(cloud.points[idx[near]], weights[near])
        normal_xz = plane.normal[[0, 2]]
        length = np.linalg.norm(normal_xz)
        if length < 0.9:
            continue
        mean_normal = n_xz[near].mean(axis=0)
        if normal_xz @ mean_normal < 0:
            plane = PlaneFit(-plane.normal, -plane.offset, plane.sigma_offset, plane.sigma_angle_rad,
                             plane.inlier_count, plane.residual_rms, plane.effective_n)
            normal_xz = -normal_xz
        normal_xz = normal_xz / np.linalg.norm(normal_xz)

        d_az2 = np.abs((azimuth - (np.degrees(np.arctan2(normal_xz[1], normal_xz[0])) % 360.0) + 180.0) % 360.0 - 180.0)
        refined = (d_az2 < 15.0) & (np.abs(plane.distance(cloud.points[idx])) < 0.045) & ~claimed
        if refined.sum() * voxel_pitch_m**2 < min_peak_area_m2 * 0.5:
            continue
        plane = fit_plane(cloud.points[idx[refined]], weights[refined])
        if plane.normal @ np.array([normal_xz[0], 0.0, normal_xz[1]]) < 0:
            plane = PlaneFit(-plane.normal, -plane.offset, plane.sigma_offset, plane.sigma_angle_rad,
                             plane.inlier_count, plane.residual_rms, plane.effective_n)

        claimed |= refined
        candidates.append(
            WallCandidate(
                plane=plane,
                normal_xz=normal_xz,
                offset=float(-plane.offset),
                weight=float(weights[refined].sum()),
                indices=idx[refined],
            )
        )
    return candidates


def segment_wall(
    candidate: WallCandidate,
    cloud: FusedCloud,
    floor_y: float,
    min_length_m: float = MIN_SEGMENT_LENGTH_M,
    gap_tolerance_m: float = SEGMENT_GAP_TOLERANCE_M,
) -> list[WallSegment]:
    """Split one wall plane into the runs where material was actually observed.

    A plane is infinite; a wall is not. Runs are separated only by gaps wider than
    `gap_tolerance_m`, because a doorway is a gap in the observed material but the wall
    plane continues past it, and treating every unobserved patch as a wall end would
    shatter a single wall into a dozen fragments.
    """
    pts = cloud.points[candidate.indices]
    direction = np.array([-candidate.normal_xz[1], candidate.normal_xz[0]])
    t = pts[:, [0, 2]] @ direction
    heights = pts[:, 1] - floor_y
    weights = cloud.weight[candidate.indices].astype(np.float64)

    lo, hi = t.min(), t.max()
    n_bins = max(int(np.ceil((hi - lo) / SEGMENT_BIN_M)), 1)
    bins = np.clip(((t - lo) / SEGMENT_BIN_M).astype(int), 0, n_bins - 1)

    occupied_weight = np.bincount(bins, weights=weights, minlength=n_bins)
    hi_per_bin = np.full(n_bins, -np.inf)
    lo_per_bin = np.full(n_bins, np.inf)
    np.maximum.at(hi_per_bin, bins, heights)
    np.minimum.at(lo_per_bin, bins, heights)

    extent = hi_per_bin - lo_per_bin
    occupied = (occupied_weight > 0) & (extent > 0.10)

    gap_bins = int(np.ceil(gap_tolerance_m / SEGMENT_BIN_M))
    runs: list[tuple[int, int]] = []
    start = None
    gap = 0
    for i, flag in enumerate(occupied):
        if flag:
            if start is None:
                start = i
            gap = 0
        elif start is not None:
            gap += 1
            if gap > gap_bins:
                runs.append((start, i - gap))
                start = None
                gap = 0
    if start is not None:
        runs.append((start, len(occupied) - 1))

    segments: list[WallSegment] = []
    for a, b in runs:
        t0 = lo + a * SEGMENT_BIN_M
        t1 = lo + (b + 1) * SEGMENT_BIN_M
        if t1 - t0 < min_length_m:
            continue
        in_run = (bins >= a) & (bins <= b)
        if in_run.sum() < 25:
            continue
        seg_heights = heights[in_run]
        h_low, h_high = float(np.percentile(seg_heights, 1)), float(np.percentile(seg_heights, 99))
        if h_high - h_low < MIN_WALL_HEIGHT_EXTENT_M:
            continue
        foot = -candidate.plane.offset * candidate.plane.normal
        base = foot[[0, 2]]
        base = base - (base @ direction) * direction
        segments.append(
            WallSegment(
                plane=candidate.plane,
                direction=direction,
                normal_xz=candidate.normal_xz,
                start=base + direction * t0,
                end=base + direction * t1,
                height_low=h_low,
                height_high=h_high,
                support_weight=float(weights[in_run].sum()),
                point_indices=candidate.indices[in_run],
                occupancy=occupied_weight[a : b + 1],
            )
        )
    return segments


def extract_wall_segments(
    cloud: FusedCloud, floor_y: float, ceiling_y: float | None
) -> tuple[list[WallSegment], list[WallCandidate]]:
    candidates = vote_for_walls(cloud, floor_y, ceiling_y)
    segments: list[WallSegment] = []
    for cand in candidates:
        cand.segments = segment_wall(cand, cloud, floor_y)
        segments.extend(cand.segments)
    segments.sort(key=lambda s: s.support_weight, reverse=True)
    return segments, candidates


def dominant_directions(segments: list[WallSegment], bin_deg: float = 0.5) -> float:
    """Rotation angle, in radians, that brings the dominant wall run onto the x axis.

    Weighted by segment length, so the long structural walls set the frame and a short
    diagonal return does not. The answer is modulo 90 degrees: a rectangular room has no
    preferred axis of the two, and rotating by 90 degrees would produce the same plan.
    """
    if not segments:
        return 0.0
    n_bins = int(round(90.0 / bin_deg))
    acc = np.zeros(n_bins)
    for seg in segments:
        angle = np.degrees(np.arctan2(seg.direction[1], seg.direction[0])) % 90.0
        acc[int(angle / bin_deg) % n_bins] += seg.length
    acc = gaussian_filter(acc, sigma=1.0, mode="wrap")
    peak = int(np.argmax(acc))
    # Refine with the intensity-weighted centroid of the peak's immediate neighbourhood.
    offsets = np.arange(-3, 4)
    idxs = (peak + offsets) % n_bins
    w = acc[idxs]
    centre = (peak + float((offsets * w).sum() / max(w.sum(), 1e-9))) * bin_deg
    return float(np.deg2rad(centre % 90.0))
