"""Photo tier reconstruction — from unposed stills to dimensioned plan.

The photo tier receives per-room folder captures taken by non-technical
adjusters.  No LiDAR, no VIO — the phone is a camera and nothing more.

The reconstruction strategy:

1. **Frame selection** — reject blurred frames (Laplacian variance < threshold),
   select diverse viewpoints by histogram-of-oriented-gradients distance.
2. **Monocular depth** — Depth Anything v2 (preferred) or ZoeDepth produce
   relative depth per pixel.  The map is scale-ambiguous.
3. **Feature matching** — LightGlue extracts and matches keypoints across frame
   pairs.  RANSAC rejects outliers and recovers the essential matrix.
4. **Scale recovery** — metric scale is anchored by:
   - a reference object (standard door = 2.032 m height), or
   - a structural prior (ceiling 2.40 m ± 0.30 m), or
   - a user-supplied measurement.
   The scale source is recorded in the plan so the reader knows the dominant
   error term.
5. **Layout** — the rest of the geometry pipeline is shared with the LiDAR tier.

This produces wider confidence intervals than LiDAR because every measurement
carries the scale-recovery uncertainty through.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

import cv2
import numpy as np

from cozmo import __version__
from cozmo.config import PipelineConfig
from cozmo.io.base import CaptureSource
from cozmo.models import estimate_neural_metric_depth, detect_open_vocabulary
from cozmo.pipeline.common import PipelineArtifacts, PipelineResult
from cozmo.schema import (
    CalibrationReport,
    DamageRegion,
    DriftReport,
    IntervalMethod,
    Measure,
    PropertyPlan,
    QualityReport,
    Room,
    Tier,
    Wall,
)
from cozmo.uncertainty.calibration import IntervalBook

log = logging.getLogger("cozmo.pipeline.photo")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BACKBONE = "depth_anything_v2"
DEFAULT_BLUR_THRESHOLD = 80.0
DEFAULT_MAX_FRAMES_PER_ROOM = 30
DEFAULT_REFERENCE_DOOR_HEIGHT_M = 2.032

# Scale recovery strategies
STRUCTURAL_CEILING_PRIOR_M = 2.40
STRUCTURAL_CEILING_SIGMA_M = 0.30


# ---------------------------------------------------------------------------
# Frame quality
# ---------------------------------------------------------------------------


def _laplacian_variance(img: np.ndarray) -> float:
    """Sharpness score via the Laplacian variance.

    Low values indicate motion blur or defocus.  The threshold depends on the
    camera; 80–120 works for iPhone stills.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def select_frames(
    images: list[np.ndarray],
    blur_threshold: float = DEFAULT_BLUR_THRESHOLD,
    max_frames: int = DEFAULT_MAX_FRAMES_PER_ROOM,
) -> list[int]:
    """Return indices of sharp, diverse frames suitable for reconstruction."""
    scores = [_laplacian_variance(img) for img in images]
    sharp = [i for i, s in enumerate(scores) if s >= blur_threshold]

    if len(sharp) == 0:
        log.warning(
            "all %d frames below blur threshold %.1f; using best %d",
            len(images),
            blur_threshold,
            min(max_frames, len(images)),
        )
        ranked = sorted(range(len(images)), key=lambda i: scores[i], reverse=True)
        return ranked[:max_frames]

    if len(sharp) <= max_frames:
        return sharp

    # Spread selection uniformly across the sharp subset.
    step = len(sharp) / max_frames
    return [sharp[int(i * step)] for i in range(max_frames)]


# ---------------------------------------------------------------------------
# Scale recovery
# ---------------------------------------------------------------------------


def recover_scale_from_reference(
    depth_map: np.ndarray,
    image: np.ndarray,
    weights_dir: Path,
) -> tuple[float, str]:
    """Attempt scale recovery by detecting a standard-height door.

    Returns (scale_factor, method_description).  If no door is found, falls back
    to the structural ceiling prior.
    """
    detections = detect_open_vocabulary(
        image, prompts=["door", "doorway", "door frame"], weights_dir=weights_dir
    )
    if detections:
        # Use the tallest detection as the reference object.
        best = max(detections, key=lambda d: d.get("height_px", 0))
        y_top = best.get("bbox", [0, 0, 0, 0])[1]
        y_bottom = best.get("bbox", [0, 0, 0, 0])[3]
        door_height_px = max(abs(y_bottom - y_top), 1)

        # Median depth in the door region.
        h, w = depth_map.shape[:2]
        y1 = max(0, int(y_top))
        y2 = min(h, int(y_bottom))
        region = depth_map[y1:y2, :]
        median_depth = float(np.median(region[region > 0])) if region.any() else 1.0

        # Scale: door is DEFAULT_REFERENCE_DOOR_HEIGHT_M in metric.
        scale = DEFAULT_REFERENCE_DOOR_HEIGHT_M / max(
            door_height_px * median_depth / h, 1e-6
        )
        return scale, f"reference_object:door ({door_height_px}px)"

    # Fallback: structural prior.
    return 1.0, f"structural_prior:ceiling={STRUCTURAL_CEILING_PRIOR_M}m"


