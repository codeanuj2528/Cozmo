# Benchmark report

Headline, 13 Sep 2026. Regenerable. **Operator tape** on the home flat
(`tool=tape`, feet → metres at 1 ft = 0.3048 m). Not laser. Not invented.

| status | count | what |
|---|---|---|
| **PASS** | 6 | LiDAR drift + room-overlap (home, long, photo overlap) |
| **FAIL** | 12 | LiDAR walls/footprint/intervals/adjacency; photo walls/footprint/intervals/adjacency |
| **SKIP** | 14 | ceiling + openings (no tape); assignment `c00a170fe1`; photo drift N/A |

## Tape vs LiDAR (same four rooms)

Layout: **hall (16×10 ft) — passage (2.5×11 ft) — bedroom (10×10 ft)**;
bathroom (22 sq ft) attached to hall **and** passage.

| Room | Tape | Home walk `ae3edc814d` | Long walk `163f18d3ac` |
|---|---|---|---|
| Hall | 14.86 m² (16×10 ft) | room_01 **7.15 m²** | room_01 **13.18 m²** |
| Passage | 2.55 m² (2.5×11 ft) | room_03 **3.50 m²** | room_03 **2.62 m²** |
| Bedroom | 9.29 m² (10×10 ft) | room_02 **6.04 m²** | room_02 **5.27 m²** |
| Bathroom | 2.04 m² (22 sq ft) | *not a room* | room_05 **1.99 m²** |
| Extra | — | — | room_04 2.19 m² (unmapped sliver) |
| **Footprint** | **28.75 m²** | **16.69 m² (−42%) FAIL** | **25.25 m² (−12%) FAIL** |
| Adjacency | 4 edges | 2/4, bathroom missing **FAIL** | 2/4, bedroom–passage missed, 2 phantom **FAIL** |
| Walls | ≤2 cm on ≥85% | 0/25 **FAIL** | 0/30 **FAIL** |

`room_map.json` is walk-order + photos (`room_01` hall, `room_03` passage,
`room_02` bedroom, `room_05` bathroom). Not inferred from area.

## Photo tier (same home, 58 stills, 13 Sep 2026)

Command: `cozmo run -i ../DROP_CAPTURES_HERE/03_multiroom_photos -o reports/verified/multiroom_photos`
(137 s). iPhone 17 Pro **0.5× / 14 mm**. Capture id `ae3edc814d`.

| Room | Tape | Photo | Notes |
|---|---|---|---|
| Hall | 14.86 m² | *rejected* 71.8 m² (>60 m² guard) | ceiling-heavy set |
| Passage | 2.55 m² | **17.37 m²** | scale from 2/8 floor shots |
| Bedroom | 9.29 m² | **43.50 m²** | no floor scale; borrowed 0.613 |
| Bathroom | 2.04 m² | *no_room* | same as the one-room photo run |
| **Footprint** | **28.75 m²** | **60.87 m² (+112%) FAIL** | gate is ±8% |
| Adjacency | 4 edges | 1/4 (bedroom–passage, folder name only) **FAIL** | |

Do not lead the walk-in with this plan. Intervals are ±60% and still only cover 6/10.
`one_room/photo` is the bathroom-only rejection (0 rooms), not this run.

## Video tier (do not lead)

| Input | Result | Use |
|---|---|---|
| Assignment `rgb.mp4`, no poses (`one_room/video`) | 2 rooms, **339.61 m²** vs LiDAR 17.36 | In-repo disclose |
| DROP `02` whole-flat clip (`IMG_1582.mp4`) | 1 room, **~371 m²**, 0 adjacency | Fresh run; plan not a walk-in artifact |

Both fail the same way: monocular scale. ±60% intervals do not rescue a 20× footprint.

## Hero table (assignment zips + home, LiDAR)

| Capture | This repo (verified) | Saurabh |
|---|---|---|
| `c00a170fe1` / apartment | **1 room, 17.36 m²**, ceiling unmeasured | 1 room, 17.82 m², ceiling 2.44 m prior |
| Home / `ae3edc814d` | **3 rooms, 16.69 m²** vs tape 28.75 | one room per capture |
| Long walk `163f18d3ac` | **5 rooms, 25.25 m²** vs tape 28.75 | floor-only zip collapsed to 1 room, 51.33 m² |

Plans: `reports/verified/{single_room,multiroom_home,multiroom_long}/plan.png`.

```bash
.venv/bin/python -m pytest tests/ -q
.venv/bin/python scripts/audit_plans.py reports/verified/single_room reports/verified/multiroom_home reports/verified/multiroom_long
.venv/bin/python -m cozmo.cli benchmark \
  --runs reports/verified \
  --ground-truth capture/ground_truth.csv \
  --room-map capture/room_map.json \
  --out reports/benchmark
```

That command must print **FAIL** on home footprint / walls / adjacency, and
**SKIP** on ceiling / openings and on `c00a170fe1`. A green footprint against
this tape is wrong — the LiDAR is short, not the tape.

Still missing (operator only): ceiling ×3, door widths, bathroom walls, repeat
Stray, Magicplan/Polycam. Do not invent those rows.

Do not quote `quarantine/` or `reports/eval_*`.
