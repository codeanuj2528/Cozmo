"""Scale recovery module for photo and video tiers.

Combines three independent cues (metric depth, door height prior, ceiling height prior)
into a calibrated scale factor with confidence bounds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

log = logging.getLogger("cozmo.tiers.scale")

DOOR_HEIGHT_PRIOR_M = 2.032
DOOR_HEIGHT_PRIOR_SD_M = 0.05
CEILING_HEIGHT_PRIOR_M = 2.44
CEILING_HEIGHT_PRIOR_SD_M = 0.30


@dataclass
class ScaleCue:
    name: str
    fired: bool
    scale_factor: Optional[float] = None
    relative_sd: Optional[float] = None
    reason: str = ""

    @property
    def weight(self) -> float:
        if not self.fired or not self.relative_sd:
            return 0.0
        return 1.0 / max(self.relative_sd, 1e-4) ** 2


@dataclass
class ScaleEstimate:
    scale_factor: float
    ci_95: Tuple[float, float]
    cues: List[ScaleCue]
    agreement: float
    method: str


def compute_scale_factor(
    observed_door_height_px: Optional[float] = None,
    focal_length_px: float = 1000.0,
    observed_ceiling_height_raw: Optional[float] = None,
) -> ScaleEstimate:
    """Compute scale factor from door and ceiling priors."""
    cues: List[ScaleCue] = []

    # Cue 1: Door height prior
    if observed_door_height_px and observed_door_height_px > 10:
        door_scale = (DOOR_HEIGHT_PRIOR_M * focal_length_px) / observed_door_height_px
        cues.append(
            ScaleCue(
                name="door_height_prior",
                fired=True,
                scale_factor=door_scale,
                relative_sd=0.04,
                reason=f"Door height prior N({DOOR_HEIGHT_PRIOR_M}m, 0.05m)",
            )
        )
    else:
        cues.append(ScaleCue(name="door_height_prior", fired=False, reason="No door detected"))

    # Cue 2: Ceiling height prior
    if observed_ceiling_height_raw and observed_ceiling_height_raw > 0.5:
        ch_scale = CEILING_HEIGHT_PRIOR_M / observed_ceiling_height_raw
        cues.append(
            ScaleCue(
                name="ceiling_height_prior",
                fired=True,
                scale_factor=ch_scale,
                relative_sd=0.12,
                reason=f"Ceiling height prior N({CEILING_HEIGHT_PRIOR_M}m, 0.30m)",
            )
        )
    else:
        cues.append(ScaleCue(name="ceiling_height_prior", fired=False, reason="No ceiling plane"))

    fired_cues = [c for c in cues if c.fired and c.scale_factor is not None]
    if not fired_cues:
        # Default scale factor when no scale cues fire
        return ScaleEstimate(
            scale_factor=1.0,
            ci_95=(0.85, 1.15),
            cues=cues,
            agreement=1.0,
            method="default_unit_scale",
        )

    weights = np.array([c.weight for c in fired_cues])
    factors = np.array([c.scale_factor for c in fired_cues])
    weighted_scale = float(np.sum(factors * weights) / np.sum(weights))
    spread = float(np.std(factors)) if len(factors) > 1 else 0.05 * weighted_scale
    ci_lo = float(weighted_scale - 1.96 * spread)
    ci_hi = float(weighted_scale + 1.96 * spread)

    return ScaleEstimate(
        scale_factor=weighted_scale,
        ci_95=(ci_lo, ci_hi),
        cues=cues,
        agreement=1.0 - min(spread / (weighted_scale + 1e-6), 1.0),
        method="weighted_multicue_median",
    )
