"""Video tier: a handheld walkthrough clip to a stitched whole-property plan.

The video tier sits between the other two and its structure should reflect that rather
than copying either. Like the photo tier it has no depth and no poses and must predict
both. Unlike the photo tier it has continuity: consecutive frames overlap heavily, so
poses chain, and the walk returns past places it has already been, so loop closure has
something to close.

That continuity is worth using rather than discarding. Treating a walkthrough as a bag of
per-room photo folders throws away the one advantage the tier has and forces the property
back together through doorway matching, which is a harder problem than sequential
registration and a strictly worse answer when the trajectory is right there in the file.
So the video tier registers frames in sequence into one property-wide cloud and then runs
the same core as the LiDAR tier, drift correction included.

Frame selection matters more here than anywhere else. A walkthrough is mostly redundant and
partly unusable: a phone swung through a doorway produces frames whose motion blur destroys
both the depth prediction and the registration that depends on it. Frames are therefore
scored on sharpness before anything else looks at them, and a blurred frame is dropped
rather than fed to a depth model that will confidently hallucinate a surface for it.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from cozmo.config import PipelineConfig
from cozmo.io.discover import find_videos
from cozmo.io.base import CaptureSource, Frame, Provenance
from cozmo.io.posed import PosedFrameSource
from cozmo.pipeline.common import PipelineResult
from cozmo.recon.backbone import get_backbone
from cozmo.recon.monocular import intrinsics_from_exif, make_metric
from cozmo.recon.register import register_sequential
from cozmo.schema import Tier
from cozmo.uncertainty.calibration import IntervalBook
from cozmo.util.transforms import make_pose, scale_intrinsics

log = logging.getLogger(__name__)

WORKING_WIDTH = 320
TARGET_KEYFRAMES = 120
# Variance of the Laplacian, the standard sharpness proxy. The absolute value depends on
# resolution and content, so it is used relatively: frames in the bottom fraction of the
# clip's own sharpness distribution are dropped rather than compared to a fixed number.
BLUR_REJECT_FRACTION = 0.25


def _sharpness(image: np.ndarray) -> float:
    grey = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if image.ndim == 3 else image
    return float(cv2.Laplacian(grey, cv2.CV_64F).var())


def extract_keyframes(
    video_path: Path,
    target: int = TARGET_KEYFRAMES,
    blur_reject_fraction: float = BLUR_REJECT_FRACTION,
) -> tuple[list[int], list[np.ndarray], dict[str, float]]:
    """Sample a clip down to sharp, spread-out keyframes.

    Sampled at a uniform stride first and filtered for sharpness second, so the frames that
    survive still cover the whole walk. Filtering first and then sampling would bias the
    selection toward whichever rooms the operator moved slowly through.
    """
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"cannot open video: {video_path}")

    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        total = 1 << 20
    # Oversample, then let the blur filter take its cut without dropping below target.
    wanted = max(int(target / max(1.0 - blur_reject_fraction, 0.1)), target)
    stride = max(int(total / wanted), 1)

    indices: list[int] = []
    images: list[np.ndarray] = []
    sharpness: list[float] = []
    position = 0
    while True:
        ok = capture.grab()
        if not ok:
            break
        if position % stride == 0:
            ok, bgr = capture.retrieve()
            if ok:
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                height = max(int(round(WORKING_WIDTH * rgb.shape[0] / rgb.shape[1])), 8)
                small = cv2.resize(rgb, (WORKING_WIDTH, height), interpolation=cv2.INTER_AREA)
                indices.append(position)
                images.append(small)
                sharpness.append(_sharpness(small))
        position += 1
    capture.release()

    stats = {"frames_in_clip": float(position), "frames_sampled": float(len(indices))}
    if not indices:
        return [], [], stats

    threshold = float(np.quantile(sharpness, blur_reject_fraction))
    keep = [i for i, s in enumerate(sharpness) if s >= threshold]
    if len(keep) > target:
        step = len(keep) / target
        keep = [keep[int(i * step)] for i in range(target)]

    stats["frames_kept"] = float(len(keep))
    stats["blur_threshold"] = threshold
    stats["median_sharpness"] = float(np.median(sharpness))
    return [indices[i] for i in keep], [images[i] for i in keep], stats


def build_video_plan(
    source: CaptureSource,
    config: PipelineConfig | None = None,
    book: IntervalBook | None = None,
) -> PipelineResult:
    """Reconstruct a property from one continuous walkthrough clip."""
    from cozmo.pipeline.lidar import build_lidar_plan
    from cozmo.pipeline.photo import _cloud_from_depth

    config = config or PipelineConfig()
    book = book or IntervalBook.load(config.calibration_path)
    started = time.perf_counter()
    warnings: list[str] = []

    video_path = getattr(source, "video_path", None)
    if video_path is None:
        candidates = find_videos(Path(source.meta.root))
        if not candidates:
            raise ValueError("video tier needs a .mp4 or .mov in the capture directory")
        video_path = candidates[0]

    numbers, images, stats = extract_keyframes(Path(video_path))
    if not images:
        raise ValueError(f"no usable frames extracted from {video_path}")
    warnings.append(
        f"video: {int(stats['frames_in_clip'])} frames in clip, "
        f"{int(stats['frames_sampled'])} sampled, {int(stats.get('frames_kept', 0))} kept "
        f"after blur rejection at the {BLUR_REJECT_FRACTION:.0%} quantile"
    )

    backbone = get_backbone(Path(config.weights_dir))
    height, width = images[0].shape[:2]
    # A clip carries no EXIF, so the focal length comes from the device prior. The
    # provenance is recorded because an assumed focal length is a scale error waiting to
    # happen and the reader should know it was assumed.
    k_full, focal_source = intrinsics_from_exif(None, width, height)
    warnings.append(f"video intrinsics: {focal_source}")

    clouds: list[tuple[np.ndarray, np.ndarray]] = []
    depths: list[np.ndarray] = []
    gravities: list[np.ndarray] = []
    scale_sources: list[str] = []

    for image in images:
        predicted = backbone.estimate(image)
        geometry = make_metric(
            predicted, k_full, seed=config.seed, backbone_is_metric=backbone.is_metric()
        )
        points, normals = _cloud_from_depth(geometry.depth_m, k_full, geometry.gravity_rotation)
        clouds.append((points, normals))
        depths.append(geometry.depth_m)
        gravities.append(geometry.gravity_rotation)
        scale_sources.append(geometry.scale.source)

    poses, registration_warnings = register_sequential(clouds)
    warnings.extend(registration_warnings)

    frames: list[Frame] = []
    frame_images: dict[int, np.ndarray] = {}
    for index, (pose, depth, gravity, image) in enumerate(zip(poses, depths, gravities, images)):
        if pose is None:
            continue
        frames.append(
            Frame(
                index=index,
                timestamp=float(numbers[index]),
                k_depth=k_full,
                k_rgb=k_full,
                rgb_size=(width, height),
                depth=depth,
                depth_sigma=np.full(depth.shape, 0.25 * float(np.median(depth)), dtype=np.float32),
                confidence=np.full(depth.shape, 2, dtype=np.uint8),
                pose=pose @ make_pose(gravity, np.zeros(3)),
                depth_provenance=Provenance.PREDICTED,
                pose_provenance=Provenance.ESTIMATED,
            )
        )
        frame_images[index] = image

    if len(frames) < 4:
        raise ValueError(
            f"only {len(frames)} frames registered from {len(images)} keyframes; "
            "the clip is too blurred or too fast to reconstruct"
        )
    warnings.append(f"video: {len(frames)} of {len(images)} keyframes registered")

    posed = PosedFrameSource(
        frames=frames,
        capture_id=source.meta.capture_id,
        tier=Tier.VIDEO,
        device_model=source.meta.device_model,
        root=Path(source.meta.root),
        images=frame_images,
        notes={"video": str(video_path), "focal_source": focal_source},
    )

    # Drift correction stays on: a walkthrough revisits places, which is precisely the
    # condition loop closure needs and precisely what the photo tier lacks.
    result = build_lidar_plan(posed, config, book)
    result.plan.tier = Tier.VIDEO
    result.plan.created_at = datetime.now(timezone.utc)
    result.plan.quality.tier = Tier.VIDEO
    result.plan.quality.warnings = list(result.plan.quality.warnings) + warnings
    result.plan.runtime_seconds = time.perf_counter() - started
    result.artifacts.warnings.extend(warnings)
    _ = scale_sources
    return result
