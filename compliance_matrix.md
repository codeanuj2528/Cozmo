# Compliance matrix

Requirement → where it lives → what it produces → status.

- `MET`: implemented and demonstrated on real data.
- `PARTIAL`: implemented and falling short, with the shortfall quantified.
- `FAIL`: implemented, measured against ground truth, and the gate is not met.
- `UNVERIFIED`: implemented, but the ground truth needed to score it does not exist; the gate
  reports `SKIP`, never `PASS`.
- `NOT MET`: absent.

## Part 1 — Capture route and tiers

| # | Requirement | Where | Artifact | Status |
|---|---|---|---|---|
| 1.1 | Capture route chosen and documented | `capture/PROTOCOL.md` | One-page stock-capture protocol: Stray Scanner and the native Camera | **MET** |
| 1.2 | A non-engineer can follow it literally | `capture/PROTOCOL.md` | Install table, walk script, failure table, hand-off command | **MET** |
| 1.3 | Install in under 10 minutes | `capture/PROTOCOL.md` | Two free App Store apps, no sign-in, no provisioning | **MET** |
| 1.4 | Photo tier, 2–8 stills per room, no depth or poses | `cozmo/io/photo.py`, `cozmo/pipeline/photo.py` | Runs on 58 real stills in four folders | **PARTIAL**: runs; fails its gate (2.23) |
| 1.5 | Video tier, handheld walkthrough | `cozmo/pipeline/video.py` | Runs; whole-flat clip gives one room of about 371 m², the 17.87 m² assignment room gives 339.61 m² | **NOT MET** as a metric product |
| 1.6 | LiDAR tier: depth, poses, intrinsics | `cozmo/io/stray.py`, `cozmo/pipeline/lidar.py` | Home long walk: 5 rooms, 25.27 m², 7 openings, 3/4 taped connections | **MET** |
| 1.7 | Device matrix | `capture/DEVICE_MATRIX.md` | Tier availability per device; accuracy cells pending | **PARTIAL** |
| 1.8 | Same output contract from each tier | `cozmo/schema.py`, `cozmo/pipeline/__init__.py` | One `PropertyPlan`, one `reconstruct`, three builders | **MET** |
| 1.9 | Intervals widen honestly as data thins | `cozmo/uncertainty/calibration.py` | Photo walls at ±3.0 m on average, but LiDAR intervals cover the tape on 0 of 31 measurements (2.24) | **PARTIAL** |

## Part 2 — Output contract and gates

