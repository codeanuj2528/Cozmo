# Verified LiDAR runs

Commands and numbers from 13 Sep 2026. Re-run to regenerate.

```bash
.venv/bin/python -m cozmo.cli run -i ../data/raw/c00a170fe1 -o reports/verified/single_room
.venv/bin/python -m cozmo.cli run -i ../DROP_CAPTURES_HERE/01_multiroom_lidar/ae3edc814d -o reports/verified/multiroom_home
.venv/bin/python -m cozmo.cli run -i ../data/raw/163f18d3ac -o reports/verified/multiroom_long
```

| capture | source | rooms | footprint | ceilings | declared adj. gaps | openings | runtime |
|---|---|---|---|---|---|---|---|
| `c00a170fe1` | assignment `single_room.zip` | 1 | 17.36 m² | unmeasured (no upward lap) | n/a | 1 | 22 s |
| `ae3edc814d` | `01_multiroom_lidar` | 3 | 16.69 m² | 2.627 / 2.619 / 2.425 m | all 0.000 m | 5 | 54 s |
| `163f18d3ac` | `data/raw` long walk | 5 | 25.25 m² | 2.595 / 2.628 / 2.564 / 1.86 / 2.536 m | all 0.000 m | 7 | 82 s |

The 1.86 m reading is a soffit, not a finished ceiling. No interval on these plans has a negative lower bound.

Still unmeasured: laser/tape ground truth, so accuracy gates remain SKIP. Photo and video tiers are not in this table; video sampling is honest now but the monocular scale path is still the thin-input path.