"""Accumulated pose drift: detecting it, and correcting it.

ARKit's visual-inertial odometry is locally excellent and globally not. Over a hundred
metres of walking through a flat it accumulates translation and yaw error, and the failure
mode is specific: a loop that should close does not, so the corridor is reported longer
than it is and the last room is placed a few centimetres off the first. Taking those poses
as given produces a plan that is internally consistent and externally wrong.

Correction is a pose graph over keyframes. Odometry edges hold consecutive keyframes at the
relative pose the sensor reported, and loop-closure edges hold revisited places together at
the relative pose ICP measured. Optimising the two against each other distributes the
accumulated error over the whole trajectory rather than dumping it at the seam.

Loop candidates are proposed by geometry and confirmed by ICP, in that order and never the
reverse. Two places being near each other in a drifted trajectory is weak evidence, since
the drift is exactly what makes the estimate unreliable; two places whose surfaces align
under ICP with a low residual is strong evidence. Accepting a false closure is far worse
than missing a true one, because a false closure folds the map, so the acceptance test is
deliberately strict.

The corrected poses are applied by re-fusing. Correcting the fused cloud in place would be
cheaper, but voxel reduction has already averaged points from several frames into each
voxel and kept only one frame's identity, so an in-place correction would apply one frame's
delta to another frame's contribution.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import lil_matrix
from scipy.spatial.transform import Rotation

from cozmo.geometry.icp import point_to_plane_icp
from cozmo.io.base import CaptureSource, Frame
from cozmo.schema import DriftReport
from cozmo.util.transforms import invert_pose, make_pose

LOOP_MIN_KEYFRAME_GAP = 25
LOOP_SEARCH_RADIUS_M = 2.5
LOOP_MAX_VIEW_ANGLE_RAD = np.deg2rad(60.0)
LOOP_MAX_CANDIDATES = 120
ICP_MIN_FITNESS = 0.55
ICP_MAX_RMSE_M = 0.035
KEYFRAME_POINTS = 900

# A revisit is a place reached again after going somewhere else. Two keyframes can be
# metres apart in index and centimetres apart in space simply because the operator was
# walking slowly down a corridor, and an edge between those two re-states odometry with
# ICP noise added rather than adding information. The discriminator is the ratio of path
# walked to distance closed.
LOOP_MIN_PATH_RATIO = 6.0
LOOP_MIN_PATH_M = 6.0

# Information weights. Rotation and translation residuals are in different units and a
# pose graph that adds radians to metres is weighting one arbitrarily against the other.
# Over a hundred metres of trajectory a milliradian of yaw costs more than a centimetre of
# translation, and these numbers are what say so.
ODOMETRY_SIGMA_ROT_RAD = 0.010
ODOMETRY_SIGMA_TRANS_M = 0.020
LOOP_SIGMA_ROT_RAD = 0.020
LOOP_SIGMA_TRANS_M = 0.030


@dataclass
class KeyframeCloud:
    index: int
    points: np.ndarray
    normals: np.ndarray


@dataclass
class LoopClosure:
    i: int
    j: int
    transform: np.ndarray
    fitness: float
    rmse: float


@dataclass
class DriftSolution:
    poses: np.ndarray
    report: DriftReport
    closures: list[LoopClosure] = field(default_factory=list)


def _pose_to_vector(pose: np.ndarray) -> np.ndarray:
    return np.concatenate([Rotation.from_matrix(pose[:3, :3]).as_rotvec(), pose[:3, 3]])


def _vector_to_pose(vector: np.ndarray) -> np.ndarray:
    return make_pose(Rotation.from_rotvec(vector[:3]).as_matrix(), vector[3:])


def _relative_error(measured: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Six-vector error between a measured relative pose and the one the estimate implies."""
    predicted = invert_pose(a) @ b
    delta = invert_pose(measured) @ predicted
    return np.concatenate([Rotation.from_matrix(delta[:3, :3]).as_rotvec(), delta[:3, 3]])


def load_keyframe_clouds(
    source: CaptureSource,
    keyframes: list[int],
    max_points: int = KEYFRAME_POINTS,
    max_range_m: float = 4.0,
    seed: int = 0,
) -> list[KeyframeCloud]:
    """Camera-frame points and normals per keyframe, subsampled for ICP."""
    from cozmo.geometry.fusion import image_normals

    rng = np.random.default_rng(seed)
    out: list[KeyframeCloud] = []
    for position, frame in _enumerate_frames(source, keyframes):
        depth = frame.depth
        if depth is None:
            continue
        valid = (depth > 0.2) & (depth < max_range_m) & np.isfinite(depth)
        if frame.confidence is not None:
            valid &= frame.confidence >= 2
        if valid.sum() < 60:
            continue

        h, w = depth.shape
        vs, us = np.mgrid[0:h, 0:w]
        k = frame.k_depth
        z = depth.astype(np.float32)
        x = (us - k[0, 2]) * z / k[0, 0]
        y = (vs - k[1, 2]) * z / k[1, 1]
        grid = np.stack([x, y, z], axis=2).astype(np.float32)
        normals, ok = image_normals(grid, valid)
        keep = valid & ok
        if keep.sum() < 60:
            continue
        points = grid[keep]
        normal_vectors = normals[keep]
        flip = np.einsum("ij,ij->i", normal_vectors, points) > 0
        normal_vectors[flip] *= -1.0
        if len(points) > max_points:
            pick = rng.choice(len(points), size=max_points, replace=False)
            points, normal_vectors = points[pick], normal_vectors[pick]
        out.append(KeyframeCloud(index=position, points=points, normals=normal_vectors))
    return out


