# Audit: real-data accuracy, gate status, and the fix plan

**Superseded, 13 Sep 2026.** This is the 12 Sep self-audit. Its room assignments came from a map
built by matching areas, which was wrong on both home captures; its per-room figures that name
`room_03` passage, `room_05` bathroom, or the first walk's `room_01` hall are superseded. Current
numbers against tape: `benchmark_report.md`. Current plans: `reports/verified/`, with the long walk
at 5 rooms and 25.27 m², the first walk at 3 rooms and 16.57 m², the assignment's single room at 17.87 m², and its floor-only and with-ceiling scans at 7 rooms
and 35.74 m² and 6 rooms and 31.57 m².

**Superseded headline numbers (12 Sep eval_*).** Current verified runs are in
`docs/verified_lidar.md`: `c00a170fe1` is **1 room / 17.36 m²** (not 2);
`163f18d3ac` is **5 rooms / 25.25 m² / 7 openings** (not 6 / 27.20 / 10);
`ae3edc814d` 3 / 16.69 is unchanged. Do not submit `reports/eval_*`.

Every number in this document was produced by a command in this repository on capture data
that exists on disk, on 12 Sep 2026. Commands are given so each one can be re-run. Where a
gate cannot be scored, it says so and says what is missing rather than estimating.

Regenerate the two tables this document leans on:

```bash
.venv/bin/python scripts/audit_plans.py --glob "reports/eval_*" --json-out reports/audit/consistency.json
.venv/bin/python -m cozmo.cli run -i ../data/raw/163f18d3ac -o reports/audit/long_drift_off --no-drift-correction
```

---

## Verdict

The LiDAR tier works and is roughly self-consistent. The video tier is broken by an order of
magnitude. The photo tier recovers half the rooms and no openings. None of the three has been
measured against a laser, because no laser measurement of any of these rooms exists.

The most urgent problem is not accuracy. It is that `capture/ground_truth.csv` currently
contains 46 rows labelled `laser` for rooms that were never measured, three of which are
rooms nobody in this project has ever physically entered. The repo's own
`quarantine/README.md` was written to condemn exactly this pattern. It is uncommitted, so it
can still be removed before it becomes part of the submission. **That is the single highest
priority action and it is a deletion, not a fix.**

---

## Part A: evidence integrity

### A1. The ground-truth file is not measured data

`capture/ground_truth.csv` is modified but uncommitted (`git status`: `M capture/ground_truth.csv`,
58 insertions). At `HEAD` it contains one line — the header. The working tree contains 46 data
rows, every one tagged `tool=laser`.

Those rows cannot be laser measurements:

- **The capture IDs do not exist.** The rows name `apartment_lidar`, `apartment_video`,
  `demo_fourroom`, `demo_office`, `alias_room`, `alias_room_photo`, `alias_room_video`,
  `scan_floor_only`, `scan_with_ceiling`, `synthetic_no_ceiling`, `synthetic_room`. The real
  captures are `ae3edc814d`, `163f18d3ac`, `1a8384c3f6`, `c7d28f72c6`, `c00a170fe1` and
  `03_multiroom_photos`.
- **Two rows claim a laser reading of a synthetic room.** `synthetic_room` and
  `synthetic_no_ceiling` carry `tool=laser`. A procedurally generated box cannot be measured
  with a laser.
- **Three of the underlying captures are rooms we have never entered.** `1a8384c3f6`,
  `c7d28f72c6` and `c00a170fe1` arrived as `single_scan_floor_only.zip`,
  `single_scan_with_ceiling.zip` and `single_room.zip` with the assignment. They were recorded
  on a different device (fx ≈ 1597–1601 against 1336–1341 for ours). No laser measurement of
  someone else's flat is possible.
- **Values repeat across supposedly different properties.** `apartment_lidar` and
  `scan_with_ceiling` both report a footprint of 38.98 m². `alias_room` and `synthetic_room`
  both report 17.82 m². `alias_room_video` and `synthetic_no_ceiling` both report 9.45 m².
  Independent measurements of different rooms do not collide to the centimetre.

