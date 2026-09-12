#!/usr/bin/env bash
# Fetch model weights. Nothing in this repository downloads anything at run time: the
# pipeline must be able to run cold on a machine with no network, because the walk-in test
# is a cold run, so every fetch is here and explicit.
#
# Disclosure, as the brief requires: the depth model is Depth Anything V2 Metric Indoor
# (Apache-2.0), used for monocular depth on the photo and video tiers. The LiDAR tier uses
# no learned model for geometry.
#
# The metric variant is used rather than the relative one for a specific reason. Relative
# Depth Anything predicts affine-invariant *inverse* depth, a/z + b, so inverting it does
# not give something proportional to z unless b is known. Recovering scale from the camera
# height would then be fitting one unknown to a family with two, and the shape of the room
# would come out wrong in a way no single scale factor can fix. The metric variant predicts
# z directly, which leaves scale as a single multiplicative correction that the camera
# height can honestly pin.
set -euo pipefail

WEIGHTS_DIR="${COZMO_WEIGHTS_DIR:-weights}"
mkdir -p "$WEIGHTS_DIR"

PYTHON="${PYTHON:-.venv/bin/python}"

echo "Fetching Depth Anything V2 Metric Indoor (Small) into $WEIGHTS_DIR ..."
"$PYTHON" - "$WEIGHTS_DIR" <<'PYEOF'
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

target = Path(sys.argv[1]) / "depth-anything-v2-metric-indoor-small"
target.parent.mkdir(parents=True, exist_ok=True)
path = snapshot_download(
    repo_id="depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf",
    local_dir=str(target),
    allow_patterns=["*.json", "*.safetensors", "*.txt"],
)
print(f"  -> {path}")
PYEOF

echo
echo "Done. Weights present:"
find "$WEIGHTS_DIR" -maxdepth 2 -type d -not -name '.*' | sed 's/^/  /'
echo
echo "The pipeline runs without these; it falls back to a constant-depth backbone and"
echo "says so in the plan's quality report. The photo and video tiers are not meaningful"
echo "on that fallback and their intervals widen to match."
