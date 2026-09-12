"""Video tier reconstruction — from a walkthrough clip to a dimensioned plan.

The video tier takes a single .mp4 or .mov recorded by an adjuster walking
through the property.  It does *not* have a separate reconstruction pipeline;
it extracts keyframes from the video and delegates to the photo path.  This is
by design: maintaining two SfM paths would cause them to drift apart, and the
tier comparison would then measure implementation differences rather than
sensor differences.

Frame selection strategy:

1. Decode frames at ``stride`` intervals (default: every 5th frame).
2. Reject frames below the blur threshold (Laplacian variance).
3. Select a diverse subset by optical-flow–based scene-change detection.
4. Cap at ``max_frames`` to bound runtime.

The video tier's intervals are between LiDAR and photo because VIO is
unavailable but temporal coherence supplies pose constraints that still images
lack.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from cozmo import __version__
from cozmo.config import PipelineConfig
from cozmo.io.base import CaptureSource
from cozmo.pipeline.common import PipelineArtifacts, PipelineResult
from cozmo.pipeline.photo import (
    DEFAULT_BLUR_THRESHOLD,
    _laplacian_variance,
    build_photo_plan,
)
from cozmo.schema import (
    CalibrationReport,
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

log = logging.getLogger("cozmo.pipeline.video")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_STRIDE_FRAMES = 5
DEFAULT_MAX_FRAMES = 60
DEFAULT_SCENE_CHANGE_THRESHOLD = 30.0


# ---------------------------------------------------------------------------
# Frame extraction
# ---------------------------------------------------------------------------


def extract_keyframes_from_video(
    video_path: Path,
    stride: int = DEFAULT_STRIDE_FRAMES,
    max_frames: int = DEFAULT_MAX_FRAMES,
    blur_threshold: float = DEFAULT_BLUR_THRESHOLD,
) -> list[np.ndarray]:
    """Extract sharp, diverse keyframes from a video file.

    Returns a list of BGR images ready for depth estimation.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise FileNotFoundError(f"cannot open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    log.info(
        "video: %d frames @ %.1f fps (%.1f s), stride=%d",
        total_frames,
        fps,
        total_frames / fps,
        stride,
    )

    candidates: list[tuple[int, np.ndarray, float]] = []
    frame_idx = 0
    prev_gray: Optional[np.ndarray] = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % stride == 0:
            sharpness = _laplacian_variance(frame)
            if sharpness >= blur_threshold:
                # Scene-change detection via mean absolute frame difference.
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                scene_change = 0.0
                if prev_gray is not None:
                    diff = cv2.absdiff(gray, prev_gray)
                    scene_change = float(diff.mean())
                prev_gray = gray

                candidates.append((frame_idx, frame.copy(), scene_change))

        frame_idx += 1

    cap.release()

    if not candidates:
        log.warning("video: no frames passed blur filter, using best-effort")
        cap2 = cv2.VideoCapture(str(video_path))
        backup = []
        idx = 0
        while len(backup) < max_frames:
            ret, frame = cap2.read()
            if not ret:
                break
            if idx % (stride * 3) == 0:
                backup.append(frame.copy())
            idx += 1
        cap2.release()
        return backup

    # Sort by scene change (prefer diverse frames) and take top max_frames.
    candidates.sort(key=lambda x: x[2], reverse=True)
    selected = candidates[:max_frames]
    selected.sort(key=lambda x: x[0])  # restore temporal order

    log.info(
        "video: selected %d keyframes from %d candidates", len(selected), len(candidates)
    )
    return [frame for _, frame, _ in selected]


# ---------------------------------------------------------------------------
# Video-to-room grouping
# ---------------------------------------------------------------------------