| # | Requirement | Where | Artifact | Status |
|---|---|---|---|---|
| 2.1 | Dimensioned per-room plan with walls | `cozmo/geometry/assemble.py` | `Room.walls[]` with start, end, length, plane, support | **MET** |
| 2.2 | Ceiling height per room | `cozmo/geometry/levels.py` | 2.56–2.68 m per room on the long walk, read over each room's own floor. A ceiling must be over 2.20 m, strong against everything overhead and cover 0.25 m², or the room reports it unmeasured, as the window bay does | **MET** |
| 2.3 | Floor area and openings | `cozmo/geometry/{cellcomplex,openings}.py` | `Room.floor_area`, `Room.openings[]` | **MET** |
| 2.4 | Stitched multi-room plan, correct adjacency | `cozmo/geometry/assemble.py`, `cozmo/stitch/rooms.py` | Against 4 taped edges: long walk 3/4 with one untaped extra, first walk 2/4, photo 1/4 | **PARTIAL** |
| 2.5 | Per-surface damage regions, class and metric extent | `cozmo/damage/detect.py` | `DamageRegion` with surface, class and extent in metres; one 0.08 m² false positive on the damage-free first walk, none on the long walk | **MET** |
| 2.6 | Concealed-damage flags with the rule that fired | `cozmo/damage/rules.py` | `ConcealedFlag.rule_text` | **MET** |
| 2.7 | Scope line items keyed to surfaces | `cozmo/scope/generate.py` | `ScopeItem.surface_id`, `driver_damage_ids` | **MET** |
| 2.8 | A confidence interval on every measurement | `cozmo/schema.py` `Measure` | No code path emits a bare float for a physical quantity | **MET** |
| 2.9 | One command per capture | `cozmo/cli.py` | `cozmo run --input DIR --out DIR` | **MET** |
| 2.10 | JSON to the published schema | `cozmo/schema.py` | Pydantic-validated `plan.json` | **MET** |
| 2.11 | Rendered plan | `cozmo/render/` | `plan.svg` and `plan.png` per run | **MET** |
| 2.12 | Benchmark: multi-room, 3+ rooms and a connector | `DROP_CAPTURES_HERE/01_multiroom_lidar`, `data/raw/163f18d3ac` | Hall, passage, bedroom, bathroom, walked twice | **MET** |
| 2.13 | Benchmark: furnished room with staged damage, two classes | — | — | **NOT MET**: not captured |
| 2.14 | Benchmark: the same rooms at all three tiers | `DROP_CAPTURES_HERE/0{1,2,3}_*` | LiDAR, video and per-room photo folders of the one flat | **MET** as captures; photo and video fail their gates |
| 2.15 | Benchmark: one room captured twice at the same tier | `ae3edc814d`, `163f18d3ac` | Two LiDAR walks of the same flat, both covering the bedroom | **MET** as a capture; the gate fails (2.21) |
| 2.16 | Laser or tape ground truth on everything | `capture/ground_truth.csv` | Tape walls, areas and adjacency; no ceilings, doors or bathroom walls | **PARTIAL** |
| 2.17 | Raw sensor data submitted | `DROP_CAPTURES_HERE/`, `data/raw/` | Two Stray exports, 58 stills, one walkthrough | **PARTIAL**: the 18,649-frame export is outside git |
| 2.18 | Gate: opening widths ≤2 cm on ≥85%, detection scored | `cozmo/bench/gates.py` `gate_opening_widths` | Misses and phantoms both counted | **UNVERIFIED**: no door tape |
| 2.19 | Gate: ceiling height ≤1.5 cm per room | `cozmo/bench/gates.py` `gate_ceiling_height` | Implemented | **UNVERIFIED**: no ceiling tape |
| 2.20 | Gate: repeat ceiling spread ≤1 cm, and say which failure | `cozmo/bench/gates.py` `gate_repeatability`, `benchmark_report.md` | Bedroom 0.4 cm, hall 0.8 cm, passage 27.5 cm; unrepeatable where segmentation differs | **FAIL** |
| 2.21 | Gate: repeatability 1 cm or 0.5% per wall | `cozmo/bench/gates.py` `gate_repeatability` | 0/25 walls agree; the same bedroom differs by 0.31 and 0.61 m | **FAIL** |
| 2.22 | Gate: drift accountability with an on/off ablation | `cozmo/geometry/drift.py`, `known_failure_modes.md` §5 | Pose graph with ICP-verified closures; four-way ablation | **MET** |
| 2.23 | Gate: photo-tier whole-property stitch, ±8% | `cozmo/stitch/rooms.py` | 3 rooms, 92.00 m² against 28.75 m² (+220%), adjacency 2/4 from folder names | **FAIL** |
| 2.24 | Calibration scored at every tier | `cozmo/uncertainty/calibration.py`, `gate_interval_coverage` | LiDAR covers 0/16 and 0/15; photo 7/11; not fitted in-sample | **FAIL** |

## Part 3 — Head-to-head

| # | Requirement | Where | Artifact | Status |
|---|---|---|---|---|
| 3.1 | Compare against one consumer app on 2 rooms | — | — | **NOT MET**: no export captured |
| 3.2 | Name the app and version, submit its export | `DROP_CAPTURES_HERE/08_competitor_export` | Empty | **NOT MET** |
| 3.3 | Beat or tie on ≥70% of shared dimensions | `cozmo/bench/headtohead.py` | Harness present, no data | **NOT MET** |

## Part 4 — Fix loop

