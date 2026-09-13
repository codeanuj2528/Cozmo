# Known failure modes

Every entry here was observed on real data, not imagined. Where a number appears, it was
measured on the benchmark captures and can be reproduced with the command given.

## 1. The photo tier does not meet its accuracy gates

**Status: fails, and is reported as failing.**

On the benchmark property the photo tier reports one room of four at a footprint 36% below
the LiDAR reconstruction. It does not reach the ±8% gate.

The cause is measured, not guessed. Depth Anything V2 Metric Indoor over-predicts depth on
these photographs by a factor established two independent ways:

| method | factor |
|---|---|
| Camera height implied by the detected floor, against a true ~1.45 m | 1.76 |
| Median ratio of LiDAR depth to predicted depth, 8 frames, same property | 1.57 |

The photographs are 0.5x ultra-wide (14 mm equivalent, 88° horizontal). The model is trained
on normal-field-of-view indoor imagery. A metric monocular model infers depth from apparent
size, which needs an assumed focal length, so an out-of-distribution field of view shifts its
metric scale proportionally.

**What we do about it.** A plausibility guard drops any reconstruction outside 1–60 m² or
1.8–4.2 m of ceiling and records why, so the tier reports fewer rooms rather than absurd
ones. The capture protocol now specifies the 1x lens.

**What would fix it** is in `fixloop/POSTMORTEM.md`: capture at 1x, and fit the
focal-to-scale correction against the LiDAR tier, which supplies depth ground truth on the
same property for free.

## 2. Opening detection cannot work at the photo tier

**Status: structural, not a tuning problem.**

Openings are found by looking for points *behind* a wall plane that a camera on the near side
saw through. A single photograph's depth map is a 2.5D surface: there is nothing behind it,
ever. The photo tier therefore detects zero openings, and because rooms are stitched by
matching doorways, it also produces zero adjacency and cannot stitch.

The LiDAR tier finds 10 openings on the same flat.

Fixing this needs a different detector for the photo tier — appearance-based door detection,
or a learned layout estimator — not a threshold change.

## 3. Ceiling height is unmeasurable without the upward lap

If the operator never points the phone at the ceiling there are no downward-facing surface
returns and the height cannot be computed by any method. The company's own `single_room`
sample has 61 downward-facing points in the entire scan.

The pipeline reports `ceiling unmeasured` rather than substituting a default. On the first
capture of the benchmark property, 1.4% of frames were aimed up and the result was poor; on
the second, 24.3% were, and per-room heights came out at 1.86–2.63 m -- the 1.86 m being a
soffit read as a ceiling, not a room.

## 4. Mirrors, glass and wet-look surfaces

**Handled, with residual risk.**

A mirror returns depth at the reflected distance, so the surface reads as empty and the
reflection reads as structure behind the wall — indistinguishable from a window to a
see-through test. Two defences:

- **Geometric mirror test.** Suspect points are reflected back across the wall plane; if they
  land on the room actually in front of it, the opening is a reflection. The sample flat's
  bathroom walls score 0.21–0.34 on this test.
- **Multi-view damage requirement.** A specular highlight is view-dependent and never
  reprojects to the same patch of surface twice. Requiring two viewpoints took damage on the
  author's marble-and-glass flat from 21 regions to 1, in a property with no damage in it.

Residual risk: a large mirror facing a blank wall could still pass both tests. A floor-length
mirror is the worst case and is untested.

## 5. Drift correction can make a reconstruction worse

Loop closure on a wrongly matched pair folds the map. Guards: a candidate must be a genuine
revisit (path walked at least 6× the distance closed), ICP must reach 0.55 fitness and
0.035 m RMSE, and the pose graph uses a soft-L1 loss so one surviving false closure cannot
dominate.

The ablation is reported in the benchmark table for every capture. On `163f18d3ac` (96.6 m)
the four-way ablation is, all four rows regenerable from the CLI:

| variant | rooms | footprint | Manhattan compliance | room-frame dispersion |
|---|---|---|---|---|
| drift off, snap off | 6 | 21.16 m² | 0.527 | 0.95° |
| drift off, snap on | 5 | 18.57 m² | 0.831 | 0.00° |
| drift on, snap off | 6 | 27.97 m² | 0.575 | 4.91° |
| drift on, snap on | 6 | 27.20 m² | 0.721 | 0.00° |

These four rows are the **pre-merge** ablation (regenerable from CLI flags). After
split-room merge the same capture is **5 rooms / 25.25 m²** (`docs/verified_lidar.md`).
Do not quote 27.20 as the current plan.

## 6. A room the operator did not walk into is not reported

Room segmentation requires camera track inside a face to label it interior. This is
deliberate — it is what stops the reconstruction leaking through a glass balcony door and
reporting the courtyard as a room, which it did before the rule existed (195 m² for a 44 m²
flat). The cost is that a room seen only from its doorway is omitted.

## 7. Damage detection without model weights

With no weights present the classical detector runs: colour-anomaly for stains, black-hat
ridge with tiling-pattern rejection for cracks. It is genuinely discriminative on synthetic
walls (clean → nothing; stain → one stain, no crack; crack → one crack, no stain; tile grid →
nothing) but it has no open-vocabulary capability and will miss classes it was not written
for. The plan records which detector produced each finding.

## 8. Ultra-wide lens distortion is not modelled

Intrinsics are pinhole. At 0.5x the iPhone's residual barrel distortion after in-camera
correction is not zero, and nothing here compensates for it. Another reason the protocol now
specifies 1x.

## 9. Scale uncertainty does not reach the ceiling-height interval

`sigma_height` is composed from plane-fit terms only. That is correct for the LiDAR tier,
where scale is measured by the sensor, and wrong for the photo tier, where the dominant
uncertainty is scale. Photo-tier ceiling intervals are therefore narrower than they should
be. Identified but not fixed before the deadline.

## 10. Gates without ground truth are not evaluated

10 of 14 gates currently report `SKIP` because laser measurements have not been recorded for
the benchmark property. They are not reported as passing. This is the honest state of the
evidence and it costs those marks.
