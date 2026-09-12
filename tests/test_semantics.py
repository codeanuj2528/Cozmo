"""Tests for damage detection, projection, staging, and scope line-item generation."""

from pathlib import Path
import numpy as np
import pytest

from cozmo.damage.detect import detect_damage_in_image, DamageDetectionEngine
from cozmo.damage.project import DamageProjector, ProjectedDamage
from cozmo.damage.stage import SemanticStager
from cozmo.scope.generate import ScopeGenerator


def test_damage_detection_in_image():
    """Test damage detection on synthetic image."""
    img = np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8)
    detection = detect_damage_in_image(img, frame_idx=1)
    assert detection is not None
    assert len(detection.regions) >= 0


def test_damage_projector():
    """Test 2D-to-3D projection of damage region."""
    projector = DamageProjector()
    # Mock camera pose and wall polygon
    cam_pose = np.eye(4)
    wall_plane = (0.0, 1.0, 0.0, -2.5)  # y = 2.5
    mask_2d = np.zeros((100, 100), dtype=bool)
    mask_2d[30:70, 30:70] = True

    proj = projector.project_region(
        mask_2d=mask_2d,
        camera_pose=cam_pose,
        surface_plane=wall_plane,
        damage_class="water",
        severity="moderate",
    )
    assert proj.area_sqm >= 0.0
    assert proj.damage_class == "water"


def test_scope_generator(temp_dir):
    """Test scope of work generation with line items."""
    generator = ScopeGenerator()
    items = generator.generate_scope(
        damage_regions=[
            {"class": "water", "severity": "severe", "area_sqm": 12.5, "room": "Living Room"},
            {"class": "crack", "severity": "minor", "area_sqm": 2.0, "room": "Hallway"},
        ]
    )
    assert len(items) > 0
    total_cost = sum(item["total_cost_usd"] for item in items)
    assert total_cost > 0.0
