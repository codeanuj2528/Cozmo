# Verified runs

Regenerate with the commands at the end of `benchmark_report.md`. Room names per capture are in
`capture/room_map.json`, taken from camera frames rather than from area.

| Folder | Capture | Tier | Rooms | Footprint | Ceilings, by room id | Openings | Against tape |
|---|---|---|---|---|---|---|---|
| `multiroom_long` | `163f18d3ac`, home, protocol followed | LiDAR | 5 | 25.27 m² | 2.601 / 2.635 / 2.561 / unmeasured / 2.683 m | 7 | 28.75 m², −12% |
| `multiroom_home` | `ae3edc814d`, home, ceiling lap skipped | LiDAR | 3 | 16.57 m² | 2.632 / 2.609 / 2.409 m | 5 | 28.75 m², −42% |
| `single_room` | `c00a170fe1`, assignment zip | LiDAR | 1 | 17.87 m² | unmeasured | 1 | not taped |
| `bedroom_solo` | `5621ec5c54`, the bedroom alone | LiDAR | 2 | 11.51 m² | 2.606 m / unmeasured | 0 | bedroom 7.81 m² against 9.29 m², −16% |
| `photos_1x` | the hall, 12 stills at 1× | photo | 1 | 35.12 m² | 2.743 m | 1 | 14.86 m², +136% |
| `single_scan_floor_only` | `1a8384c3f6`, assignment zip | LiDAR | 7 | 35.74 m² | all unmeasured | 5 | not taped |
| `single_scan_with_ceiling` | `c7d28f72c6`, assignment zip | LiDAR | 6 | 31.57 m² | 2.980 / 2.845 / 2.879 / unmeasured / unmeasured / 2.855 m | 6 | not taped |
| `multiroom_photos` | home, 58 stills | photo | 3 | 92.00 m² | — | 0 | 28.75 m², +220% |
| `one_room/` | one room at three tiers | all | see `one_room/RESULTS.md` | | | | |
| `gates/` | the scored gate table for the folders above | | | | | | |

The long walk's fourth room is a window bay whose only upward surface is a ledge 0.52 m above the
floor. It reported a 1.860 m ceiling, and then 3.04 m once surfaces under 2.20 m were excluded,
both read where a fitted plane crosses the world origin. Read over its own floor it has no ceiling
to measure, and its plan says so.