| # | Requirement | Where | Artifact | Status |
|---|---|---|---|---|
| 4.1 | Round 1: worst gate with its failing number | `fixloop/FIX_DECLARATION.md` | Photo footprint +422% | **MET** |
| 4.2 | Round 1: root cause with evidence | `fixloop/FIX_DECLARATION.md` | EXIF sub-IFD; fx 4125.3 against 2221.3 | **MET** |
| 4.3 | Round 1: prediction before the fix | `fixloop/FIX_DECLARATION.md` | Under +50%, committed in `d15c21b` before `80c44f3` | **MET** |
| 4.4 | Round 1: fix shipped | `cozmo/recon/monocular.py`, `cozmo/pipeline/photo.py` | Four changes | **MET** |
| 4.5 | Round 1: before and after, regenerable | `fixloop/before/`, `fixloop/after/` | Plans committed; no run manifests; re-run needs the DROP photos | **PARTIAL** |
| 4.6 | Round 1: readable diff | `git diff d15c21b..80c44f3` | Diff works; the `fixloop-before` tag is off this history | **PARTIAL** |
| 4.7 | Round 1: gate moves fail to pass | — | +422% to −36%; not a pass | **PARTIAL** |
| 4.8 | Round 1: post-mortem | `fixloop/POSTMORTEM.md` | Prediction wrong in direction, and why | **MET** |
| 4.9 | Round 2: declaration before the fix | `fixloop/round2/FIX_DECLARATION.md` | LiDAR footprint against tape; committed `88af4e3` before `20cb44a` | **MET** |
| 4.10 | Round 2: fix shipped | `cozmo/geometry/{occupancy,cellcomplex}.py`, `tests/test_ceiling_evidence.py` | Ceiling returns as interior evidence | **MET** |
| 4.11 | Round 2: before and after, regenerable | `fixloop/round2/{before,after,gates}` | Plans, run manifests and gate tables for both captures | **MET** |
| 4.12 | Round 2: gate moves | `fixloop/round2/gates/` | Before and after identical | **FAIL** |
| 4.13 | Round 2: post-mortem | `fixloop/round2/POSTMORTEM.md` | Hypothesis refuted by measurement; the room-map defect found and fixed in `e4a4ece` | **MET** |

## Part 5 — Process evidence

| # | Requirement | Where | Artifact | Status |
|---|---|---|---|---|
| 5.1 | Commit as you work | `git log` | Incremental commits naming the defect and the number it moved | **MET** |
| 5.2 | Not a single-commit dump | `git log` | Declarations committed before their fixes, twice | **MET** |

## Deliverables

| # | Requirement | Where | Status |
|---|---|---|---|
| D1 | Compliance matrix | this file | **MET** |
| D2 | Capture route and device matrix | `capture/PROTOCOL.md`, `capture/DEVICE_MATRIX.md` | **MET** |
| D3 | README to running in 15 minutes, one command per capture | `README.md`, `scripts/setup.sh` | **MET** |
| D4 | Reproduction bundle | `run_manifest.json` per run: commit, input hash, config, timings | **MET** |
| D5 | Benchmark report across three tiers | `benchmark_report.md`, `reports/verified/gates/` | **PARTIAL**: 6 PASS, 13 FAIL, 14 SKIP |
| D6 | Fix loop bundle | `fixloop/`, index `fixloop/README.md` | **MET** |
| D7 | Technical report, at most 6 pages | `technical_report.md` | **MET** |
| D8 | Raw benchmark data: sensor logs, ground truth, app exports | `DROP_CAPTURES_HERE/`, `capture/` | **PARTIAL**: no app export, partial tape |
| D9 | Weights fetched by script | `scripts/fetch_weights.sh` | **MET** |
| D10 | Runs without calling our infrastructure | no network at run time | **MET** |
| D11 | Mirrors, glass, wet-look surfaces, low light | `known_failure_modes.md` §4 | **MET** |

## Summary

| status | count |
|---|---|
| MET | 39 |
| PARTIAL | 11 |
| FAIL | 5 |
| UNVERIFIED | 2 |
| NOT MET | 5 |

Of the five `NOT MET`, four are missing captures rather than missing code: the staged-damage room
and the three head-to-head rows. The fifth is the video tier, which runs but does not produce a
metric plan. The five `FAIL` are measured shortfalls, each explained in `benchmark_report.md` or a
post-mortem.
