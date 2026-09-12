# Cozmo AI: Multi-Tier Indoor Scan to Floor Plan & Scope Engine

A production-grade, multi-tier indoor capture pipeline that transforms consumer smartphone data into dimensioned floor plans, per-surface damage assessments, concealed damage flags, and cost-keyed repair scope line items.

---

## Quickstart & Installation (Under 15 Minutes)

### Requirements
- macOS (Apple Silicon or Intel) or Linux
- Python 3.11 or 3.12
- Git

### 1. Clone Repository & Setup Virtual Environment
```bash
git clone https://github.com/anuj/cozmo.git
cd cozmo

# Create Python 3.12 environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install package with dependencies
pip install -e ".[ml,dev]" open3d
```

---

## One Command Per Capture

Reconstruct any capture directory into `plan.json` and rendered floor plans (`plan.png`, `plan.svg`):

```bash
cozmo run --input data/raw/1a8384c3f6 --out reports/capture_01
```

### Run Multi-Room Photo Tier
```bash
cozmo run --input data/captures/photo_multi_room --out reports/photo_run
```

### Run Handheld Video Tier
```bash
cozmo run --input data/captures/video_walkthrough --out reports/video_run
```

---

## Benchmark Evaluation & Reproduction

Run full Round 1 gate audit and head-to-head evaluation against ground truth:

```bash
cozmo benchmark --results reports/capture_01 --ground-truth capture/ground_truth.csv --out reports/benchmark_eval
```

Run Part 4 Fix Loop reproduction:

```bash
cozmo fixloop --input data/raw/1a8384c3f6 --out fixloop
```

Run automated Pytest test suite:

```bash
PYTHONPATH=src pytest
```

---

## Output Contract & Deliverables

Each capture outputs a single validated `plan.json` conforming to Pydantic v2 schemas:
- **Dimensioned per-room plan**: Walls, ceiling height, floor area, openings with calibrated confidence intervals (`Measure`).
- **Stitched multi-room plan**: Correct room adjacency and pose graph loop closure.
- **Damage regions**: Class, extent, severity, and surface-local bounding polygons.
- **Concealed damage flags**: Explicit rule-based flags with firing rationale and recommended actions.
- **Scope line items**: Unit-cost repair items keyed to surface IDs.

---

## Project Structure

```
├── capture/                  # Benchmark plan, recording sheet, device matrix, protocol
├── fixloop/                  # Part 4 Fix Loop declaration, before/after runs, diff
├── reports/                  # Pipeline output reports & benchmark evaluations
├── src/cozmo/
│   ├── bench/                # Benchmark scoring & head-to-head engine
│   ├── damage/               # Damage detector & concealed damage rule engine
│   ├── geometry/             # Cell complex, plane fitting, wall extraction, drift correction
│   ├── io/                   # LiDAR (Stray Scanner), Video, and Photo tier loaders
│   ├── render/               # Architectural 2D SVG/PNG floor plan renderer
│   ├── scope/                # Scope line item generator
│   ├── tiers/                # Multi-tier adapters
│   ├── cli.py                # Typer CLI application
│   ├── pipeline.py           # Core reconstruction engine
│   └── schema.py             # Pydantic v2 output contract schemas
├── tests/                    # Pytest unit and integration tests
├── Dockerfile                # Clean environment reproduction container
├── README.md                 # Setup and execution guide
├── benchmark_report.md       # Multi-tier gate audit & head-to-head table
├── capture_protocol.md       # Non-engineer capture protocol & device matrix
├── compliance_matrix.md      # Requirement to file path audit matrix
├── known_failure_modes.md    # System failure modes & engineering mitigations
└── technical_report.md       # 6-page architectural technical report
```
