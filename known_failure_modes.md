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
the second, 24.3% were, and per-room heights came out at 2.56–2.68 m, with the
window bay, whose only upward surface is a ledge, reporting none.

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
split-room merge the same capture is **5 rooms / 25.27 m²** (`docs/verified_lidar.md`).
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

The operator's tape covers walls, floor areas and adjacency on the home flat. It covers no
ceilings, doors or bathroom walls, so 14 of 33 gate rows report `SKIP`. None is reported as
passing.

## 11. Room identity has to come from what the camera saw

Room ids are assigned per reconstruction in order of area, so `room_03` means a different room in
each capture. The first room map named rooms by matching their areas to the taped areas, which is
circular when area is being scored, and it was wrong on both captures: the long walk's bathroom was
scored as the passage and the first walk's bedroom as the hall. Rooms are now named from frames
taken by the camera standing deepest inside each room (`capture/room_identity/`), and the map is
keyed by capture.

## 12. Bathroom and passage merge

On both home walks one reconstructed room holds the bathroom and part of the passage, with fill
ratios of 0.50 and 0.56. Neither room is then measured on its own: the long walk's bathroom reads
+29% and its passage −22%, and the hall–passage connection is missed because the hall appears to
open into the bathroom.

## 13. The same bedroom differs by 0.3–0.6 m between walks

The long walk reconstructs the bedroom at 2.58 × 2.08 m and the first walk at 2.89 × 2.68 m, against
a taped 10 × 10 ft. The planes just outside the long walk's bedroom are the far faces of 230 mm brick
partitions, not hidden walls, so the loss is not furniture standing in front of the walls. The
cause is not yet found. Ceiling height on the same room repeats to 4 mm.

## 14. LiDAR intervals do not cover the tape

0 of 16 and 0 of 15 measurements fall inside their intervals. The interval model includes sensor
noise, plane roughness and residual drift, and excludes segmentation error, which on this flat is
tens of centimetres. No quantiles were fitted to widen them: with two walks of one flat, the rows
used to fit would be the rows scored.

## 15. A tape in whole feet cannot adjudicate a 2 cm gate

The operator recorded 16 × 10 ft, 10 × 10 ft and 11 × 2.5 ft. A reading rounded to the foot carries
±15 cm, so the wall-length gate at 2 cm is unscorable against it in either direction. The benchmark
reports whether each room agrees with the tape to the tape's own precision beside the gate, without
using that to soften the gate.

## 16. Damage on a damage-free flat

The first walk reports one 0.08 m² water stain seen from two frames. The flat has no damage, so it
is a false positive. The long walk reports none.

## 17. Segmentation moves with the height band

The whole-property floor and ceiling bound the height bands for wall voting (to 6 cm below the
ceiling) and occupancy (to 12 cm below it). Reading those two levels over the centre of the floor
instead of at the world origin raises the long walk's property ceiling by 2.8 cm, well inside both
margins. It should change nothing. It changes the footprint from 25.27 to 24.51 m²; the bathroom
shrinks from 2.63 to 2.15 m² while the window bay grows from 2.19 to 2.35 m², so the two swap room
ids; and three water stains appear on a flat that has none. Turning off the ceiling evidence added
in fix loop round 2 leaves that result unchanged room for room, so the sensitivity lies in wall
voting and occupancy, not in that change.

The property levels are therefore still read at the origin, and the published plans are the ones
that reading produces. Neither version is closer to the tape overall: the bathroom improves from
+29% to +5% and the hall worsens from −11% to −15%. A segmentation that a 3 cm band edge can re-cut
is not stable enough to be judged by a tape recorded to the foot.

## 18. The 1× hall is nearly the right height and far too large

Twelve stills of the hall on the 1× lens reconstruct a 2.74 m ceiling, within 6% of LiDAR's 2.60 m,
over a 35.12 m² floor against 14.86 m² taped. A scale error would move both together. One photograph
of eight failed to register, and the hall has a glossy tiled floor that mirrors the windows and the
lights, the wet-look case in §4. Which of the two inflates the outline is not yet measured.

## 19. A room walked on its own keeps the passage it was entered from

The bedroom-only walk began and ended at the doorway, outside the room, so the plan holds a 3.70 m²
strip of passage beside the 7.81 m² bedroom, and the footprint row compares 11.51 m² with the
bedroom's 9.29 m². The protocol asks for both still periods just inside the doorway.

## 20. The assignment's flat, scanned twice, disagrees with itself

`single_scan_floor_only.zip` and `single_scan_with_ceiling.zip` cover the same space. They
reconstruct as 7 rooms and 35.74 m² and as 6 rooms and 31.57 m², 13% apart. Neither has tape, so
neither can be called right. Both plans also close the gaps between declared neighbours by moving
whole rooms, by up to 1.73 m, which says those rooms were not reconstructed touching in the first
place; `quality.warnings` in each plan lists every move.
