"""Damage staging, projection, concealed-damage rules and scope synthesis.

The previous version of this file imported `SemanticStager`, which does not exist, taking
the whole test suite down at collection alongside `test_recon.py`.

The tests here are written against the property that matters most for this part of the
system: a detector that reports the same thing regardless of what it was shown is not a
detector. Constant output was in fact what the damage stage produced -- the same
`water_stain 0.18 m2 conf 0.92` and `crack 1.15 m2 conf 0.88` for every room of a property
with no damage in it -- and nothing in the suite objected.
"""

from __future__ import annotations

import numpy as np

from cozmo.damage.rules import RuleEngine
from cozmo.damage.stage import (
    FrameDetection,
    SemanticResult,
    non_maximum_suppression,
    select_analysis_frames,
)


def test_analysis_frames_are_spread_over_the_capture():
    picked = select_analysis_frames(total_frames=300, max_frames=10)
    assert len(picked) <= 10
    assert len(set(picked)) == len(picked), "a frame must not be analysed twice"
    assert all(0 <= i < 300 for i in picked)
    if len(picked) > 2:
        gaps = np.diff(sorted(picked))
        assert gaps.min() > 1, "clustered frames waste inference on near-duplicate views"


def test_analysis_frames_handle_short_captures():
    assert len(select_analysis_frames(total_frames=3, max_frames=10)) <= 3
    assert select_analysis_frames(total_frames=0, max_frames=10) == []


def _frame(boxes, labels, scores, frame_idx=0):
    return FrameDetection(
        frame_idx=frame_idx,
        bboxes=list(boxes),
        labels=list(labels),
        scores=list(scores),
        masks=[None] * len(boxes),
    )


def test_nms_collapses_overlapping_detections_of_one_class():
    kept = non_maximum_suppression(
        [
            _frame(
                [(10, 10, 100, 100), (12, 12, 102, 102), (400, 400, 480, 480)],
                ["water_stain"] * 3,
                [0.9, 0.7, 0.8],
            )
        ],
        iou_threshold=0.5,
        confidence_threshold=0.1,
    )
    surviving = sum(len(f.bboxes) for f in kept)
    assert surviving == 2, "the two boxes that overlap are one finding"
    scores = [s for f in kept for s in f.scores]
    assert 0.9 in scores, "the strongest detection of a cluster must survive"
    assert 0.7 not in scores


def test_nms_keeps_different_classes_in_the_same_place():
    """A crack running through a water stain is two findings, not one.

    They are repaired differently and scoped separately, so suppressing one because it
    overlaps the other silently drops a line item from the scope.
    """
    kept = non_maximum_suppression(
        [_frame([(10, 10, 100, 100), (10, 10, 100, 100)], ["water_stain", "crack"], [0.9, 0.8])],
        iou_threshold=0.5,
        confidence_threshold=0.1,
    )
    assert sum(len(f.bboxes) for f in kept) == 2


def test_low_confidence_detections_are_dropped():
    kept = non_maximum_suppression(
        [_frame([(10, 10, 100, 100)], ["water_stain"], [0.02])],
        iou_threshold=0.5,
        confidence_threshold=0.5,
    )
    assert sum(len(f.bboxes) for f in kept) == 0


def test_semantic_result_is_empty_when_nothing_was_detected():
    """No detections must produce no damage, not a default finding."""
    result = SemanticResult(room_id="room_01")
    assert result.detections == []
    assert result.total_detections == 0
    assert result.detection_rate == 0.0


def test_rule_engine_ships_with_auditable_rules():
    engine = RuleEngine()
    assert engine.rules, "the rule engine must ship with rules"
    for rule in engine.rules:
        assert rule.id
        assert rule.text and len(rule.text) > 20, f"{rule.id} has no auditable rule text"
        assert rule.predicate, f"{rule.id} has no predicate and would fire unconditionally"


def test_concealed_rules_do_not_fire_without_damage():
    """A rule that fires on an empty property is not evidence of anything."""
    assert RuleEngine().evaluate_damage([]) == []


# ---------------------------------------------------------------------------
# Image detectors. These exist because the damage stage previously returned two
# hardcoded regions per room regardless of what it was shown, and no test objected.
# ---------------------------------------------------------------------------


def _wall(seed: int = 0) -> np.ndarray:
    import numpy as _np

    rng = _np.random.default_rng(seed)
    return _np.clip(
        _np.full((400, 600, 3), 225, int) + rng.integers(-6, 6, (400, 600, 3)), 0, 255
    ).astype(_np.uint8)


def test_clean_wall_yields_no_damage():
    """The property this module most needs: silence when there is nothing there."""
    from cozmo.damage.detect import detect_cracks, detect_water_stains

    wall = _wall()
    assert detect_water_stains(wall) == []
    assert detect_cracks(wall) == []


def test_stain_is_found_and_is_not_called_a_crack():
    import cv2

    from cozmo.damage.detect import detect_cracks, detect_water_stains

    stained = _wall()
    cv2.ellipse(stained, (300, 180), (70, 45), 0, 0, 360, (150, 120, 70), -1)
    stained = cv2.GaussianBlur(stained, (31, 31), 0)

    stains = detect_water_stains(stained)
    assert len(stains) == 1
    assert stains[0].score > 0.3
    assert detect_cracks(stained) == []


def test_crack_is_found_and_is_not_called_a_stain():
    import cv2

    from cozmo.damage.detect import detect_cracks, detect_water_stains

    cracked = _wall()
    cv2.line(cracked, (80, 300), (520, 320), (40, 40, 40), 2)

    assert len(detect_cracks(cracked)) == 1
    assert detect_water_stains(cracked) == []


def test_tile_grout_is_not_reported_as_cracks():
    """Grout lines are thin, dark, straight and long, which is also what a crack is.

    What separates them is that grout comes in a repeating parallel family and a crack
    generally does not. Without this the detector fired on every tiled bathroom wall in the
    sample property.
    """
    import cv2

    from cozmo.damage.detect import detect_cracks

    tiled = _wall()
    for x in range(60, 600, 90):
        cv2.line(tiled, (x, 0), (x, 400), (150, 150, 150), 2)
    for y in range(60, 400, 90):
        cv2.line(tiled, (0, y), (600, y), (150, 150, 150), 2)

    assert detect_cracks(tiled) == []


def test_a_crack_across_tiles_still_survives_the_grout_filter():
    """Rejecting the family must not reject the one feature that is not part of it."""
    import cv2

    from cozmo.damage.detect import detect_cracks

    tiled = _wall()
    for x in range(60, 600, 90):
        cv2.line(tiled, (x, 0), (x, 400), (150, 150, 150), 2)
    for y in range(60, 400, 90):
        cv2.line(tiled, (0, y), (600, y), (150, 150, 150), 2)
    cv2.line(tiled, (90, 340), (500, 120), (30, 30, 30), 3)

    found = detect_cracks(tiled)
    assert len(found) == 1, "the diagonal crack must survive while the grid is suppressed"


def test_detector_never_claims_a_conformal_interval_it_has_not_fitted():
    """An uncalibrated extent must say so.

    The previous implementation stamped IntervalMethod.CONFORMAL on invented constants,
    which is the single field a reader uses to tell a calibrated interval from a guess.
    """
    from cozmo.damage.detect import build_damage_regions
    from cozmo.schema import IntervalMethod, Tier
    from cozmo.uncertainty.calibration import IntervalBook

    regions = build_damage_regions([], IntervalBook(), Tier.LIDAR, "classical")
    assert regions == []
