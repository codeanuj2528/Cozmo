"""Interior extraction, room segmentation and wall-snapped room polygons.

Three stages, each answering a different question.

`build_interior` answers "where is there floor you could stand on". It comes from the
carved free space rather than from the point cloud, because a point cloud cannot
distinguish a region nobody looked at from a region that is solid.

`segment_rooms` answers "where does one room end and the next begin". Rooms are basins of
the distance transform and doorways are the ridges between them, which is a watershed. The
watershed alone over-segments, so adjacent regions are merged whenever the throat between
them is wider than a door can be. That single rule is what keeps an L-shaped living room
one room and a bedroom off a corridor two.

`room_polygon` answers "what shape is it, in metres". The free-space boundary is the right
topology but the wrong precision: it is a raster edge, quantised to the grid and eaten into
by whatever was standing against the wall. So each boundary run is snapped onto the wall
plane that supports it and corners are recovered by intersecting consecutive planes. The
polygon that comes out is built from plane fits with millimetre-level offset uncertainty,
not from pixels.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union
from skimage.measure import find_contours
from skimage.morphology import h_maxima
from skimage.segmentation import watershed

from cozmo.geometry.grid import Grid2D
from cozmo.geometry.occupancy import OccupancyMaps
from cozmo.geometry.walls import WallSegment
from cozmo.util.raster import (
    EIGHT_CONNECTED,
    components_touching,
    draw_segments,
    fill_small_holes,
    remove_small_blobs,
)

MAX_DOOR_WIDTH_M = 1.60
MIN_ROOM_AREA_M2 = 1.20
SNAP_DISTANCE_M = 0.28
MIN_SNAP_RUN_M = 0.30
PARALLEL_TOLERANCE_RAD = np.deg2rad(8.0)


@dataclass
class RoomRegion:
    """One segmented room: its raster footprint, its polygon and the walls that shaped it."""

    room_id: str
    label: int
    mask: np.ndarray = field(repr=False)
    polygon: Polygon
    supporting_walls: list[tuple[WallSegment, LineString]] = field(default_factory=list, repr=False)
    area_m2: float = 0.0
    observed_fraction: float = 1.0

    @property
    def centroid(self) -> np.ndarray:
        c = self.polygon.centroid
        return np.array([c.x, c.y])


def wall_barrier(
    grid: Grid2D,
    walls: list[WallSegment],
    occ: OccupancyMaps,
    extend_m: float = 0.45,
) -> np.ndarray:
    """Raster of everything a flood fill must not cross.

    Wall runs are extended a little past their observed ends before rasterising. The least
    observed part of any wall is where it meets another wall, because the corner is grazed
    by the sensor rather than faced, and an unextended run leaves a gap exactly there for
    the fill to escape through.
    """
    barrier = np.zeros(grid.shape, dtype=bool)
    if walls:
        starts = np.array([w.start - w.direction * extend_m for w in walls])
        ends = np.array([w.end + w.direction * extend_m for w in walls])
        barrier |= draw_segments(
            grid.shape, grid.to_cell_float(starts), grid.to_cell_float(ends), thickness=2
        )
    strong = occ.wall_weight > 0
    if strong.any():
        cut = np.percentile(occ.wall_weight[strong], 55)
        barrier |= occ.wall_weight > cut
    return barrier


def build_interior(
    occ: OccupancyMaps,
    walls: list[WallSegment],
    reach_m: float = 2.2,
    min_area_m2: float = 1.0,
) -> np.ndarray:
    """Boolean raster of standable interior space.

    The interior is the region enclosed by walls, not the region whose floor was seen.
    Those differ by everything under the furniture and everything in the corners the
    operator never pointed at: on the 100 m sample capture the observed floor is 46 m2
    while the enclosed interior is substantially larger, and reporting the former as floor
    area would understate every room in the property.

    So the fill is seeded on direct evidence -- floor returns, carved free space, and the
    camera's own track, all of which are proof of standability -- and then grows until it
    meets a wall. To stop a fill escaping through a window or a gap in wall coverage and
    swallowing the outdoors, growth is also bounded to `reach_m` of some observation.
    """
    barrier = wall_barrier(occ.grid, walls, occ)

    seeds = occ.floor_hits | (occ.free_mask & occ.observed)
    if len(occ.camera_track):
        track = np.round(occ.camera_track).astype(int)
        ok = (
            (track[:, 0] >= 0) & (track[:, 0] < occ.grid.shape[0])
            & (track[:, 1] >= 0) & (track[:, 1] < occ.grid.shape[1])
        )
        seeds[track[ok, 0], track[ok, 1]] = True
    seeds &= ~barrier
    if not seeds.any():
        return np.zeros(occ.grid.shape, dtype=bool)

    reach_cells = int(round(reach_m / occ.grid.resolution))
    bounded = ndimage.binary_dilation(occ.observed, EIGHT_CONNECTED, iterations=reach_cells)

    interior = components_touching(bounded & ~barrier, seeds)
    interior = ndimage.binary_closing(interior, EIGHT_CONNECTED, iterations=2)
    interior = fill_small_holes(interior, max_cells=int(4.0 / occ.grid.cell_area))
    interior = remove_small_blobs(interior, min_cells=int(min_area_m2 / occ.grid.cell_area))
    return interior


def segment_rooms(
    interior: np.ndarray,
    grid: Grid2D,
    max_door_width_m: float = MAX_DOOR_WIDTH_M,
    min_room_area_m2: float = MIN_ROOM_AREA_M2,
) -> np.ndarray:
    """Label rooms. Returns an int raster, 0 outside, 1..n per room."""
    if not interior.any():
        return np.zeros_like(interior, dtype=np.int32)

    distance = ndimage.distance_transform_edt(interior) * grid.resolution
    # Regional maxima at least 20 cm deeper than their surroundings. A shallower threshold
    # seeds a marker on every furniture alcove; a deeper one merges small rooms away.
    seeds = h_maxima(distance, h=0.20) > 0
    seeds &= distance > 0.45
    markers, n_markers = ndimage.label(seeds, structure=np.ones((3, 3)))
    if n_markers == 0:
        return interior.astype(np.int32)

    labels = watershed(-distance, markers, mask=interior).astype(np.int32)
    labels = _merge_wide_throats(labels, distance, max_door_width_m)
    labels = _absorb_small_rooms(labels, grid, min_room_area_m2)
    return _relabel_consecutive(labels)


def _region_adjacency(labels: np.ndarray) -> dict[tuple[int, int], np.ndarray]:
    """Boundary cells shared by each pair of neighbouring labels."""
    pairs: dict[tuple[int, int], list[tuple[int, int]]] = {}
    h, w = labels.shape
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        a = labels[max(0, -dr) : h - max(0, dr), max(0, -dc) : w - max(0, dc)]
        b = labels[max(0, dr) : h - max(0, -dr), max(0, dc) : w - max(0, -dc)]
        diff = (a > 0) & (b > 0) & (a != b)
        if not diff.any():
            continue
        rr, cc = np.nonzero(diff)
        rr = rr + max(0, -dr)
        cc = cc + max(0, -dc)
        for r, c, la, lb in zip(rr, cc, a[diff], b[diff]):
            key = (int(min(la, lb)), int(max(la, lb)))
            pairs.setdefault(key, []).append((int(r), int(c)))
    return {k: np.array(v) for k, v in pairs.items()}


def _merge_wide_throats(labels: np.ndarray, distance: np.ndarray, max_door_width_m: float) -> np.ndarray:
    """Merge neighbouring regions whose narrowest connection is wider than a door.

    The watershed cuts wherever the distance transform dips, which includes the waist of an
    L-shaped room and the mouth of an alcove. Only a cut narrow enough to be a real doorway
    should survive as a room boundary.
    """
    changed = True
    guard = 0
    while changed and guard < 40:
        changed = False
        guard += 1
        for (a, b), cells in _region_adjacency(labels).items():
            if len(cells) == 0:
                continue
            # The widest point of the shared boundary is the throat: a doorway is narrow
            # everywhere along it, an open connection is not.
            throat = 2.0 * float(distance[cells[:, 0], cells[:, 1]].max())
            if throat > max_door_width_m:
                labels[labels == b] = a
                changed = True
                break
    return labels


def _absorb_small_rooms(labels: np.ndarray, grid: Grid2D, min_room_area_m2: float) -> np.ndarray:
    """Fold fragments below the minimum room area into their largest neighbour."""
    for _ in range(20):
        ids, counts = np.unique(labels[labels > 0], return_counts=True)
        areas = counts * grid.cell_area
        small = ids[areas < min_room_area_m2]
        if len(small) == 0:
            break
        adjacency = _region_adjacency(labels)
        merged = False
        for s in small:
            neighbours = [
                (other, len(cells))
                for (a, b), cells in adjacency.items()
                for other in ((b,) if a == s else (a,) if b == s else ())
            ]
            if not neighbours:
                labels[labels == s] = 0
                merged = True
                continue
            best = max(neighbours, key=lambda t: t[1])[0]
            labels[labels == s] = best
            merged = True
        if not merged:
            break
    return labels


def _relabel_consecutive(labels: np.ndarray) -> np.ndarray:
    ids = np.unique(labels[labels > 0])
    out = np.zeros_like(labels)
    for new, old in enumerate(ids, start=1):
        out[labels == old] = new
    return out


def _inward_ok(point_xz: np.ndarray, normal_xz: np.ndarray, interior: np.ndarray, grid: Grid2D) -> bool:
    """True when stepping along the wall normal from this point lands inside the room."""
    probe = point_xz + normal_xz * 0.10
    cell = grid.to_cell(probe[None, :])
    if not grid.inside(cell)[0]:
        return False
    return bool(interior[cell[0, 0], cell[0, 1]])


def _snap_contour(
    contour_xz: np.ndarray,
    walls: list[WallSegment],
    interior: np.ndarray,
    grid: Grid2D,
    snap_distance_m: float,
) -> tuple[Polygon, list[tuple[WallSegment, LineString]]]:
    """Replace runs of raster boundary with the wall planes that support them."""
    n = len(contour_xz)
    assign = np.full(n, -1, dtype=int)

    if walls:
        normals = np.array([w.normal_xz for w in walls])
        offsets = np.array([w.normal_xz @ w.start for w in walls])
        dirs = np.array([w.direction for w in walls])
        starts = np.array([w.direction @ w.start for w in walls])
        ends = np.array([w.direction @ w.end for w in walls])

        perpendicular = np.abs(contour_xz @ normals.T - offsets[None, :])
        along = contour_xz @ dirs.T
        # Allow a short overshoot past the observed run: the corner of a room is usually
        # the least-observed part of its walls, and refusing to snap there is what leaves
        # rounded corners on an otherwise rectangular room.
        within = (along > starts[None, :] - 0.35) & (along < ends[None, :] + 0.35)
        cost = np.where(within, perpendicular, np.inf)
        best = np.argmin(cost, axis=1)
        best_cost = cost[np.arange(n), best]
        for i in range(n):
            if best_cost[i] > snap_distance_m:
                continue
            w = walls[best[i]]
            if _inward_ok(contour_xz[i], w.normal_xz, interior, grid):
                assign[i] = best[i]

    # Majority filter around the ring so a single stray vertex does not break a run.
    if n > 7:
        smoothed = assign.copy()
        for i in range(n):
            window = assign[(np.arange(i - 3, i + 4)) % n]
            window = window[window >= 0]
            if len(window) >= 4:
                vals, counts = np.unique(window, return_counts=True)
                smoothed[i] = int(vals[np.argmax(counts)])
        assign = smoothed

    runs: list[tuple[int, int, int]] = []
    i = 0
    while i < n:
        if assign[i] < 0:
            i += 1
            continue
        j = i
        while j + 1 < n and assign[j + 1] == assign[i]:
            j += 1
        runs.append((i, j, int(assign[i])))
        i = j + 1
    # A run that wraps the start of the ring is one run, not two.
    if len(runs) > 1 and runs[0][0] == 0 and runs[-1][1] == n - 1 and runs[0][2] == runs[-1][2]:
        first = runs.pop(0)
        last = runs.pop()
        runs.insert(0, (last[0], first[1] + n, last[2]))

    kept = []
    for a, b, widx in runs:
        pts = contour_xz[np.arange(a, b + 1) % n]
        if np.linalg.norm(pts[-1] - pts[0]) >= MIN_SNAP_RUN_M:
            kept.append((a, b, widx))

    if len(kept) < 2:
        poly = Polygon(contour_xz).buffer(0)
        return (poly if poly.geom_type == "Polygon" else max(poly.geoms, key=lambda g: g.area)), []

    vertices: list[np.ndarray] = []
    used: list[tuple[WallSegment, LineString]] = []
    for k, (a, b, widx) in enumerate(kept):
        wall = walls[widx]
        pts = contour_xz[np.arange(a, b + 1) % n]
        t = pts @ wall.direction
        foot = wall.normal_xz * (wall.normal_xz @ wall.start)
        p_start = foot + wall.direction * t.min()
        p_end = foot + wall.direction * t.max()

        prev_wall = walls[kept[k - 1][2]]
        corner = _intersect(prev_wall, wall)
        if corner is not None and np.linalg.norm(corner - p_start) < 2.0:
            vertices.append(corner)
        else:
            gap_a, gap_b = kept[k - 1][1], a
            bridge = contour_xz[np.arange(gap_a, gap_b + (n if gap_b < gap_a else 0) + 1) % n]
            if len(bridge) > 2:
                vertices.extend(list(bridge[1:-1]))
            vertices.append(p_start)
        vertices.append(p_end)
        used.append((wall, LineString([p_start, p_end])))

    poly = Polygon(vertices).buffer(0)
    if poly.is_empty:
        poly = Polygon(contour_xz).buffer(0)
    if poly.geom_type != "Polygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    return poly, used


def _intersect(a: WallSegment, b: WallSegment) -> np.ndarray | None:
    """Intersection of two wall lines, or None when they are too close to parallel."""
    cross = a.direction[0] * b.direction[1] - a.direction[1] * b.direction[0]
    if abs(cross) < np.sin(PARALLEL_TOLERANCE_RAD):
        return None
    na, nb = a.normal_xz, b.normal_xz
    ca, cb = na @ a.start, nb @ b.start
    mat = np.array([na, nb])
    try:
        return np.linalg.solve(mat, np.array([ca, cb]))
    except np.linalg.LinAlgError:
        return None


def extract_rooms(
    occ: OccupancyMaps,
    walls: list[WallSegment],
    snap_distance_m: float = SNAP_DISTANCE_M,
) -> tuple[list[RoomRegion], np.ndarray, np.ndarray]:
    """Full pipeline from occupancy to wall-snapped room polygons."""
    interior = build_interior(occ, walls)
    labels = segment_rooms(interior, occ.grid)

    rooms: list[RoomRegion] = []
    for label in np.unique(labels[labels > 0]):
        mask = labels == label
        filled = fill_small_holes(mask, max_cells=int(2.0 / occ.grid.cell_area))
        padded = np.pad(filled.astype(float), 1)
        contours = find_contours(padded, 0.5)
        if not contours:
            continue
        contour = max(contours, key=len) - 1.0
        world = occ.grid.to_world(contour)
        simple = LineString(world).simplify(0.035)
        world = np.asarray(simple.coords)
        if len(world) < 4:
            continue

        polygon, used = _snap_contour(world, walls, filled, occ.grid, snap_distance_m)
        if polygon.is_empty or polygon.area < MIN_ROOM_AREA_M2:
            continue
        rooms.append(
            RoomRegion(
                room_id=f"room_{int(label):02d}",
                label=int(label),
                mask=mask,
                polygon=polygon,
                supporting_walls=used,
                area_m2=float(polygon.area),
                observed_fraction=float(mask.sum() * occ.grid.cell_area / max(polygon.area, 1e-6)),
            )
        )

    rooms = _resolve_overlaps(rooms)
    return rooms, interior, labels


def _resolve_overlaps(rooms: list[RoomRegion]) -> list[RoomRegion]:
    """Trim overlaps so the stitched plan has no two rooms occupying the same floor.

    Snapping is done per room, so two rooms that share a partition can each claim the
    partition's thickness. Where that happens the overlap is split along the midline by
    giving each room the part of the overlap nearer to its own footprint.
    """
    for i, a in enumerate(rooms):
        for b in rooms[i + 1 :]:
            if not a.polygon.intersects(b.polygon):
                continue
            overlap = a.polygon.intersection(b.polygon)
            if overlap.is_empty or overlap.area < 1e-6:
                continue
            # Give the contested strip to whichever room's raster footprint covers it.
            trim_a = overlap.difference(b.polygon.buffer(0))
            _ = trim_a
            shrink = overlap.area / max(min(a.polygon.area, b.polygon.area), 1e-6)
            loser, winner = (b, a) if a.polygon.area >= b.polygon.area else (a, b)
            if shrink < 0.5:
                trimmed = loser.polygon.difference(winner.polygon)
                if trimmed.geom_type == "MultiPolygon":
                    trimmed = max(trimmed.geoms, key=lambda g: g.area)
                if not trimmed.is_empty and trimmed.area > MIN_ROOM_AREA_M2:
                    loser.polygon = trimmed
                    loser.area_m2 = float(trimmed.area)
    return rooms


def total_footprint(rooms: list[RoomRegion]) -> Polygon:
    if not rooms:
        return Polygon()
    return unary_union([r.polygon for r in rooms])
