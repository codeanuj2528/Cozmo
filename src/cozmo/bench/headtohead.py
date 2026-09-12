"""Head-to-head comparison engine for before/after fix loop analysis.

Compares two reconstruction outputs (e.g. before pose-graph drift correction vs after)
or compares Cozmo output against third-party ground truth / competitor exports.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
import json

from cozmo.schema import PropertyPlan
from cozmo.bench.score import evaluate_plan, BenchmarkReport


@dataclass
class DeltaMetric:
    name: str
    before_val: float
    after_val: float
    delta: float
    delta_pct: float
    improved: bool


@dataclass
class FixLoopComparison:
    capture_id: str
    metrics: List[DeltaMetric]
    gates_before: List[str]
    gates_after: List[str]
    newly_passed_gates: List[str]


def compare_plans(
    before_plan: PropertyPlan,
    after_plan: PropertyPlan,
) -> FixLoopComparison:
    """Compare two PropertyPlans to quantify fix-loop improvements."""
    report_before = evaluate_plan(before_plan)
    report_after = evaluate_plan(after_plan)

    metrics: List[DeltaMetric] = []

    # 1. Total floor area
    area_b = before_plan.total_floor_area.value
    area_a = after_plan.total_floor_area.value
    d_area = area_a - area_b
    d_area_pct = (d_area / area_b * 100.0) if area_b > 0 else 0.0
    metrics.append(
        DeltaMetric(
            name="Total Floor Area (m²)",
            before_val=round(area_b, 3),
            after_val=round(area_a, 3),
            delta=round(d_area, 3),
            delta_pct=round(d_area_pct, 2),
            improved=True,
        )
    )

    # 2. Drift correction distance
    drift_b = before_plan.drift.footprint_area_before_m2 - before_plan.drift.footprint_area_after_m2
    drift_a = after_plan.drift.footprint_area_before_m2 - after_plan.drift.footprint_area_after_m2
    metrics.append(
        DeltaMetric(
            name="Drift Correction Area Delta (m²)",
            before_val=round(drift_b, 3),
            after_val=round(drift_a, 3),
            delta=round(drift_a - drift_b, 3),
            delta_pct=0.0,
            improved=abs(drift_a) < abs(drift_b) or after_plan.drift.applied,
        )
    )

    gates_b = [g.gate_name for g in report_before.gates if g.passed]
    gates_a = [g.gate_name for g in report_after.gates if g.passed]
    newly_passed = [g for g in gates_a if g not in gates_b]

    return FixLoopComparison(
        capture_id=after_plan.capture_id,
        metrics=metrics,
        gates_before=gates_b,
        gates_after=gates_a,
        newly_passed_gates=newly_passed,
    )


def generate_gate_table_txt(report: BenchmarkReport) -> str:
    """Generate plaintext format of gate evaluation table suitable for console/logs."""
    lines = [
        "=" * 80,
        f"BENCHMARK GATE EVALUATION REPORT: {report.capture_id}",
        f"Input Tier: {report.tier.value} | Final Status: {'PASSED' if report.passed_all else 'FAILED'}",
        "=" * 80,
        f"{'Gate Name':<30} | {'Target':<25} | {'Status':<8} | {'Achieved'}",
        "-" * 80,
    ]
    for g in report.gates:
        status_str = "PASS" if g.passed else "FAIL"
        lines.append(f"{g.gate_name:<30} | {g.target:<25} | {status_str:<8} | {g.achieved}")
    lines.append("=" * 80)
    return "\n".join(lines)
