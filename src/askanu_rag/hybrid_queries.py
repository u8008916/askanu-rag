"""Exact -> name/metadata -> bounded vectors, then evidence-only synthesis."""

import asyncio
import math
import re
from collections import Counter

from askanu_rag.course_queries import CourseQueryService, _source_from_record, classify_course_prerequisites_query
from askanu_rag.index_lifecycle import index_is_stale
from askanu_rag.models import Clarification, ClarificationOption, InsufficientEvidenceResponse, NeedsClarificationResponse, OkResponse
from askanu_rag.query_planner import QueryPlan, plan_query
from askanu_rag.retrieval.catalog import filter_records, normalize_title, record_code
from askanu_rag.retrieval.semantic import (
    LocalBm25Retriever,
    sparse_score_is_usable,
)
from askanu_rag.retrieval.hybrid import SharedHybridRetriever
from askanu_rag.synthesis import RecordSynthesisContext, SynthesisError, UNSAFE_EVIDENCE, validate_synthesis


def _matches(result):
    return () if result is None else result if isinstance(result, tuple) else (result,)


def _approved(record):
    return (record.source_id == "courses_programs_and_courses"
            and record.canonical_url.scheme == "https"
            and record.canonical_url.host == "programsandcourses.anu.edu.au")


def _display_identity(record):
    prefix = (
        f"{record.metadata_json.entity_type.title()} "
        if record.metadata_json.entity_type
        in {"major", "minor", "specialisation"}
        else ""
    )
    return (
        f"{prefix}{record_code(record)} "
        f"({record.metadata_json.academic_year}) — {record.title}"
    )