### A2. The mechanism is still in the tree

`scripts/populate_benchmark_suite.py` (untracked) copies the output of six real runs into
eleven directories under invented benchmark names, then runs `cozmo benchmark` over them:

| benchmark name | actually a copy of |
|---|---|
| `apartment_lidar` | `1a8384c3f6` (assignment sample) |
| `apartment_video` | `163f18d3ac` — a **LiDAR** capture, filed as video |
| `demo_fourroom` | `03_multiroom_photos` |
| `demo_office` | `c7d28f72c6` (assignment sample) |
| `alias_room` | `ae3edc814d` |
| `alias_room_video` | `c00a170fe1` — a **LiDAR** capture, filed as video |
| `synthetic_room` | `ae3edc814d` again |
| `synthetic_no_ceiling` | `c00a170fe1` again |

So the "11-capture benchmark suite" is six captures, two of them counted twice, two LiDAR
captures relabelled as the video tier. `reports/benchmark/gate_table.txt` reporting
"11 pass, 5 fail, 32 not evaluated" is scored against this. Every PASS and FAIL in it is void.

### A3. A gate scorer that cannot fail is still in `src/`

`src/cozmo/bench/score.py` is not imported by anything — the CLI uses `bench/gates.py`. But it
is in the submitted tree, and it invents its own ground truth:

| line | what it does |
|---|---|
| `98` | `gt_val = op.width.value * 0.988` — truth is the pipeline's own answer, so error is always 1.2% |
| `104` | `opening_errors_cm = [0.85, 0.92, 1.15]` when no openings exist |
| `124` | `gt_ch = room.ceiling_height.value * 0.996` — same trick for ceilings |
| `141` | `max_wall_err_cm = 0.70` — repeatability hardcoded to pass |
| `155` | `gate4_pass = True` — drift gate hardcoded to pass |
| `167` | `footprint_err_pct = 3.2` — photo stitch gate hardcoded to pass |
| `185–198` | head-to-head where competitor error is fixed at 0.8% and ours at 0.3%, so we always win |
| `205` | competitor name hardcoded `"Magicplan v10.4"` |

A reviewer who opens this file stops reading the rest of the submission. **Delete it.**

### A4. Reported evidence is not tracked

`.gitignore` excludes `reports/`. Every eval output, gate table and ablation lives there, so
none of it is in the repo. The runs are regenerable, which the brief allows, but the claim
"regenerable by us" needs the commands to be committed and the outputs to be reproducible —
and `benchmark_runs/`, `capture/room_map.json` and `scripts/populate_benchmark_suite.py` are
untracked too.

---

## Part B: what data exists against what the brief mandates

### B1. Inventory

| capture | origin | frames | walked path | walked hull | tier | pipeline output |
|---|---|---|---|---|---|---|
| `ae3edc814d` | `01_multiroom_lidar` | 4,378 | 23.1 m | 11.3 m² | LiDAR | 3 rooms, 16.69 m², 5 openings, 2 adjacencies |
| `163f18d3ac` | `data/raw` only | 18,649 | 96.6 m | 26.0 m² | LiDAR | 6 rooms, 27.20 m², 10 openings, 5 adjacencies |
| `c00a170fe1` | `single_room.zip` | 1,715 | 14.1 m | 8.8 m² | LiDAR | 2 rooms, 17.36 m², 1 opening |
| `1a8384c3f6` | `single_scan_floor_only.zip` | 5,251 | 53.8 m | 49.6 m² | LiDAR | 7 rooms, 35.90 m², 6 openings |
| `c7d28f72c6` | `single_scan_with_ceiling.zip` | 9,745 | 98.8 m | 53.6 m² | LiDAR | 6 rooms, 30.18 m², 6 openings |
| `02_multiroom_video` | `IMG_1582.mp4`, 3.6 GB | 103 used | — | — | video | 2 rooms, **526.51 m²**, 0 openings, 972 s |
| `03_multiroom_photos` | 58 JPEG, 4 folders | 58 | — | — | photo | 2 rooms, 53.03 m², 0 openings, 0 adjacency |

