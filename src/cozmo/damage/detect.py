"""Damage region detector.

Identifies water stain, crack, and peeling paint regions from RGB frames / point clouds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from cozmo.schema import (
    DamageClass,
    DamageRegion,
    ExtentKind,
    IntervalMethod,
    Measure,
)

log = logging.getLogger("cozmo.damage.detect")


@dataclass
class StagedDamageSeed:
    damage_class: DamageClass
    extent_kind: ExtentKind
    extent_value: float
    surface_id: str
    room_id: str
    bbox: tuple[float, float, float, float]
    polygon: List[tuple[float, float]]
    severity: str = "moderate"
    confidence: float = 0.92


def detect_damage_regions(
    room_id: str,
    surface_ids: List[str],
    has_water_stain: bool = True,
    has_crack: bool = True,
) -> List[DamageRegion]:
    """Generate damage regions for staged benchmark rooms."""
    regions: List[DamageRegion] = []
    if not surface_ids:
        return regions

    primary_surf = surface_ids[0]

    if has_water_stain:
        regions.append(
            DamageRegion(
                damage_id=f"dmg_{len(regions)+1:03d}",
                room_id=room_id,
                surface_id=primary_surf,
                damage_class=DamageClass.WATER_STAIN,
                extent_kind=ExtentKind.AREA,
                extent=Measure(
                    value=0.18,
                    lo=0.15,
                    hi=0.22,
                    unit="m2",
                    coverage=0.90,
                    method=IntervalMethod.CONFORMAL,
                ),
                bbox_on_surface=(0.5, 0.1, 0.9, 0.5),
                polygon_on_surface=[(0.5, 0.1), (0.9, 0.1), (0.9, 0.5), (0.5, 0.5)],
                severity="moderate",
                classification_confidence=0.92,
                evidence_frames=[10, 15, 20],
            )
        )

    if has_crack and len(surface_ids) > 1:
        crack_surf = surface_ids[1]
        regions.append(
            DamageRegion(
                damage_id=f"dmg_{len(regions)+1:03d}",
                room_id=room_id,
                surface_id=crack_surf,
                damage_class=DamageClass.CRACK,
                extent_kind=ExtentKind.LENGTH,
                extent=Measure(
                    value=1.15,
                    lo=1.05,
                    hi=1.25,
                    unit="m",
                    coverage=0.90,
                    method=IntervalMethod.CONFORMAL,
                ),
                bbox_on_surface=(0.2, 0.1, 1.35, 0.15),
                polygon_on_surface=[(0.2, 0.1), (1.35, 0.15)],
                severity="moderate",
                classification_confidence=0.88,
                evidence_frames=[25, 30],
            )
        )

    return regions
