"""Small deterministic-first plan. Explicit constraints never become fallback hints."""

import re
from dataclasses import dataclass
from typing import Literal

from askanu_rag.course_queries import COURSE_CODE_CANDIDATE_PATTERN, PREREQUISITES_INTENT_PATTERN
from askanu_rag.retrieval.catalog import CatalogReader, normalize_title, record_code
from askanu_rag.retrieval.identifiers import (
    normalize_course_code,
    normalize_program_code,
    normalize_subplan_code,
)


@dataclass(frozen=True)
class QueryPlan:
    route: Literal[
        "exact", "name", "metadata", "semantic", "hybrid", "unsupported"
    ]
    identifiers: tuple[tuple[str, str], ...] = ()
    title: str | None = None
    entity_type: str | None = None
    academic_year: str | None = None
    session: str | None = None
    fact: str = "overview"
    list_shaped: bool = False
    semantic_query: str | None = None
    invalid_constraints: bool = False

    @property
    def semantic_allowed(self) -> bool:
        return self.route in {"semantic", "hybrid"} and not self.invalid_constraints


SESSION_PATTERN = re.compile(r"\b(first semester|second semester|semester [12]|summer session|winter session)\b", re.I)
YEAR_PATTERN = re.compile(r"(?<!\d)\d{4}(?!\d)")