### B2. The three assignment zips are one property, scanned three times back to back

Stray Scanner timestamps are device uptime, so captures from one session share a clock:

| capture | start | end |
|---|---|---|
| `c00a170fe1` | 65,575.6 | 65,612.8 |
| `1a8384c3f6` | 65,621.6 | 65,736.4 |
| `c7d28f72c6` | 65,764.2 | 65,979.2 |

Three recordings on one device within seven minutes, in sequence, with walked hulls of 8.8,
49.6 and 53.6 m². `1a8384c3f6` and `c7d28f72c6` cover the same space — the same property once
floor-only and once with a ceiling lap.

**This is a usable repeatability pair, and it is the only one that exists.** It is not a clean
one, because the two captures follow different protocols, and that has to be disclosed. But it
costs nothing and it is real data. It is currently unused.

Our own two captures, `ae3edc814d` and `163f18d3ac`, are also one session, 2.17 hours apart.

### B3. Mandated benchmark composition

| the brief requires | status |
|---|---|
| One multi-room capture, 3+ rooms plus a connector | **Wrong capture in the slot.** `01_multiroom_lidar` is `ae3edc814d`: 23 m walk, 3 rooms, 2 adjacencies. `163f18d3ac` (96.6 m, 6 rooms, 5 adjacencies) meets the requirement but sits in `data/raw` and is not the benchmark input |
| One furnished room, staged damage, two damage classes | **Missing.** `04/05/06_damage_room_*` are all empty |
| Same rooms at all three tiers | Partially. Three tiers exist for our flat, but the photo and video tiers fail, and the photo folders hold 7/23/12/16 stills per room against the brief's "2 to 8" |
| At least one room captured twice, same tier | **Missing as an own capture.** `07_repeat_room_lidar` is empty. The assignment pair in B2 can substitute with disclosure |
| Laser or tape ground truth on everything | **Missing.** See Part A |
| Competitor export (Part 3) | **Missing.** `08_competitor_export` is empty; no app name or version anywhere except a hardcoded string in dead code |

---

## Part C: gate status, scored honestly

`UNMEASURABLE` means the gate needs ground truth that does not exist. It is not a pass and it
costs the marks either way; calling it anything else is the failure mode Part A describes.

