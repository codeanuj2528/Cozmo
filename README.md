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

Read `AUDIT.md` before this section. It carries the measured gate status, a defect register
and the fix plan, and every number in it names the capture it came from.

The LiDAR tier works, on one capture: `163f18d3ac`, a 96.6 m walk, returns 6 rooms, 27.20 m²,
10 openings and 5 adjacencies in 235 s. Its per-room ceiling heights are 1.86–2.63 m, and the
1.86 m is a soffit mistaken for a ceiling rather than a room. **That capture lives in
`data/raw/`, not in the benchmark slot:** `DROP_CAPTURES_HERE/01_multiroom_lidar` holds
`ae3edc814d`, a 23.1 m walk that returns 3 rooms and 16.69 m². Numbers in the other documents
that read "6 rooms, 27.20 m²" belong to `163f18d3ac` and are being corrected to say so.

The photo tier recovers 2 of 4 rooms with no openings and no adjacency, so it does not stitch.
The video tier returns 526.51 m² for 2 rooms and is broken by an order of magnitude.

No laser or tape ground truth exists for any capture, so every accuracy gate reports `SKIP`.
`capture/ground_truth.csv` is the empty template on purpose: it was briefly filled with
invented rows, and `quarantine/README.md` records what was removed and why.
