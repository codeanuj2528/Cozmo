"""Photo tier: per-room folders of unposed stills to a stitched whole-property plan.

The tier's whole job is to manufacture the two things the LiDAR tier is handed for free --
metric depth and a pose per frame -- and then hand the result to the same reconstruction
core. Everything after that point is literally the same code as the LiDAR tier: the same
wall extraction, the same cell complex, the same opening detection, the same ceiling
measurement. That is deliberate, and it is the only way the three tiers stay comparable
instead of quietly becoming three different products that happen to share a repository.

Per room the sequence is: predict depth, level and scale each image against the floor,
register the images to each other in the three degrees of freedom that survive levelling,
fuse, then reconstruct. Rooms arrive in separate folders with nothing in common, so the
whole-property plan is assembled afterwards by matching the doorways that two rooms both
saw -- which is the gate the brief adds specifically because a photo path that handles
single rooms only fails.

What this tier cannot do is pretend to LiDAR accuracy. Measured against LiDAR on the sample
capture, the depth model's mean absolute relative error is 0.28 and its per-frame scale
varies by a third. The intervals reported here are wide because that is what the
measurement says, and a narrow interval on this input would be exactly the confident
garbage the brief penalises.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from cozmo import __version__
from cozmo.config import PipelineConfig
from cozmo.io.base import CaptureSource, Frame, Provenance
from cozmo.io.posed import PosedFrameSource
from cozmo.pipeline.common import PipelineArtifacts, PipelineResult
from cozmo.recon.backbone import get_backbone
from cozmo.recon.frames import select_diverse_frames
from cozmo.recon.monocular import intrinsics_from_exif, make_metric
from cozmo.recon.register import register_room
from cozmo.schema import (
    CalibrationReport,
    DriftReport,
    IntervalMethod,
    PropertyPlan,
    QualityReport,
    Room,
    Tier,
)
from cozmo.stitch.rooms import stitch_property
from cozmo.uncertainty.calibration import IntervalBook
from cozmo.util.transforms import make_pose, scale_intrinsics

log = logging.getLogger(__name__)

# Geometry runs at a working resolution rather than the photograph's own. A 12 MP still
# back-projects to twelve million points per image, which the fusion stage would then
# immediately voxel-reduce away; the LiDAR tier reasons at 256x192 and does well.
WORKING_WIDTH = 320
MAX_IMAGES_PER_ROOM = 8


@dataclass
class RoomReconstruction:
    room_id: str
    label: str
    room: Room | None
    frames_used: int
    registered: int
    scale_sources: list[str]
    warnings: list[str]


def _prepare_image(path: Path) -> tuple[np.ndarray, np.ndarray] | None:
    """Load a still and return it with its working-resolution copy."""
    raw = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if raw is None:
        return None
    rgb = cv2.cvtColor(raw, cv2.COLOR_BGR2RGB)
    height = max(int(round(WORKING_WIDTH * rgb.shape[0] / rgb.shape[1])), 8)
    small = cv2.resize(rgb, (WORKING_WIDTH, height), interpolation=cv2.INTER_AREA)
    return rgb, small


def build_room_frames(
    image_paths: list[Path],
    backbone,
    config: PipelineConfig,
) -> tuple[list[Frame], dict[int, np.ndarray], list[str], list[str]]:
    """Depth, level, scale and register one room's stills into posed frames."""
    warnings: list[str] = []
    scale_sources: list[str] = []

    loaded: list[tuple[Path, np.ndarray, np.ndarray]] = []
    for path in image_paths[: MAX_IMAGES_PER_ROOM * 2]:
        prepared = _prepare_image(path)
        if prepared is not None:
            loaded.append((path, prepared[0], prepared[1]))
    if not loaded:
        return [], {}, [], ["no readable images"]

    if len(loaded) > MAX_IMAGES_PER_ROOM:
        keep = select_diverse_frames([small for _, _, small in loaded], MAX_IMAGES_PER_ROOM)
        loaded = [loaded[i] for i in sorted(keep)]

    clouds: list[tuple[np.ndarray, np.ndarray]] = []
    per_image: list[dict] = []

    for path, full, small in loaded:
        k_full, focal_source = intrinsics_from_exif(path, full.shape[1], full.shape[0])
        k_small = scale_intrinsics(
            k_full, (full.shape[1], full.shape[0]), (small.shape[1], small.shape[0])
        )
        predicted = backbone.estimate(small)
        geometry = make_metric(
            predicted, k_small, seed=config.seed, backbone_is_metric=backbone.is_metric()
        )
        scale_sources.append(geometry.scale.source)

        points, normals = _cloud_from_depth(geometry.depth_m, k_small, geometry.gravity_rotation)
        if len(points) < 300:
            warnings.append(f"{path.name}: too few depth points to use")
            continue
        clouds.append((points, normals))
        per_image.append(
            {
                "path": path,
                "full": full,
                "small": small,
                "k_small": k_small,
                "depth": geometry.depth_m,
                "gravity": geometry.gravity_rotation,
                "focal_source": focal_source,
                "scale": geometry.scale,
            }
        )

    if not clouds:
        return [], {}, scale_sources, warnings + ["no image produced usable geometry"]

    registration = register_room(clouds, floor_y=0.0)
    if registration.failed:
        warnings.append(
            f"{len(registration.failed)} of {len(clouds)} photographs did not register"
        )

    frames: list[Frame] = []
    images: dict[int, np.ndarray] = {}
    for entry in registration.frames:
        meta = per_image[entry.index]
        # The frame's pose is the registration transform composed with the gravity
        # rotation that levelled it, since the depth is expressed in the camera's own
        # frame and the core expects a world-from-camera pose.
        pose = entry.pose @ make_pose(meta["gravity"], np.zeros(3))
        index = len(frames)
        frames.append(
            Frame(
                index=index,
                timestamp=float(index),
                k_depth=meta["k_small"],
                k_rgb=meta["k_small"],
                rgb_size=(meta["small"].shape[1], meta["small"].shape[0]),
                depth=meta["depth"],
                depth_sigma=np.full(
                    meta["depth"].shape,
                    max(meta["scale"].relative_uncertainty, 0.10) * float(np.median(meta["depth"])),
                    dtype=np.float32,
                ),
                confidence=np.full(meta["depth"].shape, 2, dtype=np.uint8),
                pose=pose,
                depth_provenance=Provenance.PREDICTED,
                pose_provenance=Provenance.ESTIMATED,
                rgb_path=meta["path"],
            )
        )
        images[index] = meta["small"]

    return frames, images, scale_sources, warnings


