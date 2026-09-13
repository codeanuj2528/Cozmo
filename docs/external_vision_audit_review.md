# Review of the external "GOT-Vision" audit

An executive audit summary and `got_vision_audit_code.zip` (`got_vision_audit.py`,
`CLAUDE_CODE_PROMPT.md`) were supplied on 13 Sep 2026. Both were read. The script was **not
executed**: it is output from an outside tool, and every claim that mattered could be checked
with this repository's own code against the original captures.

The audit's conclusion — "topology credible, metric scale not audit-grade from images alone" —
is broadly right. Several of the specific findings behind it are wrong about this data, and
the reason is traceable to the script.

## Claim by claim

| # | Audit claim | Verdict | Evidence |
|---|---|---|---|
| 1 | "No usable focal-length or 35 mm EXIF" | **Wrong for these files** | `got_vision_audit.py:67` reads `im.getexif()`, which is IFD0 only. The focal length lives in the EXIF sub-IFD `0x8769`. On the 58 photos in `03_multiroom_photos`: via IFD0 `None` ×58; via the sub-IFD **14 mm ×54, 17 mm ×2, 21 mm ×2**. This is the same defect this pipeline had and fixed in fix loop round 1. |
| 2 | "Video is 640×360, 5 fps, 25.2 s" | **Not our capture** | The script reads `video/IMG_1582_walk.mp4` (line 190), a derivative. The capture is `IMG_1582.mp4`: **2160×3840, 119.9 fps, 276.4 s, 3.64 GB**. |
| 3 | "Ground-truth ceilings 2.60 / 2.55 / 2.50 / 2.45 m" | **Not ground truth** | Hardcoded at `got_vision_audit.py:34-39` and repeated as "ground truth" in the prompt. The operator's tape (`capture/ground_truth.csv`) has **no ceiling rows**. They are not added; the ceiling gate stays `SKIP`. |
| 4 | "Adjacency: PASS, no missing edge" | **Not a detection** | Lines 229-234 compare the ground-truth graph with a hardcoded copy of it, and record `visual_detection_status: REQUIRES_VISION_STAGE`. Measured by this pipeline against the tape: long walk **3/4** (missed hall–passage, one edge to the untaped window bay), home walk **2/4**, photo tier **1/4**. |
| 5 | Per-room "visual estimated area", all PASS | **Not a measurement** | Ranges such as "hall ~14-16 m²" are not produced by the script, which refuses to estimate area (its own docstring, line 16). Measured here on the long walk, rooms named from camera frames: hall 13.18 m² (−11%), bedroom 5.28 m² (−43%), bathroom 2.63 m² (+29%, merged with the upper passage), passage 1.99 m² (−22%). |
| 6 | Monocular depth over-estimates on ultra-wide frames; the 0.60-0.65 ratio "cannot be verified" | **Right about the risk; verified here** | Unverifiable from images alone, as stated — but not from images alone here. Against LiDAR depth of the same flat, the median LiDAR/predicted ratio is **0.635** (1.57× over-prediction); the camera height implied by the detected floor gives **1.76×**. |
| 7 | Calibrate 0.5× and 1× separately | **Reasonable; untestable on this set** | EXIF `LensModel` puts all 58 photos on one lens, the 2.22 mm ultra-wide of an iPhone 17 Pro: 54 at the 14 mm equivalent, 4 digitally cropped to 17 or 21 mm. There is no 1× photo to calibrate against. The protocol now requires the 1× lens. Not implemented. |
| 8 | Undistort ultra-wide frames first | **Reasonable; not implemented** | iPhone stills carry in-camera lens correction and no distortion coefficients in EXIF. Recorded in `known_failure_modes.md` §8. |
| 9 | Needs metric anchors such as door widths | **Right** | Door widths are not taped, so the opening-width gate is `SKIP`. Requested from the operator. |
| 10 | A ceiling below 2.20 m is critical | **Right, and acted on** | The long walk published room_04, a window bay, with a **1.860 m** ceiling. Raising the bound to 2.20 m exposed a worse defect: the room then reported **3.04 m**, because room levels were read where each fitted plane crosses the world origin, 4.7 m away, from a patch tilted 15 degrees. Room levels are now read over the room's own floor; a ceiling must be more than 2.20 m up, strong against everything overhead, and cover 0.25 m². The bay, whose only upward surface is a window ledge 0.52 m above the floor, now reports its ceiling as unmeasured (`geometry/levels.py`, `tests/test_levels_sanity.py`). The same defect had moved the long walk's passage ceiling by 15 cm. |
| 11 | No visible damage in the flat | **Consistent** | The long walk reports no damage. The home walk reports one 0.08 m² water stain from two frames — a false positive on a property with none, disclosed rather than tuned away. |
| 12 | Three-edge graph, no hall–bathroom edge | **Conflicts with the operator's tape** | The tape lists hall–bathroom and passage–bathroom for one bathroom door "at the hall/passage junction". The tape is kept; the operator has been asked which side the door opens onto. |

## The prompt's requirements, against this repository

| Requirement | Status here |
|---|---|
| Never fabricate area; mark unverifiable rows | Met: gates without ground truth report `SKIP`; the photo tier drops physically implausible rooms. |
| Separate 0.5× and 1× calibration | Not met; see claim 7. |
| Undistort before geometry | Not met; see claim 8. |
| Metric scale as a separate stage | Met: `recon/monocular.py`. |
| Doorway edges with frame evidence, not copied from ground truth | LiDAR: edges come from the walked trajectory and detected openings. Photo: edges come from folder names and are scored as such. |
| Ceiling plane-to-plane, or `UNVERIFIED` | Met at LiDAR; unmeasured ceilings abstain. |
| Damage bbox, class, size, severity, confidence, source frame | Met: `DamageRegion` carries surface-local extent in metres and evidence frames. |
| Tests for scale, area error, graph, ceiling thresholds | Met, 66 tests. |
| JSON and CSV | JSON only. |
