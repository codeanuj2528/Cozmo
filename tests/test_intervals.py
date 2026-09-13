"""Thin-tier intervals must not look like a survey."""

from __future__ import annotations

import pytest

from cozmo.schema import IntervalMethod, Tier
from cozmo.uncertainty.calibration import IntervalBook, THIN_TIER_RELATIVE_FLOOR


def test_photo_prior_is_at_least_sixty_percent():
    book = IntervalBook()
    wall = book.measure("wall_length", 4.0, Tier.PHOTO, "m", propagated_sigma=0.02)
    assert wall.method is IntervalMethod.PROPAGATED
    assert wall.half_width == pytest.approx(THIN_TIER_RELATIVE_FLOOR * 4.0)
    assert wall.lo == pytest.approx(4.0 * (1.0 - THIN_TIER_RELATIVE_FLOOR))
    assert wall.hi == pytest.approx(4.0 * (1.0 + THIN_TIER_RELATIVE_FLOOR))


def test_video_prior_is_at_least_sixty_percent():
    book = IntervalBook()
    area = book.measure("floor_area", 17.36, Tier.VIDEO, "m2")
    assert area.method is IntervalMethod.PRIOR
    assert area.half_width == pytest.approx(THIN_TIER_RELATIVE_FLOOR * 17.36)


def test_lidar_stays_tight():
    book = IntervalBook()
    wall = book.measure("wall_length", 4.0, Tier.LIDAR, "m", propagated_sigma=0.02)
    assert wall.half_width < 0.10
    assert wall.method is IntervalMethod.PROPAGATED
