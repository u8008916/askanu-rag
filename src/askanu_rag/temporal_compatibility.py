"""Narrow V1 legacy-temporal to V7 split-temporal normalisation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from askanu_rag.models import (
    ConstraintScope,
    ConstraintSemanticType,
    ConstraintSet,
    ScopedConstraint,
)

_DATE_RE = re.compile(
    r"\b(today|tomorrow|this friday|next week|this weekend|this week|"
    r"next month|\d{4}-\d{2}-\d{2})\b",
    re.IGNORECASE,
)
_AFTER_RE = re.compile(r"\bafter\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.IGNORECASE)
_BEFORE_RE = re.compile(r"\bbefore\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.IGNORECASE)
_BETWEEN_RE = re.compile(
    r"\bbetween\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+and\s+"
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TemporalNormalisation:
    constraints: ConstraintSet
    removed_legacy: bool = False


def _clock(hour: str, minute: str | None, meridiem: str | None) -> str:
    value = int(hour)
    if meridiem and meridiem.casefold() == "pm" and value != 12:
        value += 12
    if meridiem and meridiem.casefold() == "am" and value == 12:
        value = 0
    return f"{value:02d}:{int(minute or 0):02d}"


def _legacy_parts(value: object) -> dict[ConstraintSemanticType, str]:
    if not isinstance(value, str):
        return {}
    normalised = re.sub(r"\s+", " ", value.casefold().replace("_", " ").strip())
    parts: dict[ConstraintSemanticType, str] = {}
    date = _DATE_RE.search(normalised)
    if date:
        parts[ConstraintSemanticType.DATE_WINDOW] = date.group(1).casefold()

    between = _BETWEEN_RE.search(normalised)
    after = _AFTER_RE.search(normalised)
    before = _BEFORE_RE.search(normalised)
    if between:
        parts[ConstraintSemanticType.TIME_OF_DAY_WINDOW] = (
            f"between {_clock(*between.groups()[:3])} and "
            f"{_clock(*between.groups()[3:])}"
        )
    elif after:
        parts[ConstraintSemanticType.TIME_OF_DAY_WINDOW] = (
            f"after {_clock(*after.groups())}"
        )
    elif before:
        parts[ConstraintSemanticType.TIME_OF_DAY_WINDOW] = (
            f"before {_clock(*before.groups())}"
        )
    elif "evening" in normalised:
        parts[ConstraintSemanticType.TIME_OF_DAY_WINDOW] = "evening"
    return parts


def scopes_overlap(left: ConstraintScope, right: ConstraintScope) -> bool:
    if left.domain != right.domain:
        return False
    for field in ("entity_kind", "canonical_entity_id", "intent"):
        left_value = getattr(left, field)
        right_value = getattr(right, field)
        if left_value is not None and right_value is not None and left_value != right_value:
            return False
    return True


def _constraint_key(constraint: ScopedConstraint) -> tuple[object, ...]:
    scope = constraint.scope
    return (
        constraint.semantic_type,
        scope.domain,
        scope.entity_kind,
        scope.canonical_entity_id,
        scope.intent,
    )


def normalise_legacy_temporal_constraints(
    inherited: ConstraintSet,
    explicit: ConstraintSet,
) -> TemporalNormalisation:
    """Remove overlapping legacy authority and preserve recognised independent parts."""

    explicit_temporal = tuple(
        item
        for item in explicit.items
        if item.semantic_type
        in {
            ConstraintSemanticType.DATE_WINDOW,
            ConstraintSemanticType.TIME_OF_DAY_WINDOW,
        }
    )
    if not explicit_temporal:
        return TemporalNormalisation(inherited)

    kept: list[ScopedConstraint] = []
    derived: list[ScopedConstraint] = []
    removed = False
    explicit_types = {item.semantic_type for item in explicit_temporal}
    for item in inherited.items:
        overlaps = any(
            scopes_overlap(item.scope, current.scope)
            for current in explicit_temporal
        )
        if (
            item.semantic_type != ConstraintSemanticType.LEGACY_TEMPORAL_WINDOW
            or not overlaps
        ):
            kept.append(item)
            continue

        removed = True
        for semantic_type, value in _legacy_parts(item.value).items():
            if semantic_type in explicit_types:
                continue
            derived.append(
                item.model_copy(
                    update={"semantic_type": semantic_type, "value": value}
                )
            )

    existing_keys = {_constraint_key(item) for item in kept}
    for item in sorted(derived, key=lambda candidate: -candidate.introduced_turn):
        key = _constraint_key(item)
        if key not in existing_keys:
            kept.append(item)
            existing_keys.add(key)
    return TemporalNormalisation(ConstraintSet(items=tuple(kept)), removed)
