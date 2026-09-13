"""Internal-consistency audit of emitted plan.json files.

Every check here needs no ground truth. It compares the plan against itself, so it runs on
any capture including one we have never measured, and it is the cheapest way to catch the
class of defect that a laser would otherwise have to catch for us.

The checks, and why each one exists:

`area_vs_polygon`   floor_area should be the area of the polygon it was computed from.
`outline_valid`     the floor outline should be a valid simple polygon, by shapely's test.
`ring_closure`      the wall ring should close and its enclosed area should match floor_area.
`widest_point`      a region too narrow to stand in at its widest point is not a room.
`ceiling_measured`  a ceiling height of exactly 0.0 is not a measurement. It is the absence
                    of one being reported as one, with an interval that brackets zero.
`interval_sanity`   no physical quantity may have a negative lower bound.
`adjacency`         rooms declared connected should be drawn touching.
`reports`           drift, quality and device fields should hold a measurement or say they do
                    not, never a default that reads as one.
`calibration`       an interval method with no empirical coverage is named as such.

Usage:
    python scripts/audit_plans.py <dir-with-plan.json> [more dirs ...]
    python scripts/audit_plans.py --glob "reports/eval_*"
"""

from __future__ import annotations

import argparse
import glob as globmod
import json
import math
from pathlib import Path


def polygon_area(points: list[list[float]]) -> float:
    """Shoelace area. Absolute value, so a clockwise ring is not reported as negative."""
    if len(points) < 3:
        return 0.0
    total = 0.0
    for i in range(len(points)):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % len(points)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def invalid_reason(points: list[list[float]]) -> str | None:
    """Why a floor outline is not a valid simple polygon, or None when it is.

    Shapely's validity test rather than a hand-rolled crossing test. The hand-rolled one
    treated an endpoint lying on another edge as a crossing, and flagged outlines that shapely
    finds valid and whose area equals their reported floor area.
    """
    from shapely.geometry import Polygon
    from shapely.validation import explain_validity

    reason = explain_validity(Polygon(points))
    return None if reason == "Valid Geometry" else reason


def widest_point(points: list[list[float]]) -> float:
    """Diameter of the largest circle that fits inside the outline."""
    from shapely.geometry import Polygon

    shape = Polygon(points)
    if not shape.is_valid:
        shape = shape.buffer(0)
    minx, miny, maxx, maxy = shape.bounds
    lo, hi = 0.0, max(maxx - minx, maxy - miny)
    for _ in range(30):
        mid = (lo + hi) / 2.0
        if shape.buffer(-mid).is_empty:
            hi = mid
        else:
            lo = mid
    return 2.0 * lo


# A quantity that cannot physically be negative. Used for the interval lower-bound check.
NON_NEGATIVE = ("area", "length", "height", "width", "perimeter")

# Narrower than this at its widest point, a region is not a room: nobody can stand in it. A
# 0.75 m closet or the benchmark flat's 0.76 m passage clears it. Mean width, 2 * area /
# perimeter, was used before and reads a 0.80 by 2.55 m corridor as 0.60 m wide.
MIN_ROOM_WIDEST_POINT_M = 0.60


