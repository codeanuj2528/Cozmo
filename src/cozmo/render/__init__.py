"""Render package for vector and raster floor plan generation."""

from cozmo.render.plan import build_plan_drawing, render_svg, save_plan_image
from cozmo.render.backends import to_svg, to_png
from cozmo.schema import PropertyPlan
from pathlib import Path
import tempfile


def render_floorplan_svg(plan: PropertyPlan) -> str:
    """Render property plan to SVG format string."""
    return render_svg(plan)


def render_floorplan_png(plan: PropertyPlan) -> bytes:
    """Render property plan to PNG format bytes."""
    drawing = build_plan_drawing(plan, show_intervals=True)
    title = f"Floor Plan - Capture {plan.capture_id}"
    subtitle = f"Tier: {plan.tier.value.upper()} | Total Floor Area: {plan.total_floor_area.value:.2f} m²"
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        to_png(drawing, Path(tmp.name), title, subtitle)
        return Path(tmp.name).read_bytes()


__all__ = [
    "build_plan_drawing",
    "render_svg",
    "save_plan_image",
    "render_floorplan_svg",
    "render_floorplan_png",
]
