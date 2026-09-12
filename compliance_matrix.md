# Compliance matrix

Requirement → where it lives → what it produces → status.

`MET` means implemented and demonstrated on real data. `PARTIAL` means implemented and
falling short, with the shortfall quantified. `NOT MET` means absent. `UNVERIFIED` means
built and runnable but not yet scored, because the laser ground truth for the benchmark
property has not been recorded — those rows report `SKIP` in the gate table rather than
`PASS`.

## Part 1 — Capture route and tiers

| # | Requirement | Where | Artifact | Status |
|---|---|---|---|---|
| 1.1 | Capture route chosen and documented | `capture/PROTOCOL.md` | One-page stock-capture protocol, Stray Scanner + native Camera | **MET** |
| 1.2 | Non-engineer can follow it literally | `capture/PROTOCOL.md` | Install table, walk script, failure table, hand-off command | **MET** |
| 1.3 | Install in under 10 minutes | `capture/PROTOCOL.md` | Two free App Store apps, no sign-in, no provisioning | **MET** |
| 1.4 | Photo tier — 2 to 8 stills per room, no depth, no poses | `cozmo/io/photo.py`, `cozmo/pipeline/photo.py` | Runs on 58 real stills across 4 rooms | **PARTIAL** — runs, fails its accuracy gate; see 2.14 |
| 1.5 | Video tier — handheld walkthrough | `cozmo/pipeline/video.py` | Keyframe extraction with blur rejection, sequential registration | **PARTIAL** — runs; not scored against ground truth |
| 1.6 | LiDAR tier — depth, poses, intrinsics | `cozmo/io/stray.py`, `cozmo/pipeline/lidar.py` | 6 rooms, 27.20 m², 10 openings, 5 adjacency on the real capture | **MET** |
| 1.7 | Device matrix | `capture/DEVICE_MATRIX.md` | Tier availability per device; accuracy cells marked `pending` until measured | **PARTIAL** — matrix present, accuracy cells unfilled pending laser |
| 1.8 | Same output contract from each tier | `cozmo/schema.py`, `cozmo/pipeline/__init__.py` | One `PropertyPlan`, one `reconstruct`, three builders | **MET** |
| 1.9 | Intervals widen as sensor data thins | `cozmo/uncertainty/calibration.py` | Per-tier priors; photo-tier walls at ±134 cm on the real capture | **MET** |

## Part 2 — Output contract and gates

| # | Requirement | Where | Artifact | Status |
|---|---|---|---|---|
| 2.1 | Dimensioned per-room plan with walls | `cozmo/geometry/assemble.py` | `Room.walls[]`, each with start, end, length, plane, support | **MET** |
| 2.2 | Ceiling height per room | `cozmo/geometry/levels.py` | Per-room, 2.49–2.68 m on the real capture; `unmeasured` when not observed | **MET** |
| 2.3 | Floor area and openings | `cozmo/geometry/{cellcomplex,openings}.py` | `Room.floor_area`, `Room.openings[]` | **MET** |
| 2.4 | Stitched multi-room plan, correct adjacency | `cozmo/geometry/assemble.py`, `cozmo/stitch/rooms.py` | 5 adjacencies from trajectory on the real capture | **MET** at LiDAR/video; **NOT MET** at photo tier |
| 2.5 | Per-surface damage regions, class and metric extent | `cozmo/damage/detect.py` | `DamageRegion` with surface_id, class, metric extent | **MET** |
| 2.6 | Concealed-damage flags with the rule that fired | `cozmo/damage/rules.py` | `ConcealedFlag.rule_text` carries the readable rule | **MET** |
| 2.7 | Scope line items keyed to surfaces | `cozmo/scope/generate.py` | `ScopeItem.surface_id`, `driver_damage_ids` | **MET** |
| 2.8 | Confidence interval on every measurement | `cozmo/schema.py` `Measure` | No code path emits a bare float for a physical quantity | **MET** |
| 2.9 | One command per capture | `cozmo/cli.py` | `cozmo run --input DIR --out DIR` | **MET** |
| 2.10 | JSON to the published schema | `cozmo/schema.py` | Pydantic-validated `plan.json` | **MET** |
| 2.11 | Rendered plan | `cozmo/render/` | `plan.svg` and `plan.png` per run | **MET** |
| 2.12 | Benchmark: multi-room, 3+ rooms plus connector | `DROP_CAPTURES_HERE/01_multiroom_lidar` | Hall, passage, bedroom, bathroom; 107.6 m walked | **MET** |
| 2.13 | Benchmark: furnished room, staged damage, two classes | — | — | **NOT MET** — not captured before the deadline |
| 2.14 | Benchmark: same rooms at all three tiers | `DROP_CAPTURES_HERE/0{1,2,3}_*` | LiDAR + video + per-room photo folders of one property | **MET** as captures; photo tier fails its gate |
| 2.15 | Benchmark: one room captured twice, same tier | — | — | **NOT MET** — repeat scan not captured |
| 2.16 | Laser or tape ground truth on everything | `capture/ground_truth.csv` | Template and recording sheet shipped; **not filled** | **NOT MET** |
| 2.17 | Raw sensor data submitted | `DROP_CAPTURES_HERE/` | 18,649-frame Stray export, 58 stills, walkthrough clip | **MET** |
| 2.18 | Gate: opening widths ≤2 cm on ≥85%, detection scored | `cozmo/bench/gates.py` `gate_opening_widths` | Phantoms and misses both counted in the denominator | **UNVERIFIED** — no ground truth |
| 2.19 | Gate: ceiling height ≤1.5 cm per room | `cozmo/bench/gates.py` `gate_ceiling_height` | Implemented | **UNVERIFIED** |
| 2.20 | Gate: repeat spread ≤1 cm, and say which failure it is | `cozmo/bench/gates.py` `gate_repeatability` | Bias and spread scored separately | **UNVERIFIED** — needs the repeat capture |
| 2.21 | Gate: repeatability 1 cm or 0.5% per wall | `cozmo/bench/gates.py` `gate_repeatability` | Cyclic wall pairing | **UNVERIFIED** |
| 2.22 | Gate: drift accountability with on/off ablation | `cozmo/geometry/drift.py`, `known_failure_modes.md` §5 | Four-way ablation table on the real capture | **MET** |
| 2.23 | Gate: photo-tier whole-property stitch, ±8% | `cozmo/stitch/rooms.py` | Stitcher built; 0 openings so nothing to match | **NOT MET** — footprint −36%, 1 room of 4 |
| 2.24 | Calibration scored at every tier | `cozmo/uncertainty/calibration.py`, `cozmo/bench/gates.py` | Split conformal with finite-sample correction; `gate_interval_coverage` | **UNVERIFIED** — fits from residuals, none exist yet |

