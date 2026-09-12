"""Tests for schema definitions and interval measurements."""

from __future__ import annotations

import pytest
from cozmo.schema import (
    IntervalMethod,
    Measure,
    Opening,
    OpeningType,
    PropertyPlan,
    Room,
    Tier,
)


def test_measure_interval_contains():
    m = Measure(value=2.45, lo=2.43, hi=2.47, unit="m", coverage=0.90, method=IntervalMethod.CONFORMAL)
    assert m.half_width == pytest.approx(0.02)
    assert m.contains(2.45)
    assert m.contains(2.44)
    assert not m.contains(2.50)


def test_opening_validation():
    op = Opening(
        opening_id="op_001",
        type=OpeningType.DOOR,
        wall_id="wall_01",
        width=Measure(value=0.85, lo=0.83, hi=0.87, unit="m"),
        height=Measure(value=2.05, lo=2.03, hi=2.07, unit="m"),
        sill_height=Measure(value=0.0, lo=0.0, hi=0.0, unit="m"),
        offset_along_wall=Measure(value=1.2, lo=1.1, hi=1.3, unit="m"),
        detection_confidence=0.95,
    )
    assert op.type == OpeningType.DOOR
    assert op.detection_confidence == 0.95
