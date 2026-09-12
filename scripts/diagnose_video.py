"""Why the video tier returns a footprint an order of magnitude too large.

A full video run does not complete on a 16 GB machine, so the failure cannot be studied by
reading its output. This probes the stage the failure is suspected to be in -- sequential
registration of monocular clouds -- without building an occupancy grid, which is the stage
that exhausts memory.

The measurement that matters is the extent of the recovered trajectory. The operator walked
a flat; if the poses say they walked hundreds of metres across tens of metres of ground,
registration has failed and every number downstream of it is that failure propagating.

Usage:
    .venv/bin/python scripts/diagnose_video.py PATH_TO_VIDEO [--keyframes 40]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

from cozmo.pipeline.photo import _cloud_from_depth
from cozmo.recon.backbone import get_backbone
from cozmo.recon.monocular import intrinsics_from_exif, make_metric
from cozmo.recon.register import register_sequential

WORKING_WIDTH = 320


def seek_keyframes(path: Path, count: int) -> tuple[list[int], list[np.ndarray], dict]:
    """Grab `count` frames spread across the clip, by seeking rather than decoding all.

    `pipeline/video.py` walks the whole clip with grab(), which on a 33k-frame 4K clip is
    most of its 972 s runtime. Seeking is not frame-exact on a long GOP, but for measuring
    trajectory extent it does not need to be.
    """
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise SystemExit(f"cannot open {path}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    stride = max(total // max(count, 1), 1)

    indices, images = [], []
    for i in range(count):
        pos = i * stride
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        ok, bgr = cap.read()
        if not ok or bgr is None:
            break
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h = max(int(round(WORKING_WIDTH * rgb.shape[0] / rgb.shape[1])), 8)
        images.append(cv2.resize(rgb, (WORKING_WIDTH, h), interpolation=cv2.INTER_AREA))
        indices.append(pos)
    cap.release()

    return indices, images, {
        "total_frames": total,
        "fps": fps,
        "duration_s": total / fps if fps else 0.0,
        "stride_frames": stride,
        "seconds_between_keyframes": stride / fps if fps else 0.0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--keyframes", type=int, default=40)
    ap.add_argument("--weights", type=Path, default=Path("weights"))
    ap.add_argument("--consensus", action="store_true",
                    help="Apply one property-wide scale instead of letting each frame self-scale.")
    args = ap.parse_args()

    indices, images, stats = seek_keyframes(args.video, args.keyframes)
    print(f"clip: {stats['total_frames']} frames, {stats['fps']:.2f} fps, "
          f"{stats['duration_s']:.1f} s")
    print(f"sampled {len(images)} keyframes, {stats['seconds_between_keyframes']:.2f} s apart")
    print("  (pipeline/video.py targets 120 keyframes, so "
          f"{stats['duration_s'] / 120:.2f} s apart on this clip)")

    backbone = get_backbone(args.weights)
    h, w = images[0].shape[:2]
    k_full, focal_source = intrinsics_from_exif(None, w, h)
    print(f"\nworking resolution {w}x{h}, focal {k_full[0, 0]:.1f} px ({focal_source})")
    print(f"implied horizontal field of view "
          f"{2 * np.degrees(np.arctan(w / (2 * k_full[0, 0]))):.1f} deg")

    clouds, depth_medians, scales, sources, depths, gravities = [], [], [], [], [], []
    for image in images:
        geometry = make_metric(
            backbone.estimate(image), k_full, seed=0, backbone_is_metric=backbone.is_metric()
        )
        clouds.append(_cloud_from_depth(geometry.depth_m, k_full, geometry.gravity_rotation))
        depth_medians.append(float(np.median(geometry.depth_m)))
        scales.append(float(geometry.scale.factor))
        sources.append(geometry.scale.source)
        depths.append(geometry.depth_m)
        gravities.append(geometry.gravity_rotation)

    print(f"\npredicted depth: median {np.median(depth_medians):.2f} m, "
          f"range {min(depth_medians):.2f}-{max(depth_medians):.2f} m")

    # Each frame recovers its own metric scale from its own floor plane, and
    # pipeline/video.py collects those provenances into `scale_sources` and then discards
    # them with `_ = scale_sources`. If they disagree, the clouds ICP is asked to align are
    # not the same size as each other, and no rigid transform can reconcile that.
    scale_arr = np.asarray(scales)
    print(f"\nper-frame metric scale: median {np.median(scale_arr):.3f}, "
          f"range {scale_arr.min():.3f}-{scale_arr.max():.3f}, "
          f"spread {scale_arr.max() / max(scale_arr.min(), 1e-9):.2f}x")
    counts: dict[str, int] = {}
    for s in sources:
        key = s.split(",")[0]
        counts[key] = counts.get(key, 0) + 1
    for key, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:3d} frames  {key}")

    if args.consensus:
        grounded = [f for f, s in zip(scales, sources) if s == "camera_height_correction"]
        consensus = float(np.median(grounded)) if grounded else 1.0
        print(f"\napplying property consensus scale {consensus:.3f} from "
              f"{len(grounded)} grounded keyframes")
        clouds = [
            _cloud_from_depth(
                (depths[i] * (consensus / max(scales[i], 1e-6))).astype(np.float32),
                k_full, gravities[i],
            )
            for i in range(len(depths))
        ]

    poses, warnings = register_sequential(clouds)
    registered = [p for p in poses if p is not None]
    print(f"\nregistration: {len(registered)} of {len(clouds)} frames placed")
    for line in warnings[:10]:
        print(f"  W: {line}")

    if len(registered) < 2:
        print("\ntoo few frames placed to measure a trajectory")
        return

    centres = np.array([p[:3, 3] for p in registered])
    steps = np.linalg.norm(np.diff(centres, axis=0), axis=1)
    print("\ntrajectory the poses describe")
    print(f"  path length      {steps.sum():8.2f} m")
    print(f"  extent x/y/z     {np.ptp(centres[:, 0]):8.2f} / "
          f"{np.ptp(centres[:, 1]):.2f} / {np.ptp(centres[:, 2]):.2f} m")
    print(f"  step between keyframes: median {np.median(steps):.2f} m, max {steps.max():.2f} m")
    print(f"  implied walking speed   {steps.sum() / stats['duration_s']:.2f} m/s")

    print("\npoint cloud the plan would be built from")
    pts = np.vstack([
        (pose[:3, :3] @ c[0].T).T + pose[:3, 3]
        for pose, c in zip(poses, clouds) if pose is not None
    ])
    print(f"  {len(pts)} points, bounding box "
          f"{np.ptp(pts[:, 0]):.1f} x {np.ptp(pts[:, 1]):.1f} x {np.ptp(pts[:, 2]):.1f} m")
    footprint = np.ptp(pts[:, 0]) * np.ptp(pts[:, 2])
    print(f"  horizontal bounding area {footprint:.1f} m2")


if __name__ == "__main__":
    main()
