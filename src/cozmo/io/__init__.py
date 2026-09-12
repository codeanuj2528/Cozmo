"""Input IO module for loading multi-tier captures."""

from __future__ import annotations

import json
from pathlib import Path

from cozmo.io.base import CaptureSource
from cozmo.io.photo import PhotoCapture
from cozmo.io.stray import StrayCapture
from cozmo.io.video import VideoCapture
from cozmo.schema import Tier


def load_capture(root: Path | str, capture_id: str | None = None) -> CaptureSource:
    """Load a capture source automatically identifying its tier."""
    p = Path(root)
    if not p.exists():
        raise FileNotFoundError(f"Capture path does not exist: {root}")

    # Read capture.json if present
    c_json = p / "capture.json"
    if c_json.exists():
        data = json.loads(c_json.read_text())
        tier_str = data.get("tier", "").lower()
        if tier_str == "lidar":
            return StrayCapture(p, capture_id=capture_id or data.get("capture_id"))
        elif tier_str == "video":
            return VideoCapture(p, capture_id=capture_id or data.get("capture_id"))
        elif tier_str == "photo":
            return PhotoCapture(p, capture_id=capture_id or data.get("capture_id"))

    # Auto-detect format based on files present
    if (p / "odometry.csv").exists() or any((p / sub / "odometry.csv").exists() for sub in p.iterdir() if sub.is_dir()):
        return StrayCapture(p, capture_id=capture_id)

    video_files = list(p.glob("*.mp4")) + list(p.glob("*.mov"))
    if video_files and not (p / "depth").exists():
        return VideoCapture(p, capture_id=capture_id)

    return PhotoCapture(p, capture_id=capture_id)


__all__ = ["load_capture", "StrayCapture", "VideoCapture", "PhotoCapture", "CaptureSource"]
