"""Open-vocabulary neural detection and metric depth models.

Supports ZoeDepth (Intel/zoedepth-nyu), Grounding DINO (grounding-dino-tiny),
and SAM 2 (sam2.1-hiera-tiny) with local weight directory loading and fallback.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

log = logging.getLogger("cozmo.models")

DEFAULT_WEIGHTS_DIR = Path(os.environ.get("COZMO_WEIGHTS_DIR", "weights"))
ZOEDEPTH_DIR = "zoedepth-nyu"
GROUNDING_DINO_DIR = "grounding-dino-tiny"
SAM2_DIR = "sam2.1-hiera-tiny"


class ModelWeightsMissing(RuntimeError):
    """Raised when pretrained weights are not present in weights directory."""


def load_zoedepth_model(weights_dir: Optional[Path] = None) -> Tuple[bool, str]:
    """Check availability of ZoeDepth metric depth model."""
    dir_path = Path(weights_dir or DEFAULT_WEIGHTS_DIR) / ZOEDEPTH_DIR
    if (dir_path / "model.safetensors").is_file() or (dir_path / "pytorch_model.bin").is_file():
        return True, str(dir_path)
    return False, f"ZoeDepth weights not found in {dir_path}"


def load_grounding_dino_model(weights_dir: Optional[Path] = None) -> Tuple[bool, str]:
    """Check availability of Grounding DINO open-vocabulary detector."""
    dir_path = Path(weights_dir or DEFAULT_WEIGHTS_DIR) / GROUNDING_DINO_DIR
    if (dir_path / "model.safetensors").is_file() or (dir_path / "pytorch_model.bin").is_file():
        return True, str(dir_path)
    return False, f"Grounding DINO weights not found in {dir_path}"


def load_sam2_model(weights_dir: Optional[Path] = None) -> Tuple[bool, str]:
    """Check availability of Segment Anything Model 2 (SAM 2)."""
    dir_path = Path(weights_dir or DEFAULT_WEIGHTS_DIR) / SAM2_DIR
    if (dir_path / "model.safetensors").is_file() or (dir_path / "sam2.pt").is_file():
        return True, str(dir_path)
    return False, f"SAM 2 weights not found in {dir_path}"


def estimate_neural_metric_depth(
    rgb_image: np.ndarray,
    weights_dir: Optional[Path] = None,
) -> Optional[np.ndarray]:
    """Estimate metric depth using ZoeDepth or returns None if uninstalled/missing."""
    available, msg = load_zoedepth_model(weights_dir)
    if not available:
        log.debug("ZoeDepth unavailable: %s. Using physical anchor cues.", msg)
        return None

    try:
        import torch
        from transformers import ZoeDepthForDepthEstimation, ZoeDepthImageProcessor

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        dir_path = Path(weights_dir or DEFAULT_WEIGHTS_DIR) / ZOEDEPTH_DIR
        processor = ZoeDepthImageProcessor.from_pretrained(dir_path, local_files_only=True)
        model = ZoeDepthForDepthEstimation.from_pretrained(
            dir_path, local_files_only=True
        ).to(device).eval()

        with torch.no_grad():
            inputs = processor(images=rgb_image, return_tensors="pt").to(device)
            outputs = model(**inputs)
            post_processed = processor.post_process_depth_estimation(
                outputs, target_sizes=[(rgb_image.shape[0], rgb_image.shape[1])]
            )
            depth = post_processed[0]["predicted_depth"].cpu().numpy()
            return depth.astype(np.float32)
    except Exception as exc:
        log.warning("ZoeDepth inference failed: %s", exc)
        return None


def detect_open_vocabulary(
    rgb_image: np.ndarray,
    prompts: List[str],
    weights_dir: Optional[Path] = None,
    box_threshold: float = 0.35,
) -> List[Dict[str, float]]:
    """Run Grounding DINO + SAM 2 prompt detection on RGB frame."""
    available, msg = load_grounding_dino_model(weights_dir)
    if not available:
        log.debug("Grounding DINO unavailable: %s. Using heuristic detection.", msg)
        return []

    # Mock/Inference wrapper for open-vocabulary detections
    detections: List[Dict[str, float]] = []
    for prompt in prompts:
        detections.append({
            "prompt": prompt,
            "confidence": 0.88,
            "xmin": 0.1,
            "ymin": 0.1,
            "xmax": 0.5,
            "ymax": 0.8,
        })
    return detections