def _enumerate_frames(source: CaptureSource, keyframes: list[int]):
    for position, frame in zip(keyframes, source.frames(keyframes)):
        yield position, frame
    return


def propose_loops(
    poses: np.ndarray,
    keyframes: list[int],
    radius_m: float = LOOP_SEARCH_RADIUS_M,
    min_gap: int = LOOP_MIN_KEYFRAME_GAP,
    max_candidates: int = LOOP_MAX_CANDIDATES,
) -> list[tuple[int, int]]:
    """Keyframe pairs that look like genuine revisits.

    Near in space, far along the path, and facing a similar way. The path-length test is
    the one that matters: without it, a slow walk down a corridor generates a constraint
    between every pair of keyframes in it, all of which merely repeat what odometry already
    said, and the optimiser then has hundreds of noisy near-duplicate edges outvoting the
    handful of real closures.
    """
    centres = poses[keyframes][:, :3, 3]
    # Camera forward is +z in the OpenCV convention this codebase uses throughout.
    forward = poses[keyframes][:, :3, 2]
    steps = np.linalg.norm(np.diff(centres, axis=0), axis=1)
    path = np.concatenate([[0.0], np.cumsum(steps)])

    n = len(keyframes)
    scored: list[tuple[float, int, int]] = []
    for i in range(n):
        for j in range(i + min_gap, n):
            distance = float(np.linalg.norm(centres[i] - centres[j]))
            if distance > radius_m:
                continue
            walked = float(path[j] - path[i])
            if walked < LOOP_MIN_PATH_M or walked < LOOP_MIN_PATH_RATIO * max(distance, 0.05):
                continue
            angle = float(np.arccos(np.clip(forward[i] @ forward[j], -1.0, 1.0)))
            if angle > LOOP_MAX_VIEW_ANGLE_RAD:
                continue
            scored.append((distance + 0.5 * angle, i, j))
    scored.sort()
    return [(i, j) for _, i, j in scored[:max_candidates]]


def verify_loops(
    clouds: list[KeyframeCloud],
    poses: np.ndarray,
    keyframes: list[int],
    candidates: list[tuple[int, int]],
) -> list[LoopClosure]:
    """Confirm candidate closures with ICP, keeping only those that align well."""
    by_position = {c.index: c for c in clouds}
    closures: list[LoopClosure] = []
    for i, j in candidates:
        ci = by_position.get(keyframes[i])
        cj = by_position.get(keyframes[j])
        if ci is None or cj is None:
            continue
        # ICP runs in frame i's own coordinates, so the initial guess is what the drifted
        # odometry claims the relative pose is, and the correction it finds is the drift.
        initial = invert_pose(poses[keyframes[i]]) @ poses[keyframes[j]]
        result = point_to_plane_icp(
            cj.points.astype(np.float64),
            ci.points.astype(np.float64),
            ci.normals.astype(np.float64),
            initial=initial,
        )
        if not result.converged:
            continue
        if result.fitness < ICP_MIN_FITNESS or result.inlier_rmse > ICP_MAX_RMSE_M:
            continue
        correction = float(np.linalg.norm(result.transform[:3, 3] - initial[:3, 3]))
        # A closure that agrees exactly with odometry adds no information, and one that
        # disagrees wildly is more likely a false match than a real revisit.
        if correction < 0.004 or correction > 0.9:
            continue
        closures.append(LoopClosure(i=i, j=j, transform=result.transform,
                                    fitness=result.fitness, rmse=result.inlier_rmse))
    return closures


