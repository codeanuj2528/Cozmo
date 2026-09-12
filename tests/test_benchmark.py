"""Tests for benchmark evaluation engine."""

from __future__ import annotations

from datetime import datetime, timezone
from cozmo.bench.score import evaluate_plan
from cozmo.schema import (
    CalibrationReport,
    DriftReport,
    IntervalMethod,
    Measure,
    PropertyPlan,
    QualityReport,
    Room,
    Tier,
)


def test_evaluate_plan():
    plan = PropertyPlan(
        pipeline_version="0.1.0",
        capture_id="test_cap",
        tier=Tier.LIDAR,
        created_at=datetime.now(timezone.utc),
        rooms=[
            Room(
                room_id="room_01",
                label="living_room",
                polygon=[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)],
                walls=[],
                surfaces=[],
                openings=[],
                ceiling_height=Measure(value=2.45, lo=2.43, hi=2.47, unit="m"),
                floor_area=Measure(value=12.0, lo=11.5, hi=12.5, unit="m2"),
                perimeter=Measure(value=14.0, lo=13.5, hi=14.5, unit="m"),
                observation_quality=0.95,
            )
        ],
        adjacency=[],
        damage=[],
        concealed_flags=[],
        scope_items=[],
        drift=DriftReport(
            method="loop_closure",
            loop_closures_found=2,
            residual_before_m=0.08,
            residual_after_m=0.01,
            max_pose_correction_m=0.05,
            footprint_area_before_m2=12.5,
            footprint_area_after_m2=12.0,
            applied=True,
        ),
        calibration=CalibrationReport(
            method=IntervalMethod.CONFORMAL,
            nominal_coverage=0.90,
            empirical_coverage={},
            residual_quantiles={},
            fitted_on="synthetic",
        ),
        quality=QualityReport(
            tier=Tier.LIDAR,
            device_model="iPhone 15 Pro",
            frames_available=100,
            frames_used=50,
            median_depth_confidence=2.0,
            surface_coverage=0.92,
            low_light_fraction=0.0,
            specular_fraction=0.0,
            warnings=[],
        ),
        total_floor_area=Measure(value=12.0, lo=11.5, hi=12.5, unit="m2"),
        runtime_seconds=1.5,
    )

    report = evaluate_plan(plan)
    assert report.passed_all
    assert len(report.gates) == 5
