"""Unsupervised structural quality metrics.

These exist because most reconstruction decisions have to be made before ground truth is
available, and eyeballing a plan is not a measurement. They do not replace the tape; they
adjudicate between two versions of the pipeline on a capture nobody has measured yet, and
they are reported alongside the ground-truth gates so the reader can see which is which.

Manhattan compliance is the useful one. Buildings are overwhelmingly built to two
orthogonal directions, so a reconstruction of a rectilinear property in which wall length
is spread across many directions is telling on itself: yaw drift rotates later rooms
relative to earlier ones, and a plan whose rooms sit at slightly different angles is a plan
with uncorrected drift in it, whatever its area happens to come out as.

The metric is only meaningful on a property that is actually rectilinear, so
`dominant_direction_share` is reported next to it: if the two dominant directions do not
between them account for most of the wall length even at a generous tolerance, the property
is not Manhattan and the compliance figure should be ignored rather than optimised.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cozmo.schema import PropertyPlan


@dataclass
class StructureMetrics:
    manhattan_compliance: float
    dominant_direction_share: float
    wall_length_total_m: float
    room_count: int
    footprint_m2: float
    mean_room_angle_spread_deg: float

    def as_dict(self) -> dict[str, float]:
        return {
            "manhattan_compliance": round(self.manhattan_compliance, 4),
            "dominant_direction_share": round(self.dominant_direction_share, 4),
            "wall_length_total_m": round(self.wall_length_total_m, 3),
            "room_count": self.room_count,
            "footprint_m2": round(self.footprint_m2, 3),
            "mean_room_angle_spread_deg": round(self.mean_room_angle_spread_deg, 3),
        }


def _wall_directions(plan: PropertyPlan) -> tuple[np.ndarray, np.ndarray]:
    angles, lengths = [], []
    for room in plan.rooms:
        for wall in room.walls:
            start, end = np.array(wall.start), np.array(wall.end)
            length = float(np.linalg.norm(end - start))
            if length < 0.30:
                continue
            # Modulo 90 degrees: a wall and the wall perpendicular to it are the same
            # constraint on the building's frame, and the two are indistinguishable here.
            angles.append(np.degrees(np.arctan2(end[1] - start[1], end[0] - start[0])) % 90.0)
            lengths.append(length)
    return np.array(angles), np.array(lengths)


def _best_frame(angles: np.ndarray, lengths: np.ndarray) -> float:
    """The building frame angle that captures the most wall length, in degrees mod 90."""
    if len(angles) == 0:
        return 0.0
    grid = np.arange(0.0, 90.0, 0.25)
    # Circular distance on a 90 degree period.
    deviation = np.abs((angles[None, :] - grid[:, None] + 45.0) % 90.0 - 45.0)
    score = (lengths[None, :] * np.exp(-((deviation / 3.0) ** 2))).sum(axis=1)
    return float(grid[int(np.argmax(score))])


def structure_metrics(plan: PropertyPlan, tolerance_deg: float = 2.0) -> StructureMetrics:
    angles, lengths = _wall_directions(plan)
    total = float(lengths.sum()) if len(lengths) else 0.0
    footprint = float(sum(r.floor_area.value for r in plan.rooms))

    if total == 0.0:
        return StructureMetrics(0.0, 0.0, 0.0, len(plan.rooms), footprint, 0.0)

    frame = _best_frame(angles, lengths)
    deviation = np.abs((angles - frame + 45.0) % 90.0 - 45.0)
    compliance = float(lengths[deviation <= tolerance_deg].sum() / total)
    generous = float(lengths[deviation <= 8.0].sum() / total)

    spreads = []
    for room in plan.rooms:
        room_angles, room_lengths = _wall_directions(
            PropertyPlan(
                pipeline_version=plan.pipeline_version, capture_id=plan.capture_id,
                tier=plan.tier, created_at=plan.created_at, rooms=[room], adjacency=[],
                damage=[], concealed_flags=[], scope_items=[], drift=plan.drift,
                calibration=plan.calibration, quality=plan.quality,
                total_floor_area=plan.total_floor_area, runtime_seconds=0.0,
            )
        )
        if len(room_angles) < 2:
            continue
        room_frame = _best_frame(room_angles, room_lengths)
        room_deviation = np.abs((room_angles - room_frame + 45.0) % 90.0 - 45.0)
        spreads.append(float(np.average(room_deviation, weights=room_lengths)))

    return StructureMetrics(
        manhattan_compliance=compliance,
        dominant_direction_share=generous,
        wall_length_total_m=total,
        room_count=len(plan.rooms),
        footprint_m2=footprint,
        mean_room_angle_spread_deg=float(np.mean(spreads)) if spreads else 0.0,
    )


def room_frame_dispersion(plan: PropertyPlan) -> float:
    """Spread, in degrees, of the per-room building frames.

    Zero when every room agrees on which way the building faces. Yaw drift shows up here
    directly and shows up nowhere else without ground truth: it barely moves the area, it
    barely moves any single wall length, and it rotates the last room relative to the first.
    """
    frames = []
    for room in plan.rooms:
        angles, lengths = [], []
        for wall in room.walls:
            start, end = np.array(wall.start), np.array(wall.end)
            length = float(np.linalg.norm(end - start))
            if length < 0.40:
                continue
            angles.append(np.degrees(np.arctan2(end[1] - start[1], end[0] - start[0])) % 90.0)
            lengths.append(length)
        if len(angles) < 2:
            continue
        frames.append(_best_frame(np.array(angles), np.array(lengths)))
    if len(frames) < 2:
        return 0.0
    frames_arr = np.array(frames)
    reference = frames_arr[0]
    deviation = (frames_arr - reference + 45.0) % 90.0 - 45.0
    return float(np.std(deviation))