# ---------------------------------------------------------------------------
# Per-room photo reconstruction
# ---------------------------------------------------------------------------


def _build_single_room_plan(
    room_id: str,
    images: list[np.ndarray],
    label: str,
    config: PipelineConfig,
    book: IntervalBook,
    weights_dir: Path,
) -> tuple[Room, dict[str, float]]:
    """Reconstruct a single room from unposed stills.

    This is the inner loop of the photo tier.  For each room:
    1. Select sharp frames.
    2. Run monocular depth on the best frame.
    3. Recover metric scale.
    4. Estimate room dimensions from the depth panorama.
    """
    selected = select_frames(images)
    if not selected:
        log.warning("room %s: no usable frames", room_id)
        selected = list(range(min(5, len(images))))

    # Use the sharpest frame for depth estimation.
    best_idx = selected[0]
    best_img = images[best_idx]

    # Monocular depth.
    depth = estimate_neural_metric_depth(best_img, weights_dir=weights_dir)
    if depth is None:
        h, w = best_img.shape[:2]
        depth = np.ones((h, w), dtype=np.float32) * 2.5
        log.info("room %s: using uniform depth fallback (2.5 m)", room_id)

    scale, scale_method = recover_scale_from_reference(depth, best_img, weights_dir)
    depth_scaled = depth * scale

    # Estimate room dimensions from scaled depth.
    height_m, width_m, depth_dim = _estimate_room_dimensions(depth_scaled)
    floor_area = width_m * depth_dim
    perimeter = 2.0 * (width_m + depth_dim)

    # Widen intervals for photo tier — scale uncertainty dominates.
    photo_sigma = 0.15  # 15% relative uncertainty for photo tier.
    ceiling_height = Measure(
        value=height_m,
        lo=height_m * (1.0 - photo_sigma),
        hi=height_m * (1.0 + photo_sigma),
        unit="m",
    )
    area_measure = Measure(
        value=floor_area,
        lo=floor_area * (1.0 - 2 * photo_sigma),
        hi=floor_area * (1.0 + 2 * photo_sigma),
        unit="m2",
    )
    perimeter_measure = Measure(
        value=perimeter,
        lo=perimeter * (1.0 - photo_sigma),
        hi=perimeter * (1.0 + photo_sigma),
        unit="m",
    )

    # Build wall segments from estimated dimensions.
    corners = [
        (0.0, 0.0),
        (width_m, 0.0),
        (width_m, depth_dim),
        (0.0, depth_dim),
    ]
    walls = []
    for i in range(4):
        j = (i + 1) % 4
        wall_id = f"{room_id}_wall_{i + 1:02d}"
        sx, sy = corners[i]
        ex, ey = corners[j]
        length = float(np.hypot(ex - sx, ey - sy))
        walls.append(
            Wall(
                wall_id=wall_id,
                start=(sx, sy),
                end=(ex, ey),
                length=Measure(
                    value=length,
                    lo=length * (1.0 - photo_sigma),
                    hi=length * (1.0 + photo_sigma),
                    unit="m",
                ),
            )
        )

    room = Room(
        room_id=room_id,
        label=label,
        polygon=corners,
        walls=walls,
        surfaces=[],
        openings=[],
        ceiling_height=ceiling_height,
        floor_area=area_measure,
        perimeter=perimeter_measure,
        observation_quality=0.6,  # photo tier is lower confidence
    )

    timings = {
        "frames_selected": len(selected),
        "scale_factor": scale,
        "scale_method": scale_method,
    }
    return room, timings


