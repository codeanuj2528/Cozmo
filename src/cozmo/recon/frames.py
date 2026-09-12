"""Frame selection and quality filtering for the photo and video tiers.

Selecting which frames to reconstruct from is as important as the reconstruction
itself.  Too few frames miss geometry; too many slow the pipeline without adding
information; blurred or dark frames introduce noise.

This module provides:

1. **Blur rejection** — Laplacian variance below a threshold → frame is blurred.
2. **Exposure filtering** — frames that are too dark or too bright are penalised.
3. **Diversity sampling** — among the accepted frames, select a diverse subset
   by maximising the minimum pairwise distance in HOG-descriptor space.

The result is a compact set of frames that covers the scene geometry well.
"""

from __future__ import annotations

import logging
from typing import Optional

import cv2
import numpy as np

log = logging.getLogger("cozmo.recon.frames")


def _sharpness(image: np.ndarray) -> float:
    """Laplacian variance — higher is sharper."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _brightness(image: np.ndarray) -> float:
    """Mean brightness in [0, 255]."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    return float(gray.mean())


def _hog_descriptor(image: np.ndarray, resize: int = 128) -> np.ndarray:
    """Compact HOG descriptor for diversity sampling.

    We resize to a fixed resolution and compute a coarse orientation histogram.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    gray = cv2.resize(gray, (resize, resize))

    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag, angle = cv2.cartToPolar(gx, gy, angleInDegrees=True)

    n_bins = 9
    bin_width = 360.0 / n_bins
    cell_size = resize // 4

    descriptors = []
    for cy in range(4):
        for cx in range(4):
            y1, y2 = cy * cell_size, (cy + 1) * cell_size
            x1, x2 = cx * cell_size, (cx + 1) * cell_size
            cell_mag = mag[y1:y2, x1:x2].ravel()
            cell_ang = angle[y1:y2, x1:x2].ravel()

            hist = np.zeros(n_bins, dtype=np.float32)
            for m, a in zip(cell_mag, cell_ang):
                b = int(a / bin_width) % n_bins
                hist[b] += m

            norm = np.linalg.norm(hist) + 1e-6
            descriptors.append(hist / norm)

    return np.concatenate(descriptors)


def select_diverse_frames(
    images: list[np.ndarray],
    max_frames: int = 30,
    blur_threshold: float = 80.0,
    brightness_range: tuple[float, float] = (30.0, 230.0),
) -> list[int]:
    """Select a diverse subset of frames for reconstruction.

    1. Filter by sharpness and brightness.
    2. Among accepted frames, greedily select the most diverse set by
       maximising minimum pairwise HOG distance.

    Returns frame indices into the original ``images`` list.
    """
    n = len(images)
    if n == 0:
        return []

    # Phase 1: quality filter.
    accepted: list[tuple[int, float]] = []
    for i, img in enumerate(images):
        sharp = _sharpness(img)
        bright = _brightness(img)

        if sharp < blur_threshold:
            continue
        if bright < brightness_range[0] or bright > brightness_range[1]:
            continue

        accepted.append((i, sharp))

    if not accepted:
        log.warning("no frames pass quality filter; using top %d by sharpness", max_frames)
        scores = [(i, _sharpness(img)) for i, img in enumerate(images)]
        scores.sort(key=lambda x: x[1], reverse=True)
        return [i for i, _ in scores[:max_frames]]

    if len(accepted) <= max_frames:
        return [i for i, _ in accepted]

    # Phase 2: diversity sampling via greedy farthest-point.
    indices = [i for i, _ in accepted]
    descs = np.array([_hog_descriptor(images[i]) for i in indices])

    selected = [0]  # start with the first accepted frame
    min_dists = np.full(len(indices), np.inf)

    for _ in range(max_frames - 1):
        last = selected[-1]
        dists = np.linalg.norm(descs - descs[last], axis=1)
        min_dists = np.minimum(min_dists, dists)
        min_dists[selected] = -1.0  # exclude already selected
        next_idx = int(np.argmax(min_dists))
        selected.append(next_idx)

    result = sorted([indices[s] for s in selected])
    log.info(
        "selected %d diverse frames from %d accepted (of %d total)",
        len(result),
        len(accepted),
        n,
    )
    return result
