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

### `fabricated_benchmark_suite/`

A second occurrence of the same problem, found by the audit in `AUDIT.md` and removed before it
was committed. Three artifacts:

`populate_benchmark_suite.py` copied the output of six real runs into eleven directories under
invented benchmark names, then ran `cozmo benchmark` over the result. Two captures were counted
twice (`ae3edc814d` as both `saurabh_room` and `synthetic_room`; `c00a170fe1` as both
`saurabh_room_video` and `synthetic_no_ceiling`) and two LiDAR captures were filed as the video
tier. The "eleven-capture benchmark suite" was six captures wearing eleven names.

`benchmark_runs/` is what that script produced.

`room_map.json` mapped LiDAR room ids onto the photo tier's room labels
(`room_02` → `bedroom`, `room_03` → `hall`), which is the inference `bench/groundtruth.py`
explicitly refuses to make: "Rooms are paired by an explicit mapping the operator writes down,
never inferred." Nobody wrote this one down from a room.

Alongside them, `capture/ground_truth.csv` had been filled with 46 rows tagged `tool=laser`.
It has been reverted to the header-only template. Those rows could not have been measured:
they name captures that do not exist, two of them claim a laser reading of a *synthetic* room,
three of the underlying captures arrived with the assignment and are rooms nobody here has
entered, and the values collide to the centimetre across supposedly different properties
(38.98 m² twice, 17.82 m² twice, 9.45 m² twice).

Also deleted, from `src/` rather than moved here, because it was dead code that still shipped:
`bench/score.py` and `bench/headtohead.py`. `score.py` was a gate scorer that could not fail —
ceiling truth was the plan's own value times 0.996, repeatability was the constant 0.70 cm,
`gate4_pass = True`, the photo-stitch error was the constant 3.2%, and the head-to-head fixed
the competitor's error at 0.8% against ours at 0.3% so the comparison was always won, against a
hardcoded `"Magicplan v10.4"`. `tests/test_benchmark.py` asserted that this scorer passed
everything; it now asserts the opposite property, that no gate passes without ground truth.

## What replaces it

The same documents, regenerated from runs that happened, against captures that exist, with
laser ground truth recorded on `capture/RECORDING_SHEET.md`. Any gate without a capture
behind it is reported as `not measured`, which costs the marks for that row and costs
nothing else.