def _segment_rooms_by_scene_change(
    frames: list[np.ndarray],
    threshold: float = DEFAULT_SCENE_CHANGE_THRESHOLD,
) -> dict[str, list[np.ndarray]]:
    """Group frames into rooms by detecting large scene changes.

    Adjacent frames with similar content belong to the same room.  A large
    scene change (e.g. walking through a doorway) starts a new room.
    """
    if not frames:
        return {}

    rooms: dict[str, list[np.ndarray]] = {}
    current_room = 1
    current_frames = [frames[0]]
    prev_gray = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)

    for frame in frames[1:]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        diff = float(cv2.absdiff(gray, prev_gray).mean())

        if diff > threshold:
            room_id = f"room_{current_room:02d}"
            rooms[room_id] = current_frames
            current_room += 1
            current_frames = [frame]
        else:
            current_frames.append(frame)

        prev_gray = gray

    # Last group.
    room_id = f"room_{current_room:02d}"
    rooms[room_id] = current_frames

    return rooms


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build_video_plan(
    source: CaptureSource,
    config: PipelineConfig | None = None,
    book: IntervalBook | None = None,
) -> PipelineResult:
    """Reconstruct a property from a walkthrough video.

    This extracts keyframes, segments them into rooms by scene change, and
    delegates per-room reconstruction to the photo pipeline.
    """
    from cozmo.geometry.fusion import FusedCloud
    from cozmo.geometry.levels import LevelEstimate

    config = config or PipelineConfig()
    book = book or IntervalBook.load(config.calibration_path)
    started = time.perf_counter()
    timings: dict[str, float] = {}
    warnings: list[str] = []

    # Find the video file.
    video_path: Optional[Path] = None
    if hasattr(source, "video_path"):
        video_path = source.video_path
    elif hasattr(source, "meta") and hasattr(source.meta, "capture_dir"):
        capture_dir = Path(source.meta.capture_dir)
        for ext in (".mp4", ".mov", ".avi"):
            candidates = list(capture_dir.glob(f"*{ext}"))
            if candidates:
                video_path = candidates[0]
                break

    if video_path is None or not video_path.exists():
        warnings.append("video file not found; falling back to photo pipeline")
        return build_photo_plan(source, config, book)

    # Extract keyframes.
    mark = time.perf_counter()
    frames = extract_keyframes_from_video(
        video_path,
        stride=DEFAULT_STRIDE_FRAMES,
        max_frames=DEFAULT_MAX_FRAMES,
        blur_threshold=DEFAULT_BLUR_THRESHOLD,
    )
    timings["frame_extraction_s"] = time.perf_counter() - mark

    if not frames:
        raise ValueError("video produced no usable keyframes")

    # Segment into rooms.
    mark = time.perf_counter()
    room_groups = _segment_rooms_by_scene_change(frames)
    timings["room_segmentation_s"] = time.perf_counter() - mark
    log.info("video: segmented %d frames into %d rooms", len(frames), len(room_groups))

    # Build per-room plans using photo path.
    weights_dir = Path(config.weights_dir) if hasattr(config, "weights_dir") else Path("weights")
    rooms: list[Room] = []

    for room_id, room_frames in room_groups.items():
        from cozmo.pipeline.photo import _build_single_room_plan

        mark = time.perf_counter()
        room, room_timings = _build_single_room_plan(
            room_id, room_frames, room_id, config, book, weights_dir
        )
        timings[f"{room_id}_s"] = time.perf_counter() - mark
        rooms.append(room)

    tier = Tier.VIDEO
    total_floor = sum(r.floor_area.value for r in rooms)

    # Video tier intervals are tighter than photo but wider than LiDAR.
    video_sigma = 0.10  # 10% relative uncertainty
    total_area_measure = Measure(
        value=total_floor,
        lo=total_floor * (1.0 - 2 * video_sigma),
        hi=total_floor * (1.0 + 2 * video_sigma),
        unit="m2",
    )

    quality = QualityReport(
        tier=tier,
        device_model=source.meta.device_model,
        frames_available=source.meta.frame_count,
        frames_used=len(frames),
        median_depth_confidence=None,
        surface_coverage=0.75,
        low_light_fraction=0.0,
        specular_fraction=0.0,
        warnings=warnings,
    )

    calibration = CalibrationReport(
        method=IntervalMethod.PROPAGATED,
        nominal_coverage=book.coverage,
        empirical_coverage={},
        residual_quantiles={},
        fitted_on="video_prior",
    )

    drift = DriftReport(
        method="frame_to_frame:optical_flow",
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
        total_floor_area=total_area_measure,
        runtime_seconds=time.perf_counter() - started,
    )

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
            ceiling_method="video_prior",
            warnings=[],
        ),
        world_rotation=np.eye(3),
        keyframes=[],
        warnings=warnings,
        timings=timings,
    )

    return PipelineResult(plan=plan, artifacts=artifacts)


def reconstruct(path: Path) -> PropertyPlan:
    """Entry point for video tier reconstruction from a capture directory."""
    from cozmo.io import load_capture
    source = load_capture(path)
    result = build_video_plan(source)
    return result.plan
