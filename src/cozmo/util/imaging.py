"""Image statistics the quality report records."""

from __future__ import annotations

from typing import Iterable

import numpy as np

# Mean luma, on a 0-255 scale, below which a frame counts as low light. Auto-exposure keeps a lit
# room well above it; below it exposure has run out, and noise and motion blur dominate.
LOW_LIGHT_MEAN_LUMA = 50.0


def mean_luma(rgb: np.ndarray) -> float:
    """Rec. 601 luma averaged over a frame, sampled every fourth pixel."""
    sample = np.asarray(rgb)[::4, ::4, :3].astype(np.float32)
    return float((0.299 * sample[..., 0] + 0.587 * sample[..., 1] + 0.114 * sample[..., 2]).mean())


def low_light_fraction(images: Iterable[np.ndarray]) -> float | None:
    """Share of frames darker than LOW_LIGHT_MEAN_LUMA, or None when there are no frames."""
    lumas = [mean_luma(image) for image in images if image is not None and np.asarray(image).ndim == 3]
    if not lumas:
        return None
    return float(np.mean([luma < LOW_LIGHT_MEAN_LUMA for luma in lumas]))
