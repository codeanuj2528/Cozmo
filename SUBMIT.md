# What to submit, and what to show

13 Sep 2026. Every number here was read from a committed `plan.json`, `run_manifest.json` or
gate table.

## Lead the walk-in with LiDAR

| File | What it shows |
|---|---|
| `reports/verified/multiroom_long/plan.png` | The home flat, protocol followed. 5 rooms, 25.27 m² against a taped 28.75 m² (−12%). The hall reconstructs at 15.8 × 9.6 ft against a taped 16 × 10 ft. |
| `reports/verified/single_room/plan.png` | The assignment's `single_room.zip`. 1 room, 17.87 m², one opening, ceiling unmeasured because that capture has no upward lap. |
| `reports/verified/multiroom_home/plan.png` | The same flat on a first walk with the ceiling lap skipped. 3 rooms, 16.57 m² (−42%). Worth showing beside the long walk: it is why the protocol makes the ceiling lap mandatory. |

Examiner command after `scripts/setup.sh`:

```bash
.venv/bin/python -m cozmo.cli run -i <stray-folder> -o runs/demo
```

## Disclose; do not lead

| File | Result |
|---|---|
| `reports/verified/multiroom_photos/plan.png` | Photo tier, 58 stills on 0.5×. 3 rooms, 92.00 m² (+220%). FAIL. |
| `reports/verified/one_room/video/plan.png` | Video tier on the room LiDAR puts at 17.87 m²: 339.61 m². Scale failed. |
| `reports/verified/one_room/photo/plan.png` | Bathroom stills only: no room recovered. |
| DROP `02_multiroom_video` | Whole-flat video: one room of about 371 m². Not in the repository. |

## Accuracy against tape

Full detail in `benchmark_report.md`. Gates: **6 PASS, 13 FAIL, 14 SKIP**
(`reports/verified/gates/gate_table.txt`). Footprint, walls, interval coverage, adjacency and
repeatability fail, and the report says why for each.

**Room names come from the camera, not from area.** `capture/room_map.json` names each
reconstructed room from frames taken inside it, saved in `capture/room_identity/`. The previous
map was assigned by area and was wrong on both captures. Those frames show the inside of your
home: delete the folder if you would rather not publish it, and the map's `_evidence` block still
cites the frame numbers.

## Fix loop

| Round | Gate | Declared cause | Predicted | Result |
|---|---|---|---|---|
| 1, photo tier | footprint +422% against LiDAR, before tape existed | focal length read from the wrong EXIF IFD | under +50%, not a pass | +916%, then −36% after three more changes; FAIL |
| 2, LiDAR | footprint −12% and −42% against tape | furniture bounding rooms short of their walls | bedroom 8–9.5 m², footprint PASS | no change at all; hypothesis refuted; the diagnosis found the room-map defect |

Round 1: `fixloop/FIX_DECLARATION.md`, `fixloop/POSTMORTEM.md`, diff `git diff d15c21b..80c44f3`.
Round 2: `fixloop/round2/`, declaration `88af4e3` before fix `20cb44a`, with before and after runs,
manifests and gate tables. Index: `fixloop/README.md`. Neither round moved a gate to PASS, and both
post-mortems say why. The tag `fixloop-before` is off this history; do not check it out.

## The external audit

`docs/external_vision_audit_review.md` answers the "GOT-Vision" executive summary claim by claim.
Its "no focal-length EXIF", "640×360 video" and "ceiling ground truth 2.60 / 2.55 / 2.50 / 2.45 m"
findings come from its own script rather than from these captures. Its 2.20 m ceiling sanity bound was right. Adding it exposed that room ceilings were read where a
fitted plane crosses the world origin rather than over the room; both are fixed in `8aaf149`.

## Do not invent

- Ceiling heights, door widths, bathroom walls. The tape has none, so those gates stay SKIP. Do not
  copy the audit script's ceiling constants into `ground_truth.csv`.
- No consumer-app export exists, so the Part 3 head-to-head scores zero.
- DROP slots `04` to `06`, the staged-damage room, are empty.

## Only you can do these

1. Laser the ceiling in each room, three readings per room, into `capture/ground_truth.csv`.
2. Measure each door width, and the bathroom's walls.
3. Say which side the bathroom door opens onto. The tape lists both hall–bathroom and
   passage–bathroom for one door at the junction; the external audit assumes the passage only.
4. Tape the bedroom wall to wall in centimetres, and say whether 10 × 10 ft included the
   wardrobe. A tape in whole feet cannot adjudicate a 2 cm gate.
5. Magicplan or Polycam on two rooms, into `08_competitor_export/`, with the app version.
6. Photos at 1×, four to eight per room, with floor in frame.

## Do not put in the zip

- `quarantine/`, which holds fabricated artefacts kept only as an audit trail
- `reports/eval_*`, superseded runs
- the 3.6 GB video

## Pushing

The remote `codeanuj2528/Cozmo` has diverged from this history. Merge or rebase; do not force-push
unless you mean to overwrite it. Do not squash: the incremental history is scored.
