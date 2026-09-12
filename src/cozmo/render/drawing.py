"""A tiny drawing model shared by the vector and raster renderers.

The plan is built once into backend-independent primitives and then written out twice.
Writing the drawing logic once per output format guarantees the two drift apart, and the
one that gets looked at less is the one that ends up wrong -- which is invariably the one
in the report.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Style:
    stroke: str | None = None
    fill: str | None = None
    width: float = 1.0
    dash: tuple[float, float] | None = None
    opacity: float = 1.0


@dataclass
class Polygon:
    points: list[tuple[float, float]]
    style: Style
    holes: list[list[tuple[float, float]]] = field(default_factory=list)


@dataclass
class Line:
    start: tuple[float, float]
    end: tuple[float, float]
    style: Style


@dataclass
class Arc:
    centre: tuple[float, float]
    radius: float
    start_deg: float
    end_deg: float
    style: Style


@dataclass
class Text:
    position: tuple[float, float]
    content: str
    size: float = 10.0
    colour: str = "#1b1b1f"
    anchor: str = "middle"
    weight: str = "normal"
    rotation_deg: float = 0.0


@dataclass
class Circle:
    centre: tuple[float, float]
    radius: float
    style: Style


Primitive = Polygon | Line | Arc | Text | Circle


@dataclass
class Drawing:
    """Primitives in world metres, plus the extent they occupy."""

    primitives: list[Primitive] = field(default_factory=list)
    min_x: float = 0.0
    min_y: float = 0.0
    max_x: float = 1.0
    max_y: float = 1.0

    def add(self, primitive: Primitive) -> None:
        self.primitives.append(primitive)

    def set_extent(self, min_x: float, min_y: float, max_x: float, max_y: float, margin: float = 0.8) -> None:
        self.min_x, self.min_y = min_x - margin, min_y - margin
        self.max_x, self.max_y = max_x + margin, max_y + margin

    @property
    def width(self) -> float:
        return max(self.max_x - self.min_x, 1e-6)

    @property
    def height(self) -> float:
        return max(self.max_y - self.min_y, 1e-6)