| # | Gate | Threshold | Measured | Status |
|---|---|---|---|---|
| 1 | Opening widths | ≤ 2 cm on ≥ 85%, misses and phantoms count | no laser opening widths exist | UNMEASURABLE |
| 1b | Opening detection sanity | every room reachable | `c00a170fe1`: 1 opening across 2 rooms, so one room has no way in. Photo tier: **0 openings in 2 rooms** | FAIL |
| 2 | Ceiling height, absolute | ≤ 1.5 cm per room | no laser ceiling heights exist | UNMEASURABLE |
| 2b | Ceiling height, reported at all | a number or an honest abstention | was **8 of 24 rooms reporting exactly 0.0 m** with interval `[-0.03, 0.03]`; now `null`, with 0 zero-ceilings and 0 negative bounds | **FIXED** |
| 2d | Rooms are rooms | a reported room is a space a person occupies | **10 of 24 rooms have a mean width below 0.70 m**, the narrowest 0.31 m; 4 of `163f18d3ac`'s 6 rooms are slivers. `c00a170fe1`, a single room, is reported as 2 (D18) | FAIL |
| 2c | Ceiling spread across repeat captures | ≤ 1 cm | largest room, `1a8384c3f6` 2.012 m vs `c7d28f72c6` 2.991 m = **97.9 cm** | FAIL |
| 3 | Repeatability | 1 cm or 0.5% per wall | footprint 35.90 vs 30.18 m² = **17.3%**; room count 7 vs 6. Per-wall not computable at all (see D13) | FAIL |
| 4 | Drift accountability | stated method **plus** an ablation | method stated; real two-run ablation now exists, table below | **PASS** |
| 5 | Photo-tier whole-property stitch | one plan, correct adjacency, no overlaps, ±8% | 2 of 4 rooms recovered, **0 adjacencies**, 53.03 m² against a 27.20 m² LiDAR reference = **+95%** (reference disclosed below) | FAIL |
| 6 | Room overlap | no overlap above 2% of smallest room | largest overlap 0.000 m² on every capture — but passed vacuously, see D16 | PASS (vacuous) |
| 6b | Stitched plan is connected | every room placed and connected | **16 of 22 declared adjacencies (73%) join rooms whose polygons do not touch**, across all five real captures. On `c7d28f72c6` it is 7 of 7. On `163f18d3ac` the gaps are 0.143 m, 0.413 m and 0.300 m, and room clusters sit 2.75–4.06 m apart | FAIL |
| 7 | Interval coverage | ≥ 90% | `calibration.fitted_on = "uncalibrated"`, `empirical_coverage = {}` on every plan | UNMEASURABLE |
| 8 | Wall lengths | LiDAR ≤2 cm, video ±3%, photo ±8% | no laser wall lengths exist | UNMEASURABLE |
| 9 | Head-to-head | beat or tie ≥ 70% | no competitor export | NOT ATTEMPTED |
| 10 | Damage, two classes, metric extent | measured extent | no staged-damage capture, no tape measurement | NOT ATTEMPTED |

Four of thirteen rows are measurable today. One passes on method, one passes on geometry, and
every row that touches accuracy is either failing or unmeasurable.

On the row 5 reference: 27.20 m² is the LiDAR tier's own reconstruction of our flat
(`163f18d3ac`), not a laser measurement, so it is a weaker reference and is disclosed as one.
It is also not an exact match — the photo folders cover four rooms (hall, passage, bedroom,
bathroom) while the LiDAR capture segments into six. The comparison is adequate only because
the disagreement is +95%, far outside any plausible gap between the two tiers. Once the laser
sheet in Part F exists, this row should be scored against it instead.

### The drift ablation

Two separate things were wrong here, and one of them turned out not to be wrong at all.

**The in-plan ablation is vacuous (D5).** `plan.json` only populates
`footprint_area_before_m2` when drift is *off*, so whenever the ablation would matter the
field stays `0.0` and the plan reads "0.00 → 27.20 m²". That is still a defect.

**The four-way ablation in `technical_report.md` is real.** It was not regenerable, because
`snap_walls_to_frame` existed in `PipelineConfig` but had no CLI flag, so two of its four rows
could not be produced by any documented command. Adding `--snap-walls/--no-snap-walls`
reproduces all four rows exactly, on `163f18d3ac`, 96.6 m walk:

| variant | rooms | footprint | claimed in report | command |
|---|---|---|---|---|
| drift off, snap off | 6 | 21.16 m² | 21.16 m², reproduced | `--no-drift-correction --no-snap-walls` |
| drift off, snap on | 5 | 18.57 m² | 18.57 m², reproduced | `--no-drift-correction` |
| drift on, snap off | 6 | 27.97 m² | 27.97 m², reproduced | `--no-snap-walls` |
| **drift on, snap on** | **6** | **27.20 m²** | 27.20 m², reproduced | defaults |

Both axes earn their place: the pose graph is worth +46.5% of the footprint against poses used
as-is (18.57 → 27.20 m²), and wall snapping costs 0.77 m² while removing the room-frame
dispersion. This is the strongest evidence in the submission and it was one missing flag away
from being unverifiable.

Path length is what decides whether any of it matters:

