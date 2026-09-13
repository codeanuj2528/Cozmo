# Verified LiDAR runs

Numbers and the per-room comparison against tape are in `benchmark_report.md`; the run table is
in `reports/verified/README.md`. This page keeps what those do not.

## Adjacency is closed after translation

On the multi-room plans, rooms declared adjacent are translated until they touch, rather than
observed touching. `quality.warnings` in each `plan.json` records the gap each closure removed.
The plan then reports those rooms as sharing a wall, and says it did so.

## Ceilings

A room's ceiling height is read plane to plane over the centre of that room's own floor. Three
rules decide whether there is a ceiling to read: it is more than 2.20 m above the floor, it is at
least 20% as strong as the strongest downward-facing surface overhead, and its returns cover at
least 0.25 m². A room that fails any of them reports its ceiling as unmeasured and says why in
`quality.warnings`. It never reports 0.0 m, and no interval has a negative lower bound.

On the long walk these rules turn room_04 from a 1.860 m ceiling into an unmeasured one. Its only
upward surface is a window ledge 0.52 m above the floor: it is a bay, not a room, though the
pipeline still counts its 2.19 m² in the footprint.

The whole-property floor and ceiling that bound wall voting and occupancy are still read at the
world origin. Reading them over the floor instead moves the long walk's property ceiling by 2.8 cm
and its footprint by 0.76 m²; see `known_failure_modes.md` §17.

## Older runs

`reports/eval_*` predate the split-room merge and the camera-frame room map. Do not quote them.
