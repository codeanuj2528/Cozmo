# Cozmo — technical report

Handheld iPhone capture to a dimensioned floor plan, damage map and repair scope, at three
input tiers. Six pages, as specified; the page cap is why this omits things that went well
and spends its space on the decisions and the numbers.

---

## 1. Architecture

One sentence governs the whole design: **a tier's job is to produce frames carrying
intrinsics, metric depth and a pose. Everything after that is the same code.**

```
Stray Scanner ─┐
               ├─ Frame{K, depth, pose} ─→ fuse ─→ gravity ─→ walls ─→ cell complex
walkthrough ───┤                                      ↓          ↓          ↓
               │                                    levels    openings   rooms
per-room stills┘                                                    ↓
                                            damage → concealed rules → scope → plan.json
```

LiDAR is handed all three fields. Photo and video manufacture them — monocular depth,
gravity from the floor plane, scale from camera height, pose from registration — and then
call the identical `build_lidar_plan`. Three parallel reconstruction stacks would drift
apart and only one would stay correct, and the tier comparison would then be measuring
implementation differences rather than sensor differences.

**The floor plan is a cell complex, not a raster.** The wall lines partition the floor; each
face is labelled interior or exterior from direct evidence (observed floor, carved free
space, camera track). A flood fill was tried first and leaked through a glass balcony door,
reporting 195 m² for a 44 m² flat. A face of an arrangement is bounded by lines on all sides,
so a labelling mistake cannot propagate, and corners arrive as exact line intersections
rather than staircases of pixels — which is what lets a room polygon inherit the
millimetre-level offset uncertainty of the plane fits beneath it.

**Walls come from a Hough accumulator over (normal azimuth, signed offset)**, each point
voting once into the bin its own measured normal selects. Sharper than a classical line
Hough, where every point smears a sinusoid across a cluttered accumulator. Peaks are accepted
on observed surface area, not on a fraction of total vote weight: a forty-wall apartment
divides its weight forty ways, so the strongest genuine peak carries 0.28% of the total and
any fraction-of-total threshold admits everything or nothing.

Two wall representations are maintained deliberately. Tight segments, which stop at every
gap, answer "is there material along this boundary" for the cell complex. Bridged runs answer
"where are the holes" for opening detection. No single gap tolerance is both narrower than a
doorway and wider than one, so trying to serve both from one representation means every
doorway splits its wall and no segment then spans the door to notice it.

---

## 2. Tiers and the device matrix

| Device | Photo | Video | LiDAR |
|---|---|---|---|
| iPhone 15/16/17 Pro, Pro Max | yes | yes | yes |
| iPhone 15/16/17 non-Pro | yes | yes | no sensor |
| iPhone 14 and older | out of contract | out of contract | out of contract |

**LiDAR.** Stray Scanner export: ARKit poses, 256×192 depth in millimetres, per-frame
intrinsics, ARKit's own confidence channel. Depth is weighted by inverse variance from a
noise model of confidence class and range, never thresholded, so a low-confidence return
still contributes in proportion to what it is worth. Absolute scale comes from the sensor.

**Video.** No depth, no poses; both estimated. It keeps the one thing the photo tier lacks —
continuity — so frames register sequentially into one property-wide cloud and drift
correction applies. Keyframes are sampled at uniform stride *first* and blur-filtered second,
so coverage is not biased toward the rooms the operator moved slowly through.

**Photo.** No depth, no poses, no continuity. Per room: metric depth per image, gravity from
the floor plane, scale from camera height, then registration in the three degrees of freedom
that survive levelling — yaw from wall-normal histograms, translation by occupancy
cross-correlation, then ICP. That order matters: ICP has a small basin of convergence and
fails from the identity, and two photographs from opposite corners of a room often share
almost no texture but always share the room's shape.

Measured accuracy is not tabulated here because the laser ground truth for the benchmark
property has not been recorded. `capture/DEVICE_MATRIX.md` carries those cells marked
`pending`, filled by `cozmo benchmark` and never by hand.

---

## 3. Drift

The brief makes "poses used as-is" an automatic fail, and it is right to. ARKit's odometry is
locally excellent and globally not: over a 96.6 m walk the loop does not close, the corridor
comes out long, and the last room lands centimetres from the first.

Correction is a pose graph over keyframes: odometry edges at the reported relative pose,
loop-closure edges at the pose ICP measured. **Loop candidates are proposed by geometry and
confirmed by ICP, never the reverse.** A candidate must be a genuine revisit — path walked at
least 6× the distance closed, and at least 6 m. Without that test a slow walk down a corridor
generates a constraint between every pair of keyframes in it, all merely restating odometry
with ICP noise added; that mistake produced 114 "closures" and made the map worse. With it,
41 survive on the sample apartment and 110 on the author's flat.

Rotation and translation residuals are weighted by separate information terms. A pose graph
that adds radians to metres is weighting one arbitrarily against the other, and over 100 m a
milliradian of yaw costs more than a centimetre of translation. A soft-L1 loss keeps one
false closure that survived verification from folding the map; some always survive, because
two bathrooms in the same flat look alike to a geometric matcher.

