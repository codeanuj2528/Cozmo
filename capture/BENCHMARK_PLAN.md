# Benchmark capture plan

The brief specifies the composition so it cannot be flattered. This is the shot list. Work
through it in order; the whole thing is one afternoon plus measuring.

## Captures required

| # | Capture | Tiers | Why the brief needs it |
|---|---|---|---|
| 1 | **Multi-room**: three or more rooms plus a connector (corridor, hallway or landing) | LiDAR, video, photo | Stitching, adjacency, drift accountability |
| 2 | **Furnished room with staged damage**, two damage classes present | LiDAR, video, photo | Damage regions, metric extent, scope items |
| 3 | **Repeat** of one room from capture 1, same tier, walked again from scratch | LiDAR (and video if time) | Repeatability gate |

Capture 2 can be one of the rooms in capture 1, captured separately. That is allowed and
saves an hour.

At the photo tier, capture 1 must arrive as **one folder per room**, because the gate is
that per-room photo folders still stitch into one property.

## Staging the damage

Two classes, both non-destructive and both disclosed in the report as staged:

- **Water stain.** Print a brown irregular stain on A3, or brew strong tea and stain a
  sheet of paper. Tape it flat to a wall or ceiling. Aim for 30-50 cm across.
- **Crack.** Run a 2-3 mm black tape or a length of dark thread across a wall in an
  irregular line, 60 cm or longer.

Optional third if convenient: **peeling paint**, a strip of masking tape lifted at one edge.

Photograph each staged item close up before you start, next to the tape measure, so the
report can show what was staged and how big it really was.

## What to measure with the laser

Fill `ground_truth.csv` as you go. Measuring after the fact from memory is how a benchmark
becomes fiction.

Per room:
- **Ceiling height.** Three readings at different points in the room, floor to ceiling.
  Record all three; their spread is the ground truth's own uncertainty.
- **Every wall, corner to corner**, at about 1.2 m height. Name the walls N/E/S/W or 1/2/3.
- **Room diagonal**, corner to opposite corner. This is the check on the wall readings: if
  the walls and the diagonal disagree, one of them is wrong and you want to know now.

Per opening:
- **Width** across the reveal at mid height.
- **Height** floor to head.
- **Sill height** floor to sill, zero for a door.

Per damage item:
- **Bounding width and height** of the affected area.

Property level:
- Note which rooms connect to which, through which door.

## Accuracy notes for the sheet

- A laser measurer reads to about 2 mm. Note the model in the sheet header.
- Measure to the finished surface, not to skirting board or trim. The pipeline reports the
  wall face.
- For ceiling height, measure to the finished ceiling, not to a light fitting.
- Where a room has a dropped or stepped ceiling, record each level separately and say so.

## After capturing

```bash
.venv/bin/python -m cozmo.cli run --input <folder> --out runs/apt_multi
.venv/bin/python -m cozmo.cli benchmark --runs runs --ground-truth capture/ground_truth.csv --out reports/benchmark
```
