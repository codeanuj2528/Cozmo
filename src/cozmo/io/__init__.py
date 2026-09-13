"""Input IO module for loading multi-tier captures."""

from __future__ import annotations

import json
from pathlib import Path

from cozmo.io.base import CaptureSource
from cozmo.io.photo import PhotoCapture
from cozmo.io.discover import find_images, find_videos
from cozmo.io.stray import StrayCapture
from cozmo.io.video import VideoCapture
from cozmo.schema import Tier


def load_capture(root: Path | str, capture_id: str | None = None) -> CaptureSource:
    """Load a capture source, identifying its tier from the files present.

    An optional capture.json beside the capture may name the tier, the capture id and the
    device model. Stray Scanner exports record no device model of their own, so for LiDAR and
    video the declared model is the only source; photographs keep the model their EXIF records.
    """
    p = Path(root)
    if not p.exists():
        raise FileNotFoundError(f"Capture path does not exist: {root}")

    declared: dict = {}
    c_json = p / "capture.json"
    if c_json.exists():
        declared = json.loads(c_json.read_text())
    capture_id = capture_id or declared.get("capture_id")
    device = {"device_model": declared["device_model"]} if declared.get("device_model") else {}
    tier_str = str(declared.get("tier", "")).lower()

    if tier_str == "lidar":
        return StrayCapture(p, capture_id=capture_id, **device)
    if tier_str == "video":
        return VideoCapture(p, capture_id=capture_id, **device)
    if tier_str == "photo":
        return PhotoCapture(p, capture_id=capture_id)

    if (p / "odometry.csv").exists() or any((p / sub / "odometry.csv").exists() for sub in p.iterdir() if sub.is_dir()):
        return StrayCapture(p, capture_id=capture_id, **device)

    video_files = find_videos(p)
    if video_files and not (p / "depth").exists():
        return VideoCapture(p, capture_id=capture_id, **device)

    return PhotoCapture(p, capture_id=capture_id)


__all__ = ["load_capture", "StrayCapture", "VideoCapture", "PhotoCapture", "CaptureSource"]
