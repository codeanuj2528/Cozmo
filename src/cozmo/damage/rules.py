"""Concealed-damage rule evaluation engine.

Evaluates structured YAML rules without eval() to produce ConcealedFlag objects.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

import yaml

from cozmo.schema import ConcealedFlag

log = logging.getLogger("cozmo.damage.rules")
DEFAULT_RULES_PATH = Path(__file__).with_name("rules.yaml")

RULE_FIELDS = {
    "damage_class",
    "surface_kind",
    "area_m2",
    "max_extent_m",
    "min_height_above_floor_m",
    "max_height_above_floor_m",
    "severity",
    "confidence",
    "distance_to_exterior_corner_m",
    "distance_to_opening_m",
    "wall_has_opening",
    "room_id",
    "surface_id",
}

OPERATORS: Dict[str, Callable[[Any, Any], bool]] = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "lt": lambda a, b: a is not None and a < b,
    "lte": lambda a, b: a is not None and a <= b,
    "gt": lambda a, b: a is not None and a > b,
    "gte": lambda a, b: a is not None and a >= b,
    "in": lambda a, b: a in b if isinstance(b, (list, tuple, set)) else a == b,
    "not_in": lambda a, b: a not in b if isinstance(b, (list, tuple, set)) else a != b,
    "contains": lambda a, b: b in (a or ()),
}


@dataclass
class RuleEvaluation:
    field: str
    op: str
    expected: Any
    actual: Any
    passed: bool


class ConcealedRule:
    def __init__(
        self,
        rule_id: str,
        text: str,
        predicate: Mapping[str, Any],
        severity: str = "medium",
        probability: float = 0.5,
        recommended_action: str = "",
        inspection_priority: int = 3,
    ) -> None:
        self.id = rule_id
        self.text = text
        self.predicate = predicate
        self.severity = severity
        self.probability = probability
        self.recommended_action = recommended_action
        self.inspection_priority = inspection_priority

    def evaluate(self, context: Mapping[str, Any]) -> Tuple[bool, List[RuleEvaluation]]:
        evaluations: List[RuleEvaluation] = []
        fired = _eval_node(self.predicate, context, evaluations)
        return fired, evaluations


def _eval_node(
    node: Mapping[str, Any], context: Mapping[str, Any], evaluations: List[RuleEvaluation]
) -> bool:
        if "all_of" in node:
            return all(_eval_node(child, context, evaluations) for child in node["all_of"])
        if "any_of" in node:
            return any(_eval_node(child, context, evaluations) for child in node["any_of"])
        if "none_of" in node:
            return not any(_eval_node(child, context, evaluations) for child in node["none_of"])

        fld = node.get("field")
        op = node.get("op")
        val = node.get("value")
        if not fld or not op or op not in OPERATORS:
            return False

        actual = context.get(fld)
        fn = OPERATORS[op]
        passed = bool(fn(actual, val))
        evaluations.append(
            RuleEvaluation(field=fld, op=op, expected=val, actual=actual, passed=passed)
        )
        return passed


class RuleEngine:
    def __init__(self, rules_path: Optional[Path] = None) -> None:
        path = rules_path or DEFAULT_RULES_PATH
        self.rules: List[ConcealedRule] = []
        if path.exists():
            data = yaml.safe_load(path.read_text()) or {}
            for rdict in data.get("rules", []):
                self.rules.append(
                    ConcealedRule(
                        rule_id=rdict["id"],
                        text=rdict["text"],
                        predicate=rdict["predicate"],
                        severity=rdict.get("severity", "medium"),
                        probability=rdict.get("probability", 0.5),
                        recommended_action=rdict.get("recommended_action", ""),
                        inspection_priority=rdict.get("inspection_priority", 3),
                    )
                )

    def evaluate_damage(
        self, damage_regions: Sequence[Any], room_surfaces: Optional[Sequence[Any]] = None
    ) -> List[ConcealedFlag]:
        flags: List[ConcealedFlag] = []
        for idx, dmg in enumerate(damage_regions):
            ctx = {
                "damage_class": getattr(dmg, "damage_class", "").value if hasattr(getattr(dmg, "damage_class", ""), "value") else str(getattr(dmg, "damage_class", "")),
                "surface_kind": getattr(dmg, "surface_kind", "wall"),
                "area_m2": getattr(dmg.extent, "value", 0.0) if hasattr(dmg, "extent") else 0.0,
                "max_extent_m": getattr(dmg.extent, "value", 0.0) if hasattr(dmg, "extent") else 0.0,
                "min_height_above_floor_m": getattr(dmg, "min_height_above_floor_m", 0.1),
                "max_height_above_floor_m": getattr(dmg, "max_height_above_floor_m", 2.0),
                "severity": getattr(dmg, "severity", "moderate"),
                "confidence": getattr(dmg, "classification_confidence", 0.9),
                "distance_to_exterior_corner_m": getattr(dmg, "distance_to_exterior_corner_m", 0.3),
                "distance_to_opening_m": getattr(dmg, "distance_to_opening_m", 0.5),
                "wall_has_opening": getattr(dmg, "wall_has_opening", False),
                "room_id": getattr(dmg, "room_id", "room_01"),
                "surface_id": getattr(dmg, "surface_id", "surf_01"),
            }
            for rule in self.rules:
                fired, _ = rule.evaluate(ctx)
                if fired:
                    flags.append(
                        ConcealedFlag(
                            flag_id=f"flag_{len(flags)+1:03d}",
                            rule_id=rule.id,
                            rule_text=rule.text,
                            room_id=getattr(dmg, "room_id", "room_01"),
                            surface_id=getattr(dmg, "surface_id", None),
                            triggered_by=[getattr(dmg, "damage_id", f"dmg_{idx+1:03d}")],
                            confidence=rule.probability,
                            recommended_action=rule.recommended_action,
                        )
                    )
        return flags
