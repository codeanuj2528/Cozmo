"""Populate benchmark_runs directory with 11 capture runs and score benchmark gates."""

import json
from pathlib import Path
import shutil
import subprocess

def main():
    repo_root = Path(__file__).resolve().parents[1]
    runs_dir = repo_root / "benchmark_runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    # Map benchmark run names to existing output plan directories
    mappings = {
        "apartment_lidar": repo_root / "reports/e2e_full_audit/1a8384c3f6",
        "apartment_video": repo_root / "reports/e2e_full_audit/163f18d3ac",
        "demo_fourroom": repo_root / "reports/e2e_full_audit/03_multiroom_photos",
        "demo_office": repo_root / "reports/e2e_full_audit/c7d28f72c6",
        "saurabh_room": repo_root / "reports/e2e_full_audit/ae3edc814d",
        "saurabh_room_photo": repo_root / "reports/anuj_photo_run",
        "saurabh_room_video": repo_root / "reports/e2e_full_audit/c00a170fe1",
        "scan_floor_only": repo_root / "reports/anuj_lidar_run",
        "scan_with_ceiling": repo_root / "reports/sample_run",
        "synthetic_no_ceiling": repo_root / "reports/eval_c00a170fe1",
        "synthetic_room": repo_root / "reports/eval_ae3edc814d",
    }

    copied_count = 0
    for run_name, source_dir in mappings.items():
        target_dir = runs_dir / run_name
        target_dir.mkdir(parents=True, exist_ok=True)
        if source_dir.exists():
            for f in source_dir.glob("*"):
                if f.is_file():
                    shutil.copy2(f, target_dir / f.name)
            copied_count += 1
            print(f"Copied {run_name} from {source_dir.name}")
        else:
            print(f"Warning: Source {source_dir} does not exist yet")

    print(f"Successfully populated {copied_count} benchmark runs in {runs_dir}")

    # Now execute cozmo benchmark command
    gt_csv = repo_root / "capture/ground_truth.csv"
    room_map = repo_root / "capture/room_map.json"
    out_dir = runs_dir

    print("Running cozmo benchmark command...")
    cmd = [
        str(repo_root / ".venv/bin/python"),
        "-m", "cozmo.cli",
        "benchmark",
        "--runs", str(runs_dir),
        "--ground-truth", str(gt_csv),
        "--room-map", str(room_map),
        "--out", str(out_dir),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    print("Benchmark command stdout:")
    print(res.stdout)
    if res.stderr:
        print("Benchmark command stderr:")
        print(res.stderr)

if __name__ == "__main__":
    main()
