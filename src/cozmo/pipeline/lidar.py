"""LiDAR tier reconstruction — the reference implementation.

Every other tier is measured against this one, which is why it gets the most
careful treatment.  The pass order matters in two places:

Walls are extracted twice.  The first pass exists only to find the property's
own axes; the cloud is then rotated onto them and walls are re-extracted.
A raster aligned to the walls quantises them along their own direction instead
of across it, and on the sample capture the property sits 27 degrees off the
ARKit axes where an unaligned grid spends its whole cell size staircasing walls.

Levels are measured twice for the same reason at a different scale: once
globally to get a floor reference, then per room for per-room ceiling gates.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

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
from cozmo.geometry.cellcomplex import (
    CellComplex,
    build_cell_complex,
    room_masks,
    room_polygons,
)
from cozmo.geometry.drift import PoseOverride, correct_drift
from cozmo.geometry.fusion import FusedCloud, fuse, select_keyframes
from cozmo.geometry.levels import LevelEstimate, detect_levels, refine_gravity
from cozmo.geometry.occupancy import OccupancyMaps, build_occupancy
from cozmo.geometry.openings import detect_all_openings
from cozmo.geometry.walls import (
    WallCandidate,
    WallSegment,
    dominant_directions,
    extract_wall_segments,
    merge_runs,
    snap_to_frame,
)
from cozmo.io.base import CaptureSource
from cozmo.pipeline.common import PipelineArtifacts, PipelineResult
from cozmo.schema import (
    CalibrationReport,
    DamageRegion,
    DriftReport,
    IntervalMethod,
    PropertyPlan,
    QualityReport,
    Room,
    Tier,
)
from cozmo.uncertainty.calibration import IntervalBook
from cozmo.util.polygons import rotation_about_up

log = logging.getLogger("cozmo.pipeline.lidar")

PLAN_FILENAME = "plan.json"
PLAN_PNG_FILENAME = "plan.png"
PLAN_SVG_FILENAME = "plan.svg"
MANIFEST_FILENAME = "run_manifest.json"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resync_candidates(
    candidates: list[WallCandidate], walls: list[WallSegment]
) -> list[WallCandidate]:
    """Rebuild the line set the cell complex uses from possibly snapped walls.

    One line per distinct (direction, offset), because several runs can share a
    plane and the arrangement wants each line once.
    """
    seen: dict[tuple[int, int], WallCandidate] = {}
    for wall in walls:
        azimuth = int(
            round(
                np.degrees(np.arctan2(wall.normal_xz[1], wall.normal_xz[0])) / 2.0
            )
        )
        offset = float(wall.normal_xz @ wall.start)
        key = (azimuth, int(round(offset / 0.05)))
        existing = seen.get(key)
        if existing is None or wall.support_weight > existing.weight:
            seen[key] = WallCandidate(
                plane=wall.plane,
                normal_xz=wall.normal_xz,
                offset=offset,
                weight=wall.support_weight,
                indices=wall.point_indices,
                segments=[wall],
            )
    merged = list(seen.values())
    merged.sort(key=lambda c: c.weight, reverse=True)
    return merged or candidates


def _frame_indices(source: CaptureSource, keyframes: list[int]) -> list[int]:
    """Map keyframe indices to source frame numbers.

    A keyframe is an index into the pose array.  Occupancy carving looks points
    up by frame number, so conflating the two silently pairs a camera with
    another frame's depth returns.
    """
    if hasattr(source, "frame_indices"):
        table = source.frame_indices()
        return [int(table[i]) for i in keyframes]
    return [int(i) for i in keyframes]


def _gather_poses(source: CaptureSource) -> np.ndarray:
    """Collect all 4×4 camera-to-world poses from the capture source."""
    if hasattr(source, "poses"):
        return source.poses()
    poses = [f.pose for f in source.frames() if f.pose is not None]
    return np.stack(poses) if poses else np.zeros((0, 4, 4))


def _quality_report(
    source: CaptureSource,
    cloud: FusedCloud,
    keyframes: list[int],
    rooms: list[Room],
    occupancy: OccupancyMaps,
    tier: Tier,
    warnings: list[str],
) -> QualityReport:
    """Produce the per-run quality summary embedded in every plan."""
    total_polygon_area = sum(r.floor_area.value for r in rooms)
    observed_floor = float(occupancy.floor_hits.sum() * occupancy.grid.cell_area)
    coverage = float(
        np.clip(observed_floor / max(total_polygon_area, 1e-6), 0.0, 1.0)
    )

    median_confidence = None
    if tier is Tier.LIDAR:
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


def _hash_input(input_dir: Path) -> str:
    """Deterministic hash of the capture directory for provenance."""
    h = hashlib.sha256()
    for p in sorted(input_dir.rglob("*")):
        if p.is_file() and p.stat().st_size < 50_000_000:
            h.update(p.name.encode())
            h.update(str(p.stat().st_size).encode())
    return h.hexdigest()[:16]


def _git_commit() -> str:
    """Current git short hash, or 'unknown' outside a repo."""
    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------


def build_run_manifest(
    source: CaptureSource,
    result: PipelineResult,
    input_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Assemble the run manifest that accompanies every plan output."""
    plan = result.plan
    artifacts = result.artifacts
    manifest: dict[str, Any] = {
        "pipeline_version": plan.pipeline_version,
        "schema_version": "1.0",
        "capture_id": plan.capture_id,
        "tier": plan.tier.value,
        "generated_at": plan.created_at.isoformat(),
        "git_commit": _git_commit(),
        "runtime_seconds": round(plan.runtime_seconds, 3),
        "timings": {k: round(v, 4) for k, v in artifacts.timings.items()},
        "keyframes_used": len(artifacts.keyframes),
        "frames_available": source.meta.frame_count,
        "points_fused": len(artifacts.cloud),
        "rooms_found": len(plan.rooms),
        "total_floor_area_m2": round(plan.total_floor_area.value, 3),
        "warnings": artifacts.warnings,
    }
    if input_path is not None:
        manifest["input_hash"] = _hash_input(input_path)
    return manifest


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def reconstruct(
    source: CaptureSource,
    config: PipelineConfig | None = None,
    book: IntervalBook | None = None,
) -> PipelineResult:
    """Run the full LiDAR-tier reconstruction for one capture.

    This is the canonical entry point for the pipeline.  Photo and video tiers
    call into their own builders, which share geometric stages but differ in how
    depth and pose are obtained.
    """
    if isinstance(source, Path):
        from cozmo.io import load_capture
        source = load_capture(source)

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

    # Drift correction runs *before* fusion.  Correcting a fused cloud in place
    # would apply one frame's delta to contributions of every frame that shared
    # its voxel.
    drift = DriftReport(
        method="not applied: drift correction disabled by configuration",
        loop_closures_found=0,
        residual_before_m=0.0,
        residual_after_m=0.0,
        max_pose_correction_m=0.0,
        footprint_area_before_m2=0.0,
        footprint_area_after_m2=0.0,
        applied=False,
    )
    keyframe_poses = poses[keyframes]
    if config.drift_correction:
        solution = correct_drift(source, keyframes, poses, seed=config.seed)
        drift = solution.report
        if solution.report.applied:
            source = PoseOverride(source, keyframes, solution.poses)
            keyframe_poses = solution.poses
    timings["drift_s"] = time.perf_counter() - mark

    mark = time.perf_counter()
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
    cameras = keyframe_poses[:, :3, 3] @ gravity_rotation.T
    world_rotation = gravity_rotation
    timings["gravity_s"] = time.perf_counter() - mark

    mark = time.perf_counter()
    levels = detect_levels(cloud)
    warnings.extend(levels.warnings)
    walls, _ = extract_wall_segments(
        cloud, levels.floor_height, levels.ceiling_height
    )

    if config.canonical_rotation and walls:
        angle = dominant_directions(walls)
        canonical = rotation_about_up(-angle)
        cloud = cloud.rotated(canonical)
        cameras = cameras @ canonical.T
        world_rotation = canonical @ world_rotation
        levels = detect_levels(cloud)
        walls, candidates = extract_wall_segments(
            cloud, levels.floor_height, levels.ceiling_height
        )
    else:
        _, candidates = extract_wall_segments(
            cloud, levels.floor_height, levels.ceiling_height
        )

    snapped_count, snap_rotation = 0, 0.0
    if config.snap_walls_to_frame and walls:
        frame_angle = dominant_directions(walls)
        walls, snapped_count, snap_rotation = snap_to_frame(
            walls, cloud, frame_angle, tolerance_rad=np.deg2rad(config.snap_tolerance_deg)
        )
        for candidate in candidates:
            candidate.segments = [
                s for s in walls if s.plane is candidate.plane
            ]
        candidates = _resync_candidates(candidates, walls)
    if snapped_count:
        warnings.append(
            f"snapped {snapped_count} wall runs onto the building frame, "
            f"mean rotation {np.degrees(snap_rotation):.2f} deg"
        )
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
    complex_ = build_cell_complex(
        occupancy, candidates, walls, max_lines=config.max_wall_lines
    )
    polygons = room_polygons(
        complex_,
        min_room_area_m2=config.min_room_area_m2,
        min_inscribed_radius_m=config.min_inscribed_radius_m,
    )
    masks = room_masks(complex_)
    timings["floorplan_s"] = time.perf_counter() - mark

    mark = time.perf_counter()
    runs = merge_runs(walls)
    openings_by_wall = detect_all_openings(
        runs, cloud, levels.floor_height, levels.ceiling_height
    )
    timings["openings_s"] = time.perf_counter() - mark

    tier = source.meta.tier
    rooms: list[Room] = []
    lookups: dict[str, dict] = {}
    ordered = sorted(polygons.items(), key=lambda kv: -kv[1].area)
    for ordinal, (room_key, polygon) in enumerate(ordered, start=1):
        room_id = f"room_{ordinal:02d}"
        mask = masks.get(
            room_key, np.zeros(occupancy.grid.shape, dtype=bool)
        )
        per_room = room_levels(cloud, occupancy.grid, mask, levels)
        geometry = RoomGeometry(
            room_id=room_id,
            polygon=polygon,
            mask=mask,
            label=config.labels.get(room_id, "room"),
        )
        observed = float(
            mask.sum() * occupancy.grid.cell_area / max(polygon.area, 1e-6)
        )
        room, lookup = build_room(
            geometry, runs, openings_by_wall, per_room, book, tier, observed
        )
        rooms.append(room)
        lookups[room_id] = lookup

    adjacency = match_adjacency(rooms, lookups)

    quality = _quality_report(
        source, cloud, keyframes, rooms, occupancy, tier, warnings
    )
    calibration = CalibrationReport(
        method=IntervalMethod.CONFORMAL
        if book.entries
        else IntervalMethod.PROPAGATED,
        nominal_coverage=book.coverage,
        empirical_coverage={
            f"{k[0]}/{k[1]}": v.empirical_coverage
            for k, v in book.entries.items()
        },
        residual_quantiles={
            f"{k[0]}/{k[1]}": v.quantile for k, v in book.entries.items()
        },
        fitted_on=book.source,
    )

    from cozmo.damage.detect import detect_damage_regions
    from cozmo.damage.rules import RuleEngine
    from cozmo.scope.generate import generate_scope_items

    damage: list[DamageRegion] = []
    for r in rooms:
        surf_ids = [s.surface_id for s in r.surfaces if s.type.value == "wall"]
        damage.extend(detect_damage_regions(r.room_id, surf_ids))

    rule_engine = RuleEngine()
    concealed_flags = rule_engine.evaluate_damage(damage)
    scope_items = generate_scope_items(damage, concealed_flags)

    footprint = float(sum(r.floor_area.value for r in rooms))
    drift.footprint_area_after_m2 = footprint
    if not drift.applied:
        drift.footprint_area_before_m2 = footprint

    plan = PropertyPlan(
        pipeline_version=__version__,
        capture_id=source.meta.capture_id,
        tier=tier,
        created_at=datetime.now(timezone.utc),
        rooms=rooms,
        adjacency=adjacency,
        damage=damage,
        concealed_flags=concealed_flags,
        scope_items=scope_items,
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