def _cloud_from_depth(
    depth: np.ndarray, k: np.ndarray, gravity: np.ndarray, stride: int = 2
) -> tuple[np.ndarray, np.ndarray]:
    """Back-project a depth map into a gravity-aligned cloud with normals."""
    from cozmo.geometry.fusion import image_normals

    h, w = depth.shape
    vs, us = np.mgrid[0:h, 0:w]
    valid = np.isfinite(depth) & (depth > 0.2) & (depth < 12.0)
    z = depth.astype(np.float32)
    x = (us - k[0, 2]) * z / k[0, 0]
    y = (vs - k[1, 2]) * z / k[1, 1]
    grid = np.stack([x, y, z], axis=2).astype(np.float32)

    normals, ok = image_normals(grid, valid)
    keep = valid & ok
    keep[::stride, ::stride] &= True
    sub = np.zeros_like(keep)
    sub[::stride, ::stride] = True
    keep &= sub
    if keep.sum() < 50:
        return np.zeros((0, 3)), np.zeros((0, 3))

    points = grid[keep].astype(np.float64)
    vectors = normals[keep].astype(np.float64)
    flip = np.einsum("ij,ij->i", vectors, points) > 0
    vectors[flip] *= -1.0
    return points @ gravity.T, vectors @ gravity.T