def plan_query(question: str, catalog: CatalogReader) -> QueryPlan:
    courses = list(COURSE_CODE_CANDIDATE_PATTERN.finditer(question))
    identities = [("course", normalize_course_code(match.group(1))) for match in courses]
    spans = [match.span() for match in courses]
    # Known stored non-course identities are matched without inventing code grammars.
    known_non_courses = {
        (r.metadata_json.entity_type, record_code(r))
        for r in catalog.all_records()
        if r.metadata_json.entity_type != "course"
    }
    for kind, code in sorted(known_non_courses):
        for match in re.finditer(r"(?<!\w)" + re.escape(code) + r"(?!\w)", question, re.I):
            identities.append((kind, code))
            spans.append(match.span())
    # Unknown non-course identities require an explicit type label. A bare token
    # retains the legacy Program interpretation only when no stored identity matched.
    labelled = re.search(
        r"\b(program|major|minor|speciali[sz]ation)\s+code\s+"
        r"[\"']?([^\s?\"',]+)",
        question,
        re.I,
    )
    if labelled:
        label = labelled.group(1).casefold()
        kind = "specialisation" if label in {"specialisation", "specialization"} else label
        normalizer = normalize_program_code if kind == "program" else normalize_subplan_code
        identities.append((kind, normalizer(labelled.group(2))))
        spans.append(labelled.span(2))
    elif not identities and re.fullmatch(r"[A-Z]{2,}[A-Z0-9_-]*", question.strip()):
        identities.append(("program", normalize_program_code(question)))

    years = {m.group() for m in YEAR_PATTERN.finditer(question) if not any(m.start() < end and m.end() > start for start, end in spans)}
    sessions = {m.group().casefold().replace("semester 1", "first semester").replace("semester 2", "second semester") for m in SESSION_PATTERN.finditer(question)}
    requested_types = {
        entity_type
        for entity_type, pattern in (
            ("course", r"\bcourses?\b"),
            ("program", r"\bprograms?\b"),
            ("major", r"\bmajors?\b"),
            ("minor", r"\bminors?\b"),
            ("specialisation", r"\bspeciali[sz]ations?\b"),
        )
        if re.search(pattern, question, re.I)
    }
    entity_type = next(iter(requested_types), None) if len(requested_types) == 1 else None
    invalid = len(years) > 1 or len(sessions) > 1 or len(requested_types) > 1
    # Relative years/sessions must not be silently interpreted as unconstrained.
    invalid |= bool(re.search(r"\b(?:current|latest|next|last|this)\s+(?:academic\s+)?(?:year|semester|session)\b|\bthird semester\b", question, re.I))
    fact = "overview"
    if re.search(r"\bco-?requisites?\b", question, re.I):
        fact = "corequisites"
    elif re.search(r"\badmission requirements?\b", question, re.I):
        fact = "admission_requirements"
    elif re.search(r"\bprogram requirements?\b", question, re.I):
        fact = "program_requirements"
    elif re.search(r"\blearning outcomes?\b", question, re.I):
        fact = "learning_outcomes"
    elif re.search(r"\bdescription\b", question, re.I):
        fact = "description"
    elif PREREQUISITES_INTENT_PATTERN.search(question):
        fact = "prerequisites"
    elif re.search(r"\brequirements?\b", question, re.I):
        fact = "requirements"
    elif re.search(r"\b(?:offered|offerings?|semesters?|sessions?)\b", question, re.I):
        fact = "offerings"
    elif re.search(r"\bincompatibilit(?:y|ies)\b", question, re.I):
        fact = "incompatibilities"
    elif re.search(r"\bassumed knowledge\b", question, re.I):
        fact = "assumed_knowledge"
    elif re.search(r"\b(?:fees?|deadlines?|eligibility|guarantee)\b", question, re.I):
        fact = "unsupported"
    plural_discovery = bool(
        re.search(
            r"\b(?:courses|programs|majors|minors|speciali[sz]ations)\b",
            question,
            re.I,
        )
        and not identities
    )
    list_shaped = bool(
        re.search(r"\b(?:list|compare)\b", question, re.I)
        or len({identifier for _kind, identifier in identities}) > 1
        or plural_discovery
    )
    common = dict(entity_type=entity_type, academic_year=next(iter(years), None), session=next(iter(sessions), None), fact=fact,
                  list_shaped=list_shaped, invalid_constraints=invalid)
    descriptive = bool(
        re.search(
            r"\b(?:teaches?|covers?|learn|study|related to|focused on|"
            r"involv(?:e|es|ing)|about)\b",
            question,
            re.I,
        )
    )
    if identities:
        unique_identities = tuple(dict.fromkeys(identities))
        if entity_type:
            typed_identities = tuple(
                identity
                for identity in unique_identities
                if identity[0] == entity_type
            )
            if typed_identities:
                unique_identities = typed_identities
        if (
            descriptive
            and entity_type == "course"
            and re.search(r"\b(?:after|following)\b", question, re.I)
            and all(kind == "course" for kind, _identifier in unique_identities)
        ):
            return QueryPlan(
                "hybrid",
                identifiers=unique_identities,
                semantic_query=question,
                **common,
            )
        return QueryPlan("exact", identifiers=unique_identities, **common)

    name = question.strip().rstrip("?.!")
    name = re.sub(
        r"^(?:(?:what (?:is|are) the )?(?:admission |program )?requirements? for|"
        r"(?:what (?:is|are) the )?co-?requisites? for|"
        r"(?:what (?:is|are) the )?learning outcomes? (?:for|of)|"
        r"(?:what (?:is|are) the )?description (?:for|of)|"
        r"what are the prerequisites for|prerequisites for|tell me about|"
        r"what (?:is|are)|is|show me)\s+",
        "",
        name,
        flags=re.I,
    )
    name = re.sub(r"^(?:the\s+)?(?:course|program|major|minor|speciali[sz]ation)\s+(?:named|called)\s+", "", name, flags=re.I)
    name = re.sub(r"\s+(?:in|for)?\s*\d{4}$", "", name, flags=re.I)
    name = re.sub(r"\s+(?:offered\s+)?(?:in\s+)?(?:first semester|second semester|semester [12]|summer session|winter session)(?:,?\s*\d{4})?$", "", name, flags=re.I)
    name = name.strip(" \"'")
    normalized = normalize_title(name)
    known_names = {normalize_title(record.title) for record in catalog.all_records()}
    if normalized in known_names or re.search(r"\b(?:named|called)\b|[\"']", question) or (question.casefold().startswith("tell me about ") and not descriptive):
        return QueryPlan("name", title=normalized, **common)
    if descriptive:
        if entity_type or re.search(r"\bANU\b", question, re.I):
            return QueryPlan("semantic", semantic_query=question, **common)
        return QueryPlan("unsupported", **common)
    metadata_only = re.sub(r"\b(?:list|show|me|all|the|courses?|programs?|majors?|minors?|speciali[sz]ations?|offered|in|for)\b", "", question, flags=re.I)
    metadata_only = SESSION_PATTERN.sub("", metadata_only)
    metadata_only = YEAR_PATTERN.sub("", metadata_only).strip(" ,?.!")
    if entity_type and not metadata_only:
        return QueryPlan("metadata", **{**common, "list_shaped": True})
    return QueryPlan("unsupported", **common)
