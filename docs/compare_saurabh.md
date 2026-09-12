# Us vs Saurabh (`sasaurabh11/cozmo`)

Same brief. His repo is public: https://github.com/sasaurabh11/cozmo
His own numbers below are taken from the `plan.json` files he committed under `benchmark_runs/`. Ours are from `reports/verified/` on 13 Sep 2026.

He is more honest in the write-up and more complete in the packaging. We are stronger on the thing the brief actually calls the product: a **stitched multi-room LiDAR plan**.

---

## Same-capture LiDAR (assignment zips)

These three zips came with the assignment. Both of us ran them.

| Capture | Ours | Saurabh | Who is closer to the brief |
|---|---|---|---|
| `c00a170fe1` / `single_room` / his `apartment_lidar` | **1 room, 17.36 m²**, ceiling **unmeasured** | **1 room, 17.82 m²**, ceiling **2.44 m prior** (not measured) | Tie on footprint (~3% apart). We win honesty: we do not invent 2.44 m |
| `1a8384c3f6` / `scan_floor_only` | 7 rooms, 35.90 m² (older run) | **1 room, 51.33 m²**, ceiling 2.44 prior | He collapses a whole flat into one polygon. The brief wants rooms + adjacency. We over-segment; he under-segments |
| `c7d28f72c6` / `scan_with_ceiling` | 6 rooms, 30.18 m² | **1 room, 39.01 m²**, ceiling **3.07 m measured** | He actually measured a ceiling (40% of points above camera). We split rooms. His 3.07 m is the better ceiling story; his one-room plan fails the multi-room contract |

His own report says this out loud: *"the LiDAR tier emits exactly one room per capture"*. That is an automatic miss on the stitched-plan row. We do not have that miss: `ae3edc814d` is 3 rooms, all declared adjacencies at gap 0; `163f18d3ac` is 5 rooms, all four adjacencies at gap 0.

---

## Where he is ahead (steal the idea, do not copy the repo)

| Item | Him | Us | What to do |
|---|---|---|---|
| Photo stitch | 3 rooms, 2 adjacencies, no overlaps (`saurabh_room_photo`, 34.20 m², interval **±60%**) | 2 of 4 rooms, 0 adjacency, 53.03 m² | Port the *idea*: per-folder reconstruct + doorway/name stitch, and **widen intervals to ±60%** instead of looking confident |
| Video | 3 rooms / 2 adj from a 37 s clip, ±60% | Was 526 m² / 2 rooms; sampling is now honest but scale is still thin | Same: segment the walk, publish wide intervals, do not pretend metric |
| Install in 15 min | `scripts/setup.sh` + synthetic smoke test | uv + fetch_weights, no one-shot setup | Add a setup script and a ray-traced fixture with known 3.60×2.80×2.50 |
| Fix loop packaging | Declaration commit → fix commit → `fixloop/before` + `after` on 11 captures, predicted 35 cm got **34.5 cm** | We have a photo-footprint loop; ceiling honesty is a better gate and is already shipped | Re-declare on a gate we can regenerate (ceiling unmeasured, or adjacency gap) with before/after folders |
| Intervals on thin input | Photo/video **±60%**, named degradations | Photo still looks narrower than the depth error | Widen photo/video intervals so they cannot score as confident garbage |
| Honesty in the report | 26 PASS / 23 FAIL / 45 SKIP, SKIPs explained | We got there after quarantine | Keep this. Do not re-fill `ground_truth.csv` |

His 0.1 cm wall error is on a **ray-traced box**, not a real room. That is a valid unit test, not a benchmark win. We should have the same fixture. It does not beat a laser on a real flat.

---

## Where we are ahead (do not throw this away)

| Item | Us | Him |
|---|---|---|
| Multi-room LiDAR (the product surface) | 3 and 5 rooms, adjacencies geometrically closed | 1 room per capture, always |
| Unmeasured ceiling | `null`, renderer says "unmeasured" | 2.44 m prior on every photo/video and on floor-only LiDAR |
| Negative intervals | Clamped; 0 on the verified runs | ci_95 can still look like a measurement of a prior |
| Drift ablation on a long walk | 18.57 → 27.20 m² on `163f18d3ac`, four-way table regenerable from CLI | Ablation field exists; LiDAR still one polygon |
| Same sample zip, single room | 17.36 m², 1 room | 17.82 m², 1 room — essentially the same number |

---

## Shared holes (neither of us has shipped these)

Both submissions are missing the same scored rows:

1. **Laser / tape ground truth on a real property** — 15% accuracy row is SKIP for both
2. **Head-to-head vs Polycam/Magicplan** — 10%, both at zero
3. **Staged damage, two classes, taped** — both not met
4. **Same rooms at all three tiers with a connector, scored** — both partial
5. **iPhone 15 walk-in ready at photo and video** — his photo stitch is more complete; our video is safer (will not emit 500 m²) but not walk-in-ready

---

## What I need from you (inputs only)

Not code. These are things only you can produce.

1. **Laser sheet** = a laser measurer or a tape, and the printed `capture/RECORDING_SHEET.md`. For each room in your flat: 3× ceiling height, every wall, every door/window width, which room connects through which door. Type the numbers into `capture/ground_truth.csv`. Without this, neither you nor Saurabh can claim the 15% accuracy row.
2. **Polycam or Magicplan export** of two of those rooms (free tier), plus the app version written down. 10% of the score.
3. **One room walked a second time** in Stray Scanner, saved to `07_repeat_room_lidar/`.
4. **Optional but scored:** one furnished room with two staged damages (e.g. a paper “water stain” and a taped “crack”), captured at all three tiers, damages taped.

Photo and video from your house are already in `DROP_CAPTURES_HERE/02_*` and `03_*`. I will run those next; they are not a substitute for (1)–(3).
