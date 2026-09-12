"""Feature matching between overlapping room observations.

This module provides robust feature matching for establishing spatial
relationships between frames that may observe the same physical structure
from different viewpoints or rooms.

Two matching strategies are supported:

1. **Classical** — ORB features + brute-force matching + RANSAC fundamental
   matrix estimation.  No GPU required, runs everywhere.

2. **Learned** — LightGlue (or SuperPoint+SuperGlue) features via the
   :mod:`cozmo.models` interface.  Higher quality matches but requires the
   ``[ml]`` optional dependency and model weights.

The matcher returns ``FeatureMatch`` objects that carry the matched keypoints,
inlier mask, and the estimated geometric transformation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

log = logging.getLogger("cozmo.stitch.match")


@dataclass
class FeatureMatch:
    """Result of matching two images."""

    image_i: int
    image_j: int
    keypoints_i: np.ndarray  # (N, 2) pixel coordinates in image_i
    keypoints_j: np.ndarray  # (N, 2) pixel coordinates in image_j
    inlier_mask: np.ndarray  # (N,) boolean mask of RANSAC inliers
    fundamental_matrix: Optional[np.ndarray] = None  # (3, 3) if estimated
    confidence: float = 0.0

    @property
    def num_inliers(self) -> int:
        return int(self.inlier_mask.sum())

    @property
    def inlier_ratio(self) -> float:
        n = len(self.inlier_mask)
        return float(self.num_inliers / n) if n > 0 else 0.0


def _extract_orb_features(
    image: np.ndarray, max_features: int = 2000
) -> tuple[np.ndarray, np.ndarray]:
    """Extract ORB keypoints and descriptors.

    Returns (keypoints_xy, descriptors).  If no features are found, returns
    empty arrays.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    orb = cv2.ORB_create(nfeatures=max_features)
    kps, descs = orb.detectAndCompute(gray, None)

    if kps is None or descs is None:
        return np.zeros((0, 2), dtype=np.float32), np.zeros((0, 32), dtype=np.uint8)

    pts = np.array([kp.pt for kp in kps], dtype=np.float32)
    return pts, descs


def _match_descriptors(
    desc_i: np.ndarray,
    desc_j: np.ndarray,
    ratio_threshold: float = 0.75,
) -> list[tuple[int, int]]:
    """Brute-force match with Lowe's ratio test.

    Returns list of (idx_i, idx_j) pairs.
    """
    if len(desc_i) < 2 or len(desc_j) < 2:
        return []

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    raw_matches = bf.knnMatch(desc_i, desc_j, k=2)

    good = []
    for pair in raw_matches:
        if len(pair) < 2:
            continue
        m, n = pair
        if m.distance < ratio_threshold * n.distance:
            good.append((m.queryIdx, m.trainIdx))

    return good


def _estimate_fundamental(
    pts_i: np.ndarray,
    pts_j: np.ndarray,
    ransac_threshold: float = 3.0,
) -> tuple[Optional[np.ndarray], np.ndarray]:
    """RANSAC fundamental matrix estimation.

    Returns (F, inlier_mask).  F is None if estimation fails.
    """
    if len(pts_i) < 8:
        return None, np.ones(len(pts_i), dtype=bool)

    f_mat, mask = cv2.findFundamentalMat(
        pts_i, pts_j, cv2.FM_RANSAC, ransac_threshold
    )
    if mask is None:
        mask = np.ones(len(pts_i), dtype=np.uint8)

    return f_mat, mask.ravel().astype(bool)


def match_features(
    image_i: np.ndarray,
    image_j: np.ndarray,
    idx_i: int = 0,
    idx_j: int = 1,
    max_features: int = 2000,
    ratio_threshold: float = 0.75,
    ransac_threshold: float = 3.0,
    min_inliers: int = 15,
) -> Optional[FeatureMatch]:
    """Match features between two images using ORB + RANSAC.

    Returns a ``FeatureMatch`` if enough inliers are found, else ``None``.
    """
    pts_i, desc_i = _extract_orb_features(image_i, max_features)
    pts_j, desc_j = _extract_orb_features(image_j, max_features)

    if len(pts_i) == 0 or len(pts_j) == 0:
        log.debug("no features in one or both images")
        return None

    pairs = _match_descriptors(desc_i, desc_j, ratio_threshold)
    if len(pairs) < min_inliers:
        log.debug(
            "only %d matches (need %d); skipping pair (%d, %d)",
            len(pairs),
            min_inliers,
            idx_i,
            idx_j,
        )
        return None

    matched_i = pts_i[np.array([p[0] for p in pairs])]
    matched_j = pts_j[np.array([p[1] for p in pairs])]

    f_mat, inlier_mask = _estimate_fundamental(
        matched_i, matched_j, ransac_threshold
    )

    n_inliers = int(inlier_mask.sum())
    if n_inliers < min_inliers:
        log.debug(
            "only %d inliers after RANSAC (need %d); skipping (%d, %d)",
            n_inliers,
            min_inliers,
            idx_i,
            idx_j,
        )
        return None

    confidence = float(n_inliers / len(pairs))

    return FeatureMatch(
        image_i=idx_i,
        image_j=idx_j,
        keypoints_i=matched_i,
        keypoints_j=matched_j,
        inlier_mask=inlier_mask,
        fundamental_matrix=f_mat,
        confidence=confidence,
    )


def match_all_pairs(
    images: list[np.ndarray],
    min_overlap: int = 15,
    max_pairs: int = 100,
) -> list[FeatureMatch]:
    """Match all adjacent image pairs in a sequence.

    Only adjacent pairs (i, i+1) are matched by default.  For loop-closure
    detection, also check pairs (i, j) where j - i > threshold.
    """
    matches = []
    n = len(images)

    # Adjacent pairs.
    for i in range(n - 1):
        result = match_features(images[i], images[i + 1], idx_i=i, idx_j=i + 1)
        if result is not None:
            matches.append(result)

    # Loop closure candidates: first vs. last quarter.
    if n > 10:
        quarter = max(n // 4, 1)
        for i in range(quarter):
            for j in range(n - quarter, n):
                if len(matches) >= max_pairs:
                    break
                result = match_features(images[i], images[j], idx_i=i, idx_j=j)
                if result is not None:
                    matches.append(result)
                    log.info("loop closure candidate: frames %d ↔ %d (%d inliers)", i, j, result.num_inliers)

    return matches
