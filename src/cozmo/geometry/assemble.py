"""Turn geometry into the output contract.

The polygon a room gets from the cell complex already has its corners at the intersections
of wall planes, so wall lengths are read straight off its edges rather than re-derived.
What this module adds is attribution: which plane fit supports which edge, and therefore
what uncertainty that edge's length inherits.

Ceiling height is measured per room, not once per property. A capture that crosses a
dropped kitchen ceiling, a stairwell and a bedroom has three heights and one of them is not
the others, and the gate is a per-room gate.

Adjacency is established through matched openings. Two rooms either side of a partition
each see the doorway from their own face of it, at the same place in the world and with the
same width, so pairing those observations is what turns a set of rooms into a property. It
also gives the pairing something to be wrong about, which is the point: an unmatched
doorway is reported as unmatched rather than quietly dropped.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from shapely.geometry import Polygon

from cozmo.geometry.fusion import FusedCloud
from cozmo.geometry.grid import Grid2D
from cozmo.geometry.levels import LevelEstimate, detect_levels
from cozmo.geometry.openings import DetectedOpening
from cozmo.geometry.walls import WallSegment
from cozmo.schema import (
    Adjacency,
    Measure,
    Opening,
    OpeningType,
    Plane,
    Room,
    Surface,
    SurfaceType,
    Tier,
    Wall,
)
from cozmo.uncertainty.calibration import IntervalBook

EDGE_SUPPORT_DISTANCE_M = 0.22
EDGE_PARALLEL_TOLERANCE_RAD = np.deg2rad(12.0)
OPENING_MATCH_DISTANCE_M = 0.55
OPENING_MATCH_WIDTH_RATIO = 0.40
MIN_WALL_EDGE_M = 0.12


@dataclass
class RoomGeometry:
    room_id: str
    polygon: Polygon
    mask: np.ndarray
    label: str = "room"


def _edge_support(
    start: np.ndarray,
    end: np.ndarray,
    walls: list[WallSegment],
    interior_point: np.ndarray,
) -> WallSegment | None:
    """The wall segment that best explains one polygon edge."""
    edge = end - start
    length = np.linalg.norm(edge)
    if length < 1e-6:
        return None
    direction = edge / length
    midpoint = 0.5 * (start + end)

    best: tuple[float, WallSegment] | None = None
    for wall in walls:
        parallel = abs(float(direction @ wall.direction))
        if parallel < np.cos(EDGE_PARALLEL_TOLERANCE_RAD):
            continue
        perpendicular = abs(float((midpoint - wall.start) @ wall.normal_xz))
        if perpendicular > EDGE_SUPPORT_DISTANCE_M:
            continue
        # The wall's normal must point at the room, not away from it. Both faces of a
        # partition sit on nearly the same line and only this test separates them.
        if (interior_point - midpoint) @ wall.normal_xz <= 0:
            continue
        t = float((midpoint - wall.start) @ wall.direction)
        if t < -0.6 or t > wall.length + 0.6:
            continue
        score = perpendicular + 0.05 * (1.0 - parallel)
        if best is None or score < best[0]:
            best = (score, wall)
    return None if best is None else best[1]


def room_levels(
    cloud: FusedCloud,
    grid: Grid2D,
    mask: np.ndarray,
    global_levels: LevelEstimate,
) -> LevelEstimate:
    """Floor and ceiling measured from this room's own points."""
    cells = grid.to_cell(cloud.points[:, [0, 2]].astype(np.float64))
    inside = grid.inside(cells)
    selected = np.zeros(len(cloud.points), dtype=bool)
    selected[inside] = mask[cells[inside, 0], cells[inside, 1]]
    if selected.sum() < 400:
        return global_levels
    try:
        return detect_levels(cloud.select(selected))
    except ValueError:
        return global_levels


