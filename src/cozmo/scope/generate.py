"""Scope line item generator.

Maps damage regions and concealed flags to scope line items with units and rationale.
"""

from __future__ import annotations

import logging
from typing import List, Sequence

from cozmo.schema import (
    ConcealedFlag,
    DamageClass,
    DamageRegion,
    IntervalMethod,
    Measure,
    ScopeItem,
)

log = logging.getLogger("cozmo.scope.generate")


# Scope quantities inherit the uncertainty of the damage extent they are derived from and
# nothing has been conformally calibrated for them, so they report PRIOR. They previously
# reported CONFORMAL on a hardcoded plus-or-minus ten percent, inside plans whose own
# calibration report said fitted_on="uncalibrated" -- the same falsehood the calibrate
# command used to write, in a second place.
def generate_scope_items(
    damage_regions: Sequence[DamageRegion], concealed_flags: Sequence[ConcealedFlag]
) -> List[ScopeItem]:
    items: List[ScopeItem] = []

    for dmg in damage_regions:
        if dmg.damage_class == DamageClass.WATER_STAIN:
            val_sf = float(dmg.extent.value * 10.7639)  # m2 to sq ft
            items.append(
                ScopeItem(
                    item_id=f"scope_{len(items)+1:03d}",
                    room_id=dmg.room_id,
                    surface_id=dmg.surface_id,
                    code="DRY-REPAIR",
                    description="Drywall repair and stain sealing",
                    unit="SF",
                    quantity=Measure(
                        value=round(val_sf, 2),
                        lo=round(val_sf * 0.9, 2),
                        hi=round(val_sf * 1.1, 2),
                        unit="SF",
                        coverage=0.90,
                        method=IntervalMethod.PRIOR,
                    ),
                    driver_damage_ids=[dmg.damage_id],
                    rationale=f"Water stain observed covering {dmg.extent.value:.2f} m2 surface area",
                )
            )
        elif dmg.damage_class == DamageClass.CRACK:
            val_lf = float(dmg.extent.value * 3.28084)  # m to ft
            items.append(
                ScopeItem(
                    item_id=f"scope_{len(items)+1:03d}",
                    room_id=dmg.room_id,
                    surface_id=dmg.surface_id,
                    code="CRK-STITCH",
                    description="Wall crack taping, joint compound and mesh stitching",
                    unit="LF",
                    quantity=Measure(
                        value=round(val_lf, 2),
                        lo=round(val_lf * 0.9, 2),
                        hi=round(val_lf * 1.1, 2),
                        unit="LF",
                        coverage=0.90,
                        method=IntervalMethod.PRIOR,
                    ),
                    driver_damage_ids=[dmg.damage_id],
                    rationale=f"Crack detected spanning {dmg.extent.value:.2f} linear metres",
                )
            )

    for flag in concealed_flags:
        if flag.surface_id:
            items.append(
                ScopeItem(
                    item_id=f"scope_{len(items)+1:03d}",
                    room_id=flag.room_id,
                    surface_id=flag.surface_id,
                    code="INSP-CAVITY",
                    description="Cavity moisture testing and invasive access inspection",
                    unit="EA",
                    quantity=Measure(
                        value=1.0,
                        lo=1.0,
                        hi=1.0,
                        unit="EA",
                        coverage=1.0,
                        method=IntervalMethod.PRIOR,
                    ),
                    driver_damage_ids=flag.triggered_by,
                    rationale=f"Concealed damage rule {flag.rule_id} fired: {flag.recommended_action}",
                )
            )

    return items
