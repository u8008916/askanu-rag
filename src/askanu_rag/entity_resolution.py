"""Deterministic entity-catalogue boundary for V7 understanding.

The catalogue supplies approved canonical identities.  Safe natural-language
aliases remain an understanding-layer concern and never create source facts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, Sequence

from askanu_rag.models import (
    Domain,
    EntityKind,
    EntityResolutionBasis,
    ResolvedEntity,
)
from askanu_rag.models.conversation_state import ENTITY_DOMAIN

_SPACE_RE = re.compile(r"\s+")
_COURSE_CODE_RE = re.compile(r"\bCOMP\s*(\d{4}[A-Z]?)\b", re.IGNORECASE)


def normalise_entity_text(value: str) -> str:
    return _SPACE_RE.sub(" ", value.casefold().strip())


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(
        re.search(
            rf"(?<![a-z0-9]){re.escape(normalise_entity_text(phrase))}(?![a-z0-9])",
            text,
        )
    )


@dataclass(frozen=True)
class CanonicalEntity:
    domain: Domain
    kind: EntityKind
    canonical_id: str
    canonical_name: str
    identifiers: tuple[str, ...] = ()
    source_record_id: str | None = None

    def __post_init__(self) -> None:
        if ENTITY_DOMAIN[self.kind] != self.domain:
            raise ValueError("catalogue entity kind is incompatible with domain")
        if not self.canonical_id.strip() or not self.canonical_name.strip():
            raise ValueError("catalogue identity and name must be non-empty")


class EntityCatalogue(Protocol):
    """Read-only approved canonical-identity boundary."""

    def canonical_entities(self) -> tuple[CanonicalEntity, ...]: ...


class InMemoryEntityCatalogue:
    """Deterministic catalogue useful for fixtures and injected snapshots."""

    def __init__(self, entities: Sequence[CanonicalEntity]) -> None:
        identities = [entity.canonical_id.casefold() for entity in entities]
        if len(set(identities)) != len(identities):
            raise ValueError("canonical entity IDs must be unique")
        self._entities = tuple(entities)

    def canonical_entities(self) -> tuple[CanonicalEntity, ...]:
        return self._entities


@dataclass(frozen=True)
class SafeEntityAlias:
    phrase: str
    canonical_id: str


@dataclass(frozen=True)
class ExplicitEntityResolution:
    entity: ResolvedEntity | None = None
    possible_entities: tuple[ResolvedEntity, ...] = ()


def _resolved(
    entity: CanonicalEntity,
    *,
    turn: int,
    basis: EntityResolutionBasis,
) -> ResolvedEntity:
    return ResolvedEntity(
        domain=entity.domain,
        kind=entity.kind,
        canonical_id=entity.canonical_id,
        canonical_name=entity.canonical_name,
        source_record_id=entity.source_record_id,
        resolution_basis=basis,
        mentioned_turn=turn,
    )


def _unique_matches(
    matches: Sequence[CanonicalEntity],
) -> tuple[CanonicalEntity, ...]:
    by_id = {match.canonical_id.casefold(): match for match in matches}
    return tuple(sorted(by_id.values(), key=lambda item: item.canonical_id))


def _resolution(
    matches: Sequence[CanonicalEntity],
    *,
    turn: int,
    basis: EntityResolutionBasis,
) -> ExplicitEntityResolution:
    unique = _unique_matches(matches)
    resolved = tuple(_resolved(item, turn=turn, basis=basis) for item in unique)
    if len(resolved) == 1:
        return ExplicitEntityResolution(entity=resolved[0])
    return ExplicitEntityResolution(possible_entities=resolved)


def resolve_explicit_entity(
    question: str,
    turn: int,
    *,
    catalogue: EntityCatalogue,
    aliases: Sequence[SafeEntityAlias] = (),
) -> ExplicitEntityResolution:
    """Apply identifier > canonical name > safe-alias resolution precedence."""

    normalised = normalise_entity_text(question)
    entities = catalogue.canonical_entities()
    by_id = {entity.canonical_id.casefold(): entity for entity in entities}
    identifiers = [
        entity
        for entity in entities
        if any(
            _contains_phrase(normalised, identifier)
            for identifier in (entity.canonical_id, *entity.identifiers)
        )
    ]
    course_codes = tuple(
        dict.fromkeys(
            f"COMP{match.group(1).upper()}"
            for match in _COURSE_CODE_RE.finditer(question)
        )
    )
    if identifiers or course_codes:
        matches = list(identifiers)
        matches.extend(
            by_id.get(
                code.casefold(),
                CanonicalEntity(
                    domain=Domain.COURSES,
                    kind=EntityKind.COURSE,
                    canonical_id=code,
                    canonical_name=code,
                ),
            )
            for code in course_codes
        )
        return _resolution(
            matches,
            turn=turn,
            basis=EntityResolutionBasis.EXPLICIT_IDENTIFIER,
        )

    names = [
        entity
        for entity in entities
        if _contains_phrase(normalised, entity.canonical_name)
    ]
    if names:
        return _resolution(
            names,
            turn=turn,
            basis=EntityResolutionBasis.CANONICAL_NAME,
        )

    alias_matches = [
        by_id[alias.canonical_id.casefold()]
        for alias in aliases
        if alias.canonical_id.casefold() in by_id
        and _contains_phrase(normalised, alias.phrase)
    ]
    if alias_matches:
        return _resolution(
            alias_matches,
            turn=turn,
            basis=EntityResolutionBasis.SAFE_ALIAS,
        )
    return ExplicitEntityResolution()


DEFAULT_ENTITY_CATALOGUE = InMemoryEntityCatalogue(
    (
        CanonicalEntity(
            domain=Domain.COURSES,
            kind=EntityKind.COURSE,
            canonical_id="COMP1110",
            canonical_name="Structured Programming",
        ),
        CanonicalEntity(
            domain=Domain.ACCOMMODATION,
            kind=EntityKind.RESIDENCE,
            canonical_id="warrumbul-lodge",
            canonical_name="Warrumbul Lodge",
        ),
        CanonicalEntity(
            domain=Domain.ACCOMMODATION,
            kind=EntityKind.RESIDENCE,
            canonical_id="bruce-hall",
            canonical_name="Bruce Hall",
        ),
    )
)

DEFAULT_SAFE_ENTITY_ALIASES: tuple[SafeEntityAlias, ...] = (
    SafeEntityAlias("structurd programming", "COMP1110"),
    SafeEntityAlias("structured programing", "COMP1110"),
    SafeEntityAlias("warrumbul", "warrumbul-lodge"),
)