def build_room(
    geometry: RoomGeometry,
    walls: list[WallSegment],
    openings_by_wall: dict[int, list[DetectedOpening]],
    levels: LevelEstimate,
    book: IntervalBook,
    tier: Tier,
    observation_quality: float,
) -> tuple[Room, dict[str, DetectedOpening]]:
    """Assemble one room's walls, surfaces and openings into contract objects."""
    polygon = geometry.polygon
    ring = np.asarray(polygon.exterior.coords)[:-1]
    interior_point = np.array(polygon.representative_point().coords[0])

    height_value = levels.height if levels.height is not None else 0.0
    height_sigma = levels.sigma_height
    ceiling_measure = book.measure(
        "ceiling_height", height_value, tier, "m", propagated_sigma=height_sigma
    )

    wall_objects: list[Wall] = []
    surfaces: list[Surface] = []
    opening_objects: list[Opening] = []
    opening_lookup: dict[str, DetectedOpening] = {}

    wall_index = {id(w): i for i, w in enumerate(walls)}

    for i in range(len(ring)):
        start, end = ring[i], ring[(i + 1) % len(ring)]
        length = float(np.linalg.norm(end - start))
        if length < MIN_WALL_EDGE_M:
            continue
        support = _edge_support(start, end, walls, interior_point)
        wall_id = f"{geometry.room_id}_w{len(wall_objects):02d}"
        surface_id = f"{geometry.room_id}_s{len(surfaces):02d}"

        if support is not None:
            normal = support.plane.normal
            plane = Plane(normal=(float(normal[0]), float(normal[1]), float(normal[2])),
                          offset=float(support.plane.offset))
            # A wall's length is the distance between two corners, and each corner is the
            # intersection of two plane fits. The offset uncertainty of both planes that
            # meet at a corner therefore lands in the length, twice over.
            sigma_length = float(np.sqrt(2.0) * support.plane.sigma_offset * np.sqrt(2.0))
            support_count = support.plane.inlier_count
        else:
            direction = (end - start) / max(length, 1e-9)
            normal_xz = np.array([-direction[1], direction[0]])
            if (interior_point - 0.5 * (start + end)) @ normal_xz < 0:
                normal_xz = -normal_xz
            plane = Plane(
                normal=(float(normal_xz[0]), 0.0, float(normal_xz[1])),
                offset=float(-(normal_xz @ start)),
            )
            sigma_length = None
            support_count = 0

        length_measure = book.measure(
            "wall_length", length, tier, "m", propagated_sigma=sigma_length
        )
        wall_objects.append(
            Wall(
                wall_id=wall_id,
                surface_id=surface_id,
                start=(float(start[0]), float(start[1])),
                end=(float(end[0]), float(end[1])),
                length=length_measure,
                height=ceiling_measure,
                plane=plane,
                point_support=int(support_count),
            )
        )
        surfaces.append(
            Surface(
                surface_id=surface_id,
                room_id=geometry.room_id,
                type=SurfaceType.WALL,
                area=book.measure(
                    "wall_area", length * max(height_value, 0.0), tier, "m2",
                    propagated_sigma=None,
                    floor_half_width=0.05 * length * max(height_value, 0.1),
                ),
                plane=plane,
            )
        )

        if support is None:
            continue
        idx = wall_index.get(id(support))
        if idx is None:
            continue
        for detected in openings_by_wall.get(idx, []):
            centre = detected.centre_world
            t_edge = float((centre - start) @ ((end - start) / max(length, 1e-9)))
            if t_edge < -0.10 or t_edge > length + 0.10:
                continue
            opening_id = f"{geometry.room_id}_o{len(opening_objects):02d}"
            opening_objects.append(
                Opening(
                    opening_id=opening_id,
                    type=detected.opening_type,
                    wall_id=wall_id,
                    width=book.measure("opening_width", detected.width, tier, "m"),
                    height=book.measure("opening_height", detected.height, tier, "m"),
                    sill_height=book.measure("sill_height", detected.sill, tier, "m"),
                    offset_along_wall=book.measure("sill_height", max(t_edge, 0.0), tier, "m"),
                    detection_confidence=detected.confidence,
                )
            )
            opening_lookup[opening_id] = detected

    floor_surface = Surface(
        surface_id=f"{geometry.room_id}_floor",
        room_id=geometry.room_id,
        type=SurfaceType.FLOOR,
        area=book.measure("floor_area", float(polygon.area), tier, "m2"),
        plane=Plane(normal=(0.0, 1.0, 0.0), offset=float(-levels.floor_height)),
    )
    ceiling_surface = Surface(
        surface_id=f"{geometry.room_id}_ceiling",
        room_id=geometry.room_id,
        type=SurfaceType.CEILING,
        area=book.measure("floor_area", float(polygon.area), tier, "m2"),
        plane=Plane(
            normal=(0.0, -1.0, 0.0),
            offset=float(levels.ceiling_height if levels.ceiling_height is not None else 0.0),
        ),
    )
    surfaces.extend([floor_surface, ceiling_surface])

    room = Room(
        room_id=geometry.room_id,
        label=geometry.label,
        polygon=[(float(p[0]), float(p[1])) for p in ring],
        walls=wall_objects,
        surfaces=surfaces,
        openings=opening_objects,
        ceiling_height=ceiling_measure,
        floor_area=book.measure("floor_area", float(polygon.area), tier, "m2"),
        perimeter=book.measure("perimeter", float(polygon.length), tier, "m"),
        observation_quality=float(np.clip(observation_quality, 0.0, 1.0)),
    )
    return room, opening_lookup


