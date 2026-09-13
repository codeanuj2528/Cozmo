# Cozmo

Handheld iPhone capture to a dimensioned floor plan, damage map and repair scope. Three
input tiers — photos, video, LiDAR — one output contract.

## Running on a fresh capture, on a clean machine

Four commands, about ten minutes, most of it the first model download.

```bash
git clone <this repo> && cd cozmo
./scripts/setup.sh                                   # venv + LiDAR smoke test on a 3.60×2.80×2.50 m box
# Photo/video only:
./scripts/fetch_weights.sh                           # ~95 MB, the only network access
```

`scripts/setup.sh` picks a CPython 3.11–3.12 interpreter (`requires-python` in
`pyproject.toml`), installs `.[dev]`, ray-traces a known box, and reconstructs it.
Weights stay opt-in: LiDAR is pure geometry. Photo/video also need `.[ml]` before
`scripts/fetch_weights.sh`.

**Try it now (no capture required):** after setup, open the plans we already ran.

```bash
open reports/verified/single_room/plan.png      # 1 room, 17.36 m², assignment zip
open reports/verified/multiroom_home/plan.png   # 3 rooms, 16.69 m² — the product
```

Then, one command per new capture:

```bash
.venv/bin/python -m cozmo.cli run --input <capture-dir> --out runs/my_capture
```

The tier is detected from what the directory holds. It writes `plan.json`, `plan.svg`,
`plan.png` and `run_manifest.json`.

```
runs/my_capture/
  plan.json           the output contract, schema-validated
  plan.svg            the floor plan, vector
  plan.png            the floor plan, raster
  run_manifest.json   git commit, input hash, config, per-stage timings
```

Nothing reaches the network at run time. `scripts/fetch_weights.sh` is the only fetch and it
is a separate, explicit step, because the walk-in test is a cold run.

### What each tier expects

| Tier | Input | Detected by |
|---|---|---|
| LiDAR | Stray Scanner export folder | `odometry.csv` present |
| Video | Folder holding one `.mov` / `.mp4` (any capitalisation) | a video file present |
| Photo | Folder of per-room subfolders of stills, `.jpg` / `.heic` | neither of the above |

```
photos/
  hall/       IMG_1583.HEIC ...
  bedroom/    IMG_1608.HEIC ...
```

Subfolder names become the room labels on the plan.

## The other commands

```bash
# Score every run against laser ground truth. Gates with no truth behind them report SKIP,
# never PASS.
.venv/bin/python -m cozmo.cli benchmark --runs runs --ground-truth capture/ground_truth.csv \
    --room-map capture/room_map.json --out reports/benchmark

# Fit split-conformal interval quantiles from measured residuals. Writes nothing if there
# are no residuals.
.venv/bin/python -m cozmo.cli calibrate --runs runs --ground-truth capture/ground_truth.csv

# Drift on/off ablation
.venv/bin/python -m cozmo.cli run --input <dir> --out runs/no_drift --no-drift-correction
```

## What to show an examiner

`SUBMIT.md` — which plans are real, which failures to disclose, what not to invent.
`benchmark_report.md` — one-page PASS / FAIL / SKIP headline.

## Where to look

| | |
|---|---|
| What to capture, and how | `capture/PROTOCOL.md` |
| What to measure with the laser | `capture/RECORDING_SHEET.md`, `capture/ground_truth.csv` |
| Which tier runs on which device | `capture/DEVICE_MATRIX.md` |
| Requirement → file → artifact → status | `compliance_matrix.md` |
| Architecture and the error budget | `technical_report.md` |
| What does not work, with numbers | `known_failure_modes.md` |
| The Part 4 fix loop | `fixloop/` |
| Artifacts that could not be reproduced | `quarantine/README.md` |

## Layout

```
src/cozmo/
  schema.py        the output contract; every quantity is a Measure with an interval
  config.py        every default, in one place
  cli.py           run / benchmark / calibrate / fixloop
  io/              capture readers, one per input format
  recon/           depth backbone, monocular metric recovery, registration
  geometry/        fusion, planes, levels, walls, openings, cell complex, drift, assembly
  stitch/          joining separately reconstructed rooms
  damage/          detection, projection to surfaces, concealed-damage rules
  scope/           repair line items
  uncertainty/     split-conformal calibration
  render/          plan drawing, SVG and PNG backends
  bench/           ground truth, gates, structural metrics
```

The design principle worth knowing before reading the code: **a tier's job is to produce
frames carrying intrinsics, metric depth and a pose. After that, all three tiers run the
same reconstruction core.** LiDAR is handed all three; photo and video manufacture them. If
you are looking for a tier-specific bug, it is almost certainly in the front half.

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

50 tests. They cover geometry primitives, the ray-traced 3.60×2.80×2.50 box, thin-tier
intervals, and the schema contract. Several exist because a defect got past review.

## State of the evidence

Current numbers: `docs/verified_lidar.md` and `SUBMIT.md`. `AUDIT.md` is the 12 Sep
self-audit; its 6-room / 27.20 m² / 2-room `c00a170fe1` lines are **pre-merge** and
superseded.

| Capture | Rooms | Area | Show? |
|---|---|---|---|
| `c00a170fe1` | **1** | **17.36 m²** | yes — walk-in |
| `ae3edc814d` | **3** | **16.69 m²** | yes — stitched home |
| `163f18d3ac` | **5** | **25.25 m²** | yes — long walk |
| same-room video | 2 | 339.61 m² | disclose fail |
| home walkthrough video | 1 | ~371 m² | disclose fail; do not lead |
| bathroom 0.5× photos | 0 | 0.00 m² | bathroom-only, not the 4-folder run |
| home 4-folder photos | 2 | 60.87 m² | disclose fail vs tape 28.75 |

**Choose the LiDAR tier for walk-in.** Photo stills on disk are 0.5× ultra-wide; video
scale is not metric. Home tape is in `capture/ground_truth.csv` (`tool=tape`):
footprint gates **FAIL** (16.69 / 25.25 vs 28.75 m²). Ceiling and door rows are
still empty, so those gates stay `SKIP`. `quarantine/` is the audit trail of
removed fakes — do not quote it.
