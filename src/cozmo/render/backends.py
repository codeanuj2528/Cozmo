"""Write a Drawing out as SVG or PNG.

World coordinates are metres on the xz plane with z increasing away from the origin, and
both backends flip that axis so the plan reads the way a plan reads. Doing the flip in the
backend rather than in the drawing keeps the primitives in world coordinates, so a
primitive's position can still be checked against a measurement.
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np

from cozmo.render.drawing import Arc, Circle, Drawing, Line, Polygon, Style, Text

TITLE_BLOCK_PX = 96
MARGIN_PX = 28


def _scale_for(drawing: Drawing, target_px: int) -> float:
    return target_px / max(drawing.width, drawing.height)


class _Projector:
    """World metres to pixels, with the vertical axis flipped."""

    def __init__(self, drawing: Drawing, scale: float, offset_y: float = 0.0):
        self.drawing = drawing
        self.scale = scale
        self.offset_y = offset_y

    def __call__(self, point) -> tuple[float, float]:
        x = (point[0] - self.drawing.min_x) * self.scale + MARGIN_PX
        y = (self.drawing.max_y - point[1]) * self.scale + MARGIN_PX + self.offset_y
        return x, y

    def length(self, metres: float) -> float:
        return metres * self.scale


def _stroke_attrs(style: Style, project: _Projector) -> str:
    parts = []
    if style.stroke:
        parts.append(f'stroke="{style.stroke}"')
        parts.append(f'stroke-width="{max(project.length(style.width), 0.4):.2f}"')
        parts.append('stroke-linejoin="round"')
        parts.append('stroke-linecap="round"')
    else:
        parts.append('stroke="none"')
    parts.append(f'fill="{style.fill}"' if style.fill else 'fill="none"')
    if style.dash:
        a, b = project.length(style.dash[0]), project.length(style.dash[1])
        parts.append(f'stroke-dasharray="{a:.2f},{b:.2f}"')
    if style.opacity < 1.0:
        parts.append(f'opacity="{style.opacity:.2f}"')
    return " ".join(parts)


def to_svg(drawing: Drawing, title: str, subtitle: str, target_px: int = 1400) -> str:
    scale = _scale_for(drawing, target_px)
    width = int(drawing.width * scale) + 2 * MARGIN_PX
    height = int(drawing.height * scale) + 2 * MARGIN_PX + TITLE_BLOCK_PX
    project = _Projector(drawing, scale, offset_y=TITLE_BLOCK_PX)

    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        '<g font-family="Helvetica Neue, Helvetica, Arial, sans-serif">',
        f'<text x="{MARGIN_PX}" y="38" font-size="22" font-weight="600" fill="#22222a">'
        f"{escape(title)}</text>",
        f'<text x="{MARGIN_PX}" y="62" font-size="12" fill="#7a7a86">{escape(subtitle)}</text>',
        f'<line x1="{MARGIN_PX}" y1="{TITLE_BLOCK_PX - 14}" x2="{width - MARGIN_PX}" '
        f'y2="{TITLE_BLOCK_PX - 14}" stroke="#dedcd4" stroke-width="1"/>',
    ]

    for item in drawing.primitives:
        if isinstance(item, Polygon):
            pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in (project(p) for p in item.points))
            out.append(f'<polygon points="{pts}" {_stroke_attrs(item.style, project)}/>')
        elif isinstance(item, Line):
            x1, y1 = project(item.start)
            x2, y2 = project(item.end)
            out.append(
                f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                f"{_stroke_attrs(item.style, project)}/>"
            )
        elif isinstance(item, Circle):
            cx, cy = project(item.centre)
            out.append(
                f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{project.length(item.radius):.2f}" '
                f"{_stroke_attrs(item.style, project)}/>"
            )
        elif isinstance(item, Arc):
            out.append(_svg_arc(item, project))
        elif isinstance(item, Text):
            x, y = project(item.position)
            anchor = {"middle": "middle", "start": "start", "end": "end"}[item.anchor]
            transform = (
                f' transform="rotate({-item.rotation_deg:.2f} {x:.2f} {y:.2f})"'
                if abs(item.rotation_deg) > 0.01
                else ""
            )
            out.append(
                f'<text x="{x:.2f}" y="{y:.2f}" font-size="{item.size:.1f}" fill="{item.colour}" '
                f'text-anchor="{anchor}" font-weight="{item.weight}"{transform}>'
                f"{escape(item.content)}</text>"
            )

    out.append(_svg_scale_bar(drawing, project, height))
    out.append("</g></svg>")
    return "\n".join(out)


def _svg_arc(arc: Arc, project: _Projector) -> str:
    start = (
        arc.centre[0] + arc.radius * np.cos(np.deg2rad(arc.start_deg)),
        arc.centre[1] + arc.radius * np.sin(np.deg2rad(arc.start_deg)),
    )
    end = (
        arc.centre[0] + arc.radius * np.cos(np.deg2rad(arc.end_deg)),
        arc.centre[1] + arc.radius * np.sin(np.deg2rad(arc.end_deg)),
    )
    x1, y1 = project(start)
    x2, y2 = project(end)
    r = project.length(arc.radius)
    sweep = (arc.end_deg - arc.start_deg) % 360.0
    large = 1 if sweep > 180 else 0
    # The y flip reverses the sense of rotation, so the SVG sweep flag is the opposite of
    # the mathematical one.
    return (
        f'<path d="M {x1:.2f} {y1:.2f} A {r:.2f} {r:.2f} 0 {large} 0 {x2:.2f} {y2:.2f}" '
        f"{_stroke_attrs(arc.style, project)}/>"
    )


def _svg_scale_bar(drawing: Drawing, project: _Projector, height: int) -> str:
    metres = 1.0 if drawing.width < 8 else 5.0
    x0, y0 = MARGIN_PX, height - 20
    length = project.length(metres)
    return (
        f'<g><line x1="{x0}" y1="{y0}" x2="{x0 + length:.1f}" y2="{y0}" stroke="#22222a" '
        f'stroke-width="2"/>'
        f'<line x1="{x0}" y1="{y0 - 4}" x2="{x0}" y2="{y0 + 4}" stroke="#22222a" stroke-width="2"/>'
        f'<line x1="{x0 + length:.1f}" y1="{y0 - 4}" x2="{x0 + length:.1f}" y2="{y0 + 4}" '
        f'stroke="#22222a" stroke-width="2"/>'
        f'<text x="{x0 + length + 8:.1f}" y="{y0 + 4}" font-size="11" fill="#7a7a86">'
        f"{metres:.0f} m</text></g>"
    )


def to_png(drawing: Drawing, path: Path, title: str, subtitle: str, dpi: int = 150) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.patches as mpatches
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    aspect = drawing.height / drawing.width
    fig_w = 11.0
    fig, ax = plt.subplots(figsize=(fig_w, fig_w * aspect + 1.1), dpi=dpi)
    ax.set_facecolor("#ffffff")
    fig.patch.set_facecolor("#ffffff")

    # Line widths are given in metres, so they are converted through the axes scale to
    # points rather than guessed. This is what keeps a wall the same thickness on a small
    # bathroom plan and a whole-property plan.
    points_per_metre = fig_w * 72.0 / drawing.width

    for item in drawing.primitives:
        if isinstance(item, Polygon):
            patch = mpatches.Polygon(
                item.points,
                closed=True,
                facecolor=item.style.fill or "none",
                edgecolor=item.style.stroke or "none",
                linewidth=item.style.width * points_per_metre if item.style.stroke else 0,
                alpha=item.style.opacity,
                joinstyle="round",
            )
            ax.add_patch(patch)
        elif isinstance(item, Line):
            lc = LineCollection(
                [[item.start, item.end]],
                colors=item.style.stroke or "none",
                linewidths=item.style.width * points_per_metre,
                alpha=item.style.opacity,
                linestyles=(0, (item.style.dash[0] * points_per_metre, item.style.dash[1] * points_per_metre))
                if item.style.dash
                else "solid",
                capstyle="round",
            )
            ax.add_collection(lc)
        elif isinstance(item, Circle):
            ax.add_patch(
                mpatches.Circle(
                    item.centre, item.radius,
                    facecolor=item.style.fill or "none",
                    edgecolor=item.style.stroke or "none",
                    linewidth=item.style.width * points_per_metre,
                    alpha=item.style.opacity,
                )
            )
        elif isinstance(item, Arc):
            ax.add_patch(
                mpatches.Arc(
                    item.centre, 2 * item.radius, 2 * item.radius,
                    theta1=min(item.start_deg, item.end_deg),
                    theta2=max(item.start_deg, item.end_deg),
                    edgecolor=item.style.stroke or "none",
                    linewidth=item.style.width * points_per_metre,
                    linestyle="--" if item.style.dash else "-",
                )
            )
        elif isinstance(item, Text):
            # SVG and matplotlib disagree on the name of centred text; the drawing model
            # uses the SVG spelling because that is the primary output.
            ha = {"middle": "center", "start": "left", "end": "right"}[item.anchor]
            ax.text(
                item.position[0], item.position[1], item.content,
                fontsize=item.size * 0.85, color=item.colour, ha=ha,
                va="center", rotation=item.rotation_deg, rotation_mode="anchor",
                fontweight=item.weight,
            )

    ax.set_xlim(drawing.min_x, drawing.max_x)
    ax.set_ylim(drawing.min_y, drawing.max_y)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"{title}\n{subtitle}", fontsize=12, loc="left", color="#22222a", pad=14)
    fig.tight_layout()
    fig.savefig(path, dpi=dpi, facecolor="#ffffff", bbox_inches="tight")
    plt.close(fig)


def render_plan(plan, out_dir: Path, stem: str = "plan") -> dict[str, Path]:
    from cozmo.render.plan import build_plan_drawing

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    drawing = build_plan_drawing(plan)
    title = f"{plan.capture_id}"
    subtitle = (
        f"{plan.tier.value} tier  |  {len(plan.rooms)} rooms  |  "
        f"{plan.total_floor_area.value:.2f} m2 "
        f"[{plan.total_floor_area.lo:.2f}, {plan.total_floor_area.hi:.2f}]  |  "
        f"{plan.created_at:%Y-%m-%d %H:%M} UTC"
    )
    svg_path = out_dir / f"{stem}.svg"
    png_path = out_dir / f"{stem}.png"
    svg_path.write_text(to_svg(drawing, title, subtitle))
    to_png(drawing, png_path, title, subtitle)
    return {"svg": svg_path, "png": png_path}
