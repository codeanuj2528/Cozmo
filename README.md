# Cozmo

Handheld iPhone capture to a dimensioned floor plan, damage map and repair scope. Three
input tiers — photos, video, LiDAR — one output contract.

## Running on a fresh capture, on a clean machine

Four commands, about ten minutes, most of it the first model download.

```bash
git clone <this repo> && cd cozmo
curl -LsSf https://astral.sh/uv/install.sh | sh     # if uv is not already present
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[ml]"
./scripts/fetch_weights.sh                           # ~95 MB, the only network access
```

Then, one command per capture:

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
    --out reports/benchmark

# Fit split-conformal interval quantiles from measured residuals. Writes nothing if there
# are no residuals.
.venv/bin/python -m cozmo.cli calibrate --runs runs --ground-truth capture/ground_truth.csv

# Drift on/off ablation
.venv/bin/python -m cozmo.cli run --input <dir> --out runs/no_drift --no-drift-correction
```

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

40 tests. They cover the geometry primitives against closed-form answers, the detectors
against synthetic walls where the right answer is known, and the schema contract. Several
exist because a defect got past review and into a real run; those name the defect in the
docstring.

## State of the evidence

The LiDAR tier works: on a 107 m walk through a four-space flat it returns 6 rooms, 27.20 m²,
per-room ceiling heights of 2.49–2.68 m, 10 openings, 5 adjacencies, in 86 s.

The photo tier does not meet its accuracy gates and `known_failure_modes.md` §1 says why,
with the measurement.

10 of 14 gates report `SKIP` because laser ground truth for the benchmark property has not
been recorded. They are not reported as passing.
