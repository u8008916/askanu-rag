"""Small deterministic-first plan. Explicit constraints never become fallback hints."""

import re
from dataclasses import dataclass
from typing import Literal

from askanu_rag.course_queries import COURSE_CODE_CANDIDATE_PATTERN, PREREQUISITES_INTENT_PATTERN
from askanu_rag.retrieval.catalog import CatalogReader, normalize_title, record_code
from askanu_rag.retrieval.identifiers import normalize_course_code, normalize_program_code


@dataclass(frozen=True)
class QueryPlan:
    route: Literal["exact", "name", "metadata", "semantic", "unsupported"]
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
        return self.route == "semantic" and not self.identifiers and not self.invalid_constraints


SESSION_PATTERN = re.compile(r"\b(first semester|second semester|semester [12]|summer session|winter session)\b", re.I)
YEAR_PATTERN = re.compile(r"(?<!\d)\d{4}(?!\d)")


def plan_query(question: str, catalog: CatalogReader) -> QueryPlan:
    courses = list(COURSE_CODE_CANDIDATE_PATTERN.finditer(question))
    identities = [("course", normalize_course_code(match.group(1))) for match in courses]
    spans = [match.span() for match in courses]
    # Known stored program identities are matched without inventing a schema regex.
    for code in {record_code(r) for r in catalog.all_records() if r.metadata_json.entity_type == "program"}:
        for match in re.finditer(r"(?<!\w)" + re.escape(code) + r"(?!\w)", question, re.I):
            identities.append(("program", code))
            spans.append(match.span())
    # Unknown program identity is explicit via a code label or a bare uppercase token.
    program = re.search(r"\bprogram code\s+[\"']?([^\s?\"',]+)", question, re.I)
    if program:
        identities.append(("program", normalize_program_code(program.group(1))))
        spans.append(program.span(1))
    elif not identities and re.fullmatch(r"[A-Z]{2,}[A-Z0-9_-]*", question.strip()):
        identities.append(("program", normalize_program_code(question)))

    years = {m.group() for m in YEAR_PATTERN.finditer(question) if not any(m.start() < end and m.end() > start for start, end in spans)}
    sessions = {m.group().casefold().replace("semester 1", "first semester").replace("semester 2", "second semester") for m in SESSION_PATTERN.finditer(question)}
    course_type = bool(re.search(r"\bcourses?\b", question, re.I))
    program_type = bool(re.search(r"\bprograms?\b", question, re.I))
    entity_type = "course" if course_type and not program_type else "program" if program_type and not course_type else None
    invalid = len(years) > 1 or len(sessions) > 1 or (course_type and program_type)
    # Relative years/sessions must not be silently interpreted as unconstrained.
    invalid |= bool(re.search(r"\b(?:current|latest|next|last|this)\s+(?:academic\s+)?(?:year|semester|session)\b|\bthird semester\b", question, re.I))
    fact = "overview"
    if PREREQUISITES_INTENT_PATTERN.search(question):
        fact = "prerequisites"
    elif re.search(r"\b(?:offered|offerings?|semesters?|sessions?)\b", question, re.I):
        fact = "offerings"
    elif re.search(r"\bincompatibilit(?:y|ies)\b", question, re.I):
        fact = "incompatibilities"
    elif re.search(r"\bassumed knowledge\b", question, re.I):
        fact = "assumed_knowledge"
    elif re.search(r"\b(?:fees?|deadlines?|eligibility|guarantee)\b", question, re.I):
        fact = "unsupported"
    common = dict(entity_type=entity_type, academic_year=next(iter(years), None), session=next(iter(sessions), None), fact=fact,
                  list_shaped=bool(re.search(r"\b(?:list|compare)\b|,|\band\b", question, re.I)), invalid_constraints=invalid)
    if identities:
        return QueryPlan("exact", identifiers=tuple(dict.fromkeys(identities)), **common)

    descriptive = bool(re.search(r"\b(?:teaches?|covers?|learn|study|related to|focused on)\b", question, re.I))
    name = question.strip().rstrip("?.!")
    name = re.sub(r"^(?:what are the prerequisites for|prerequisites for|tell me about|what (?:is|are)|is|show me)\s+", "", name, flags=re.I)
    name = re.sub(r"^(?:the\s+)?(?:course|program)\s+(?:named|called)\s+", "", name, flags=re.I)
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
    metadata_only = re.sub(r"\b(?:list|show|me|all|the|courses?|programs?|offered|in|for)\b", "", question, flags=re.I)
    metadata_only = SESSION_PATTERN.sub("", metadata_only)
    metadata_only = YEAR_PATTERN.sub("", metadata_only).strip(" ,?.!")
    if entity_type and not metadata_only:
        return QueryPlan("metadata", **{**common, "list_shaped": True})
    return QueryPlan("unsupported", **common)