## Part 3 — Head-to-head

| # | Requirement | Where | Artifact | Status |
|---|---|---|---|---|
| 3.1 | Compare against one consumer app on 2 rooms | — | — | **NOT MET** — competitor export not captured |
| 3.2 | Name the app and version, submit its export | `DROP_CAPTURES_HERE/08_competitor_export` | Folder prepared, empty | **NOT MET** |
| 3.3 | Beat or tie on ≥70% of shared dimensions | `cozmo/bench/headtohead.py` | Comparison harness present, no data | **NOT MET** |

## Part 4 — Fix loop

| # | Requirement | Where | Artifact | Status |
|---|---|---|---|---|
| 4.1 | Worst gate named with its failing number | `fixloop/FIX_DECLARATION.md` §1 | Photo-tier footprint, +422% | **MET** |
| 4.2 | Root-cause hypothesis with evidence | `fixloop/FIX_DECLARATION.md` §2 | EXIF sub-IFD; fx 4125.3 vs 2221.3 | **MET** |
| 4.3 | Predicted number, stated before the fix | `fixloop/FIX_DECLARATION.md` §3 | Predicted <+50%; committed before the fix commit | **MET** |
| 4.4 | Fix shipped | `cozmo/recon/monocular.py`, `cozmo/pipeline/photo.py` | Four changes, in the commit after the declaration | **MET** |
| 4.5 | Before and after, both regenerable | `fixloop/before/`, `fixloop/after/` | Full run outputs; regeneration commands in the declaration §4 | **MET** |
| 4.6 | Readable diff | `git diff fixloop-before..HEAD` | Tag `fixloop-before` marks the pre-fix state | **MET** |
| 4.7 | Gate moves fail → pass | — | +422% → −36%. Large movement, gate not passed | **PARTIAL** |
| 4.8 | Post-mortem where the prediction was wrong | `fixloop/POSTMORTEM.md` | Prediction wrong in direction; why, and the real cause measured two ways | **MET** |

## Part 5 — Process evidence

| # | Requirement | Where | Artifact | Status |
|---|---|---|---|---|
| 5.1 | Commit as you work, auditable history | `git log` | Incremental commits, each with the defect it fixed and the number it moved | **MET** |
| 5.2 | Not a single-commit dump | `git log` | Work committed across the build, declaration committed before its fix | **MET** |

## Deliverables

| # | Requirement | Where | Status |
|---|---|---|---|
| D1 | Compliance matrix | this file | **MET** |
| D2 | Capture route + device matrix | `capture/PROTOCOL.md`, `capture/DEVICE_MATRIX.md` | **MET** |
| D3 | Repo, README to running in 15 min, one command per capture | `README.md` | **MET** |
| D4 | Reproduction bundle | `run_manifest.json` per run: git commit, input hash, config, timings | **MET** |
| D5 | Benchmark report across three tiers | `reports/benchmark/gate_table.txt` | **PARTIAL** — 4 pass, 0 fail, 10 not evaluated |
| D6 | Fix loop bundle | `fixloop/` | **MET** |
| D7 | Technical report, max 6 pages | `technical_report.md` | **MET** |
| D8 | Raw benchmark data | `DROP_CAPTURES_HERE/` | **PARTIAL** — captures yes, ground truth no |
| D9 | Weights fetched by script | `scripts/fetch_weights.sh` | **MET** |
| D10 | Runs without calling our infrastructure | no network at run time; `scripts/fetch_weights.sh` is the only fetch | **MET** |
| D11 | Mirrors, glass, wet-look, low light covered | `known_failure_modes.md` §4 | **MET** |

## Summary

| status | count |
|---|---|
| MET | 38 |
| PARTIAL | 7 |
| UNVERIFIED (built, needs ground truth) | 5 |
| NOT MET | 7 |

Every `NOT MET` except 2.23 is a missing capture rather than missing code: the staged-damage
room, the repeat scan, the competitor export and the laser measurements. The harness for each
is built and will score them as soon as the data exists. 2.23, the photo-tier stitch, is a
genuine engineering shortfall and is written up as one in `known_failure_modes.md` §1–2.
