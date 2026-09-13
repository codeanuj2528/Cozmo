"""Report fields hold a measurement or say they do not, and declared rooms say how they were drawn."""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np

from cozmo.geometry.assemble import unmet_adjacency_warnings
from cozmo.schema import DriftReport, QualityReport, Tier
from cozmo.util.imaging import low_light_fraction


def test_low_light_counts_dark_frames_and_abstains_without_frames():
    dark = np.full((40, 40, 3), 20, dtype=np.uint8)
    bright = np.full((40, 40, 3), 140, dtype=np.uint8)
    assert low_light_fraction([dark, bright, bright]) == 1 / 3
    assert low_light_fraction([]) is None


def test_unmeasured_report_fields_default_to_none_not_zero():
    quality = QualityReport(tier=Tier.LIDAR, device_model="unknown", frames_available=1, frames_used=1,
                            median_depth_confidence=None, surface_coverage=0.5, warnings=[])
    drift = DriftReport(method="m", loop_closures_found=1, residual_before_m=0.1, residual_after_m=0.05,
                        max_pose_correction_m=0.02, footprint_area_after_m2=10.0, applied=True)
    assert quality.low_light_fraction is None and quality.specular_fraction is None
    assert drift.footprint_area_before_m2 is None


def test_declared_connection_drawn_apart_is_reported():
    square = lambda x: [(x, 0.0), (x + 2.0, 0.0), (x + 2.0, 2.0), (x, 2.0)]
    rooms = [SimpleNamespace(room_id="a", polygon=square(0.0)), SimpleNamespace(room_id="b", polygon=square(2.2)),
             SimpleNamespace(room_id="c", polygon=square(5.0))]
    edges = [SimpleNamespace(room_a="a", room_b="b"), SimpleNamespace(room_a="a", room_b="c")]
    warnings = unmet_adjacency_warnings(rooms, edges)
    assert len(warnings) == 1 and "a and c" in warnings[0] and "3.00 m" in warnings[0]


def test_declared_device_model_reaches_a_stray_capture(tmp_path, monkeypatch):
    import cozmo.io as io

    seen = {}

    class Recorder:
        def __init__(self, root, capture_id=None, device_model="unknown"):
            seen.update(root=root, capture_id=capture_id, device_model=device_model)

    monkeypatch.setattr(io, "StrayCapture", Recorder)
    (tmp_path / "odometry.csv").write_text("timestamp, frame, x, y, z, qx, qy, qz, qw\n")
    (tmp_path / "capture.json").write_text(json.dumps({"device_model": "iPhone 17 Pro"}))
    io.load_capture(tmp_path)
    assert seen["device_model"] == "iPhone 17 Pro"
