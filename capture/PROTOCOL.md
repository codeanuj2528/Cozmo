# Cozmo capture protocol (stock app route)

One page. A non-engineer follows it literally. Nothing here needs a developer, an account,
or a cable.

## What to install

| Tier | App | Where | Cost |
|---|---|---|---|
| LiDAR | **Stray Scanner** | iOS App Store | Free |
| Video | **Camera** (built in) | Already on the phone | Free |
| Photo | **Camera** (built in) | Already on the phone | Free |

Install time: under two minutes on any iPhone. No sign-in.

## Before you start, in every tier

1. Turn the lights on. All of them. Open blinds.
2. Wipe the lens.
3. Hold the phone **upright (portrait)**, screen facing you, in both hands at chest height,
   roughly 1.4 m off the floor.
4. Walk at the pace of a slow stroll. About one step per second. Do not sweep the phone
   fast; a fast sweep is the single most common cause of a bad capture.
5. If a room has a mirror or a glass shower screen, do not stand square in front of it.
   Pass it at an angle. Note it on the ground-truth sheet.

---

## Tier 1: LiDAR (iPhone Pro only)

Open Stray Scanner. Tap the red record button. Then, **in each room in turn**:

1. **Stand still just inside the doorway for 3 seconds.** Do not move. This anchors the
   room.
2. **Lap one, walls.** Walk the perimeter of the room, keeping about 1.2 m away from the
   walls, with the phone tilted down about 15 degrees. Keep walls in view, not floor.
3. **Lap two, ceiling.** Walk the same loop again with the phone tilted **up** about 30
   degrees so the ceiling fills the top of the screen.
   *This lap is not optional.* Without it the ceiling height cannot be measured at all,
   only guessed. Roughly 20 extra seconds per room.
4. **Every doorway, from both sides.** Stand about 1.5 m back from each doorway and face
   it squarely for 3 seconds. Then walk through and do the same from the other room. A
   doorway seen from one side only cannot be used to join the two rooms together.
5. **Walk into every room.** A room you only looked into from the doorway is reported as
   unmeasured, on purpose.
6. **Return to where you started** and stand still for 3 seconds before stopping the
   recording. This closes the loop and is what lets accumulated drift be corrected.

Time: about 60 to 90 seconds per room. A four-room flat takes under 6 minutes.

Stop recording. In Stray Scanner, tap the recording, then **Share** and **Save to Files**.
It saves a folder. Hand over the whole folder, or a zip of it.

## Tier 2: Video

Native Camera app, **Video** mode, **1080p at 30 fps** (Settings > Camera > Record Video).
Do not use 4K: it fills storage and adds nothing here.

Same walk as the LiDAR tier, both laps included, doorways from both sides, returning to
the start. One continuous clip for the whole property. Do not stop and restart.

Hand over the `.MOV` file.

## Tier 3: Photos

Native Camera app, **Photo** mode. Per room, **between 4 and 8 stills** (the contract
allows 2, but 4 is where the plan stops being a guess):

1. One from each corner of the room, shooting toward the opposite corner.
2. One square-on to each doorway, taken from about 2 m back, **with the doorway fully in
   frame including both edges and the top**.
3. One of each wall that has damage on it.

Keep the phone upright. Do not zoom. Do not use Portrait mode. Do not crop or edit
afterwards, and do not send them through WhatsApp: both strip the camera information the
pipeline needs to recover scale.

**Put each room's photos in their own folder, named after the room.** For example:

```
photos/
  01_living_room/   IMG_4101.HEIC  IMG_4102.HEIC  ...
  02_corridor/      IMG_4110.HEIC  ...
  03_bedroom/       IMG_4115.HEIC  ...
```

The folder names are the only room labels the photo tier gets. Spell them how you want
them to appear on the plan.

## Handing the capture to the pipeline

Copy the folders onto the machine and run one command per capture:

```bash
cozmo run <path-to-capture> --tier lidar --out runs/my_capture
```

`--tier video` and `--tier photo` take the `.MOV` and the folder-of-folders respectively.

## What makes a capture fail

| Symptom | Cause | Fix |
|---|---|---|
| Ceiling height reported as unmeasured | Lap two was skipped | Redo lap two |
| A room missing from the plan | Nobody walked into it | Walk into it |
| Two rooms not joined | Doorway captured from one side only | Face the doorway from both rooms |
| Wide intervals everywhere | Walked too fast, or too dark | Slow down, turn the lights on |
| A phantom doorway | Mirror photographed square-on | Pass mirrors at an angle |
