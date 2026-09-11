"""Output contract.

Every number the pipeline reports is a `Measure`: a point estimate plus an interval and
the name of the method that produced the interval. There is no path in the codebase that
emits a bare float for a physical quantity, because an uncalibrated number is the failure
mode this contract exists to prevent.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0.0"


class Tier(str, Enum):
    """Input tier. Ordered from thinnest to richest sensor data."""

    PHOTO = "photo"
    VIDEO = "video"
    LIDAR = "lidar"


class IntervalMethod(str, Enum):
    CONFORMAL = "conformal_split"
    PROPAGATED = "propagated_covariance"
    BOOTSTRAP = "bootstrap"
    PRIOR = "prior_only"


class Measure(BaseModel):
    """A physical quantity with a calibrated interval.

    `lo`/`hi` bound the quantity at `coverage` nominal probability. `method` records how
    the interval was produced so a reader can tell a calibrated interval from a guess.
    """

    model_config = ConfigDict(frozen=True)

    value: float
    lo: float
    hi: float
    unit: str
    coverage: float = 0.90
    method: IntervalMethod = IntervalMethod.CONFORMAL

    @property
    def half_width(self) -> float:
        return 0.5 * (self.hi - self.lo)

    def contains(self, truth: float) -> bool:
        return self.lo <= truth <= self.hi


class OpeningType(str, Enum):
    DOOR = "door"
    WINDOW = "window"
    PASS_THROUGH = "pass_through"


class SurfaceType(str, Enum):
    WALL = "wall"
    FLOOR = "floor"
    CEILING = "ceiling"


class Plane(BaseModel):
    """Plane in the property frame: unit normal `n` and offset `d` with n . x + d = 0."""

    normal: tuple[float, float, float]
    offset: float


class Opening(BaseModel):
    opening_id: str
    type: OpeningType
    wall_id: str
    width: Measure
    height: Measure
    sill_height: Measure
    offset_along_wall: Measure
    detection_confidence: float = Field(ge=0.0, le=1.0)
    connects_to_room: str | None = None


class Wall(BaseModel):
    wall_id: str
    surface_id: str
    start: tuple[float, float]
    end: tuple[float, float]
    length: Measure
    height: Measure
    plane: Plane
    point_support: int = Field(description="Number of observed 3D points that fit this wall plane.")


class Surface(BaseModel):
    surface_id: str
    room_id: str
    type: SurfaceType
    area: Measure
    plane: Plane


class Room(BaseModel):
    room_id: str
    label: str
    polygon: list[tuple[float, float]] = Field(description="Floor outline, property frame, metres.")
    walls: list[Wall]
    surfaces: list[Surface]
    openings: list[Opening]
    ceiling_height: Measure
    floor_area: Measure
    perimeter: Measure
    observation_quality: float = Field(ge=0.0, le=1.0)


class Adjacency(BaseModel):
    room_a: str
    room_b: str
    opening_a: str
    opening_b: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str


class DamageClass(str, Enum):
    WATER_STAIN = "water_stain"
    MOLD = "mold"
    CRACK = "crack"
    HOLE = "hole"
    PEELING_PAINT = "peeling_paint"
    SMOKE_SOOT = "smoke_soot"
    MISSING_MATERIAL = "missing_material"
    IMPACT_DAMAGE = "impact_damage"


class ExtentKind(str, Enum):
    AREA = "area"
    LENGTH = "length"


class DamageRegion(BaseModel):
    damage_id: str
    room_id: str
    surface_id: str
    damage_class: DamageClass
    extent_kind: ExtentKind
    extent: Measure
    bbox_on_surface: tuple[float, float, float, float] = Field(
        description="(u_min, v_min, u_max, v_max) in surface-local metres."
    )
    polygon_on_surface: list[tuple[float, float]]
    severity: Literal["minor", "moderate", "severe"]
    classification_confidence: float = Field(ge=0.0, le=1.0)
    evidence_frames: list[int]


class ConcealedFlag(BaseModel):
    flag_id: str
    rule_id: str
    rule_text: str = Field(description="The rule as written, so a reader can audit the firing.")
    room_id: str
    surface_id: str | None
    triggered_by: list[str] = Field(description="damage_ids and measurement ids that fired the rule.")
    confidence: float = Field(ge=0.0, le=1.0)
    recommended_action: str


class ScopeItem(BaseModel):
    item_id: str
    room_id: str
    surface_id: str
    code: str
    description: str
    unit: Literal["SF", "LF", "EA", "SY", "HR"]
    quantity: Measure
    driver_damage_ids: list[str]
    rationale: str


class DriftReport(BaseModel):
    """What the pipeline did about accumulated pose drift, with the numbers."""

    method: str
    loop_closures_found: int
    residual_before_m: float
    residual_after_m: float
    max_pose_correction_m: float
    footprint_area_before_m2: float
    footprint_area_after_m2: float
    applied: bool


class CalibrationReport(BaseModel):
    method: IntervalMethod
    nominal_coverage: float
    empirical_coverage: dict[str, float]
    residual_quantiles: dict[str, float]
    fitted_on: str = Field(description="Which benchmark split the conformal quantiles came from.")


class QualityReport(BaseModel):
    tier: Tier
    device_model: str
    frames_available: int
    frames_used: int
    median_depth_confidence: float | None
    surface_coverage: float = Field(ge=0.0, le=1.0)
    low_light_fraction: float
    specular_fraction: float = Field(description="Fraction of surface area flagged mirror/glass.")
    warnings: list[str]


class PropertyPlan(BaseModel):
    """Root object. One per capture."""

    schema_version: str = SCHEMA_VERSION
    pipeline_version: str
    capture_id: str
    tier: Tier
    created_at: datetime
    rooms: list[Room]
    adjacency: list[Adjacency]
    damage: list[DamageRegion]
    concealed_flags: list[ConcealedFlag]
    scope_items: list[ScopeItem]
    drift: DriftReport
    calibration: CalibrationReport
    quality: QualityReport
    total_floor_area: Measure
    runtime_seconds: float
