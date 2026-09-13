"""Accuracy of each tier against the tape, in the form the device matrix reports it.

Reads every plan under a runs directory, pairs its measurements with the ground truth exactly as
the benchmark does, and prints the median and 90th-percentile error per tier and quantity. The
accuracy cells in capture/DEVICE_MATRIX.md are copied from this output, not written by hand.

    .venv/bin/python scripts/accuracy_table.py --runs reports/verified \\
        --ground-truth capture/ground_truth.csv --room-map capture/room_map.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from cozmo.bench.groundtruth import collect_residuals, load_ground_truth, resolve_capture_id
from cozmo.schema import PropertyPlan


def main() -> None:
    parser = argparse.ArgumentParser(description="Per-tier accuracy against ground truth.")
    parser.add_argument("--runs", type=Path, default=Path("reports/verified"))
    parser.add_argument("--ground-truth", type=Path, default=Path("capture/ground_truth.csv"))
    parser.add_argument("--room-map", type=Path, default=Path("capture/room_map.json"))
    args = parser.parse_args()

    truth = load_ground_truth(args.ground_truth, args.room_map)
    rows: dict[tuple[str, str], list[tuple[str, float, float]]] = {}
    for path in sorted(args.runs.glob("*/plan.json")):
        plan = PropertyPlan(**json.loads(path.read_text()))
        capture_id = resolve_capture_id(plan, path.parent.name, truth)
        for key, pairs in collect_residuals(plan, truth, capture_id).items():
            rows.setdefault(key, []).extend((path.parent.name, p, a) for p, a in pairs)

    print("| Tier | Quantity | n | Median error | 90th percentile | Runs |")
    print("|---|---|---|---|---|---|")
    for (tier, quantity), entries in sorted(rows.items()):
        absolute = np.array([abs(p - a) for _, p, a in entries])
        relative = np.array([abs(p - a) / a for _, p, a in entries if a])
        unit = "m²" if quantity == "floor_area" else "m"
        runs = ", ".join(sorted({run for run, _, _ in entries}))
        print(
            f"| {tier} | {quantity} | {len(entries)} "
            f"| {np.median(absolute):.2f} {unit} ({np.median(relative):.0%}) "
            f"| {np.percentile(absolute, 90):.2f} {unit} ({np.percentile(relative, 90):.0%}) | {runs} |"
        )


if __name__ == "__main__":
    main()