def build_photo_plan(
    source: CaptureSource,
    config: PipelineConfig | None = None,
    book: IntervalBook | None = None,
) -> PipelineResult:
    """Reconstruct a property from per-room photo folders."""
    from cozmo.pipeline.lidar import build_lidar_plan

    config = config or PipelineConfig()
    book = book or IntervalBook.load(config.calibration_path)
    started = time.perf_counter()
    warnings: list[str] = []

    folders = getattr(source, "room_folders", None)
    if not folders:
        raise ValueError("photo tier needs a capture exposing room_folders")

    backbone = get_backbone(Path(config.weights_dir))
    if not backbone.is_metric():
        warnings.append(
            f"depth backbone '{backbone.name}' is not metric; photo-tier scale rests "
            "entirely on the camera-height prior and intervals widen accordingly"
        )

    # Loop closure needs a revisit after going elsewhere, which a handful of stills of one
    # room does not contain. Running it here would find nothing and cost a minute.
    room_config = config.with_overrides(drift_correction=False, detect_damage=False)

    reconstructions: list[RoomReconstruction] = []
    all_scale_sources: list[str] = []
    for ordinal, (name, paths) in enumerate(sorted(folders.items()), start=1):
        room_id = f"room_{ordinal:02d}"
        frames, images, scale_sources, room_warnings = build_room_frames(paths, backbone, config)
        all_scale_sources.extend(scale_sources)
        if not frames:
            reconstructions.append(
                RoomReconstruction(room_id, name, None, 0, 0, scale_sources, room_warnings)
            )
            warnings.extend(f"{name}: {w}" for w in room_warnings)
            continue

        room_source = PosedFrameSource(
            frames=frames,
            capture_id=f"{source.meta.capture_id}:{name}",
            tier=Tier.PHOTO,
            device_model=source.meta.device_model,
            images=images,
        )
        try:
            result = build_lidar_plan(room_source, room_config, book)
        except Exception as exc:
            warnings.append(f"{name}: reconstruction failed ({exc})")
            reconstructions.append(
                RoomReconstruction(room_id, name, None, len(frames), 0, scale_sources, room_warnings)
            )
            continue

        rooms = result.plan.rooms
        if not rooms:
            warnings.append(f"{name}: no room recovered from {len(frames)} photographs")
            reconstructions.append(
                RoomReconstruction(room_id, name, None, len(frames), len(frames), scale_sources, room_warnings)
            )
            continue

        largest = max(rooms, key=lambda r: r.floor_area.value)
        renamed = largest.model_copy(update={"room_id": room_id, "label": name})
        reconstructions.append(
            RoomReconstruction(room_id, name, renamed, len(frames), len(frames), scale_sources, room_warnings)
        )
        warnings.extend(f"{name}: {w}" for w in room_warnings)

    recovered = [r for r in reconstructions if r.room is not None]
    stitched, adjacency, stitch_warnings = stitch_property([r.room for r in recovered])
    warnings.extend(stitch_warnings)

    from cozmo.geometry.assemble import total_area

    plan = PropertyPlan(
        pipeline_version=__version__,
        capture_id=source.meta.capture_id,
        tier=Tier.PHOTO,
        created_at=datetime.now(timezone.utc),
        rooms=stitched,
        adjacency=adjacency,
        damage=[],
        concealed_flags=[],
        scope_items=[],
        drift=DriftReport(
            method=(
                "not applicable at the photo tier: loop closure requires revisiting a place "
                "after going elsewhere, and per-room stills contain no trajectory to close"
            ),
            loop_closures_found=0,
            residual_before_m=0.0,
            residual_after_m=0.0,
            max_pose_correction_m=0.0,
            footprint_area_before_m2=float(sum(r.floor_area.value for r in stitched)),
            footprint_area_after_m2=float(sum(r.floor_area.value for r in stitched)),
            applied=False,
        ),
        calibration=CalibrationReport(
            method=IntervalMethod.CONFORMAL if book.entries else IntervalMethod.PRIOR,
            nominal_coverage=book.coverage,
            empirical_coverage={
                f"{k[0]}/{k[1]}": v.empirical_coverage for k, v in book.entries.items()
            },
            residual_quantiles={f"{k[0]}/{k[1]}": v.quantile for k, v in book.entries.items()},
            fitted_on=book.source,
        ),
        quality=QualityReport(
            tier=Tier.PHOTO,
            device_model=source.meta.device_model,
            frames_available=source.meta.frame_count,
            frames_used=sum(r.frames_used for r in reconstructions),
            median_depth_confidence=None,
            surface_coverage=float(len(recovered) / max(len(reconstructions), 1)),
            low_light_fraction=0.0,
            specular_fraction=0.0,
            warnings=warnings + [f"depth backbone: {backbone.name}"],
        ),
        total_floor_area=total_area(stitched, book, Tier.PHOTO),
        runtime_seconds=time.perf_counter() - started,
    )

    artifacts = PipelineArtifacts(
        cloud=None,
        cameras=np.zeros((0, 3)),
        occupancy=None,
        complex=None,
        walls=[],
        levels=None,
        world_rotation=np.eye(3),
        keyframes=[],
        warnings=warnings,
        timings={"total_s": time.perf_counter() - started},
    )
    return PipelineResult(plan=plan, artifacts=artifacts)