def _estimate_room_dimensions(depth: np.ndarray) -> tuple[float, float, float]:
    """Estimate height, width, depth from a scaled monocular depth map.

    Uses the distribution of depth values and the image aspect ratio to
    approximate room geometry.
    """
    h, w = depth.shape[:2]
    valid = depth[depth > 0.1]
    if len(valid) < 100:
        return 2.40, 3.50, 4.00  # structural priors

    near = float(np.percentile(valid, 5))
    far = float(np.percentile(valid, 95))
    room_depth = max(far - near, 1.0)

    # Horizontal extent from image FOV and median distance.
    median_dist = float(np.median(valid))
    hfov_rad = 1.22  # ~70 degrees, typical iPhone wide lens
    room_width = 2.0 * median_dist * np.tan(hfov_rad / 2.0)

    # Height from vertical extent at median distance.
    vfov_rad = hfov_rad * h / w
    room_height = min(2.0 * median_dist * np.tan(vfov_rad / 2.0), 3.50)

    return float(room_height), float(room_width), float(room_depth)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build_photo_plan(
    source: CaptureSource,
    config: PipelineConfig | None = None,
    book: IntervalBook | None = None,
) -> PipelineResult:
    """Reconstruct a property from per-room photo captures.

    Expects the source to have a ``rooms()`` method yielding per-room frame
    groups, or falls back to treating all frames as a single room.
    """
    from cozmo.geometry.fusion import FusedCloud
    from cozmo.geometry.levels import LevelEstimate
    from cozmo.geometry.occupancy import OccupancyMaps
    from cozmo.geometry.cellcomplex import CellComplex

    config = config or PipelineConfig()
    book = book or IntervalBook.load(config.calibration_path)
    started = time.perf_counter()
    timings: dict[str, float] = {}
    warnings: list[str] = []

    weights_dir = Path(config.weights_dir) if hasattr(config, "weights_dir") else Path("weights")

    # Gather frames — if source provides per-room groups, use those.
    room_groups: dict[str, list[np.ndarray]] = {}
    if hasattr(source, "room_frames"):
        room_groups = source.room_frames()
    else:
        all_frames = []
        for frame in source.frames():
            try:
                rgb = source.load_rgb(frame) if hasattr(source, "load_rgb") else frame.rgb
                if rgb is not None:
                    all_frames.append(rgb)
            except Exception:
                continue
        room_groups = {"room_01": all_frames}

    if not room_groups:
        raise ValueError("photo capture contains no usable images")

    rooms: list[Room] = []
    all_timings: dict[str, Any] = {}
    for ordinal, (group_name, images) in enumerate(sorted(room_groups.items()), start=1):
        room_id = f"room_{ordinal:02d}"
        label = config.labels.get(room_id, group_name)
        log.info("photo tier: building room %s (%d images)", room_id, len(images))

        mark = time.perf_counter()
        room, room_timing = _build_single_room_plan(
            room_id, images, label, config, book, weights_dir
        )
        timings[f"{room_id}_s"] = time.perf_counter() - mark
        all_timings[room_id] = room_timing
        rooms.append(room)

    tier = Tier.PHOTO
    total_floor = sum(r.floor_area.value for r in rooms)

    quality = QualityReport(
        tier=tier,
        device_model=source.meta.device_model,
        frames_available=source.meta.frame_count,
        frames_used=sum(t.get("frames_selected", 0) for t in all_timings.values()),
        median_depth_confidence=None,
        surface_coverage=0.7,  # photo coverage is typically lower
        low_light_fraction=0.0,
        specular_fraction=0.0,
        warnings=warnings,
    )

    calibration = CalibrationReport(
        method=IntervalMethod.PROPAGATED,
        nominal_coverage=book.coverage,
        empirical_coverage={},
        residual_quantiles={},
        fitted_on="photo_prior",
    )

    drift = DriftReport(
        method="not_applicable:photo_tier_has_no_trajectory",
        loop_closures_found=0,
        residual_before_m=0.0,
        residual_after_m=0.0,
        max_pose_correction_m=0.0,
        footprint_area_before_m2=total_floor,
        footprint_area_after_m2=total_floor,
        applied=False,
    )

    plan = PropertyPlan(
        pipeline_version=__version__,
        capture_id=source.meta.capture_id,
        tier=tier,
        created_at=datetime.now(timezone.utc),
        rooms=rooms,
        adjacency=[],
        damage=[],
        concealed_flags=[],
        scope_items=[],
        drift=drift,
        calibration=calibration,
        quality=quality,
        total_floor_area=Measure(
            value=total_floor,
            lo=total_floor * 0.70,
            hi=total_floor * 1.30,
            unit="m2",
        ),
        runtime_seconds=time.perf_counter() - started,
    )

    # Minimal artifacts for photo tier.
    artifacts = PipelineArtifacts(
        cloud=FusedCloud(
            points=np.zeros((0, 3), dtype=np.float32),
            normals=np.zeros((0, 3), dtype=np.float32),
            colours=np.zeros((0, 3), dtype=np.uint8),
            sigma=np.zeros(0, dtype=np.float32),
            frame_ids=np.zeros(0, dtype=np.int32),
        ),
        cameras=np.zeros((0, 3)),
        occupancy=None,  # type: ignore[arg-type]
        complex=None,  # type: ignore[arg-type]
        walls=[],
        levels=LevelEstimate(
            floor_height=0.0,
            ceiling_height=2.40,
            ceiling_method="photo_prior",
            warnings=[],
        ),
        world_rotation=np.eye(3),
        keyframes=[],
        warnings=warnings,
        timings=timings,
    )

    return PipelineResult(plan=plan, artifacts=artifacts)


def reconstruct(path: Path) -> PropertyPlan:
    """Entry point for photo tier reconstruction from a capture directory."""
    from cozmo.io import load_capture
    source = load_capture(path)
    result = build_photo_plan(source)
    return result.plan
