# Known Failure Modes, Physical Limitations & Engineering Mitigations

Real-world indoor captures contain complex physical optical phenomena, low light, specular surfaces, and motion artifacts. Below is the systematic failure mode audit and engineering mitigation matrix built into the Cozmo AI pipeline.

---

## 1. Specular & Transparent Surfaces (Mirrors, Glass, Wet Finishes)

### Failure Mechanism
- LiDAR pulses penetrate transparent glass or reflect off mirrors and wet tiles, creating virtual 3D point phantom rooms behind wall faces.

### Pipeline Mitigation
- **Carving Occupancy Grid**: Camera rays from poses pass through interior volume. Points detected beyond estimated wall planes with zero backward ray agreement are filtered as mirror reflections.
- **Specular Fraction Flagging**: `QualityReport.specular_fraction` flags surfaces where > 5% of returns fail ray agreement.
- **Wall Support RANSAC**: Plane fitting requires strong point support across contiguous 2D spatial clusters, filtering scattered mirror ghost points.

---

## 2. Low Light & Textureless Surfaces (Blank White Walls, Dark Rooms)

### Failure Mechanism
- RGB feature matchers fail on featureless drywall or in low-light conditions (< 15 lux), causing drift in video/photo structure-from-motion.

### Pipeline Mitigation
- **LiDAR Depth Fallback**: On Pro devices, depth is populated directly from raw LiDAR sensors independent of visual texture.
- **Conformal Interval Widening**: When visual illumination or surface coverage drops, interval bounds (`lo`, `hi`) automatically widen via conformal calibration tables.
- **Low Light Fraction**: `QualityReport.low_light_fraction` reports illumination degradation.

---

## 3. Accumulated Pose Drift on Long Walkthroughs

### Failure Mechanism
- Unchecked visual-inertial odometry drift over multi-room loops causes room boundary misalignments, wall doubling, and overlapping rooms.

### Pipeline Mitigation
- **Pose Graph Optimization & Loop Closure**: `correct_drift()` identifies loop closure keyframes and optimizes global camera poses.
- **Cell Complex Arrangement**: Room polygons are formed from a unified arrangement of global candidate lines, preventing room overlap by construction.
- **Ablation Arm**: `drift.applied` records footprint area before and after optimization.

---

## 4. Unmeasured Ceiling Height & Stepped Volume

### Failure Mechanism
- Rooms with soffits, dropped ceilings, or unmeasured ceiling heights create elevation ambiguity in global point clouds.

### Pipeline Mitigation
- **Per-Room Level Histogramming**: `room_levels()` extracts separate floor and ceiling heights for each individual room polygon rather than applying a global single-height assumption.
- **Conformal Interval Coverage**: Unmeasured ceiling height measurements fall back to prior uncertainty bounds (`PRIOR_ONLY` or wide conformal intervals) to avoid confident-garbage outputs.

---

## Summary Matrix

| Failure Mode | Physical Cause | Primary Mitigation | Output Contract Signal |
|---|---|---|---|
| **Mirror Phantoms** | LiDAR reflection | Ray carving & contiguous RANSAC | `specular_fraction` |
| **Low Light** | Poor photon counts | LiDAR fallback & interval widening | `low_light_fraction` |
| **Pose Drift** | Odometry accumulation | Pose graph loop closure | `drift.loop_closures_found` |
| **Unfitted Openings** | Occluded reveals | Bridged wall segment search | `detection_confidence` |
