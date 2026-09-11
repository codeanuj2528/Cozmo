"""Pipeline configuration.

Defaults are the values the benchmark was run at. They are collected here rather than left
as literals at their call sites so that a reported number can be traced to the settings
that produced it, and so the ablations the report needs (drift correction on and off,
canonical rotation on and off) are one field each rather than a code change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PipelineConfig:
    voxel_m: float = 0.02
    grid_resolution_m: float = 0.03
    min_depth_confidence: int = 1
    max_depth_range_m: float = 5.0
    max_keyframes: int = 600
    keyframe_translation_m: float = 0.08
    keyframe_rotation_deg: float = 6.0

    canonical_rotation: bool = True
    drift_correction: bool = True
    detect_damage: bool = True
    build_scope: bool = True

    max_wall_lines: int = 44
    min_room_area_m2: float = 1.5

    calibration_path: Path | None = Path("calibration/intervals.json")
    weights_dir: Path = Path("weights")
    seed: int = 0

    labels: dict[str, str] = field(default_factory=dict)

    def with_overrides(self, **kwargs) -> PipelineConfig:
        data = {**self.__dict__, **kwargs}
        return PipelineConfig(**data)
