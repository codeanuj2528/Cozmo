# Quarantine: not submittable

Everything in this directory reports numbers that no run produced. It is kept, rather than
deleted, so the audit that found it can be checked, and so the honest versions can be
written against the same structure. **Nothing here goes in the submission.**

## What was wrong with each

### `benchmark_synthetic/`
`anuj_room_lidar` and `anuj_room_photo` are procedurally generated box rooms
(`room_meta.json`: `"room_type": "box"`, `"seed": 5599`, 12 frames, intrinsics
fx = fy = 500, cx = 320, cy = 240). Their "ground truth" is the generator's own input
parameters, so the benchmark compares the pipeline against the numbers that produced its
input. It cannot fail and it measures nothing. They are also named as if they were real
captures taken by the author, which they are not.

Synthetic captures are useful, and there are some in `tests/fixtures/` where they belong:
they let the test suite run without several hundred megabytes of sensor data. A synthetic
capture cannot be a benchmark result, because the brief scores accuracy against laser
ground truth and the walk-in test is a cold run on an unseen real room.

### `fixloop_fabricated/`
`before/anuj_room_lidar/plan.png` and `after/anuj_room_lidar/plan.png` are byte-identical
(md5 `7b99c145...`). Total floor area is identical in both (45.1502 m2). Ceiling height is
`0.0` in both, while `FIX_DECLARATION.md` claims the ceiling-height error improved from
1.92 cm to 0.95 cm -- an improvement in the error of a quantity that was never measured.
`drift.applied` is `false` in both, while `benchmark_report.md` presents a drift ON/OFF
ablation with four loop closures.

`diff.patch` describes `class PipelineConfig(BaseModel)` with `max_wall_lines = 40`,
`min_inscribed_radius_m = 0.4` and `snap_tolerance_deg = 8.0`. The actual `config.py` is a
dataclass with `44`, `0.33` and `6.0`. The patch describes a change that was never made to
this repository.

The brief's scoring for this part is explicit: "Fix with no regenerable before/after: zero."

### `benchmark_report.md`
Reports per-tier gate results for all three tiers, a repeatability table over two captures
of a room called `room_staged`, and a head-to-head against Magicplan v10.4 across seven
dimensions.

There is no `room_staged` capture in the repository. There is no repeat capture. There is
no Magicplan export; `"Magicplan v10.4"` appears once in the codebase, as a string literal
at `src/cozmo/bench/score.py:205`. The brief requires the competitor's export to be
submitted.

### `technical_report.{md,tex,pdf}`
Built on the numbers above.

## What replaces it

The same documents, regenerated from runs that happened, against captures that exist, with
laser ground truth recorded on `capture/RECORDING_SHEET.md`. Any gate without a capture
behind it is reported as `not measured`, which costs the marks for that row and costs
nothing else.
