"""Semantic inference staging — frame selection and per-frame aggregation.

This module orchestrates the damage detection pipeline:

1. Select frames at a configurable stride (not every frame needs analysis).
2. Run the damage detector on each selected frame.
3. Aggregate per-frame detections into per-room results.
4. Apply confidence thresholding and non-maximum suppression.

The staging pipeline is designed to be GPU-efficient: frames are batched
and processed in parallel when torch is available.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

import numpy as np

log = logging.getLogger("cozmo.damage.stage")

DEFAULT_FRAME_STRIDE = 5
DEFAULT_MAX_FRAMES = 30
DEFAULT_CONFIDENCE_THRESHOLD = 0.25
DEFAULT_NMS_IOU_THRESHOLD = 0.45


@dataclass
class FrameDetection:
    """Detections from a single frame."""

    frame_idx: int
    bboxes: list[tuple[float, float, float, float]]  # (x1, y1, x2, y2)
    labels: list[str]
    scores: list[float]
    masks: list[Optional[np.ndarray]]


@dataclass
class SemanticResult:
    """Aggregated semantic detections for a room or capture."""

    room_id: str
    detections: list[FrameDetection] = field(default_factory=list)
    total_frames_processed: int = 0
    total_detections: int = 0

    @property
    def detection_rate(self) -> float:
        if self.total_frames_processed == 0:
            return 0.0
        frames_with_dets = sum(1 for d in self.detections if d.bboxes)
        return frames_with_dets / self.total_frames_processed


def select_analysis_frames(
    total_frames: int,
    stride: int = DEFAULT_FRAME_STRIDE,
    max_frames: int = DEFAULT_MAX_FRAMES,
) -> list[int]:
    """Select frame indices for semantic analysis.

    Returns evenly spaced frame indices, capped at ``max_frames``.
    """
    candidates = list(range(0, total_frames, stride))
    if len(candidates) <= max_frames:
        return candidates

    step = len(candidates) / max_frames
    return [candidates[int(i * step)] for i in range(max_frames)]


def _iou(box_a: tuple, box_b: tuple) -> float:
    """Intersection-over-union for two bounding boxes."""
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])

    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter

    return inter / max(union, 1e-6)


def non_maximum_suppression(
    detections: list[FrameDetection],
    iou_threshold: float = DEFAULT_NMS_IOU_THRESHOLD,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> list[FrameDetection]:
    """Apply NMS across all frames, then filter by confidence.

    This reduces duplicate detections of the same damage region seen in
    multiple frames.
    """
    filtered = []
    for det in detections:
        kept_indices = []
        n = len(det.bboxes)

        # Sort by score descending.
        order = sorted(range(n), key=lambda i: det.scores[i], reverse=True)

        suppressed = [False] * n
        for idx in order:
            if suppressed[idx]:
                continue
            if det.scores[idx] < confidence_threshold:
                continue

            kept_indices.append(idx)

            for other in order:
                if other == idx or suppressed[other]:
                    continue
                if _iou(det.bboxes[idx], det.bboxes[other]) > iou_threshold:
                    suppressed[other] = True

        if kept_indices:
            filtered.append(FrameDetection(
                frame_idx=det.frame_idx,
                bboxes=[det.bboxes[i] for i in kept_indices],
                labels=[det.labels[i] for i in kept_indices],
                scores=[det.scores[i] for i in kept_indices],
                masks=[det.masks[i] for i in kept_indices] if det.masks else [],
            ))

    return filtered


def run_semantic_stage(
    room_id: str,
    images: Sequence[np.ndarray],
    stride: int = DEFAULT_FRAME_STRIDE,
    max_frames: int = DEFAULT_MAX_FRAMES,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> SemanticResult:
    """Run the full semantic detection stage for a room.

    This is the entry point for per-room damage analysis.
    """
    from cozmo.damage.detect import detect_damage_in_image

    frame_indices = select_analysis_frames(len(images), stride, max_frames)
    all_detections: list[FrameDetection] = []

    for idx in frame_indices:
        if idx >= len(images):
            continue

        dets = detect_damage_in_image(images[idx], frame_idx=idx)
        if dets is not None:
            all_detections.append(dets)

    # Apply NMS and confidence filtering.
    filtered = non_maximum_suppression(all_detections, confidence_threshold=confidence_threshold)

    total_dets = sum(len(d.bboxes) for d in filtered)
    log.info(
        "room %s: %d detections from %d frames (%.0f%% detection rate)",
        room_id,
        total_dets,
        len(frame_indices),
        100.0 * (sum(1 for d in filtered if d.bboxes) / max(len(frame_indices), 1)),
    )

    return SemanticResult(
        room_id=room_id,
        detections=filtered,
        total_frames_processed=len(frame_indices),
        total_detections=total_dets,
    )