class HybridQueryService:
    def __init__(self, repository, synthesis_client=None, semantic_retriever=None,
                 *, vector_retriever=None, timeout_seconds=30, top_k=5,
                 min_score=0.2, max_candidates=10):
        if not 1 <= top_k <= 5 or not 0 < min_score <= 1:
            raise ValueError("Invalid bounded retrieval settings.")
        self.repository = repository
        self.synthesis_client = synthesis_client
        self.semantic = (
            semantic_retriever
            if semantic_retriever is not None
            else LocalBm25Retriever()
        )
        self.vector = vector_retriever
        self.merger = SharedHybridRetriever(max_candidates=max_candidates)
        self.timeout_seconds = timeout_seconds
        self.top_k = top_k
        self.min_score = min_score
        self.legacy = CourseQueryService(repository, synthesis_client, timeout_seconds)

    def retrieve(self, plan: QueryPlan):
        """Return stored objects only; untrusted ranking IDs cannot supply facts."""
        if plan.invalid_constraints or plan.route == "unsupported":
            return ()
        if plan.route == "exact":
            found = []
            for kind, identifier in plan.identifiers:
                if plan.entity_type and kind != plan.entity_type:
                    return ()
                lookup_by_type = getattr(self.repository, "find_by_code", None)
                if lookup_by_type is not None:
                    matched = lookup_by_type(kind, identifier, plan.academic_year)
                elif kind == "course":
                    matched = self.repository.find_course_by_code(
                        identifier, plan.academic_year
                    )
                elif kind == "program":
                    matched = self.repository.find_program_by_code(
                        identifier, plan.academic_year
                    )
                else:
                    return ()
                group = filter_records(
                    _matches(matched),
                    plan.entity_type,
                    plan.academic_year,
                    plan.session,
                )
                if not group:
                    return ()  # No silent subset answer for an explicit set.
                found.extend(group)
            return tuple(found)
        records = self.repository.all_records()
        if plan.route == "name":
            records = tuple(r for r in records if normalize_title(r.title) == plan.title)
        candidates = filter_records(records, plan.entity_type, plan.academic_year, plan.session)
        if plan.route == "hybrid":
            required_codes = tuple(
                identifier for kind, identifier in plan.identifiers if kind == "course"
            )
            candidates = tuple(
                record
                for record in candidates
                if all(
                    re.search(
                        r"(?<![A-Z0-9])" + re.escape(code) + r"(?![A-Z0-9])",
                        getattr(record.metadata_json, "prerequisites", None) or "",
                        re.I,
                    )
                    for code in required_codes
                )
            )
        if plan.route not in {"semantic", "hybrid"}:
            return candidates
        # Hard filter BEFORE constructing/ranking vectors; rehydrate from this set.
        candidates = tuple(r for r in candidates if _approved(r))
        if getattr(self.semantic, "uses_persistent_index", False):
            target_version = getattr(self.semantic, "target_version", None)
            candidates = tuple(
                record
                for record in candidates
                if not index_is_stale(record, target_version=target_version)
            )
        if not candidates or not plan.semantic_allowed:
            return ()
        try:
            sparse_hits = self.semantic.search(plan.semantic_query, candidates, top_k=self.top_k, min_score=self.min_score)
        except Exception:
            raise SynthesisError() from None
        by_id = {record.record_id: record for record in candidates}
        sparse = [
            (by_id[hit.record_id], hit.score)
            for hit in sparse_hits
            if hit.record_id in by_id
            and sparse_score_is_usable(
                self.semantic, hit.score, min_score=self.min_score
            )
        ]
        dense = []
        if self.vector is not None:
            try:
                vector_hits = self.vector.search(
                    plan.semantic_query,
                    domain="courses",
                    allowed_records=candidates,
                    top_k=self.top_k,
                )
            except Exception:
                # Courses retain the proven sparse path if dense retrieval is
                # unavailable; deterministic/exact behavior never depends on it.
                vector_hits = ()
            dense = [
                (by_id[hit.record.record_id], hit.score, hit.retrieval_unit_ids)
                for hit in vector_hits
                if hit.record.record_id in by_id
                and math.isfinite(hit.score)
                and self.min_score <= hit.score <= 1
            ]
        chosen = [
            candidate.record
            for candidate in self.merger.merge(sparse=sparse, semantic=dense)
        ][: self.top_k]
        if not plan.academic_year:
            keys = {(r.metadata_json.entity_type, record_code(r)) for r in chosen}
            siblings = tuple(r for r in candidates if (r.metadata_json.entity_type, record_code(r)) in keys)
            if len(siblings) > len(chosen):
                return siblings  # Top-k must not resolve a missing year.
        return tuple(chosen)

    async def answer(self, question, request_id):
        plan = plan_query(question, self.repository)
        if plan.route == "unsupported" and not plan.invalid_constraints:
            return None
        if plan.invalid_constraints:
            return InsufficientEvidenceResponse(answer="Please specify one explicit academic year, session and entity type.", request_id=request_id)
        # Preserve Day 4 single-course prerequisite handling/context exactly.
        legacy_query = classify_course_prerequisites_query(question)
        if (legacy_query is not None and legacy_query.academic_year == plan.academic_year
                and plan.route == "exact" and len(plan.identifiers) == 1
                and plan.identifiers[0][0] == "course" and plan.entity_type != "program"
                and plan.fact == "prerequisites" and plan.session is None):
            return await self.legacy.answer(question, request_id)
        records = self.retrieve(plan)
        if not records:
            return InsufficientEvidenceResponse(answer="I could not find stored evidence matching all requested constraints.", request_id=request_id)
        identities = Counter((r.metadata_json.entity_type, record_code(r)) for r in records)
        if (any(count > 1 for count in identities.values())
                or (
                    plan.route in {"exact", "name"}
                    and len(records) > 1
                    and not plan.list_shaped
                )
                or len(records) > self.top_k):
            return NeedsClarificationResponse(
                answer="Please choose a specific entity and academic year to narrow the request.",
                clarification=Clarification(id="clar-course-program-selection", type="entity_selection",
                    options=[ClarificationOption(id=r.record_id, label=_display_identity(r)) for r in records[:20]],
                    allow_multiple=plan.list_shaped), request_id=request_id)
        context = self._context(records, plan, question)
        if context is None:
            return InsufficientEvidenceResponse(answer="The stored evidence does not establish the requested information.",
                sources=[_source_from_record(r) for r in records], request_id=request_id)
        answer = context.allowed_answers[0]
        if self.synthesis_client is not None:
            try:
                raw = await asyncio.wait_for(self.synthesis_client.synthesize(context), self.timeout_seconds)
                answer = validate_synthesis(raw, context)
            except Exception:
                raise SynthesisError() from None
        return OkResponse(answer=answer, sources=[_source_from_record(r) for r in records], request_id=request_id)

    def _context(self, records, plan, question):
        evidence, sentences = [], []
        for record in records:
            metadata = record.metadata_json
            projected = {"entity_type": metadata.entity_type, "code": record_code(record), "academic_year": metadata.academic_year, "title": record.title}
            identity = _display_identity(record)
            if plan.fact == "unsupported":
                return None
            if plan.fact == "overview":
                excerpt = record.content if len(record.content) <= 600 else record.content[:600].rsplit(" ", 1)[0] + "…"
                projected["content_excerpt"] = excerpt
                sentence = f"{identity}. Stored excerpt: {excerpt}"
            elif plan.fact == "offerings":
                offerings = getattr(metadata, "offerings", None)
                if offerings is None:
                    return None
                sessions = [o.get("session") for o in offerings if isinstance(o.get("session"), str) and o["session"].strip()]
                if plan.session:
                    sessions = [value for value in sessions if normalize_title(value) in (
                        plan.session, f"{plan.session}, {metadata.academic_year}",
                        f"{plan.session} {metadata.academic_year}")]
                if not sessions:
                    return None  # No inferred absence from missing metadata.
                projected["sessions"] = sessions
                sentence = f"{identity}. Stored offering sessions: {'; '.join(sessions)}"
            else:
                fact = plan.fact
                if fact == "requirements":
                    fact = (
                        "program_requirements"
                        if metadata.entity_type == "program"
                        else "requirements"
                    )
                value = getattr(metadata, fact, None)
                if isinstance(value, list):
                    clean_values = [item for item in value if isinstance(item, str) and item.strip()]
                    if not clean_values:
                        return None
                    projected[fact] = clean_values
                    sentence = (
                        f"{identity}. Stored {fact.replace('_', ' ')}: "
                        + "; ".join(clean_values)
                    )
                else:
                    if not isinstance(value, str) or not value.strip():
                        return None
                    projected[fact] = value
                    sentence = f"{identity}. Stored {fact.replace('_', ' ')}: {value}"
            if UNSAFE_EVIDENCE.search(sentence) or len(sentence) > 3000:
                raise SynthesisError()
            evidence.append(projected)
            sentences.append(sentence)
        answer = "\n\n".join(sentences)
        if len(answer) > 3600:
            return None
        return RecordSynthesisContext(question, tuple(evidence), (answer, "Stored matches:\n" + answer))