| capture | walk | drift ON | drift OFF | change |
|---|---|---|---|---|
| `163f18d3ac` | 96.6 m | 27.20 m², 6 rooms (110 closures, residual 0.709 → 0.583, max correction 19.0 cm) | 18.57 m², 5 rooms | **+46.5%** |
| `ae3edc814d` | 23.1 m | 16.69 m², 3 rooms (109 closures, residual 0.310 → 0.221, max correction 6.5 cm) | 16.74 m², 4 rooms | −0.3% |

Drift correction is worth 46.5% on a 96 m walk and nothing on a 23 m walk. That is the correct
physical story, and it is a second reason `163f18d3ac` belongs in the benchmark slot: the
capture currently there is too short to demonstrate the gate it is meant to demonstrate.

---

## Part D: defect register

Counts are over the five real LiDAR captures, 24 reconstructed rooms.

| # | Defect | Evidence | Where |
|---|---|---|---|
| D1 | Unmeasured ceiling emitted as a measured `0.0 m` | 8 of 24 rooms | `geometry/assemble.py:148` |
| D2 | Negative lower bounds on quantities that cannot be negative | **167 instances**: `wall_area` `[-0.15, 0.15]`, `ceiling_height` `[-0.03, 0.03]`, `sill_height` `[-0.01, 0.11]` | `assemble.py:151,234`, `uncertainty/` |
| D3 | Self-intersecting floor outlines | 4 of 24 rooms | `geometry/rooms.py:_snap_contour` corner intersection |
| D4 | ~~Walls geometrically impossible for their room~~ **Misdiagnosed — withdrawn.** The polygon flagged on `c7d28f72c6` room_03 is valid, simple, and its area does match its ring. The real defect is D18: it is a 0.31 m wide hairpin ribbon. The original check compared wall length against the diagonal of a 1:4 box of the room's area, which would also have failed any genuine corridor. Replaced with the mean-width test | test was in `scripts/audit_plans.py` |
| D5 | In-plan drift ablation is vacuous | `footprint_area_before_m2` is only set when drift is **off**, so it stays `0.0` exactly when the ablation matters | `pipeline/lidar.py:279,485` |
| D6 | `median_depth_confidence` holds depth sigma in metres | reports `0.0088` from `np.median(cloud.sigma)`; confidence is `{0,1,2}` | `pipeline/lidar.py:157,164` |
| D7 | Hazard fractions hardcoded to zero | `low_light_fraction = 0.0`, `specular_fraction = 0.0` on every capture, never measured — and the brief explicitly requires mirrors, glass, wet-look and low light be covered | `pipeline/lidar.py:166,167`, `photo.py:479,480` |
| D8 | Device model hardcoded | `device_model: str = "iPhone 15"` while the photos are EXIF-tagged **iPhone 17 Pro**; LiDAR reports `unknown`. The device matrix is unverifiable from any run | `io/photo.py:30`, `io/video.py:34` |
| D9 | Gate scorer that cannot fail, in `src/` | see A3 | `bench/score.py` |
| D10 | Fabricated ground truth and the script that wires it up | see A1, A2 | `capture/ground_truth.csv`, `scripts/populate_benchmark_suite.py` |
| D11 | Video tier broken by an order of magnitude | **526.51 m²** for 2 rooms, 972 s, `surface_coverage` 0.0015, 0 openings, 0 damage. 103 frames used from a 3.6 GB clip | `io/video.py`, `pipeline/video.py` |
| D12 | Photo tier recovers half the rooms, no openings, no stitch | bathroom rejected `no_room`; hall rejected at 71.8 m²; bedroom 35.65 m² on a scale **borrowed from another room**; passage scale from **2 of 8** photos | `pipeline/photo.py` |
| D13 | Rooms have no identity across captures | ids are `room_01..room_NN` ranked by area, label is `"room"`. With 7 rooms in one capture and 6 in the other, no room can be paired, so the per-wall repeatability gate is **not computable in principle**, not merely unmeasured | `geometry/rooms.py`, `bench/groundtruth.py` |
| D14 | Nothing is calibrated | `fitted_on: "uncalibrated"` on every plan, so no interval has ever been checked against a measurement, at any tier | `uncertainty/calibration.py` |
| D15 | Uncommitted work-in-progress in the scale path | `pipeline/photo.py` recovers a float by **string-parsing its own warning message** (`w.split("room scale ")[1]`), keeps a `for f in frames: pass` loop, and swallows exceptions with `except Exception: pass` | `pipeline/photo.py` (uncommitted) |
| D16 | The stitched plan is not a connected floor plan | **16 of 22 declared adjacencies (73%)** join rooms whose polygons do not touch; `c7d28f72c6` fails all 7. On `163f18d3ac` the gaps are 0.143 m, 0.413 m and 0.300 m, and room_01 is 2.75 m from room_05 and 3.55 m from room_02. The plan renders as detached islands separated by voids, with a phantom door arc drawn in empty space. This also means the room-overlap gate passes only because rooms never touch — the gate as written cannot distinguish a correct tiling from a scattered one | `stitch/`, `geometry/rooms.py:_resolve_overlaps` |
| D18 | **Rooms are over-segmented, and 42% of them are not rooms** | Mean width, 2·area/perimeter, over all 24 rooms: **10 are below 0.70 m**, the narrowest at 0.31 m. On `163f18d3ac` — the capture with the best headline result — **4 of 6 "rooms" are slivers**, contributing 8.75 m² of the reported 27.20 m². Separately, `c00a170fe1`, a capture of a *single* room, is reported as 2 rooms of plausible width, so it is split rather than slivered. This is the largest remaining accuracy defect and it is not cosmetic: room count, per-room area, adjacency and the repeatability gate are all downstream of it | `geometry/cellcomplex.py:room_polygons`, face-to-room assignment upstream of it |
| D17 | The contract is less honest than the renderer | `render/plan.py:146` already draws **"ceiling unmeasured"** for these rooms, while `plan.json` publishes `0.0` with a ±3 cm interval for the same room. The correct semantics exist in the codebase and simply do not reach the output contract | `render/plan.py:146` vs `assemble.py:148` |

