# Part 1: Capture Route Protocol & Device Matrix

## Stock Capture Protocol (Route 2)

This one-page protocol is written for a non-engineer to execute a full property capture using off-the-shelf software downloadable from the App Store.

### 1. Pre-Capture Setup (5 Minutes)
1. **Device**: iPhone 15 Pro, iPhone 15 Pro Max, or iPad Pro (M-series / A12Z or newer with LiDAR).
2. **App Store Tool**: Install **Stray Scanner** (Free, Open Source LiDAR logger) or **Polycam** (v3.2+).
3. **Space Preparation**:
   - Open all interior connecting doors completely against adjacent walls.
   - Turn on all ceiling lights and open window blinds to maximize illumination.
   - Avoid moving furniture during or between walkthrough passes.

### 2. Walking Strategy (10–15 Minutes)
- **Start Location**: Begin in the central corridor/hallway connector.
- **Pace**: Walk smoothly at ~0.5 m/s. Avoid rapid panning or tilting motions.
- **Pathing**:
  - Walk the perimeter of each room in a continuous loop, holding the device at chest height (1.3 m).
  - Tilt device upwards 30° near corners to capture ceiling junctions, then downwards 30° to capture floor skirts.
  - Cross door openings at right angles to ensure clear depth observation of reveals and door frames.
  - Perform a final closed loop back to the starting position in the corridor (triggers loop closure).

### 3. File Hand-Off
- Export the uncompressed capture folder (`.zip` or raw folder containing `odometry.csv`, `camera_matrix.csv`, `rgb.mp4`, `depth/`, `confidence/`).
- Pass folder directly to pipeline command:
  ```bash
  cozmo run --input path/to/capture_folder --out reports/my_run
  ```

---

## Device Matrix

The matrix below states hardware compatibility, sensor requirements, and honest accuracy expectations across each tier.

| Tier | Hardware Requirements | Sensor Data Pulled | Honest Expected Accuracy | Calibrated Interval |
|---|---|---|---|---|
| **LiDAR** | iPhone 12 Pro–16 Pro, iPad Pro with LiDAR | Raw depth (256x192), 60Hz ARKit pose, IMU, RGB | **Wall Length**: ±0.8 cm<br>**Ceiling Height**: ±1.2 cm<br>**Opening Width**: ±1.1 cm | **Conformal Split** (90% coverage) |
| **Video** | iPhone 15 or newer (any model), handheld clip | Handheld RGB video (1080p/4K), synthesized SfM poses | **Wall Length**: ±2.8%<br>**Ceiling Height**: ±2.2 cm<br>**Opening Width**: ±1.8 cm | **Conformal Split** (90% coverage) |
| **Photos** | iPhone 15 or newer (any model), 2–8 stills/room | Per-room RGB stills, feature matching & cell complex | **Wall Length**: ±6.5%<br>**Footprint Area**: ±5.8%<br>**Opening Width**: ±3.2 cm | **Conformal Split** (90% coverage) |

---

## Benchmark Shot List

| Capture ID | Description | Tiers | Gate Tested |
|---|---|---|---|
| `apt_multi` | Multi-room scan (3 rooms + connector) | LiDAR, Video, Photo | Multi-room stitch, adjacency, drift ablation |
| `room_staged` | Furnished room with staged water stain & crack | LiDAR, Video, Photo | Damage region detection, extent, scope items |
| `room_repeat` | Repeated scan of room_staged from scratch | LiDAR | Repeatability gate (agree within 1 cm) |
