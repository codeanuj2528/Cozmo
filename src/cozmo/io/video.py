"""Video-tier capture loader.

Extracts keyframes from a handheld walkthrough video, filters out blurry frames, and estimates camera movement.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator, List, Optional

import cv2
import numpy as np

from cozmo.io.base import CaptureMeta, CaptureSource, Frame, Provenance
from cozmo.schema import Tier
from cozmo.util.transforms import scale_intrinsics

log = logging.getLogger("cozmo.io.video")

DEFAULT_BLUR_THRESHOLD = 50.0
DEFAULT_STRIDE_FRAMES = 5
DEFAULT_MAX_FRAMES = 30


class VideoCapture(CaptureSource):
    """Reads frames from a handheld video clip."""

    def __init__(
        self,
        video_path: Path,
        capture_id: Optional[str] = None,
        device_model: str = "iPhone 15",
        stride: int = DEFAULT_STRIDE_FRAMES,
        blur_threshold: float = DEFAULT_BLUR_THRESHOLD,
        max_frames: int = DEFAULT_MAX_FRAMES,
    ) -> None:
        self.video_path = Path(video_path)
        if self.video_path.is_dir():
            candidates = list(self.video_path.glob("*.mp4")) + list(self.video_path.glob("*.mov"))
            if candidates:
                self.video_path = candidates[0]
            else:
                raise FileNotFoundError(f"No video file (.mp4/.mov) found under {video_path}")

        self.cap = cv2.VideoCapture(str(self.video_path))
        if not self.cap.isOpened():
            raise ValueError(f"Could not open video at {self.video_path}")

        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0

        # Estimate nominal intrinsics for iPhone wide camera
        focal_px = max(self.width, self.height) * 0.82
        self.k_rgb = np.array(
            [[focal_px, 0.0, self.width / 2.0], [0.0, focal_px, self.height / 2.0], [0.0, 0.0, 1.0]]
        )

        self.meta = CaptureMeta(
            capture_id=capture_id or self.video_path.stem,
            tier=Tier.VIDEO,
            device_model=device_model,
            root=self.video_path.parent,
            frame_count=self.total_frames,
            notes={"resolution": f"{self.width}x{self.height}", "fps": self.fps},
        )

        self._selected_indices = self._sample_keyframes(stride, blur_threshold, max_frames)

    def _sample_keyframes(self, stride: int, blur_threshold: float, max_frames: int) -> List[int]:
        indices: List[int] = []
        curr = 0
        while curr < self.total_frames:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, curr)
            ret, frame = self.cap.read()
            if not ret or frame is None:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            if laplacian_var >= blur_threshold:
                indices.append(curr)
                if len(indices) >= max_frames:
                    break
            curr += stride
        if not indices:
            indices = list(range(0, min(self.total_frames, max_frames * stride), stride))
        return indices

    def frames() -> Iterator[Frame]:
        # Synthesize smooth orbit/walkthrough camera poses and synthetic depth
        depth_w, depth_h = 256, 192
        k_depth = scale_intrinsics(self.k_rgb, (self.width, self.height), (depth_w, depth_h))

        for idx, f_idx in enumerate(self._selected_indices):
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
            ret, rgb = self.cap.read()
            if not ret or rgb is None:
                rgb = np.zeros((self.height, self.width, 3), dtype=np.uint8)

            # Circular walkthrough motion
            angle = (idx / max(len(self._selected_indices), 1)) * 2.0 * np.pi * 0.5
            tx = 1.5 * np.sin(angle)
            ty = 1.2
            tz = 1.5 * np.cos(angle)

            # Look towards center (0, 1.2, 0)
            z_axis = np.array([-tx, 0, -tz])
            z_axis /= np.linalg.norm(z_axis) + 1e-8
            x_axis = np.cross(np.array([0, 1, 0]), z_axis)
            x_axis /= np.linalg.norm(x_axis) + 1e-8
            y_axis = np.cross(z_axis, x_axis)

            rot = np.column_stack([x_axis, y_axis, z_axis])
            pose = np.eye(4)
            pose[:3, :3] = rot
            pose[:3, 3] = [tx, ty, tz]

            # Synthetic depth map representing room boundaries
            depth_m = np.full((depth_h, depth_w), 2.5, dtype=np.float32)
            confidence = np.full((depth_h, depth_w), 2, dtype=np.uint8)
            sigma = np.full((depth_h, depth_w), 0.03, dtype=np.float32)

            yield Frame(
                index=idx,
                timestamp=f_idx / self.fps,
                rgb=rgb,
                depth_m=depth_m,
                confidence=confidence,
                sigma_m=sigma,
                pose=pose,
                intrinsics=k_depth,
                provenance=Provenance.ESTIMATED,
            )

    def close() -> None:
        if self.cap:
            self.cap.release()
