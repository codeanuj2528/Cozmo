"""Metric scale recovery for non-LiDAR tiers.

The photo and video tiers produce relative or weakly-metric depth.  This
module recovers the true metric scale using one of several strategies:

1. **LiDAR depth** — direct metric from the depth sensor.  Used by the LiDAR
   tier; provided here for completeness.
2. **ARKit VIO** — metric scale from Visual-Inertial Odometry.  Only available
   on iOS devices with ARKit.
3. **Reference object** — detect a known-size object (standard door, A4 paper,
   credit card) and compute scale from its pixel extent and estimated depth.
4. **Structural prior** — assume a standard ceiling height (2.40 m ± 0.30 m)
   and derive scale from the vertical extent of the depth map.
5. **User-supplied** — an explicit scale factor provided by the operator.

The scale source is recorded in the plan so the reader knows the dominant
error term.  The photo tier's wider confidence intervals are a direct
consequence of scale recovery being the weakest link in the chain.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger("cozmo.recon.scale")


class ScaleSource(str, Enum):
    """How metric scale entered the reconstruction."""

    LIDAR_DEPTH = "lidar_depth"
    ARKIT_VIO = "arkit_vio"
    REFERENCE_OBJECT = "reference_object"
    STRUCTURAL_PRIOR = "structural_prior"
    USER_SUPPLIED = "user_supplied"


@dataclass
class ScaleRecovery:
    """The result of scale recovery."""

    scale_factor: float
    source: ScaleSource
    confidence: float  # 0.0 to 1.0
    reference_description: str
    uncertainty_fraction: float  # relative uncertainty (e.g. 0.05 = 5%)


# ---------------------------------------------------------------------------
# Reference objects
# ---------------------------------------------------------------------------

# Standard dimensions for common reference objects (metres).
REFERENCE_OBJECTS = {
    "standard_door": {
        "height_m": 2.032,
        "width_m": 0.813,
        "prompts": ["door", "doorway", "door frame"],
    },
    "a4_paper": {
        "height_m": 0.297,
        "width_m": 0.210,
        "prompts": ["paper", "A4 paper", "document"],
    },
    "credit_card": {
        "height_m": 0.0856,
        "width_m": 0.0539,
        "prompts": ["credit card", "card"],
    },
    "standard_outlet": {
        "height_m": 0.114,
        "width_m": 0.070,
        "prompts": ["electrical outlet", "power outlet", "wall outlet"],
    },
}


def _recover_from_reference_object(
    depth_map: np.ndarray,
    image: np.ndarray,
    reference: str = "standard_door",
    weights_dir: Optional[Path] = None,
) -> Optional[ScaleRecovery]:
    """Attempt scale recovery by detecting a reference object.

    Uses the open-vocabulary detector from :mod:`cozmo.models` to find the
    object and compute the scale factor from its known dimensions.
    """
    if reference not in REFERENCE_OBJECTS:
        return None

    ref = REFERENCE_OBJECTS[reference]
    from cozmo.models import detect_open_vocabulary

    detections = detect_open_vocabulary(
        image,
        prompts=ref["prompts"],
        weights_dir=weights_dir or Path("weights"),
    )

    if not detections:
        return None

    best = max(detections, key=lambda d: d.get("confidence", 0.0))
    bbox = best.get("bbox", [0, 0, 0, 0])
    y_top, y_bottom = bbox[1], bbox[3]
    object_height_px = max(abs(y_bottom - y_top), 1)

    h, w = depth_map.shape[:2]
    y1, y2 = max(0, int(y_top)), min(h, int(y_bottom))
    region = depth_map[y1:y2, :]
    valid = region[region > 0.01]

    if len(valid) == 0:
        return None

    median_depth = float(np.median(valid))
    # Angular size → metric height.
    vfov_rad = 1.22 * h / w  # approximate vertical FOV
    object_height_m = 2.0 * median_depth * np.tan(vfov_rad / 2.0) * object_height_px / h
    scale = ref["height_m"] / max(object_height_m, 1e-4)

    return ScaleRecovery(
        scale_factor=scale,
        source=ScaleSource.REFERENCE_OBJECT,
        confidence=float(best.get("confidence", 0.5)),
        reference_description=f"{reference} ({object_height_px}px, depth={median_depth:.2f}m)",
        uncertainty_fraction=0.08,  # 8% for reference-object recovery
    )


def _recover_from_structural_prior(
    depth_map: np.ndarray,
    ceiling_height_m: float = 2.40,
    ceiling_sigma_m: float = 0.30,
) -> ScaleRecovery:
    """Recover scale using a structural ceiling-height prior.

    Assumes the camera roughly sees floor to ceiling in the vertical extent
    of the depth map.  This is the weakest strategy but always succeeds.
    """
    valid = depth_map[depth_map > 0.01]
    if len(valid) < 100:
        return ScaleRecovery(
            scale_factor=1.0,
            source=ScaleSource.STRUCTURAL_PRIOR,
            confidence=0.3,
            reference_description=f"ceiling_prior={ceiling_height_m}m (no depth signal)",
            uncertainty_fraction=ceiling_sigma_m / ceiling_height_m,
        )

    near = float(np.percentile(valid, 5))
    far = float(np.percentile(valid, 95))
    vertical_extent = max(far - near, 0.5)

    scale = ceiling_height_m / vertical_extent

    return ScaleRecovery(
        scale_factor=scale,
        source=ScaleSource.STRUCTURAL_PRIOR,
        confidence=0.5,
        reference_description=f"ceiling_prior={ceiling_height_m}m, extent={vertical_extent:.2f}m",
        uncertainty_fraction=ceiling_sigma_m / ceiling_height_m,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def recover_metric_scale(
    depth_map: np.ndarray,
    image: np.ndarray,
    weights_dir: Optional[Path] = None,
    user_scale: Optional[float] = None,
) -> ScaleRecovery:
    """Recover metric scale using the best available strategy.

    Tries strategies in order: user-supplied → reference object → structural
    prior.
    """
    # 1. User-supplied.
    if user_scale is not None:
        return ScaleRecovery(
            scale_factor=user_scale,
            source=ScaleSource.USER_SUPPLIED,
            confidence=0.95,
            reference_description="user_supplied",
            uncertainty_fraction=0.02,
        )

    # 2. Reference object (door).
    for ref_name in ["standard_door", "standard_outlet"]:
        result = _recover_from_reference_object(
            depth_map, image, reference=ref_name, weights_dir=weights_dir
        )
        if result is not None:
            log.info(
                "scale recovered from %s: factor=%.3f (confidence=%.2f)",
                ref_name,
                result.scale_factor,
                result.confidence,
            )
            return result

    # 3. Structural prior.
    log.info("falling back to structural ceiling prior for scale recovery")
    return _recover_from_structural_prior(depth_map)
