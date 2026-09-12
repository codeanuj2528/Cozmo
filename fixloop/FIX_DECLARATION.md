# Part 4: Fix Loop Declaration

## 1. Single Worst-Performing Gate
- **Failing Gate**: **Ceiling Height Accuracy Gate** (Target: ≤ 1.5 cm per room error across captures).
- **Baseline Metric**: **1.92 cm** mean room ceiling height error on multi-room and unaligned wall captures, exceeding the ≤ 1.5 cm threshold by 0.42 cm (Fail).

## 2. Root-Cause Hypothesis & Empirical Evidence
- **Hypothesis**: ARKit depth points on ceilings suffer from global tilt and minor non-orthogonal alignment. When wall planes are extracted prior to snapping candidate planes onto the dominant building axes frame, unaligned wall normals create staircasing along room boundaries. This causes room bounding boxes and vertical level histogram slice boundaries to span across stepped height bins, introducing a systematic +1.9 cm upward bias in per-room ceiling height extraction.
- **Evidence**: In `before_run.json`, `walls.snap_to_frame` was disabled (`snap_walls_to_frame = false`). Point cloud cell complex boundaries showed wall normal drift of up to 4.2° relative to the gravity-refined dominant axes, causing ceiling plane histogram binning to capture high-elevation noise points near wall top junctions.

## 3. Intended Fix & Predicted Metric
- **Shipped Fix**: Implemented strict dominant-axis wall snapping (`snap_to_frame`) and resynchronized cell complex candidate planes (`_resync_candidates`). Quantized cell complex bounding planes force room boundaries to lie exactly on the true wall faces, isolating ceiling elevation histograms strictly inside interior room volume.
- **Predicted Metric**: Ceiling height error reduces from **1.92 cm → 0.95 cm** (moving the gate from **FAIL** to **PASS**).

## 4. Verification & Regenerability
- **Before Run Output**: `fixloop/before_run.json`
- **After Run Output**: `fixloop/after_run.json`
- **Regeneration Command**: `cozmo fixloop --input data/raw/1a8384c3f6 --out fixloop`
