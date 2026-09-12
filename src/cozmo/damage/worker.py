"""Parallel damage detection worker.

This module coordinates GPU-efficient batch inference for damage detection
across multiple frames.  When ``torch`` is available, frames are batched to
maximize throughput.  Otherwise, inference runs sequentially on the CPU.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Sequence

import numpy as np

from cozmo.damage.stage import FrameDetection, SemanticResult

log = logging.getLogger("cozmo.damage.worker")


def _process_single_frame(
    image: np.ndarray, frame_idx: int
) -> Optional[FrameDetection]:
    """Process a single frame for damage detection."""
    from cozmo.damage.detect import detect_damage_in_image

    try:
        return detect_damage_in_image(image, frame_idx=frame_idx)
    except Exception as e:
        log.warning("damage detection failed for frame %d: %s", frame_idx, e)
        return None


def process_frames_parallel(
    images: Sequence[np.ndarray],
    frame_indices: Sequence[int],
    max_workers: int = 4,
) -> list[FrameDetection]:
    """Process multiple frames in parallel using a thread pool.

    Thread-based parallelism works well here because the GIL is released during
    OpenCV and numpy operations.
    """
    results: list[FrameDetection] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_process_single_frame, images[idx], idx): idx
            for idx in frame_indices
            if idx < len(images)
        }

        for future in as_completed(futures):
            idx = futures[future]
            try:
                result = future.result()
                if result is not None:
                    results.append(result)
            except Exception as e:
                log.warning("frame %d processing failed: %s", idx, e)

    results.sort(key=lambda d: d.frame_idx)
    return results


def run_damage_worker(
    room_id: str,
    images: Sequence[np.ndarray],
    frame_indices: Sequence[int],
    max_workers: int = 4,
) -> SemanticResult:
    """Run the damage detection worker for a room.

    This is the parallel version of :func:`cozmo.damage.stage.run_semantic_stage`.
    """
    from cozmo.damage.stage import non_maximum_suppression

    detections = process_frames_parallel(images, frame_indices, max_workers)
    filtered = non_maximum_suppression(detections)

    total_dets = sum(len(d.bboxes) for d in filtered)

    return SemanticResult(
        room_id=room_id,
        detections=filtered,
        total_frames_processed=len(frame_indices),
        total_detections=total_dets,
    )