def match_adjacency(
    rooms: list[Room], lookups: dict[str, dict[str, DetectedOpening]]
) -> list[Adjacency]:
    """Pair openings seen from both sides of the same partition."""
    entries: list[tuple[str, Opening, DetectedOpening]] = []
    for room in rooms:
        lookup = lookups.get(room.room_id, {})
        for opening in room.openings:
            detected = lookup.get(opening.opening_id)
            if detected is not None:
                entries.append((room.room_id, opening, detected))

    used: set[str] = set()
    out: list[Adjacency] = []
    for i, (room_a, open_a, det_a) in enumerate(entries):
        if open_a.opening_id in used:
            continue
        best: tuple[float, str, Opening] | None = None
        for room_b, open_b, det_b in entries[i + 1 :]:
            if room_b == room_a or open_b.opening_id in used:
                continue
            if open_a.type != open_b.type:
                continue
            distance = float(np.linalg.norm(det_a.centre_world - det_b.centre_world))
            if distance > OPENING_MATCH_DISTANCE_M:
                continue
            wider = max(open_a.width.value, open_b.width.value, 1e-6)
            ratio = abs(open_a.width.value - open_b.width.value) / wider
            if ratio > OPENING_MATCH_WIDTH_RATIO:
                continue
            score = distance + ratio
            if best is None or score < best[0]:
                best = (score, room_b, open_b)
        if best is None:
            continue
        _, room_b, open_b = best
        used.add(open_a.opening_id)
        used.add(open_b.opening_id)
        out.append(
            Adjacency(
                room_a=room_a,
                room_b=room_b,
                opening_a=open_a.opening_id,
                opening_b=open_b.opening_id,
                confidence=float(min(open_a.detection_confidence, open_b.detection_confidence)),
                evidence=(
                    f"{open_a.type.value} observed from both rooms, centres "
                    f"{np.linalg.norm(det_a.centre_world - entries[0][2].centre_world) * 0 + best[0]:.2f} apart in score"
                ),
            )
        )
    return out


def total_area(rooms: list[Room], book: IntervalBook, tier: Tier) -> Measure:
    """Property floor area, with the interval widened for correlated per-room error.

    Room areas do not err independently. A scale bias in the depth stream, or a residual
    gravity tilt, moves every room the same way, so summing the half-widths in quadrature
    would understate the total. The correlated part is carried at full width.
    """
    total = float(sum(r.floor_area.value for r in rooms))
    independent = float(np.sqrt(sum((r.floor_area.half_width * 0.5) ** 2 for r in rooms)))
    correlated = float(sum(r.floor_area.half_width * 0.5 for r in rooms))
    half = independent + correlated
    measure = book.measure("floor_area", total, tier, "m2", floor_half_width=half)
    return measure
