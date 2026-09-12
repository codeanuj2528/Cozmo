"""Photo-tier capture loader.

Reads per-room photo folders containing 2 to 8 stills per room, without poses or depth.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import cv2
import numpy as np

from cozmo.io.base import CaptureMeta, CaptureSource, Frame, Provenance
from cozmo.schema import Tier
from cozmo.util.transforms import scale_intrinsics

log = logging.getLogger("cozmo.io.photo")


class PhotoCapture(CaptureSource):
    """Reads photo folders per room for multi-room whole-property stitching."""

    def __init__(
        self,
        root: Path,
        capture_id: Optional[str] = None,
        device_model: str = "iPhone 15",
    ) -> None:
        self.root = Path(root)
        self.room_folders: Dict[str, List[Path]] = {}

        # Discover per-room subfolders or image files
        subdirs = [p for p in self.root.iterdir() if p.is_dir() and not p.name.startswith(".")]
        if subdirs:
            for s in subdirs:
                imgs = sorted(
                    list(s.glob("*.jpg")) + list(s.glob("*.jpeg")) + list(s.glob("*.png"))
                )
                if imgs:
                    self.room_folders[s.name] = imgs
        else:
            imgs = sorted(
                list(self.root.glob("*.jpg")) + list(self.root.glob("*.jpeg")) + list(self.root.glob("*.png"))
            )
            if imgs:
                self.room_folders["room_01"] = imgs

        if not self.room_folders:
            raise FileNotFoundError(f"No image files (.jpg/.png) found under {root}")

        total_images = sum(len(imgs) for imgs in self.room_folders.values())
        self.meta = CaptureMeta(
            capture_id=capture_id or self.root.name,
            tier=Tier.PHOTO,
            device_model=device_model,
            root=self.root,
            frame_count=total_images,
            notes={"rooms": len(self.room_folders), "photo_count": total_images},
        )

    def frames(self) -> Iterator[Frame]:
        depth_w, depth_h = 256, 192
        global_idx = 0

        for room_name, img_paths in sorted(self.room_folders.items()):
            n_photos = len(img_paths)
            for r_idx, img_p in enumerate(img_paths):
                rgb = cv2.imread(str(img_p))
                if rgb is None:
                    rgb = np.zeros((1080, 1440, 3), dtype=np.uint8)
                h, w = rgb.shape[:2]

                focal_px = max(w, h) * 0.8
                k_rgb = np.array([[focal_px, 0.0, w / 2.0], [0.0, focal_px, h / 2.0], [0.0, 0.0, 1.0]])
                k_depth = scale_intrinsics(k_rgb, (w, h), (depth_w, depth_h))

                # Synthesize room poses around corners
                angle = (r_idx / max(n_photos, 1)) * 2.0 * np.pi * 0.8
                tx = 2.0 * np.sin(angle)
                ty = 1.2
                tz = 2.0 * np.cos(angle)

                rot = np.eye(3)
                pose = np.eye(4)
                pose[:3, :3] = rot
                pose[:3, 3] = [tx, ty, tz]

                depth_m = np.full((depth_h, depth_w), 3.0, dtype=np.float32)
                confidence = np.full((depth_h, depth_w), 1, dtype=np.uint8)
                sigma = np.full((depth_h, depth_w), 0.08, dtype=np.float32)

                yield Frame(
                    index=global_idx,
                    timestamp=float(global_idx),
                    rgb=rgb,
                    depth_m=depth_m,
                    confidence=confidence,
                    sigma_m=sigma,
                    pose=pose,
                    intrinsics=k_depth,
                    provenance=Provenance.ESTIMATED,
                )
                global_idx += 1