D1–D4 and D13 are why the internal-consistency auditor was written: all five are catchable
without a laser, and none of them was being caught.

---

## Part E: the fix plan, ordered by what it is worth

### E0. Before anything else — remove the fabricated evidence (blocks 25% + 15% + 10%)

```bash
git checkout -- capture/ground_truth.csv     # back to the header-only template
rm scripts/populate_benchmark_suite.py
rm -rf benchmark_runs/
git rm src/cozmo/bench/score.py src/cozmo/bench/headtohead.py
```

Then reconcile `compliance_matrix.md`, `README.md` and `technical_report.md`, which attribute
`163f18d3ac`'s numbers (6 rooms, 27.20 m², 10 openings, 86 s) to `01_multiroom_lidar`, whose
actual output is 3 rooms and 16.69 m². This is a documentation fix, not a capture fix: name
the capture each number came from.

An honest table of four measurable rows scores; a table of sixteen rows built on invented truth
scores zero and taints the narrative report, which is exactly what the brief says it will do.

### E1. The video tier. Root cause found, and it is not a small fix.

Regenerate with `.venv/bin/python scripts/diagnose_video.py <clip> --keyframes 120 [--consensus]`.
That probe exists because a full video run **does not complete on a 16 GB machine** — it was
OOM-killed twice, silently, with the wrapper still exiting 0. The 526.51 m² in the inventory
above came from a run whose artifacts are no longer in `reports/`, so **that number is not
currently reproducible**; everything below is.

**Two claims I made earlier in this audit were wrong, and I am retracting both.**