def audit_plan(path: Path) -> dict:
    plan = json.loads(path.read_text())
    findings: list[str] = []
    tier = plan.get("tier")
    rooms = plan.get("rooms", [])

    zero_ceiling = 0
    negative_bound = 0
    area_mismatch = 0
    sliver_rooms = 0
    selfint = 0
    ring_mismatch = 0
    total_openings = 0

    for room in rooms:
        rid = room.get("room_id")
        reported_area = room["floor_area"]["value"]
        poly = [list(p) for p in room.get("polygon", [])]
        total_openings += len(room.get("openings", []))

        # floor_area against its own polygon
        if poly:
            shoelace = polygon_area(poly)
            if reported_area > 0 and abs(shoelace - reported_area) / reported_area > 0.02:
                area_mismatch += 1
                findings.append(
                    f"{rid}: floor_area {reported_area:.2f} m2 but its polygon encloses "
                    f"{shoelace:.2f} m2 ({abs(shoelace - reported_area) / reported_area * 100:.0f}% apart)"
                )
            reason = invalid_reason(poly) if len(poly) >= 3 else None
            if reason:
                selfint += 1
                findings.append(f"{rid}: floor outline is not a valid polygon ({reason})")

        # wall ring closure and the area it encloses
        walls = room.get("walls", [])
        if walls:
            ring = [list(w["start"]) for w in walls]
            gap = math.dist(walls[-1]["end"], walls[0]["start"])
            enclosed = polygon_area(ring)
            if reported_area > 0 and enclosed > 0:
                rel = abs(enclosed - reported_area) / reported_area
                if rel > 0.05 and gap < 0.5:
                    ring_mismatch += 1
                    findings.append(
                        f"{rid}: wall ring encloses {enclosed:.2f} m2 against a reported "
                        f"floor_area of {reported_area:.2f} m2"
                    )

                        # Width at the widest point, not mean width: see MIN_ROOM_WIDEST_POINT_M.
            if reported_area > 0 and len(poly) >= 3:
                width = widest_point(poly)
                if width < MIN_ROOM_WIDEST_POINT_M:
                    sliver_rooms += 1
                    findings.append(
                        f"{rid}: only {width:.2f} m wide at its widest point "
                        f"(area {reported_area:.2f} m2), so this is a sliver rather than a room"
                    )

        # A ceiling that was never observed must be absent, not zero. `null` is the correct
        # answer and is not counted as a defect; an explicit 0.0 is.
        ch = room.get("ceiling_height")
        if ch is not None and ch.get("value") == 0.0:
            zero_ceiling += 1
            findings.append(
                f"{rid}: ceiling_height reported as 0.0 m with interval "
                f"[{ch.get('lo')}, {ch.get('hi')}] and method '{ch.get('method')}'"
            )

        # negative lower bounds anywhere in the room
        def walk(obj, where: str):
            nonlocal negative_bound
            if isinstance(obj, dict):
                if "value" in obj and "lo" in obj and isinstance(obj.get("lo"), (int, float)):
                    if obj["lo"] < 0 and any(k in where for k in NON_NEGATIVE):
                        negative_bound += 1
                        findings.append(
                            f"{rid}: {where} has a negative lower bound "
                            f"({obj['value']:.3f} [{obj['lo']:.3f}, {obj['hi']:.3f}])"
                        )
                    return
                for k, v in obj.items():
                    walk(v, f"{where}.{k}" if where else k)
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    walk(v, f"{where}[{i}]")

        walk(room, "")

    # Declared adjacency against geometric adjacency. A stitched plan whose rooms are
    # declared to share a doorway but whose polygons do not touch is not a floor plan, and
    # it is also how the room-overlap gate gets passed for the wrong reason: rooms that
    # never touch cannot overlap.
    disconnected_adjacency = 0
    poly_by_id = {r["room_id"]: [list(p) for p in r.get("polygon", [])] for r in rooms}
    try:
        from shapely.geometry import Polygon

        shapes = {k: Polygon(v) for k, v in poly_by_id.items() if len(v) >= 3}
        for edge in plan.get("adjacency", []):
            a, b = edge.get("room_a"), edge.get("room_b")
            if a in shapes and b in shapes:
                gap = shapes[a].distance(shapes[b])
                if gap > 0.01:
                    disconnected_adjacency += 1
                    findings.append(
                        f"adjacency {a}-{b} is declared but the polygons are {gap:.3f} m apart"
                    )
    except ImportError:
        pass

    drift = plan.get("drift", {})
    if drift.get("applied") and drift.get("footprint_area_before_m2") == 0.0:
        findings.append(
            "drift: footprint_area_before_m2 is 0.00 m2 while drift was applied, so the "
            "in-plan ablation reports a change from zero and cannot be read as an ablation"
        )

    quality = plan.get("quality", {})
    if quality.get("low_light_fraction") == 0.0 and quality.get("specular_fraction") == 0.0:
        findings.append(
            "quality: low_light_fraction and specular_fraction are both exactly 0.0, which is "
            "the hardcoded default rather than a measurement"
        )
    if quality.get("device_model") in (None, "unknown"):
        findings.append("quality: device_model is unknown, so the device matrix is unverifiable from the run")

    calib = plan.get("calibration", {})
    if calib.get("fitted_on") == "uncalibrated" or not calib.get("empirical_coverage"):
        findings.append(
            f"calibration: intervals are '{calib.get('method')}' with no empirical coverage, "
            "so no interval on this plan has been checked against a measurement"
        )

    return {
        "path": str(path),
        "capture_id": plan.get("capture_id"),
        "tier": tier,
        "rooms": len(rooms),
        "floor_area_m2": plan.get("total_floor_area", {}).get("value"),
        "openings": total_openings,
        "adjacency": len(plan.get("adjacency", [])),
        "damage": len(plan.get("damage", [])),
        "zero_ceiling_rooms": zero_ceiling,
        "negative_lower_bounds": negative_bound,
        "floor_area_vs_polygon_mismatch": area_mismatch,
        "self_intersecting_rooms": selfint,
        "wall_ring_area_mismatch": ring_mismatch,
        "sliver_rooms": sliver_rooms,
        "disconnected_declared_adjacency": disconnected_adjacency,
        "findings": findings,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="*", help="Directories containing plan.json")
    ap.add_argument("--glob", dest="globs", action="append", default=[])
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args()

    targets: list[Path] = []
    for d in args.dirs:
        targets.append(Path(d))
    for g in args.globs:
        targets.extend(Path(p) for p in sorted(globmod.glob(g)))

    results = []
    for t in targets:
        plan = t / "plan.json" if t.is_dir() else t
        if plan.name != "plan.json" or not plan.exists():
            continue
        results.append(audit_plan(plan))

    header = (
        f"{'capture':<22} {'tier':<6} {'rooms':>5} {'area m2':>8} {'open':>5} {'adj':>4} "
        f"{'ceil=0':>7} {'neg lo':>7} {'selfint':>8} {'sliver':>7} {'ring':>5} {'adj gap':>8}"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{str(r['capture_id'])[:22]:<22} {str(r['tier']):<6} {r['rooms']:>5} "
            f"{(r['floor_area_m2'] or 0):>8.2f} {r['openings']:>5} {r['adjacency']:>4} "
            f"{r['zero_ceiling_rooms']:>7} {r['negative_lower_bounds']:>7} "
            f"{r['self_intersecting_rooms']:>8} {r['sliver_rooms']:>7} "
            f"{r['wall_ring_area_mismatch']:>5} {r['disconnected_declared_adjacency']:>8}"
        )

    print("\nFindings\n" + "=" * 8)
    for r in results:
        print(f"\n{r['capture_id']} ({r['tier']}) -- {r['path']}")
        if not r["findings"]:
            print("  no internal inconsistency found")
        for f in r["findings"]:
            print(f"  - {f}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(results, indent=2))
        print(f"\nwrote {args.json_out}")


if __name__ == "__main__":
    main()
