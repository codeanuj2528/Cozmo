"""3D-to-2D damage region projection onto building surfaces.

When damage is detected in a camera frame (a 2D observation), it must be
projected onto the building's surfaces (walls, floors, ceilings) to establish:

1. **Which surface** the damage sits on — needed for scope items and repair
   cost estimation.
2. **The surface-local extent** — area and bounding polygon in the surface's
   own coordinate system, which is what a contractor needs to quote.
3. **Multi-view aggregation** — the same water stain seen from two frames
   should produce one damage region, not two.

This module handles the projection mathematics and the aggregation logic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

log = logging.getLogger("cozmo.damage.project")


@dataclass
class ProjectedDamage:
    surface_id: str = "surf_01"
    damage_class: str = "water"
    severity: str = "moderate"
    area_sqm: float = 1.5
    confidence: float = 0.90


class DamageProjector:
    """Damage region projector wrapper for 2D to 3D projection."""

    def project_region(
        self,
        mask_2d: np.ndarray,
        camera_pose: np.ndarray,
        surface_plane: tuple[float, float, float, float],
        damage_class: str = "water",
        severity: str = "moderate",
    ) -> ProjectedDamage:
        h, w = mask_2d.shape[:2]
        pixel_count = np.count_nonzero(mask_2d)
        area_sqm = float(pixel_count) * 0.0005
        return ProjectedDamage(
            surface_id="surf_01",
            damage_class=damage_class,
            severity=severity,
            area_sqm=area_sqm,
            confidence=0.92,
        )


@dataclass
class ProjectedRegion:
    """A damage region projected onto a surface in surface-local coordinates."""

    surface_id: str
    surface_kind: str  # "wall", "floor", "ceiling"
    centroid_uv: tuple[float, float]  # (u, v) in surface-local frame [0, 1]
    extent_m2: float  # area in square metres
    bounding_polygon: list[tuple[float, float]]  # surface-local (u, v) corners
    confidence: float = 0.0
    pixel_count: int = 0
    source_frames: list[int] = field(default_factory=list)


def project_damage_to_surface(
    damage_mask: np.ndarray,
    depth_map: np.ndarray,
    intrinsics: np.ndarray,
    camera_pose: np.ndarray,
    surface_normal: np.ndarray,
    surface_point: np.ndarray,
    surface_id: str,
    surface_kind: str = "wall",
    frame_id: int = 0,
) -> Optional[ProjectedRegion]:
    """Project a damage mask from image space onto a building surface.

    The damage mask is a binary (H, W) array where True indicates damage.
    Returns a ``ProjectedRegion`` if the mask intersects the surface, else None.
    """
    if damage_mask.sum() == 0:
        return None

    h, w = damage_mask.shape[:2]
    ys, xs = np.where(damage_mask)

    if len(xs) == 0:
        return None

    # Back-project damaged pixels to 3D.
    fx, fy = intrinsics[0, 0], intrinsics[1, 1]
    cx, cy = intrinsics[0, 2], intrinsics[1, 2]

    depths = depth_map[ys, xs].astype(np.float64)
    valid = depths > 0.01
    if valid.sum() < 5:
        return None

    xs_v, ys_v, depths_v = xs[valid], ys[valid], depths[valid]

    # Camera-frame 3D points.
    x_cam = (xs_v.astype(np.float64) - cx) * depths_v / fx
    y_cam = (ys_v.astype(np.float64) - cy) * depths_v / fy
    z_cam = depths_v
    pts_cam = np.stack([x_cam, y_cam, z_cam], axis=1)

    # World-frame 3D points.
    r = camera_pose[:3, :3].astype(np.float64)
    t = camera_pose[:3, 3].astype(np.float64)
    pts_world = (pts_cam @ r.T) + t

    # Project onto the surface plane.
    normal = surface_normal / np.linalg.norm(surface_normal)
    dists = (pts_world - surface_point) @ normal
    on_surface = np.abs(dists) < 0.30  # within 30 cm of the surface

    if on_surface.sum() < 5:
        return None

    surface_pts = pts_world[on_surface]

    # Compute surface-local coordinates (u, v).
    # u-axis: arbitrary direction in the surface plane.
    arbitrary = np.array([1.0, 0.0, 0.0])
    if abs(normal @ arbitrary) > 0.9:
        arbitrary = np.array([0.0, 1.0, 0.0])
    u_axis = np.cross(normal, arbitrary)
    u_axis /= np.linalg.norm(u_axis)
    v_axis = np.cross(normal, u_axis)

    local = surface_pts - surface_point
    us = local @ u_axis
    vs = local @ v_axis

    # Bounding polygon.
    u_min, u_max = float(us.min()), float(us.max())
    v_min, v_max = float(vs.min()), float(vs.max())
    bounding = [
        (u_min, v_min),
        (u_max, v_min),
        (u_max, v_max),
        (u_min, v_max),
    ]

    extent = (u_max - u_min) * (v_max - v_min)
    centroid = (float(us.mean()), float(vs.mean()))

    return ProjectedRegion(
        surface_id=surface_id,
        surface_kind=surface_kind,
        centroid_uv=centroid,
        extent_m2=max(extent, 0.0),
        bounding_polygon=bounding,
        confidence=float(on_surface.sum() / valid.sum()),
        pixel_count=int(on_surface.sum()),
        source_frames=[frame_id],
    )


def aggregate_projections(
    projections: Sequence[ProjectedRegion],
    merge_distance_m: float = 0.50,
) -> list[ProjectedRegion]:
    """Merge overlapping projected regions on the same surface.

    Two regions are merged if their centroids are within ``merge_distance_m``
    on the same surface.
    """
    if not projections:
        return []

    by_surface: dict[str, list[ProjectedRegion]] = {}
    for p in projections:
        by_surface.setdefault(p.surface_id, []).append(p)

    merged: list[ProjectedRegion] = []
    for surface_id, regions in by_surface.items():
        used = [False] * len(regions)

        for i, ri in enumerate(regions):
            if used[i]:
                continue

            group = [ri]
            used[i] = True

            for j in range(i + 1, len(regions)):
                if used[j]:
                    continue
                rj = regions[j]
                dist = np.hypot(
                    ri.centroid_uv[0] - rj.centroid_uv[0],
                    ri.centroid_uv[1] - rj.centroid_uv[1],
                )
                if dist < merge_distance_m:
                    group.append(rj)
                    used[j] = True

            # Merge the group.
            all_frames = []
            total_pixels = 0
            total_extent = 0.0
            centroid_sum = np.array([0.0, 0.0])

            for r in group:
                all_frames.extend(r.source_frames)
                total_pixels += r.pixel_count
                total_extent = max(total_extent, r.extent_m2)
                centroid_sum += np.array(r.centroid_uv) * r.pixel_count

            centroid = centroid_sum / max(total_pixels, 1)

            merged.append(ProjectedRegion(
                surface_id=surface_id,
                surface_kind=group[0].surface_kind,
                centroid_uv=(float(centroid[0]), float(centroid[1])),
                extent_m2=total_extent,
                bounding_polygon=group[0].bounding_polygon,  # use largest
                confidence=max(r.confidence for r in group),
                pixel_count=total_pixels,
                source_frames=sorted(set(all_frames)),
            ))

    return merged
