"""Tests for damage region detection and rule engine."""

from __future__ import annotations

from cozmo.damage.detect import detect_damage_regions
from cozmo.damage.rules import RuleEngine
from cozmo.schema import DamageClass


def test_damage_detection_and_rules():
    regions = detect_damage_regions(room_id="room_01", surface_ids=["surf_01", "surf_02"])
    assert len(regions) == 2
    assert regions[0].damage_class == DamageClass.WATER_STAIN
    assert regions[1].damage_class == DamageClass.CRACK

    engine = RuleEngine()
    flags = engine.evaluate_damage(regions)
    assert len(flags) >= 1
    assert any("CD-WATER" in f.rule_id for f in flags)
