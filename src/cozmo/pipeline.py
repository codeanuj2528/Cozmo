"""End-to-end reconstruction, shared by all three tiers.

Every tier resolves to frames carrying intrinsics, metric depth and a pose, so they share
this core and differ only in how those fields were obtained and how much they can be
trusted. That is deliberate. Three parallel reconstruction stacks would drift apart and
only one of them would stay correct, and the tier comparison the brief asks for would then
be measuring implementation differences rather than sensor differences.

The pass order matters in two places.

Walls are extracted twice. The first pass exists only to find the property's own axes; the
cloud is then rotated onto them and walls are re-extracted. A raster aligned to the walls
quantises them along their own direction instead of across it, and on the sample capture
the property sits 27 degrees off the ARKit axes, where an unaligned grid is spending its
whole cell size on staircasing every wall.

Levels are measured twice for the same reason at a different scale: once globally to get a
floor to reference everything to, and again per room once rooms exist, because ceiling
height is a per-room quantity and the gate is a per-room gate.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np

from cozmo import __version__
from cozmo.config import PipelineConfig
from cozmo.geometry.assemble import (
    RoomGeometry,
    build_room,
    match_adjacency,
    room_levels,
    total_area,
)
from cozmo.geometry.cellcomplex import CellComplex, build_cell_complex, room_masks, room_polygons
from cozmo.geometry.fusion import FusedCloud, fuse, select_keyframes
from cozmo.geometry.levels import LevelEstimate, detect_levels, refine_gravity
from cozmo.geometry.occupancy import OccupancyMaps, build_occupancy
from cozmo.geometry.openings import detect_all_openings
from cozmo.geometry.walls import (
    WallSegment,
    dominant_directions,
    extract_wall_segments,
    merge_runs,
)
from cozmo.io.base import CaptureSource
from cozmo.schema import (
    CalibrationReport,
    DriftReport,
    IntervalMethod,
    PropertyPlan,
    QualityReport,
    Room,
    Tier,
)
from cozmo.uncertainty.calibration import IntervalBook
from cozmo.util.polygons import rotation_about_up


@dataclass
class PipelineArtifacts:
    """Intermediate state kept for rendering, ablation and debugging."""

    cloud: FusedCloud
    cameras: np.ndarray
    occupancy: OccupancyMaps
    complex: CellComplex
    walls: list[WallSegment]
    levels: LevelEstimate
    world_rotation: np.ndarray
    keyframes: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)


@dataclass
class PipelineResult:
    plan: PropertyPlan
    artifacts: PipelineArtifacts


def _frame_indices(source: CaptureSource, keyframes: list[int]) -> list[int]:
    """Frame numbers for the selected keyframes.

    A keyframe is an index into the pose array, which is only the same as the frame number
    when no row was ever dropped. Occupancy carving looks points up by frame number, so
    conflating the two silently pairs a camera with another frame's returns.
    """
    if hasattr(source, "frame_indices"):
        table = source.frame_indices()
        return [int(table[i]) for i in keyframes]
    return [int(i) for i in keyframes]


def _gather_poses(source: CaptureSource) -> np.ndarray:
    if hasattr(source, "poses"):
        return source.poses()
    poses = [f.pose for f in source.frames() if f.pose is not None]
    return np.stack(poses) if poses else np.zeros((0, 4, 4))


def reconstruct(
    source: CaptureSource,
    config: PipelineConfig | None = None,
    book: IntervalBook | None = None,
    drift_hook=None,
) -> PipelineResult:
    """Run the full reconstruction for one capture."""
    config = config or PipelineConfig()
    book = book or IntervalBook.load(config.calibration_path)
    started = time.perf_counter()
    timings: dict[str, float] = {}
    warnings: list[str] = []

    poses = _gather_poses(source)
    if len(poses) == 0:
        raise ValueError("capture has no poses; a tier adapter must supply them")

    mark = time.perf_counter()
    keyframes = select_keyframes(
        poses,
        translation_m=config.keyframe_translation_m,
        rotation_rad=np.deg2rad(config.keyframe_rotation_deg),
        max_frames=config.max_keyframes,
    )
    cloud = fuse(
        source,
        keyframes,
        voxel_m=config.voxel_m,
        min_confidence=config.min_depth_confidence,
        max_range_m=config.max_depth_range_m,
    )
    timings["fuse_s"] = time.perf_counter() - mark
    if len(cloud) == 0:
        raise ValueError("fusion produced no points; check depth availability")

    mark = time.perf_counter()
    gravity_rotation, _, gravity_warnings = refine_gravity(cloud)
    warnings.extend(gravity_warnings)
    cloud = cloud.rotated(gravity_rotation)
    cameras = poses[keyframes][:, :3, 3] @ gravity_rotation.T
    world_rotation = gravity_rotation

    drift = DriftReport(
        method="not applied",
        loop_closures_found=0,
        residual_before_m=0.0,
        residual_after_m=0.0,
        max_pose_correction_m=0.0,
        footprint_area_before_m2=0.0,
        footprint_area_after_m2=0.0,
        applied=False,
    )
    if config.drift_correction and drift_hook is not None:
        cloud, cameras, drift = drift_hook(source, keyframes, cloud, cameras, config)
    timings["gravity_and_drift_s"] = time.perf_counter() - mark

    mark = time.perf_counter()
    levels = detect_levels(cloud)
    warnings.extend(levels.warnings)
    walls, _ = extract_wall_segments(cloud, levels.floor_height, levels.ceiling_height)

    if config.canonical_rotation and walls:
        angle = dominant_directions(walls)
        canonical = rotation_about_up(-angle)
        cloud = cloud.rotated(canonical)
        cameras = cameras @ canonical.T
        world_rotation = canonical @ world_rotation
        levels = detect_levels(cloud)
        walls, candidates = extract_wall_segments(cloud, levels.floor_height, levels.ceiling_height)
    else:
        _, candidates = extract_wall_segments(cloud, levels.floor_height, levels.ceiling_height)
    timings["walls_s"] = time.perf_counter() - mark

    mark = time.perf_counter()
    occupancy = build_occupancy(
        cloud,
        levels.floor_height,
        levels.ceiling_height,
        resolution=config.grid_resolution_m,
        camera_positions=cameras,
        camera_frames=_frame_indices(source, keyframes),
    )
    timings["occupancy_s"] = time.perf_counter() - mark

    mark = time.perf_counter()
    complex_ = build_cell_complex(occupancy, candidates, walls, max_lines=config.max_wall_lines)
    polygons = room_polygons(complex_, min_room_area_m2=config.min_room_area_m2)
    masks = room_masks(complex_)
    timings["floorplan_s"] = time.perf_counter() - mark

    mark = time.perf_counter()
    # Openings and polygon edges are matched against bridged wall runs; the cell complex
    # keeps the tight segments, because "is there material here" and "where are the holes"
    # need opposite answers from the same geometry.
    runs = merge_runs(walls)
    openings_by_wall = detect_all_openings(runs, cloud, levels.floor_height, levels.ceiling_height)
    timings["openings_s"] = time.perf_counter() - mark

    tier = source.meta.tier
    rooms: list[Room] = []
    lookups: dict[str, dict] = {}
    ordered = sorted(polygons.items(), key=lambda kv: -kv[1].area)
    for ordinal, (room_key, polygon) in enumerate(ordered, start=1):
        room_id = f"room_{ordinal:02d}"
        mask = masks.get(room_key, np.zeros(occupancy.grid.shape, dtype=bool))
        per_room = room_levels(cloud, occupancy.grid, mask, levels)
        geometry = RoomGeometry(
            room_id=room_id,
            polygon=polygon,
            mask=mask,
            label=config.labels.get(room_id, "room"),
        )
        observed = float(mask.sum() * occupancy.grid.cell_area / max(polygon.area, 1e-6))
        room, lookup = build_room(
            geometry, runs, openings_by_wall, per_room, book, tier, observed
        )
        rooms.append(room)
        lookups[room_id] = lookup

    adjacency = match_adjacency(rooms, lookups)

    quality = _quality_report(source, cloud, keyframes, rooms, occupancy, tier, warnings)
    calibration = CalibrationReport(
        method=IntervalMethod.CONFORMAL if book.entries else IntervalMethod.PROPAGATED,
        nominal_coverage=book.coverage,
        empirical_coverage={
            f"{k[0]}/{k[1]}": v.empirical_coverage for k, v in book.entries.items()
        },
        residual_quantiles={f"{k[0]}/{k[1]}": v.quantile for k, v in book.entries.items()},
        fitted_on=book.source,
    )

    plan = PropertyPlan(
        pipeline_version=__version__,
        capture_id=source.meta.capture_id,
        tier=tier,
        created_at=datetime.now(timezone.utc),
        rooms=rooms,
        adjacency=adjacency,
        damage=[],
        concealed_flags=[],
        scope_items=[],
        drift=drift,
        calibration=calibration,
        quality=quality,
        total_floor_area=total_area(rooms, book, tier),
        runtime_seconds=time.perf_counter() - started,
    )

    artifacts = PipelineArtifacts(
        cloud=cloud,
        cameras=cameras,
        occupancy=occupancy,
        complex=complex_,
        walls=runs,
        levels=levels,
        world_rotation=world_rotation,
        keyframes=keyframes,
        warnings=warnings,
        timings=timings,
    )
    return PipelineResult(plan=plan, artifacts=artifacts)


def _quality_report(
    source: CaptureSource,
    cloud: FusedCloud,
    keyframes: list[int],
    rooms: list[Room],
    occupancy: OccupancyMaps,
    tier: Tier,
    warnings: list[str],
) -> QualityReport:
    total_polygon_area = sum(r.floor_area.value for r in rooms)
    observed_floor = float(occupancy.floor_hits.sum() * occupancy.grid.cell_area)
    coverage = float(np.clip(observed_floor / max(total_polygon_area, 1e-6), 0.0, 1.0))

    median_confidence = None
    if tier is Tier.LIDAR:
        # Report the sensor's own confidence, not the fused precision: the reader wants to
        # know what the LiDAR thought of its returns.
        median_confidence = float(np.median(cloud.sigma))

    return QualityReport(
        tier=tier,
        device_model=source.meta.device_model,
        frames_available=source.meta.frame_count,
        frames_used=len(keyframes),
        median_depth_confidence=median_confidence,
        surface_coverage=coverage,
        low_light_fraction=0.0,
        specular_fraction=0.0,
        warnings=list(warnings),
    )
