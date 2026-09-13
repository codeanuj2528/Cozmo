# What to submit, and what to show

Verified by opening the `plan.json` / `plan.png` files, not by memory.
`reports/` was gitignored; `reports/verified/` is now tracked so the examiner
sees the same plans.

## Show these (walk-in)

| File | Why |
|---|---|
| `reports/verified/single_room/plan.png` | Assignment `c00a170fe1`. **1 room, 17.36 m²**, 1 opening, ceiling honestly unmeasured. Same zip Saurabh reports as 17.82 m². |
| `reports/verified/multiroom_home/plan.png` | Home Stray `ae3edc814d`. **3 rooms, 16.69 m²**, ceilings 2.63 / 2.62 / 2.43 m, gaps 0. He emits one room per capture. |
| `reports/verified/multiroom_long/plan.png` | Long walk `163f18d3ac`. **5 rooms, 25.25 m²**. |
| `scripts/setup.sh` | 15 min: venv + ray-traced **3.60×2.80×2.50** box → ~10.08 m², ceiling 2.50 m. |

Examiner command after `scripts/setup.sh`:

```bash
.venv/bin/python -m cozmo.cli run -i <stray-folder> -o runs/demo
```

## Disclose, do not lead with

| File | Why |
|---|---|
| `reports/verified/multiroom_photos/plan.png` | **Photo benchmark (DROP 03).** 58 stills, 4 folders. **2/4 rooms, 60.87 m²** vs tape 28.75 (+112%). Hall rejected 71.8 m²; bathroom `no_room`. Submit with these warnings; do not lead. |
| `reports/verified/one_room/photo/plan.png` | Bathroom-only 7 stills → **0 rooms**. Not the 4-folder benchmark. |
| `reports/verified/one_room/video/plan.png` | Same apartment room as LiDAR 17.36 m² → **339 m² / 2 rooms**. Scale failed. |
| DROP `02_multiroom_video` | Whole-flat clip: current-code run is **1 room ~371 m²**, 0 adjacency, coverage ~0.002. **Do not lead with that plan.** Same scale failure as `one_room/video`. |
| `reports/eval_1a8384c3f6/` | Over-segmented older floor-only zip. Prefer verified multi-room. |
| `quarantine/` | Fabricated suite. Keep in repo as the audit trail. **Do not quote its numbers.** |

## Fix loop (examiner)

Committed: `fixloop/before/plan.json` **142.03 m²** → `after/plan.json` **17.37 m²**.
Gate ±8% still **FAIL**. Readable diff: `git diff d15c21b..80c44f3`.
Do **not** `git checkout fixloop-before` — that tag is off this graph.

## Tape (filled, 13 Sep 2026)

Operator feet in `capture/ground_truth.csv`, `tool=tape`. Layout from the
operator and the photo folders: hall 16×10 — passage 2.5×11 — bedroom 10×10;
bathroom 22 sq ft on hall **and** passage. Mapping: `capture/room_map.json`.

Home LiDAR vs that tape is **FAIL** (see `benchmark_report.md`): 16.69 / 25.25 m²
against 28.75 m². Do not invent ceiling, door, or bathroom-wall rows to fill the
SKIPs.

## Do not invent

- Ceiling, door widths, bathroom walls, diagonals — still unmeasured. Leave SKIP.
- No Magicplan/Polycam export. Head-to-head 10% is zero until you drop `08_competitor_export/`.
- `04`–`07` DROP slots are empty (damage + repeat).

## You still have to do (only you)

1. Ceiling ×3 per room, door widths, bathroom walls → same CSV.
2. One room again in Stray → `07_repeat_room_lidar/`.
3. Magicplan or Polycam, 2 rooms → `08_competitor_export/` + app version.
4. Photos at **1×**, 4–8 per room, floor visible. Steps: `../DROP_CAPTURES_HERE/STEP_BY_STEP.md`.

Without (2)–(3) you can still submit an **honest** repo that beats Saurabh on stitched LiDAR and does not fake the rest.

## Do not put in the zip

- A `reports/benchmark/` that shows footprint **PASS** (the honest tape run is 16.69 / 25.25 vs 28.75, both FAIL)
- **Entire `quarantine/`** (README says nothing here is submittable)
- `scripts/generate_benchmarks.py` and `scripts/build_pdf.py` (moved under quarantine; they rebuild fake PASS / Magicplan tables)
- `reports/eval_*` (pre-merge: 2-room `c00a170fe1`, 6-room / 27.20 m² long walk, negative interval `lo`)
- Guessed metres in `ground_truth.csv`
- The 3.4 GB `IMG_1582.mp4` as a working video-tier demo (~371 m² blob)
- 0.5× photo folders as a success (the 4-folder plan is a disclosed **FAIL**)

## Commit before push (uncommitted as of this file)

Saurbh-integration that is not on `main` yet:

- `scripts/setup.sh`
- `tests/fixtures/raytrace_room.py` + `tests/test_synthetic_lidar.py` + `tests/test_intervals.py`
- thin-tier ±60% intervals, folder-name stitch
- this file, `.gitignore` exception for `reports/verified/`

History is already incremental (`fixloop-before` tag exists). Do not squash into one dump.
Remote is `codeanuj2528/Cozmo`, ahead 50 / behind 26 — rebase or merge before force-pushing, and **do not force-push** unless you mean to.
