"""Reader for Stray Scanner captures, which is the LiDAR-tier input format.

A Stray Scanner export is a directory holding

    camera_matrix.csv   3x3 pinhole intrinsics for the colour stream
    odometry.csv        per frame: timestamp, index, position, quaternion, intrinsics
    imu.csv             accelerometer and gyroscope samples
    rgb.mp4             H.264 colour, 1920x1440
    depth/NNNNNN.png    uint16 millimetres, 256x192
    confidence/NNNNNN.png  uint8 in {0, 1, 2}, ARKit's own depth confidence

The colour stream, the depth stream and the odometry rows share a frame index, so no
timestamp interpolation is needed at this tier.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np

from cozmo.io.base import CaptureMeta, Frame, Provenance
from cozmo.schema import Tier
from cozmo.util.transforms import make_pose, quat_to_matrix, scale_intrinsics

DEPTH_SIZE = (256, 192)

# ARKit depth noise. The constant term is the sensor floor at close range; the quadratic
# term is the range-dependent spread. Multipliers widen the floor for the lower confidence
# classes. These start as published-order-of-magnitude values and are re-fitted against
# tape ground truth by `cozmo calibrate`, which writes the fitted values to
# `calibration/depth_noise.json`; the numbers here are the fallback when that file is absent.
DEPTH_SIGMA_BASE_M = 0.008
DEPTH_SIGMA_RANGE_COEFF = 0.0025
CONFIDENCE_SIGMA_MULTIPLIER = {0: 7.0, 1: 2.5, 2: 1.0}


class StrayCapture:
    """Lazily reads a Stray Scanner directory."""

    def __init__(self, root: Path, capture_id: str | None = None, device_model: str = "unknown"):
        self.root = Path(root)
        if not (self.root / "odometry.csv").exists():
            inner = [p for p in self.root.iterdir() if p.is_dir() and (p / "odometry.csv").exists()]
            if len(inner) == 1:
                self.root = inner[0]
            elif len(inner) > 1:
                raise ValueError(f"{root} holds {len(inner)} captures; point at one of them")
            else:
                raise FileNotFoundError(f"no odometry.csv under {root}")

        self.k_rgb = np.loadtxt(self.root / "camera_matrix.csv", delimiter=",")
        self._rows = self._read_odometry(self.root / "odometry.csv")
        self.rgb_size = self._probe_rgb_size()
        self.k_depth = scale_intrinsics(self.k_rgb, self.rgb_size, DEPTH_SIZE)

        self._video: cv2.VideoCapture | None = None
        self._video_cursor = -1

        self.meta = CaptureMeta(
            capture_id=capture_id or self.root.name,
            tier=Tier.LIDAR,
            device_model=device_model,
            root=self.root,
            frame_count=len(self._rows),
            notes={"format": "stray_scanner", "depth_resolution": f"{DEPTH_SIZE[0]}x{DEPTH_SIZE[1]}"},
        )

    @staticmethod
    def _read_odometry(path: Path) -> list[dict]:
        rows: list[dict] = []
        with path.open() as fh:
            reader = csv.reader(fh)
            header = [h.strip() for h in next(reader)]
            idx = {name: i for i, name in enumerate(header)}
            for raw in reader:
                if not raw or len(raw) < 9:
                    continue
                try:
                    quat = [float(raw[idx[c]]) for c in ("qx", "qy", "qz", "qw")]
                    pos = [float(raw[idx[c]]) for c in ("x", "y", "z")]
                    ts = float(raw[idx["timestamp"]])
                    frame = int(raw[idx["frame"]])
                except (ValueError, KeyError):
                    continue
                if not np.all(np.isfinite(quat + pos)) or np.linalg.norm(quat) < 1e-6:
                    continue
                entry = {"timestamp": ts, "frame": frame, "pos": np.array(pos), "quat": np.array(quat)}
                # ARKit re-estimates intrinsics per frame; use them when present.
                if "fx" in idx and raw[idx["fx"]].strip():
                    try:
                        entry["k"] = np.array(
                            [
                                [float(raw[idx["fx"]]), 0.0, float(raw[idx["cx"]])],
                                [0.0, float(raw[idx["fy"]]), float(raw[idx["cy"]])],
                                [0.0, 0.0, 1.0],
                            ]
                        )
                    except (ValueError, KeyError):
                        pass
                rows.append(entry)
        if not rows:
            raise ValueError(f"{path} yielded no usable poses")
        return rows

    def _probe_rgb_size(self) -> tuple[int, int]:
        video = self.root / "rgb.mp4"
        if video.exists():
            cap = cv2.VideoCapture(str(video))
            if cap.isOpened():
                size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
                cap.release()
                if size[0] > 0:
                    return size
        # Fall back to the principal point, which sits near the image centre.
        return (int(round(self.k_rgb[0, 2] * 2)), int(round(self.k_rgb[1, 2] * 2)))

    def depth_sigma(self, depth_m: np.ndarray, confidence: np.ndarray) -> np.ndarray:
        """Per-pixel depth standard deviation in metres."""
        mult = np.full(confidence.shape, CONFIDENCE_SIGMA_MULTIPLIER[0], dtype=np.float32)
        for level, value in CONFIDENCE_SIGMA_MULTIPLIER.items():
            mult[confidence == level] = value
        return (DEPTH_SIGMA_BASE_M * mult + DEPTH_SIGMA_RANGE_COEFF * depth_m**2).astype(np.float32)

    def _load_depth(self, frame_index: int) -> tuple[np.ndarray, np.ndarray] | None:
        dpath = self.root / "depth" / f"{frame_index:06d}.png"
        cpath = self.root / "confidence" / f"{frame_index:06d}.png"
        raw = cv2.imread(str(dpath), cv2.IMREAD_UNCHANGED)
        if raw is None:
            return None
        depth = raw.astype(np.float32) / 1000.0
        if cpath.exists():
            conf = cv2.imread(str(cpath), cv2.IMREAD_UNCHANGED)
        else:
            conf = np.full(depth.shape, 2, dtype=np.uint8)
        return depth, conf

    def frames(self, indices: list[int] | None = None) -> Iterator[Frame]:
        wanted = range(len(self._rows)) if indices is None else indices
        for i in wanted:
            row = self._rows[i]
            loaded = self._load_depth(row["frame"])
            if loaded is None:
                continue
            depth, conf = loaded
            k_rgb = row.get("k", self.k_rgb)
            yield Frame(
                index=row["frame"],
                timestamp=row["timestamp"],
                k_depth=scale_intrinsics(k_rgb, self.rgb_size, DEPTH_SIZE),
                k_rgb=k_rgb,
                rgb_size=self.rgb_size,
                depth=depth,
                depth_sigma=self.depth_sigma(depth, conf),
                confidence=conf,
                pose=make_pose(quat_to_matrix(*row["quat"]), row["pos"]),
                depth_provenance=Provenance.SENSOR,
                pose_provenance=Provenance.SENSOR,
            )

    def poses(self) -> np.ndarray:
        """All poses as an (N, 4, 4) array, in file order."""
        return np.stack([make_pose(quat_to_matrix(*r["quat"]), r["pos"]) for r in self._rows])

    def load_rgb(self, frame: Frame) -> np.ndarray:
        """Decode one colour frame as RGB uint8.

        Backward seeks are expensive on a long H.264 stream, so callers that need many
        frames should sort their indices and use `load_rgb_batch`.
        """
        return self.load_rgb_batch([frame.index])[frame.index]

    def load_rgb_batch(self, frame_indices: list[int]) -> dict[int, np.ndarray]:
        """Decode several colour frames in one forward pass over the video."""
        video = self.root / "rgb.mp4"
        out: dict[int, np.ndarray] = {}
        if not video.exists():
            return out
        wanted = sorted(set(int(i) for i in frame_indices))
        cap = cv2.VideoCapture(str(video))
        if not cap.isOpened():
            return out
        try:
            cursor = 0
            for target in wanted:
                if target < cursor:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, target)
                    cursor = target
                while cursor < target:
                    if not cap.grab():
                        return out
                    cursor += 1
                ok, bgr = cap.read()
                cursor += 1
                if not ok:
                    break
                out[target] = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        finally:
            cap.release()
        return out

    def imu(self) -> np.ndarray | None:
        path = self.root / "imu.csv"
        if not path.exists():
            return None
        return np.loadtxt(path, delimiter=",", skiprows=1)
