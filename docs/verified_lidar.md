# Verified LiDAR runs

Commands and numbers from 13 Sep 2026. Re-run to regenerate.

```bash
.venv/bin/python -m cozmo.cli run -i ../data/raw/c00a170fe1 -o reports/verified/single_room
.venv/bin/python -m cozmo.cli run -i ../DROP_CAPTURES_HERE/01_multiroom_lidar/ae3edc814d -o reports/verified/multiroom_home
.venv/bin/python -m cozmo.cli run -i ../data/raw/163f18d3ac -o reports/verified/multiroom_long
```

| capture | source | rooms | footprint | ceilings | openings | runtime |
|---|---|---|---|---|---|---|
| `c00a170fe1` | assignment `single_room.zip` | 1 | 17.36 m² | unmeasured (no upward lap) | 1 | 22 s |
| `ae3edc814d` | `01_multiroom_lidar` | 3 | 16.69 m² | 2.627 / 2.619 / 2.425 m | 5 | 54 s |
| `163f18d3ac` | `data/raw` long walk | 5 | 25.25 m² | 2.595 / 2.628 / 2.564 / 1.86 / 2.536 m | 7 | 82 s |

Adjacency on the multi-room plans is **closed after translation**, not observed at zero.
`ae3edc814d` closed a **0.398 m** gap; `163f18d3ac` closed **0.143 / 0.556 / 0.609 m**.
The plan then reports those rooms as touching. That is disclosed in `quality.warnings`.

The 1.86 m reading is a soffit, not a finished ceiling. **Verified** plans have no negative
interval `lo`. Older `reports/eval_*` plans do (and `c00a170fe1` there is still 2 rooms with
`ceiling_height = 0.0`). Do not submit `eval_*` as current.

## Tape on the home flat (same four rooms)

Operator-stated feet, `tool=tape`, in `capture/ground_truth.csv`.
1 ft = 0.3048 m. Hall 16×10, passage 2.5×11, bedroom 10×10, bathroom 22 sq ft
only. Adjacency: hall–passage, passage–bedroom, hall–bathroom, passage–bathroom.

| | Tape | `ae3edc814d` | `163f18d3ac` |
|---|---|---|---|
| Hall | 14.86 m² | 7.15 m² (`room_01`) | 13.18 m² (`room_01`) |
| Passage | 2.55 m² | 3.50 m² (`room_03`) | 2.62 m² (`room_03`) |
| Bedroom | 9.29 m² | 6.04 m² (`room_02`) | 5.27 m² (`room_02`) |
| Bathroom | 2.04 m² | missing | 1.99 m² (`room_05`) |
| Footprint | 28.75 m² | 16.69 m² **−42% FAIL** | 25.25 m² **−12% FAIL** |

`c00a170fe1` has no tape (different property). Ceiling and door tape still
absent — those gates stay SKIP. Photo and video tiers are not in this table;
video sampling is honest now but the monocular scale path is still the thin-input path.