# Benchmark report

13 Sep 2026. Every number is regenerable; the commands are at the end. Ground truth is the
operator's tape (`capture/ground_truth.csv`, `tool=tape`), recorded in whole or half feet. It
covers wall lengths, floor areas and adjacency for the home flat. It does not cover ceilings,
doors or bathroom walls, so those gates report SKIP.

## Gates

| status | count |
|---|---|
| PASS | 6 |
| FAIL | 13 |
| SKIP | 14 |

Full table: `reports/verified/gates/gate_table.txt`.

PASS: drift accountability on the three LiDAR runs; room overlap on the home long walk, the home
first walk and the photo tier. FAIL: walls, footprint, interval coverage and adjacency on each of
the two home LiDAR walks and on the photo tier, plus repeatability across the two walks. SKIP:
ceiling and opening widths (no tape), the assignment zip `c00a170fe1` (different property, no
tape), and photo-tier drift (not applicable).

## Which reconstructed room is which

Named from RGB frames taken by the camera standing deepest inside each room
(`capture/room_identity/`), never from area, because area is one of the scored quantities. An
earlier map named rooms by matching areas and was wrong on both captures: it scored the long
walk's bathroom as the passage and the home walk's bedroom as the hall. Every per-room figure
published before 13 Sep is superseded.

## LiDAR against tape

Long walk `163f18d3ac`, which followed the protocol: ceiling lap done, loop closed.

| Room | Tape | LiDAR | Error | LiDAR, feet | Tape, feet |
|---|---|---|---|---|---|
| Hall | 14.86 m² | 13.18 m² | −11% | 15.8 × 9.6 | 16 × 10, matched to the tape's precision |
| Bedroom | 9.29 m² | 5.28 m² | −43% | 8.5 × 6.8 | 10 × 10 |
| Bathroom | 2.04 m² | 2.63 m² | +29% | — | area only; this room also holds the upper passage |
| Passage | 2.55 m² | 1.99 m² | −22% | 8.4 × 2.6 | 11 × 2.5, width matched, length short |
| Window bay | not taped | 2.19 m² | — | 7.9 × 3.9 | — |
| **Footprint** | **28.75 m²** | **25.27 m²** | **−12%, FAIL** | | the taped rooms alone sum to 23.08 m², −20% |

Adjacency 3/4. Found: passage–bedroom, hall–bathroom, passage–bathroom. Missed: hall–passage,
because the upper passage is merged into the bathroom. One edge beyond the tape, hall to the
window bay, which does open off the hall. Walls 0/17 within 2 cm.

Home first walk `ae3edc814d`: 1.4% of frames aimed at the ceiling, and the hall barely covered.

| Room | Tape | LiDAR | Error |
|---|---|---|---|
| Bedroom | 9.29 m² | 7.03 m² | −24% |
| Hall | 14.86 m² | 6.04 m² | −59% |
| Passage | 2.55 m² | 3.50 m² | +37%, merged with the bathroom |
| **Footprint** | **28.75 m²** | **16.57 m²** | **−42%, FAIL** |

Adjacency 2/4. Walls 0/24.

## Repeatability

The two walks are the same flat at the same tier.

| Room | Long walk | First walk | Walls apart | Ceiling apart |
|---|---|---|---|---|
| Bedroom | 2.58 × 2.08 m | 2.89 × 2.68 m | 0.31 / 0.61 m | 0.4 cm |
| Hall | 4.82 × 2.93 m | 2.88 × 2.59 m | 1.95 / 0.34 m | 0.8 cm |
| Passage | 2.55 × 0.80 m | 2.73 × 2.30 m | segmented differently | 27.5 cm |

Gate: 0/25 walls agree, ceiling spread 27.5 cm, FAIL. The brief asks which failure this is.
Ceiling height repeats to 4 mm in the bedroom and 8 mm in the hall, where both walks segment the
room the same way, and fails in the passage, where they do not: the first walk's passage room
also holds the bathroom and reports 2.41 m, the height of the strongest overhead surface in the
long walk's bathroom, while the long walk reads 2.68 m over the passage itself. Walls are
unrepeatable rather than repeatable-but-biased: the same bedroom differs by 0.3–0.6 m between
walks, so the long walk's short bedroom is a reconstruction defect and not a tape error.

## Interval coverage

LiDAR intervals cover the tape on 0 of 16 measurements on the long walk (mean half-width 11.9 cm)
and 0 of 15 on the first walk (9.6 cm). The intervals carry sensor noise, residual drift and plane
roughness. They do not carry segmentation error, and segmentation error — a merged room, a short
bedroom — runs to tens of centimetres. No quantiles were fitted to close the gap: with two walks
of one flat, the rows used to fit would be the rows scored. The photo tier covers 7 of 11 at a
mean half-width of 6.9 m, which is coverage by being uninformative.

## Photo tier

58 stills in four folders from an iPhone 17 Pro, all on its 2.22 mm ultra-wide (0.5×): 54 at the
14 mm equivalent, 4 digitally cropped.

| Room | Tape | Photo | Note |
|---|---|---|---|
| Hall | 14.86 m² | rejected at 71.8 m² | above the 60 m² plausibility bound |
| Bedroom | 9.29 m² | 44.20 m² | no floor in frame; scale borrowed |
| Passage | 2.55 m² | 28.34 m² | scale from 2 of 8 photos |
| Bathroom | 2.04 m² | 19.45 m² | no floor in frame; scale borrowed |
| **Footprint** | **28.75 m²** | **92.00 m², +220%, FAIL** | gate ±8% |

It was 60.87 m² over two rooms before `8aaf149`. Every photographed room passes through the LiDAR
geometry, and the level changes in that commit other than the 2.20 m bound re-cut it: restoring
the old 1.6 m bound alone still gives 92.00 m². It fails its gate either way.

Adjacency 2/4, and both edges come from folder names, not detection. Walls 0/10 within 8%.
Against LiDAR depth of the same flat the depth model over-predicts on 0.5× frames by 1.57×; the
camera height implied by the detected floor gives 1.76×.

## Video tier

Metric scale is not solved. The whole-flat walkthrough produces one room of about 371 m², and
the assignment zip's own `rgb.mp4` without its poses gives 339.61 m² for a room LiDAR puts at
17.87 m². Do not choose this tier at a walk-in.

## Same input, compared

| Capture | This repository | Saurabh's public submission |
|---|---|---|
| `c00a170fe1`, assignment `single_room.zip` | 1 room, 17.87 m², ceiling unmeasured | 1 room, 17.82 m², ceiling 2.44 m from a prior |

This repository published 17.36 m² for that capture until `50d192b`, which merges a short step the
cell complex leaves in the middle of a straight wall back into the wall. No consumer-app export
exists, so the Part 3 head-to-head is not done.

## Regenerate

```bash
.venv/bin/python -m cozmo.cli run -i ../data/raw/163f18d3ac -o reports/verified/multiroom_long
.venv/bin/python -m cozmo.cli run -i ../DROP_CAPTURES_HERE/01_multiroom_lidar/ae3edc814d -o reports/verified/multiroom_home
.venv/bin/python -m cozmo.cli run -i ../data/raw/c00a170fe1 -o reports/verified/single_room
.venv/bin/python -m cozmo.cli run -i ../DROP_CAPTURES_HERE/03_multiroom_photos -o reports/verified/multiroom_photos
.venv/bin/python -m cozmo.cli benchmark --runs reports/verified \
    --ground-truth capture/ground_truth.csv --room-map capture/room_map.json \
    --repeat multiroom_home,multiroom_long --out reports/benchmark
```

The benchmark command exits non-zero because gates fail. That is the expected result.