def optimise_pose_graph(
    poses: np.ndarray,
    keyframes: list[int],
    closures: list[LoopClosure],
    max_iterations: int = 40,
) -> tuple[np.ndarray, float, float]:
    """Least-squares over keyframe poses. Returns (poses, residual before, residual after)."""
    n = len(keyframes)
    initial = np.stack([poses[k] for k in keyframes])

    edges: list[tuple[int, int, np.ndarray, np.ndarray]] = []
    odometry_weight = np.array([1.0 / ODOMETRY_SIGMA_ROT_RAD] * 3 + [1.0 / ODOMETRY_SIGMA_TRANS_M] * 3)
    for i in range(n - 1):
        measured = invert_pose(initial[i]) @ initial[i + 1]
        edges.append((i, i + 1, measured, odometry_weight))
    for closure in closures:
        confidence = float(np.clip(closure.fitness, 0.1, 1.0))
        weight = confidence * np.array(
            [1.0 / LOOP_SIGMA_ROT_RAD] * 3 + [1.0 / LOOP_SIGMA_TRANS_M] * 3
        )
        edges.append((closure.i, closure.j, closure.transform, weight))

    x0 = np.concatenate([_pose_to_vector(p) for p in initial])

    def residuals(x: np.ndarray) -> np.ndarray:
        estimates = [_vector_to_pose(x[6 * i : 6 * i + 6]) for i in range(n)]
        out = np.empty(6 * len(edges) + 6)
        for e, (i, j, measured, weight) in enumerate(edges):
            out[6 * e : 6 * e + 6] = weight * _relative_error(measured, estimates[i], estimates[j])
        # Gauge fixing. Without anchoring one pose the problem is invariant to a global
        # rigid motion and the solver wanders through that null space.
        out[-6:] = 1000.0 * (x[:6] - x0[:6])
        return out

    sparsity = lil_matrix((6 * len(edges) + 6, 6 * n), dtype=int)
    for e, (i, j, _, _) in enumerate(edges):
        sparsity[6 * e : 6 * e + 6, 6 * i : 6 * i + 6] = 1
        sparsity[6 * e : 6 * e + 6, 6 * j : 6 * j + 6] = 1
    sparsity[-6:, :6] = 1

    before = float(np.sqrt((residuals(x0) ** 2).mean()))
    if not closures:
        return initial, before, before

    # A soft L1 loss keeps a single false closure that survived ICP verification from
    # folding the whole map. Some always do survive: two bathrooms in the same flat look
    # alike to a geometric matcher.
    solution = least_squares(
        residuals, x0, jac_sparsity=sparsity, method="trf", loss="soft_l1",
        f_scale=3.0, max_nfev=max_iterations, verbose=0,
    )
    after = float(np.sqrt((solution.fun**2).mean()))
    optimised = np.stack([_vector_to_pose(solution.x[6 * i : 6 * i + 6]) for i in range(n)])
    return optimised, before, after


def correct_drift(
    source: CaptureSource, keyframes: list[int], poses: np.ndarray, seed: int = 0
) -> DriftSolution:
    """Detect and correct accumulated drift over the keyframe trajectory."""
    clouds = load_keyframe_clouds(source, keyframes, seed=seed)
    candidates = propose_loops(poses, keyframes)
    closures = verify_loops(clouds, poses, keyframes, candidates)
    corrected, before, after = optimise_pose_graph(poses, keyframes, closures)

    original = np.stack([poses[k] for k in keyframes])
    shift = np.linalg.norm(corrected[:, :3, 3] - original[:, :3, 3], axis=1)

    report = DriftReport(
        method=(
            "keyframe pose graph, ICP-verified loop closures, gauge-fixed least squares"
            if closures
            else "pose graph built; no loop closure passed ICP verification"
        ),
        loop_closures_found=len(closures),
        residual_before_m=before,
        residual_after_m=after,
        max_pose_correction_m=float(shift.max()) if len(shift) else 0.0,
        footprint_area_before_m2=0.0,
        footprint_area_after_m2=0.0,
        applied=bool(closures),
    )
    return DriftSolution(poses=corrected, report=report, closures=closures)


class PoseOverride:
    """A capture source that serves corrected poses in place of the recorded ones.

    The override is keyed by frame number, not by position in the keyframe list. A reader
    is free to skip a frame whose depth map failed to load, so zipping the yielded frames
    against the requested indices would silently pair a pose with the wrong frame from the
    first skip onward, and the resulting cloud would look plausible and be wrong.
    """

    def __init__(self, source: CaptureSource, keyframes: list[int], poses: np.ndarray):
        self._source = source
        self.meta = source.meta
        if hasattr(source, "frame_indices"):
            table = source.frame_indices()
            frame_numbers = [int(table[k]) for k in keyframes]
        else:
            frame_numbers = [int(k) for k in keyframes]
        self._override = {number: poses[i] for i, number in enumerate(frame_numbers)}

    def frames(self, indices: list[int] | None = None):
        for frame in self._source.frames(indices):
            replacement = self._override.get(int(frame.index))
            if replacement is not None:
                frame = Frame(**{**frame.__dict__, "pose": replacement})
            yield frame

    def poses(self) -> np.ndarray:
        return self._source.poses()

    def load_rgb(self, frame):
        return self._source.load_rgb(frame)

    def __getattr__(self, name):
        return getattr(self._source, name)
