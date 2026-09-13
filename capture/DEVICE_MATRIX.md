# Device matrix

Which tier runs on which hardware, and what each tier honestly delivers.

## Tier availability by device

| Device | Photo | Video | LiDAR | Notes |
|---|---|---|---|---|
| iPhone 15 / 16 / 17 (non-Pro) | Yes | Yes | No | No depth sensor. Photo and video tiers are the whole capability. |
| iPhone 15 / 16 / 17 Pro, Pro Max | Yes | Yes | Yes | LiDAR at 256x192, ARKit poses and per-frame intrinsics. |
| iPad Pro (2020 onward) | Yes | Yes | Yes | Same sensor family. Not tested by us; treated as untested rather than supported. |
| iPhone 14 and older | Out of contract | Out of contract | Out of contract | Brief specifies iPhone 15 or newer. |

## Accuracy each tier delivers

Measured on one iPhone 17 Pro against the operator's tape, which is recorded in whole feet and
covers walls, floor areas and adjacency but no ceilings or doors. Wall length and floor area are
the median and 90th-percentile absolute error from `scripts/accuracy_table.py`, relative error in
brackets; the other rows are gate measurements from `reports/verified/gates/gate_table.txt`.

| Quantity | Photo | Video | LiDAR | Gate |
|---|---|---|---|---|
| Wall length | median 2.08 m (75%), p90 3.72 m (125%), n = 12 | not taped | median 0.81 m (26%), p90 2.09 m (60%), n = 28 | photo 8%, video 3%, LiDAR 2 cm |
| Room floor area | median 23.02 m² (614%), p90 32.18 m² (962%), n = 4 | not taped | median 1.58 m² (27%), p90 5.46 m² (48%), n = 8 | no separate gate |
| Ceiling height | not taped | not taped | not taped | 1.5 cm per room |
| Ceiling height spread across repeats | no repeat capture | no repeat capture | 2.9 cm for the bedroom walked alone against the long walk; 27.5 cm across the two flat walks | 1 cm |
| Opening width | not taped | not taped | not taped | 2 cm on 85% of openings |
| Repeatability per wall | no repeat capture | no repeat capture | 0/5 walls, worst 120.7 cm (bedroom); 0/25, worst 212.6 cm (flat walks) | 1 cm or 0.5% |
| Whole-property footprint | +220% (58 stills at 0.5×); the hall alone at 1× +136% | not taped | −12% (protocol walk), −42% (walk without the ceiling lap) | photo 8% |

Every cell comes from one of those two outputs. `not taped` means the ground truth that would score
it does not exist, and `no repeat capture` means that tier was captured once.

## What limits each tier

**LiDAR.** Depth is 256x192 over the full field of view, so a wall at 3 m is sampled every
2.3 cm. Range is honest to about 5 m and degrades past that; ARKit's own confidence channel
is used to weight rather than to threshold. Absolute scale comes from the sensor and needs
no recovery.

**Video.** No depth and no poses. Both are estimated, so scale is the binding constraint,
not geometry. Errors are dominated by scale drift over the length of the walk rather than
by any single measurement.

**Photo.** No depth, no poses, and no continuity between frames. Scale must be recovered
per room from the room itself. Intervals widen accordingly. On the benchmark flat it does not yet deliver usable size: the hall
shot on the 1× lens comes out 136% too large, and the whole flat on 0.5× 220% too large.
