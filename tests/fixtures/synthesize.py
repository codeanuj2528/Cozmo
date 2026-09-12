"""Synthetic Stray Scanner directory generator.

Produces fully functional mock Stray Scanner capture directories containing:
- cloud.ply (synthetic point cloud)
- odometry.csv (camera pose trajectory)
- camera_matrix.csv (intrinsic camera matrix)
- rgb/ and depth/ frame directories with PNG images
- room_meta.json (ground truth room dimensions for scoring)
"""

import json
from pathlib import Path
import numpy as np
from PIL import Image

from tests.fixtures.generate import generate_box_room, generate_l_shaped_room, generate_synthetic_depth_map


def generate_synthetic_stray_capture(
    output_dir: Path,
    room_type: str = "box",
    length_m: float = 5.0,
    width_m: float = 4.0,
    height_m: float = 2.5,
    num_frames: int = 15,
    seed: int = 42,
) -> Path:
    """Generate a complete synthetic Stray Scanner capture directory.

    Args:
        output_dir: Path to write the capture files.
        room_type: "box" or "l_shaped".
        length_m: Length of main box in metres.
        width_m: Width of main box in metres.
        height_m: Ceiling height in metres.
        num_frames: Number of synthetic camera frames to generate.
        seed: Random seed for reproducibility.

    Returns:
        Path to output_dir.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    # 1. Point Cloud (cloud.ply)
    if room_type == "l_shaped":
        pts = generate_l_shaped_room(
            wing_a_width=width_m, wing_a_depth=length_m, height=height_m, seed=seed
        )
    else:
        pts = generate_box_room(width=width_m, depth=length_m, height=height_m, seed=seed)

    cloud_path = output_dir / "cloud.ply"
    _write_ply(cloud_path, pts)

    # 2. Camera Matrix (camera_matrix.csv)
    # Standard iPhone wide camera intrinsics at 640x480 resolution
    fx, fy = 500.0, 500.0
    cx, cy = 320.0, 240.0
    K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float64)
    np.savetxt(output_dir / "camera_matrix.csv", K, delimiter=",")

    # 3. Odometry trajectory (odometry.csv)
    # Generate circular camera trajectory inside the room
    odom_path = output_dir / "odometry.csv"
    with open(odom_path, "w") as f:
        # Header expected by Stray Scanner parser in stray.py: timestamp,frame,x,y,z,qx,qy,qz,qw
        f.write("timestamp,frame,x,y,z,qx,qy,qz,qw\n")
        angles = np.linspace(0, 2 * np.pi, num_frames, endpoint=False)
        radius = min(length_m, width_m) * 0.3
        center_x = length_m / 2.0
        center_y = width_m / 2.0
        cam_h = 1.3  # eye height

        for i, angle in enumerate(angles):
            tx = center_x + radius * np.cos(angle)
            ty = center_y + radius * np.sin(angle)
            tz = cam_h + 0.05 * np.sin(angle * 2)

            # Facing towards center
            look_dir = np.array([center_x - tx, center_y - ty, 0])
            look_dir = look_dir / np.linalg.norm(look_dir)

            # Simple quaternion for horizontal facing
            yaw = np.arctan2(look_dir[1], look_dir[0])
            qx = 0.0
            qy = 0.0
            qz = np.sin(yaw / 2.0)
            qw = np.cos(yaw / 2.0)

            t_sec = 1000.0 + i * 0.5
            f.write(f"{t_sec:.3f},{i},{tx:.4f},{ty:.4f},{tz:.4f},{qx:.4f},{qy:.4f},{qz:.4f},{qw:.4f}\n")

    # 4. Frames directory (rgb/ & depth/)
    rgb_dir = output_dir / "rgb"
    depth_dir = output_dir / "depth"
    rgb_dir.mkdir(exist_ok=True)
    depth_dir.mkdir(exist_ok=True)

    for i in range(num_frames):
        # Synthetic RGB image (simple gradient/texture)
        rgb_img = rng.integers(50, 200, size=(480, 640, 3), dtype=np.uint8)
        Image.fromarray(rgb_img).save(rgb_dir / f"{i:06d}.png")

        # Synthetic depth image (uint16 in millimetres) with smooth structural gradients
        depth_m = generate_synthetic_depth_map(h=480, w=640, seed=seed + i)
        depth_img = (depth_m * 1000).astype(np.uint16)
        Image.fromarray(depth_img).save(depth_dir / f"{i:06d}.png")

    # 5. Room ground truth metadata (room_meta.json)
    gt_meta = {
        "room_type": room_type,
        "gt_dimensions": {
            "length_m": length_m,
            "width_m": width_m,
            "height_m": height_m,
            "floor_area_sqm": length_m * width_m if room_type == "box" else length_m * width_m * 0.75,
        },
        "num_frames": num_frames,
        "seed": seed,
    }
    with open(output_dir / "room_meta.json", "w") as f:
        json.dump(gt_meta, f, indent=2)

    return output_dir


def _write_ply(path: Path, points: np.ndarray) -> None:
    """Write nx3 numpy array to ASCII PLY format."""
    header = f"""ply
format ascii 1.0
element vertex {len(points)}
property float x
property float y
property float z
property uchar red
property uchar green
property uchar blue
end_header
"""
    colors = np.full((len(points), 3), 180, dtype=np.uint8)
    with open(path, "w") as f:
        f.write(header)
        for p, c in zip(points, colors):
            f.write(f"{p[0]:.4f} {p[1]:.4f} {p[2]:.4f} {c[0]} {c[1]} {c[2]}\n")
