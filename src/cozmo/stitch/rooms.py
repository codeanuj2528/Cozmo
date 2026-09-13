"""Assembling separately reconstructed rooms into one property plan.

At the LiDAR and video tiers the property arrives as one continuous walk, so the rooms are
already in a common frame and stitching is something the trajectory did for you. At the
photo tier it is not: each room is a folder of stills with nothing in common with the next
folder, reconstructed in its own arbitrary frame. The brief adds a gate for exactly this,
because a photo path that handles single rooms only fails.

The only thing two rooms physically share is the doorway between them. Both see it, both
measure its width, and the two observations are of the same hole in the same partition, so
aligning those two observations places one room relative to the other. That is the whole
method: match doorways, and let each match fix a relative pose.

Placement is a greedy spanning tree rather than a global optimisation. With a handful of
rooms the tree is what the evidence supports -- there is rarely more than one credible
door match per pair, so there is no loop to distribute error around, and a global solver
would be fitting parameters the data does not constrain. Rooms whose doorway was seen from
one side only cannot be placed, and are reported as unplaced rather than guessed at,
because a room put in the wrong place is worse than a room the plan admits it could not
locate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from shapely.geometry import Polygon

from cozmo.schema import Adjacency, Opening, OpeningType, Room, Wall

log = logging.getLogger(__name__)

WIDTH_MATCH_TOLERANCE = 0.30
MIN_MATCH_SCORE = 0.35
OVERLAP_TOLERANCE_M2 = 0.25
UNPLACED_GAP_M = 1.5
CONNECTING_TYPES = (OpeningType.DOOR, OpeningType.PASS_THROUGH)
# Folder names the brief treats as the connector between rooms. Used only when
# doorway matching has nothing to work with — the photo tier often detects
# zero openings. This is name evidence, not a measured doorway, and the
# adjacency records that.
CONNECTOR_LABELS = frozenset({"hall", "hallway", "passage", "corridor", "landing"})


@dataclass
class DoorObservation:
    room_id: str
    opening: Opening
    centre: np.ndarray
    normal: np.ndarray
    along: np.ndarray


def _rotation(angle: float) -> np.ndarray:
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, -s], [s, c]])


def door_observations(room: Room) -> list[DoorObservation]:
    """Where each connecting opening sits, and which way it faces, in the room's frame."""
    walls = {w.wall_id: w for w in room.walls}
    out: list[DoorObservation] = []
    for opening in room.openings:
        if opening.type not in CONNECTING_TYPES:
            continue
        wall = walls.get(opening.wall_id)
        if wall is None:
            continue
        start = np.array(wall.start, dtype=float)
        end = np.array(wall.end, dtype=float)
        length = float(np.linalg.norm(end - start))
        if length < 1e-6:
            continue
        along = (end - start) / length
        offset = float(np.clip(opening.offset_along_wall.value, 0.0, length))
        normal = np.array([wall.plane.normal[0], wall.plane.normal[2]], dtype=float)
        norm = float(np.linalg.norm(normal))
        normal = normal / norm if norm > 1e-6 else np.array([-along[1], along[0]])
        out.append(
            DoorObservation(
                room_id=room.room_id,
                opening=opening,
                centre=start + along * offset,
                normal=normal,
                along=along,
            )
        )
    return out


def match_score(a: DoorObservation, b: DoorObservation) -> float:
    """How well two doorway observations could be the same doorway."""
    if a.opening.type is not b.opening.type:
        return 0.0
    wa, wb = a.opening.width.value, b.opening.width.value
    if min(wa, wb) <= 0.05:
        return 0.0
    width_error = abs(wa - wb) / max(wa, wb)
    if width_error > WIDTH_MATCH_TOLERANCE:
        return 0.0

    score = 1.0 - width_error / WIDTH_MATCH_TOLERANCE
    ha, hb = a.opening.height.value, b.opening.height.value
    if ha > 0.1 and hb > 0.1:
        height_error = abs(ha - hb) / max(ha, hb)
        score = 0.65 * score + 0.35 * max(0.0, 1.0 - height_error / 0.35)
    confidence = min(a.opening.detection_confidence, b.opening.detection_confidence)
    return float(score * (0.5 + 0.5 * confidence))


def transform_room(room: Room, angle: float, translation: np.ndarray) -> Room:
    """Rigidly move a room in the floor plane, geometry and wall planes together."""
    rotation = _rotation(angle)

    def move(point) -> tuple[float, float]:
        moved = rotation @ np.asarray(point, dtype=float) + translation
        return (float(moved[0]), float(moved[1]))

    walls: list[Wall] = []
    for wall in room.walls:
        normal = rotation @ np.array([wall.plane.normal[0], wall.plane.normal[2]])
        start = move(wall.start)
        # The plane offset must be recomputed rather than rotated: n . x + d = 0 has a d
        # that depends on where the plane sits, and translating the room changes it.
        offset = -float(normal @ np.array(start))
        walls.append(
            wall.model_copy(
                update={
                    "start": start,
                    "end": move(wall.end),
                    "plane": wall.plane.model_copy(
                        update={
                            "normal": (float(normal[0]), 0.0, float(normal[1])),
                            "offset": offset,
                        }
                    ),
                }
            )
        )

    return room.model_copy(
        update={"polygon": [move(p) for p in room.polygon], "walls": walls}
    )