Drift alone does not remove residual yaw, so walls within 6° of the building frame are
rotated onto it and their offsets refit from their own points — the plane-anchored half.
Only the direction comes from the prior; the position stays measured.

**Ablation, `163f18d3ac`, 96.6 m walk, six segmented spaces.** All four rows regenerate
from the CLI; the `snap off` rows need `--no-snap-walls`, which exists for this reason:

| variant | rooms | footprint | Manhattan compliance | room-frame dispersion |
|---|---|---|---|---|
| drift off, snap off | 6 | 21.16 m² | 0.527 | 0.95° |
| drift off, snap on | 5 | 18.57 m² | 0.831 | 0.00° |
| drift on, snap off | 6 | 27.97 m² | 0.575 | 4.91° |
| **drift on, snap on** | **6** | **27.20 m²** | **0.721** | **0.00°** |

Manhattan compliance is the fraction of wall length within 2° of the dominant building frame;
room-frame dispersion is the spread of per-room frames, which is where yaw drift shows up and
nowhere else. Both are unsupervised — they adjudicate between pipeline versions on a capture
nobody has measured, and they do not replace the tape.

---

## 4. Error budget

**LiDAR tier**, in order of size:

| term | magnitude | handling |
|---|---|---|
| Residual gravity tilt | 0.46° on one sample → 4 cm over a 5 m room | Gravity refit to the observed floor before anything else runs |
| Yaw drift across rooms | 4.91° dispersion uncorrected | Pose graph + frame snapping → 0.00° |
| Depth noise | 8 mm base, +2.5 mm/m² range term | Inverse-variance weighting; plane σ from the larger of model and residual scatter |
| Plane offset | 0.1–0.4 mm on well-observed walls | Propagated into wall length as √2 × σ per corner |
| Voxel quantisation | 20 mm pitch | Positions averaged within voxel, not snapped |

**Photo tier** is dominated by one term that swamps the rest:

| term | magnitude |
|---|---|
| **Monocular depth scale** | **1.57–1.76× over-prediction, measured two ways** |
| Per-frame scale variation | 0.71–1.48 across frames |
| Depth AbsRel vs LiDAR | 0.28 mean |
| Registration | camera separations 0.07–2.52 m, ICP fitness 0.70–0.80 — not a dominant term |

The scale term is not a tuning problem. Depth Anything V2 Metric Indoor is trained on
normal-field-of-view indoor imagery; the benchmark photographs are 0.5x ultra-wide at 88°.
A metric monocular model infers depth from apparent size, which requires an assumed focal
length, so an out-of-distribution field of view shifts its metric scale proportionally.

---

## 5. Calibration

Intervals are split conformal, fitted per (tier, quantity), with the finite-sample correction
— the quantile at ⌈(n+1)(1−α)⌉/n, which is what makes the coverage guarantee hold at small n
rather than only asymptotically. Distribution-free, because a wall-length error is a mixture
of plane-fit noise, a small scale bias and the occasional gross failure, and no single normal
describes that.

Quantities calibrate in the units their error actually scales with: ceiling height in metres,
because it is equally hard to measure in a small room or a large one; wall length in percent,
because the error grows with the wall.

Where no quantile has been fitted, the interval falls back to the propagated covariance of
the fit that produced it, and `Measure.method` says `propagated` or `prior` rather than
`conformal`. **That field is load-bearing.** A previous version of `cozmo calibrate` ignored
both of its arguments and wrote a fixed table of quantiles labelled as conformal calibration;
those flowed into every measurement in every plan and made the one field a reader uses to
tell a calibrated interval from a guess into a falsehood. It now fits from residuals or
writes nothing and says why.

No quantiles are fitted at present, because fitting them needs laser ground truth and none
has been recorded. Every interval in every current plan reports `propagated` or `prior`,
truthfully.

---

## 6. The fix loop

Full account in `fixloop/`. In brief, because the honest version is the interesting one.

**Declared, before the fix:** the photo-tier footprint at 142.03 m² against a LiDAR reference
of 27.20 m², +422%. Root cause: `intrinsics_from_exif` read only `Image.getexif()`, which
returns IFD0 and holds no focal length on an iPhone JPEG; the value is in the sub-IFD at
`0x8769`. All 58 photographs carry `FocalLengthIn35mmFilm = 14`; none was read; every frame
ran at the assumed 26 mm prior. fx 4125.3 against a correct 2221.3, 1.86× too long.
**Predicted: under +50%, and explicitly not a pass.**

**Result: +916%.** The fix was correct and the number doubled.

The reasoning error: too long a focal length compresses the cloud laterally, which is true,
but the room was already too large, so the compression had been partially cancelling a bigger
error in depth. `X = (u − cx)Z/fx`, so halving fx doubles X; the area rose 1.95×, which is
that almost exactly.

