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

Populated from the benchmark set against laser ground truth. Every figure is the 90th
percentile of absolute error over the benchmark captures, which is the quantity the
conformal intervals are fitted to; the median is roughly half of each.

| Quantity | Photo | Video | LiDAR | Gate |
|---|---|---|---|---|
| Wall length | pending | pending | pending | photo 8%, video 3%, LiDAR 2 cm |
| Ceiling height | pending | pending | pending | 1.5 cm per room |
| Ceiling height spread across repeats | pending | pending | pending | 1 cm |
| Opening width | pending | pending | pending | 2 cm on 85% of openings |
| Repeatability per wall | pending | pending | pending | 1 cm or 0.5% |
| Whole-property footprint | pending | pending | pending | photo 8% |

`pending` is filled by `cozmo bench` and is not filled by hand. A number in this table that
was not produced by a benchmark run is a claim, and the point of the table is that it
contains no claims.

## What limits each tier

**LiDAR.** Depth is 256x192 over the full field of view, so a wall at 3 m is sampled every
2.3 cm. Range is honest to about 5 m and degrades past that; ARKit's own confidence channel
is used to weight rather than to threshold. Absolute scale comes from the sensor and needs
no recovery.

**Video.** No depth and no poses. Both are estimated, so scale is the binding constraint,
not geometry. Errors are dominated by scale drift over the length of the walk rather than
by any single measurement.

**Photo.** No depth, no poses, and no continuity between frames. Scale must be recovered
per room from the room itself. Intervals widen accordingly, and the honest statement is
that the photo tier delivers a plan of correct shape and approximate size, not a
dimensioned survey.