def _pose_from_match(
    fixed: DoorObservation, moving: DoorObservation
) -> tuple[float, np.ndarray]:
    """The transform that brings `moving`'s room onto `fixed`'s doorway.

    Two rooms sit on opposite sides of a partition, so the wall normals -- which both point
    into their own room -- must end up anti-parallel. That fixes the rotation. Making the
    two doorway centres coincide then fixes the translation.
    """
    target = -fixed.normal
    angle = float(
        np.arctan2(target[1], target[0]) - np.arctan2(moving.normal[1], moving.normal[0])
    )
    rotation = _rotation(angle)
    translation = fixed.centre - rotation @ moving.centre
    return angle, translation


def stitch_property(rooms: list[Room]) -> tuple[list[Room], list[Adjacency], list[str]]:
    """Place rooms into one frame by matching the doorways they share."""
    warnings: list[str] = []
    if len(rooms) <= 1:
        return list(rooms), [], warnings

    observations = {room.room_id: door_observations(room) for room in rooms}
    without_doors = [rid for rid, obs in observations.items() if not obs]
    if without_doors:
        warnings.append(
            f"{len(without_doors)} room(s) have no connecting opening detected and cannot "
            f"be stitched by doorway: {', '.join(without_doors)}"
        )

    by_id = {room.room_id: room for room in rooms}
    placed: dict[str, Room] = {}
    anchor = max(rooms, key=lambda r: r.floor_area.value)
    placed[anchor.room_id] = anchor
    placed_observations = {anchor.room_id: observations[anchor.room_id]}

    adjacency: list[Adjacency] = []
    remaining = {r.room_id for r in rooms} - {anchor.room_id}

    while remaining:
        best: tuple[float, str, DoorObservation, DoorObservation] | None = None
        for candidate in remaining:
            for moving in observations.get(candidate, []):
                for fixed_room, fixed_list in placed_observations.items():
                    for fixed in fixed_list:
                        score = match_score(fixed, moving)
                        if score >= MIN_MATCH_SCORE and (best is None or score > best[0]):
                            best = (score, candidate, fixed, moving)
        if best is None:
            break

        score, candidate, fixed, moving = best
        angle, translation = _pose_from_match(fixed, moving)
        moved = transform_room(by_id[candidate], angle, translation)

        overlap = _overlap_area(moved, placed.values())
        if overlap > OVERLAP_TOLERANCE_M2:
            # The doorway can be matched with the moving room on either side of it along
            # the wall; try the reflection before giving up on the match.
            alt_angle = angle + np.pi
            alt_rotation = _rotation(alt_angle)
            alt_translation = fixed.centre - alt_rotation @ moving.centre
            alternative = transform_room(by_id[candidate], alt_angle, alt_translation)
            if _overlap_area(alternative, placed.values()) < overlap:
                moved, angle, translation = alternative, alt_angle, alt_translation
                overlap = _overlap_area(moved, placed.values())
        if overlap > OVERLAP_TOLERANCE_M2:
            moved = _push_clear(moved, placed.values(), fixed.normal)
            warnings.append(
                f"{candidate} overlapped after doorway placement and was pushed clear; "
                f"its position along that wall is uncertain"
            )

        placed[candidate] = moved
        placed_observations[candidate] = door_observations(moved)
        remaining.discard(candidate)
        adjacency.append(
            Adjacency(
                room_a=fixed.room_id,
                room_b=candidate,
                opening_a=fixed.opening.opening_id,
                opening_b=moving.opening.opening_id,
                confidence=float(np.clip(score, 0.0, 1.0)),
                evidence=(
                    f"doorway matched across rooms: widths "
                    f"{fixed.opening.width.value:.2f} m and {moving.opening.width.value:.2f} m"
                ),
            )
        )

    if remaining:
        inferred, infer_warnings = _place_by_folder_names(
            remaining, by_id, placed, rooms
        )
        warnings.extend(infer_warnings)
        adjacency.extend(inferred)
        still = {rid for rid in remaining if rid not in placed}
        if still:
            warnings.append(
                f"{len(still)} room(s) could not be joined to the property through a "
                f"doorway or a named connector and are placed alongside it, unconnected: "
                f"{', '.join(sorted(still))}"
            )
            for room_id in sorted(still):
                placed[room_id] = _place_alongside(by_id[room_id], placed.values())

    ordered = [placed[r.room_id] for r in rooms]
    return ordered, adjacency, warnings