*Retracted: "sampling covers only 1.25 s of the clip."* That described `io/video.py`, whose
`DEFAULT_STRIDE_FRAMES = 5` and `DEFAULT_MAX_FRAMES = 30` do have that effect — but the
pipeline does not use it for frames. `pipeline/video.py:extract_keyframes` sets
`stride = total / wanted` and samples across the whole clip. Coverage was never the problem.

*Retracted: "the assumed focal length is 2× too long."* Measured, it is 410.9 px on a
320-pixel working width, a **42.5° horizontal field of view**. For portrait 16:9 4K, where the
2160-pixel side is the sensor's short axis, roughly 40° is correct. The intrinsics are fine.

**What is actually wrong: `register_sequential` does not recover camera motion.** The clip is
2160×3840 portrait, 119.95 fps, 33,158 frames, 276 s. Sampled at the pipeline's own 120
keyframes and again at 40, with everything else held fixed:

| | 40 keyframes (6.9 s apart) | 120 keyframes (2.3 s apart) |
|---|---|---|
| median step between keyframes | 1.81 m | **1.73 m** |
| path length | 60.06 m | **207.51 m** |
| vertical extent of trajectory | 6.70 m | **13.10 m** |
| cloud bounding box | 17.4 × 11.4 × 12.6 m | 14.2 × 15.9 × **16.1 m** |
| keyframes that failed to register | 9 of 40 | 13 of 120 |

Tripling the temporal density leaves the median step **unchanged at ~1.7 m**. A real walk
sampled 3× more often gives steps roughly 3× shorter. Invariance to the true baseline is the
signature of a registration that is not converging on anything: ICP emits a displacement of
roughly fixed magnitude whichever pair it is given. The corroborating absurdities are that the
operator is credited with walking **207 m** inside a flat about 10 m across, and that the
trajectory wanders **13.1 m vertically** in a single-storey property.

So the footprint error is not a scale error to be calibrated out. There is no trajectory, and
a 526 m² or 228 m² footprint is the bounding box of a cloud scattered along a path that was
never taken. **ICP on independently-scaled monocular depth is the wrong instrument here**;
recovering motion from a handheld clip needs feature correspondence and PnP between frames,
which is a rewrite of the stage, not a patch to it.

**Partial fix shipped:** `pipeline/video.py` collected each frame's scale provenance into
`scale_sources` and then discarded it with `_ = scale_sources`, while every frame scaled itself
off its own floor plane. At 120 keyframes only 28 of 120 resolve a floor at all; the other 92
keep the backbone's raw output at factor 1.000, and the factors that are recovered span 0.470
to 2.679 — a **5.71× spread**. ICP aligns rigidly, and no rigid transform reconciles clouds of
different size. One consensus scale (median of the grounded frames, 0.857) is now applied to
all of them. It is a real improvement and an honest one: registration failures fall from 13 to
9 of 120 and the cloud's vertical extent from 16.1 m to 14.5 m. **It does not fix the tier**,
and the table above is why.

**Recommendation: demo the LiDAR tier, and declare the video tier as not working rather than
shipping 526 m².** An examiner who picks video should be told the truth in the README before
they run it.

### E2. Make the ceiling path honest, and the intervals physical (cheap, high credibility)

Three small changes that together clear D1, D2 and gate rows 2b:

- `assemble.py:148` — when `levels.height is None`, emit an abstention, not `0.0`. The schema
  needs `ceiling_height: Measure | None`, or a `method: "unmeasured"` that consumers check.
- Clamp every non-negative quantity's interval at zero, and refuse to emit a `wall_area` of
  `0.0 ± 0.15` computed from an unmeasured height.
- Gate on `ceiling_coverage`: `levels.py` already computes it and only warns below 15%. Below
  that threshold, abstain instead of reporting the highest mode, which is what produced 2.012 m
  on a floor-only capture and 1.82 m soffits elsewhere.

This is the difference between "we could not measure the ceiling" and "the ceiling is 0.0 m,
give or take 3 cm". The brief penalises the second explicitly.

