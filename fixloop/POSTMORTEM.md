# Fix loop: what happened

The declaration is in `FIX_DECLARATION.md`, committed before any of this. This is the
account of running it.

## The prediction was wrong, and wrong in the wrong direction

| | value |
|---|---|
| Predicted | footprint error falls from +422% to under +50% |
| First result after the fix | **+916%** (276.34 m² against a 27.20 m² reference) |

The fix was correct — `fx` went from an assumed 4125.3 to a measured 2221.3, provenance
`exif_sub_ifd_35mm_equivalent`, implied horizontal field of view 87.9°, which matches the
0.5x ultra-wide's ~88° — and the number got twice as bad.

## Why the direction was wrong

I reasoned that too long a focal length compresses the cloud laterally. That is right.
What I failed to carry through is what it means for a room that was **already too large**:
the compression was partially cancelling a different, larger error, and removing it exposed
the whole thing.

`X = (u - cx) Z / fx`. Halving `fx` doubles `X`. The observed area went up by 1.95×, which
is that, almost exactly. The wrong intrinsics had been masking an over-prediction in `Z`.

## What the real cause is

The metric depth model over-predicts depth on this property, and the amount is now measured
two independent ways that agree:

| method | result |
|---|---|
| Camera height implied by the detected floor, against a true ~1.45 m | 2.50–2.90 m, median 2.55 → **1.76×** |
| Median ratio of LiDAR depth to predicted depth on 8 frames of the same flat | 0.635 → **1.57×** |

Depth Anything V2 Metric Indoor is trained on normal-field-of-view indoor imagery. These
photographs are 0.5x ultra-wide at 88°, outside that distribution. A metric monocular model
infers depth from apparent size, which requires an assumed focal length; give it an image
whose field of view it was not trained on and its metric scale shifts proportionally.

## What was shipped

Four changes, all of them real improvements, none of them enough:

1. **EXIF sub-IFD read** (`recon/monocular.py`). The declared fix. Focal length is now
   measured rather than assumed, and the provenance says which.
2. **Scale-correction band widened** from [0.75, 1.35] to [0.25, 4.0]
   (`recon/monocular.py`). The old band was set while the intrinsics were wrong and was
   rejecting every correct correction: the prior was asking for 0.57 and being refused.
   Bounds now only exclude the physically absurd.
3. **Room-level scale consensus** (`pipeline/photo.py`). The camera-height prior fires on
   only 3 photographs in 20, because the operator was also asked to shoot the ceiling. Scale
   is a property of the camera and the model, not of one photograph, so the median of the
   photographs that did see a floor is applied to the whole room.
4. **Plausibility guard** (`pipeline/photo.py`). A reconstruction outside 1–60 m² or
   1.8–4.2 m of ceiling is not a wide estimate, it is a wrong one. Such rooms are now
   dropped with the reason recorded, rather than published with a large interval attached.

## Where the gate ended up

| stage | footprint | rooms | note |
|---|---|---|---|
| Before | 142.03 m² (+422%) | 3 | ceilings 4.46 / 4.07 / 1.92 m |
| After EXIF fix alone | 276.34 m² (+916%) | 3 | prediction was wrong, direction was wrong |
| After all four changes | **17.37 m² (−36%)** | 1 | two rooms rejected as implausible |

**The ±8% gate does not pass.** Coverage is also down: the tier now reports one room of four
rather than three wrong ones. That is the correct trade — the brief says confident garbage
on thin input caps the total score — but it is not a pass and it is not being written up as
one.

One part of the declaration did hold: openings stayed at zero, for the stated reason.
Opening detection looks for points behind a wall plane, and a single photograph's depth map
is a 2.5D surface with nothing behind it. Correct intrinsics could not change that, and the
photo-tier stitch remains unsolved.

## What would actually fix it

In the order I would do them.

1. **Capture on the 1x main lens, not 0.5x.** The model is in distribution at ~24 mm
   equivalent and out of it at 14 mm. This costs nothing and is the single highest-value
   change; the capture protocol has been updated to specify the lens, which it previously
   did not. It could not be tested here because it needs a re-capture and the submission
   deadline is today.
2. **Fit the focal-to-scale correction explicitly.** A metric model's output scales with the
   ratio of assumed to actual focal length. Calibrating that ratio against the LiDAR tier —
   which gives depth ground truth on the same property, for free — turns an out-of-
   distribution failure into a one-parameter correction. The two measurements above already
   bracket it at 1.57–1.76×.
3. **Require more floor in the capture.** Scale fired on 3 photographs in 20. The protocol
   should ask for at least two floor-visible photographs per room, which is a one-line
   change to the instructions.

## Honest scoring of this section

Against the brief's own rubric: the root cause identified in the declaration was **real but
not the dominant one**, the shipped fix was correct and moved the number the wrong way
before other changes moved it back, and the gate **did not** move from fail to pass. The
prediction was badly wrong. By the brief's terms that earns marks for this post-mortem's
honesty and none for the prediction, and that is the correct outcome.