def folder_name_pairs(rooms: list[Room]) -> list[tuple[str, str]]:
    """Which rooms a folder name says should touch.

    A hall / passage / corridor connects to every other named room. Without a
    connector, consecutive folders in capture order are the weaker fallback
    the public submission uses when visual doorway matches fail.
    """
    labels = [(room.room_id, (room.label or room.room_id).strip().lower()) for room in rooms]
    connectors = [rid for rid, label in labels if label in CONNECTOR_LABELS]
    others = [rid for rid, label in labels if label not in CONNECTOR_LABELS]
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(a: str, b: str) -> None:
        if a == b:
            return
        key = (a, b) if a < b else (b, a)
        if key not in seen:
            seen.add(key)
            pairs.append((a, b))

    if connectors:
        for connector in connectors:
            for other in others:
                add(connector, other)
        for left, right in zip(connectors, connectors[1:]):
            add(left, right)
        return pairs
    for left, right in zip([rid for rid, _ in labels], [rid for rid, _ in labels][1:]):
        add(left, right)
    return pairs


def _place_by_folder_names(
    remaining: set[str],
    by_id: dict[str, Room],
    placed: dict[str, Room],
    all_rooms: list[Room],
) -> tuple[list[Adjacency], list[str]]:
    """Slide leftover rooms against a named connector and declare the join."""
    adjacency: list[Adjacency] = []
    warnings: list[str] = []
    pairs = folder_name_pairs(all_rooms)
    pending = set(remaining)
    progressed = True
    while pending and progressed:
        progressed = False
        for room_a, room_b in pairs:
            if room_a in placed and room_b in pending:
                fixed_id, moving_id = room_a, room_b
            elif room_b in placed and room_a in pending:
                fixed_id, moving_id = room_b, room_a
            else:
                continue
            placed[moving_id] = _place_touching(by_id[moving_id], placed[fixed_id], placed.values())
            pending.discard(moving_id)
            progressed = True
            adjacency.append(
                Adjacency(
                    room_a=fixed_id,
                    room_b=moving_id,
                    opening_a="",
                    opening_b=None,
                    confidence=0.15,
                    evidence=(
                        "folder-name connector: no doorway was observed on both sides; "
                        f"{by_id[moving_id].label} placed against {by_id[fixed_id].label}"
                    ),
                )
            )
            warnings.append(
                f"{moving_id} joined to {fixed_id} from folder names only; "
                "the doorway itself was not measured"
            )
    remaining.clear()
    remaining.update(pending)
    return adjacency, warnings


def _place_touching(room: Room, neighbour: Room, others) -> Room:
    """Put `room` on the neighbour's right edge, then push clear of overlaps."""
    own = _polygon(room)
    other = _polygon(neighbour)
    if own.is_empty or other.is_empty:
        return _place_alongside(room, others)
    shift = np.array([other.bounds[2] - own.bounds[0], other.bounds[1] - own.bounds[1]])
    moved = transform_room(room, 0.0, shift)
    return _push_clear(moved, [o for o in others if o.room_id != room.room_id], np.array([-1.0, 0.0]))


def _polygon(room: Room) -> Polygon:
    poly = Polygon(room.polygon)
    return poly if poly.is_valid else poly.buffer(0)


def _overlap_area(room: Room, others) -> float:
    poly = _polygon(room)
    if poly.is_empty:
        return 0.0
    total = 0.0
    for other in others:
        if other.room_id == room.room_id:
            continue
        intersection = poly.intersection(_polygon(other))
        if not intersection.is_empty:
            total += float(intersection.area)
    return total


def _push_clear(room: Room, others, direction: np.ndarray, step: float = 0.05) -> Room:
    """Slide a room along a direction until it stops overlapping its neighbours."""
    unit = direction / max(float(np.linalg.norm(direction)), 1e-9)
    current = room
    for _ in range(80):
        if _overlap_area(current, others) <= OVERLAP_TOLERANCE_M2:
            return current
        current = transform_room(current, 0.0, -unit * step)
    return current


def _place_alongside(room: Room, others) -> Room:
    """Park an unplaceable room clear of the property, so the plan stays readable."""
    polygons = [_polygon(other) for other in others if not _polygon(other).is_empty]
    if not polygons:
        return room
    right_edge = max(p.bounds[2] for p in polygons)
    bottom = min(p.bounds[1] for p in polygons)
    own = _polygon(room)
    if own.is_empty:
        return room
    shift = np.array([right_edge + UNPLACED_GAP_M - own.bounds[0], bottom - own.bounds[1]])
    return transform_room(room, 0.0, shift)
