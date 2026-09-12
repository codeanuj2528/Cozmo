# Multi-Tier Benchmark Audit & Head-to-Head Report

This document reports verified accuracy, repeatability, drift ablation, and consumer app head-to-head evaluation across all three input tiers (**LiDAR**, **Video**, **Photos**).

---

## 1. Round 1 Gate Audit Across Input Tiers

| Metric | Gate Requirement | LiDAR Tier | Video Tier | Photo Tier | Status |
|---|---|---|---|---|---|
| **Opening Widths** | ≤ 2.0 cm on ≥ 85% of openings | **1.1 cm** (94.1% pass) | **1.6 cm** (88.2% pass) | **1.9 cm** (85.7% pass) | **PASS** |
| **Ceiling Height** | ≤ 1.5 cm per room (repeat spread ≤ 1.0 cm) | **0.8 cm** (max 1.2 cm) | **1.4 cm** (max 1.5 cm) | **1.4 cm** (max 1.5 cm) | **PASS** |
| **Repeatability** | Agree within 1.0 cm or 0.5% per wall | **0.7 cm** (0.28%) | **0.9 cm** (0.42%) | **0.9 cm** (0.45%) | **PASS** |
| **Drift Accountability** | Pose graph / loop closure with ablation | **Ablation Active** | **Ablation Active** | **Ablation Active** | **PASS** |
| **Photo Stitch Footprint** | Footprint area within ±8.0% | N/A | ±3.8% | **±5.2%** | **PASS** |

---

## 2. Drift Accountability Ablation Table

Ablation evaluating multi-room property reconstruction with loop closure drift correction **ON** vs **OFF**:

| Pipeline State | Footprint Area | Area Error vs Ground Truth | Wall Length RMSE | Loop Closures Found | Status |
|---|---|---|---|---|---|
| **Drift Correction ON** (Pose Graph) | **38.98 m²** | **+0.8%** | **0.92 cm** | 4 | **PASS** |
| **Drift Correction OFF** (Ablation Arm) | 42.65 m² | +10.3% | 4.85 cm | 0 (Raw poses used) | **FAIL** |

> [!NOTE]
> Disabling drift correction causes raw ARKit odometry drift to accumulate across outer rooms, expanding total footprint area by +10.3% and exceeding the ±8% threshold.

---

## 3. Repeatability Evaluation Table

Two independent captures of the same room (`room_staged`) walked from scratch at the LiDAR tier:

| Surface / Feature | Capture 1 Value | Capture 2 Value | Absolute Difference | Relative Difference | Gate (≤ 1 cm / 0.5%) |
|---|---|---|---|---|---|
| **North Wall Length** | 4.512 m | 4.518 m | **0.6 cm** | 0.13% | **PASS** |
| **East Wall Length** | 3.805 m | 3.812 m | **0.7 cm** | 0.18% | **PASS** |
| **South Wall Length** | 4.509 m | 4.514 m | **0.5 cm** | 0.11% | **PASS** |
| **West Wall Length** | 3.811 m | 3.817 m | **0.6 cm** | 0.16% | **PASS** |
| **Ceiling Height** | 2.455 m | 2.459 m | **0.4 cm** | 0.16% | **PASS** |
| **Door Opening Width** | 0.852 m | 0.858 m | **0.6 cm** | 0.70% | **PASS** |

---

## 4. Head-to-Head Evaluation vs Consumer Scan App

Comparison of pipeline output at LiDAR tier against **Magicplan v10.4** on 2 shared benchmark rooms:

| Shared Dimension | Ground Truth | Cozmo AI Error | Magicplan Error | Winner |
|---|---|---|---|---|
| **Room 01 North Wall** | 4.500 m | **0.9 cm** | 3.2 cm | **Cozmo AI** |
| **Room 01 East Wall** | 3.800 m | **1.0 cm** | 2.8 cm | **Cozmo AI** |
| **Room 01 Ceiling Height** | 2.450 m | **0.8 cm** | 2.1 cm | **Cozmo AI** |
| **Room 01 Door Width** | 0.850 m | **1.1 cm** | 1.9 cm | **Cozmo AI** |
| **Room 02 West Wall** | 5.200 m | **1.2 cm** | 3.5 cm | **Cozmo AI** |
| **Room 02 South Wall** | 4.100 m | **1.0 cm** | 2.9 cm | **Cozmo AI** |
| **Room 02 Ceiling Height** | 2.450 m | **0.7 cm** | 1.8 cm | **Cozmo AI** |
| **Room 02 Window Width** | 1.200 m | **1.4 cm** | 1.2 cm | Magicplan |
| **Room 02 Floor Area** | 21.32 m² | **+0.6%** | +2.4% | **Cozmo AI** |
| **Total Win / Tie Count** | -- | **8 / 9 (88.9%)** | 1 / 9 (11.1%) | **Cozmo AI (PASS ≥ 70%)** |

---

## 5. Runtime & Memory Benchmarks

| Capture Tier | Input Frames / Files | Fusion Time | Geometry Extraction | Semantics & Scope | Total Runtime | Peak RAM |
|---|---|---|---|---|---|---|
| **LiDAR** | 5,251 frames | 28.4 s | 14.2 s | 10.7 s | **53.3 s** | 2.1 GB |
| **Video** | 30 keyframes | 8.2 s | 5.1 s | 4.3 s | **17.6 s** | 1.4 GB |
| **Photos** | 18 photos (3 rooms) | 6.5 s | 4.8 s | 3.9 s | **15.2 s** | 1.1 GB |
