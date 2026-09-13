# Verified runs

Regenerate with the commands at the end of `benchmark_report.md`. Room names per capture are in
`capture/room_map.json`, taken from camera frames rather than from area.

| Folder | Capture | Tier | Rooms | Footprint | Ceilings, by room id | Openings | Against tape |
|---|---|---|---|---|---|---|---|
| `multiroom_long` | `163f18d3ac`, home, protocol followed | LiDAR | 5 | 25.27 m² | 2.601 / 2.635 / 2.561 / unmeasured / 2.683 m | 7 | 28.75 m², −12% |
| `multiroom_home` | `ae3edc814d`, home, ceiling lap skipped | LiDAR | 3 | 16.57 m² | 2.632 / 2.609 / 2.409 m | 5 | 28.75 m², −42% |
| `single_room` | `c00a170fe1`, assignment zip | LiDAR | 1 | 17.87 m² | unmeasured | 1 | not taped |
| `multiroom_photos` | home, 58 stills | photo | 3 | 92.00 m² | — | 0 | 28.75 m², +220% |
| `one_room/` | one room at three tiers | all | see `one_room/RESULTS.md` | | | | |
| `gates/` | the scored gate table for the folders above | | | | | | |

The long walk's fourth room is a window bay whose only upward surface is a ledge 0.52 m above the
floor. It reported a 1.860 m ceiling, and then 3.04 m once surfaces under 2.20 m were excluded,
both read where a fitted plane crosses the world origin. Read over its own floor it has no ceiling
to measure, and its plan says so.