The dominant cause is §4's scale term. Three further changes followed: the scale-correction
band widened from [0.75, 1.35] to [0.25, 4.0] — the old band was set while the intrinsics
were wrong and was rejecting every correct correction, the prior asking for 0.57 and being
refused; room-level scale consensus, since the prior fires on 3 photographs in 20 and scale
belongs to the camera rather than to one photograph; and a plausibility guard, because a
113 m² bedroom is not a wide estimate, it is a wrong one, and a large interval does not
rescue it.

**142.03 → 276.34 → 17.37 m² against 27.20: +422% to −36%.** The ±8% gate does not pass, and
coverage fell from three wrong rooms to one plausible one. By the brief's own rubric that
earns marks for the post-mortem and none for the prediction, which is correct.

**Round 2, LiDAR, against the operator's tape.** Declared before the fix (`88af4e3`): footprint
−12% on the long walk and −42% on the first walk, every room short, the bedroom 5.28 m² against
9.29 m². Hypothesis: the strip between furniture and the wall behind it has no floor evidence, so
faces there are labelled exterior and rooms end at the wardrobe front; ceiling returns above the
strip should count as interior evidence. Predicted: a bedroom of 8.0–9.5 m² and a footprint inside
±5%. **Result: every room polygon identical, on both captures.** The "real walls" 0.23–0.27 m
beyond the bedroom were the far faces of 230 mm brick partitions, and the ceiling measurement
behind the prediction had bled into the neighbouring rooms through a morphological closing.
Diagnosing the non-result found a worse defect: the room map had been assigned by matching areas
and was wrong on both captures, scoring the long walk's bathroom as the passage and the first
walk's bedroom as the hall. Rooms are now named from camera frames. No gate moved.

---

## 7. Known failure modes

Ten are documented with measurements in `known_failure_modes.md`. The four that matter:

**The photo tier does not meet its gates.** §4 and §6 above. What would fix it, in order:
capture at 1x rather than 0.5x — free, and the protocol now says so; fit the focal-to-scale
correction against the LiDAR tier, which supplies depth ground truth on the same property for
nothing; require two floor-visible photographs per room.

**Opening detection cannot work at the photo tier, structurally.** Openings are found by
looking for points behind a wall plane that a camera on the near side saw through. A single
photograph's depth map is a 2.5D surface with nothing behind it, ever. Zero openings means no
doorways to match, which means no stitch. This needs a different detector, not a threshold.

**Mirrors, glass and wet-look surfaces** get two defences. A geometric mirror test reflects
suspect points back across the wall plane and asks whether they land on the room in front of
it — a reflection does, a courtyard does not; the sample flat's bathroom walls score
0.21–0.34. And damage requires corroboration from two viewpoints, because a specular
highlight is view-dependent and never reprojects to the same patch of surface twice: on the
author's marble-and-glass flat that took damage from 21 regions to 1, in a property with
none.

**Ceiling height is unmeasurable without the upward lap.** No downward-facing returns, no
height, by any method. The pipeline reports `unmeasured` rather than substituting a default.
The company's own `single_room` sample has 61 downward-facing points in the entire scan; the
author's first capture had 1.4% of frames aimed up and the second had 24.3%, and the long walk now
measures 2.56–2.68 m per room; a window bay that once reported a 1.86 m ceiling, measured
from its ledge, now abstains. Reading room levels where each fitted plane crosses the world origin
had put that bay at 3.04 m and moved a passage ceiling by 15 cm. Reading the property-wide levels
over the floor instead moves the long walk's footprint by 0.76 m², a sensitivity recorded in the
failure modes rather than shipped.

---

## 8. State of the evidence

The LiDAR tier is the one to run at a walk-in. On the home flat walked with the ceiling lap and a
closed loop (`163f18d3ac`) it returns 5 rooms and 25.27 m² against a taped 28.75 m² (−12%), with
per-room ceilings of 2.56–2.68 m, 7 openings and 3 of 4 taped connections. The hall matches the
tape to its own precision, 15.8 × 9.6 ft against 16 × 10 ft. The bedroom does not: 5.28 m²
against 9.29 m², and a second walk of the same room gives 7.03 m², so the defect is in the
reconstruction, not in the tape.

Against the tape the gates read 13 PASS, 19 FAIL, 34 SKIP. Ceiling and opening gates are SKIP
because neither was taped. LiDAR intervals cover the tape on none of 31 measurements: they model
sensor and drift error, not a merged or a short room. The photo tier fails at +220% and the video
tier does not produce a metric plan. Walked alone, the bedroom reads 7.81 m² against 9.29 m²;
photographed on the 1× lens, the hall reads 35.12 m² against 14.86 m², down from a rejected 71.8 m²
at 0.5×. The assignment's two scans of one flat, which has no tape, give 35.74 m² over 7 rooms
and 31.57 m² over 6.

An earlier generator in this repository produced a benchmark over procedurally generated rooms, a
head-to-head against an app that was never run, and a fix loop whose before and after were
byte-identical. Those artefacts were removed before submission; every number in this report comes
from `reports/verified/`.

Some ideas here came from public work on the same brief: a ray-traced test room, a one-command setup script, a relative floor on photo and video intervals, and stitching rooms by folder name when no doorway is matched.