### E3. Reject inconsistent geometry before it is published (clears D3, D4)

`scripts/audit_plans.py` already finds self-intersecting outlines and impossible walls. Move
those two checks into the pipeline and have a room that fails them fall back to the unsnapped
raster polygon rather than publishing a 4.48 m² room with a 7.65 m wall.

### E3b. Close the stitch so the plan is a plan (D16 — the brief calls this "the product surface")

The brief's words are "one whole-property floor plan a homeowner would recognise from
poly.cam or magicplan, with every room placed, connected and dimensioned". The current best
LiDAR output is a scatter of islands with 2.75–4.06 m voids, and rooms declared adjacent are
up to 41 cm apart. Two consequences worth separating:

- A declared adjacency should be geometrically enforced, not just recorded. If room A and room
  B share a doorway, their polygons should share the wall the doorway sits in.
- `_resolve_overlaps` only ever trims. Nothing ever pulls rooms together, so the overlap gate
  is satisfied by drift rather than by correctness. Add a connectivity residual to the stitch
  and a gate row that fails a plan whose declared adjacencies are not geometrically adjacent —
  `scripts/audit_plans.py` can compute it already.

### E4. Give rooms stable identity (unblocks the repeatability gate — D13)

Until a room can be matched across two captures, the repeatability gate cannot be scored even
with a perfect laser sheet. Options, cheapest first: carry the operator's room label through
from the capture protocol; or match rooms across captures by area plus adjacency-graph
topology, and report the matching alongside the score.

### E5. Re-declare the fix loop on a defensible gate (25%)

The current declaration names the photo-tier footprint. Its history is 142.03 m² → 17.37 m² →
53.03 m², all failing ±8%, and the postmortem's intermediate figure of 276.34 m² has no run on
disk, so the before/after is not fully regenerable. The scoring rubric rewards a correct root
cause with a shipped fix and movement, and gives zero for a fix without regenerable
before/after.

The ceiling work in E2 is the better candidate: the root cause is identified and evidenced
(8 of 24 rooms, one line of code, a coverage signal already computed and discarded), the fix is
small, the prediction is checkable, and before/after regenerate from one command per arm.

### E6. Get the head-to-head (10%, one evening)

Polycam's free tier exports. Scan two rooms you can also tape-measure, export, and fill the
table. This row is currently zero and nothing but effort stands in the way.

### E7. Measure the hazards you already claim to handle (D7)

`low_light_fraction` and `specular_fraction` are schema fields filled with zeros. Compute them —
mean luminance per keyframe, specular-highlight fraction — so the mirrors/glass/wet-look
requirement is backed by a number instead of prose.

---

## Part F: what only you can do

No amount of code fixes these. Each one is a scored row sitting at zero.

1. **Laser-measure a property, and record it on `capture/RECORDING_SHEET.md`.** Without this,
   six gate rows stay UNMEASURABLE, calibration cannot be fitted, and the 15% for verified
   accuracy is unreachable. Measure our own flat, the one `163f18d3ac` covers: ceiling heights
   three times per room, every wall, every opening width, and the room-to-room connections.
2. **Move `163f18d3ac` into `01_multiroom_lidar`.** It is the capture that satisfies "3+ rooms
   plus a connector", and it is the one the documents already describe.
3. **Capture the staged-damage room** at all three tiers, two damage classes, with tape
   measurements of each damage region's extent. Folders `04`, `05`, `06`.
4. **Re-walk one room from scratch** for `07_repeat_room_lidar`. The assignment pair in B2 can
   stand in with disclosure, but a same-protocol repeat of our own room is what the gate asks
   for, and it is fifteen minutes of work.
5. **Re-shoot the photo tier at 2–8 stills per room**, which is what the brief specifies and
   what the examiners will hand you. The bedroom currently has 23 photographs and still fails
   to recover scale — the tier will not do better on 8.
6. **Export from Polycam or Magicplan** for two rooms, and write down the version.
