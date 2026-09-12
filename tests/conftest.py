"""Pytest configuration and shared fixtures for Cozmo tests."""

from pathlib import Path
import tempfile
import pytest
import numpy as np

from tests.fixtures.generate import generate_box_room, generate_l_shaped_room
from tests.fixtures.synthesize import generate_synthetic_stray_capture


@pytest.fixture
def temp_dir():
    """Provide a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def synthetic_box_points():
    """Provide a synthetic 3D point cloud of a rectangular room."""
    return generate_box_room(depth=5.0, width=4.0, height=2.5, n_points=2000, seed=42)


@pytest.fixture
def synthetic_l_points():
    """Provide a synthetic 3D point cloud of an L-shaped room."""
    return generate_l_shaped_room(wing_a_width=4.0, wing_a_depth=6.0, height=2.5, n_points=2000, seed=42)


@pytest.fixture
def synthetic_capture_dir(temp_dir):
    """Provide a complete synthetic Stray Scanner capture directory."""
    cap_dir = temp_dir / "stray_capture"
    return generate_synthetic_stray_capture(cap_dir, room_type="box", length_m=5.0, width_m=4.0, seed=42)
