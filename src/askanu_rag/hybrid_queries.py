"""Exact -> name/metadata -> bounded vectors, then evidence-only synthesis."""

import asyncio
import math
from collections import Counter

from askanu_rag.course_queries import CourseQueryService, _source_from_record, classify_course_prerequisites_query
from askanu_rag.index_lifecycle import index_is_stale
from askanu_rag.models import Clarification, ClarificationOption, InsufficientEvidenceResponse, NeedsClarificationResponse, OkResponse
from askanu_rag.query_planner import QueryPlan, plan_query
from askanu_rag.retrieval.catalog import filter_records, normalize_title, record_code
from askanu_rag.retrieval.semantic import LocalTfidfRetriever
from askanu_rag.synthesis import RecordSynthesisContext, SynthesisError, UNSAFE_EVIDENCE, validate_synthesis


def _matches(result):
    return () if result is None else result if isinstance(result, tuple) else (result,)


def _approved(record):
    return (record.source_id == "courses_programs_and_courses"
            and record.canonical_url.scheme == "https"
            and record.canonical_url.host == "programsandcourses.anu.edu.au")


class HybridQueryService:
    def __init__(self, repository, synthesis_client=None, semantic_retriever=None,
                 *, timeout_seconds=30, top_k=3, min_score=0.2):
        if not 1 <= top_k <= 3 or not 0 < min_score <= 1:
            raise ValueError("Invalid bounded retrieval settings.")
        self.repository = repository
        self.synthesis_client = synthesis_client
        self.semantic = semantic_retriever if semantic_retriever is not None else LocalTfidfRetriever()
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
                lookup = self.repository.find_course_by_code if kind == "course" else self.repository.find_program_by_code
                group = filter_records(_matches(lookup(identifier, plan.academic_year)), plan.entity_type, plan.academic_year, plan.session)
                if not group:
                    return ()  # No silent subset answer for an explicit set.
                found.extend(group)
            return tuple(found)
        records = self.repository.all_records()
        if plan.route == "name":
            records = tuple(r for r in records if normalize_title(r.title) == plan.title)
        candidates = filter_records(records, plan.entity_type, plan.academic_year, plan.session)
        if plan.route != "semantic":
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
            hits = self.semantic.search(plan.semantic_query, candidates, top_k=self.top_k, min_score=self.min_score)
        except Exception:
            raise SynthesisError() from None
        by_id = {record.record_id: record for record in candidates}
        chosen, seen = [], set()
        for hit in sorted(hits, key=lambda hit: (-hit.score, hit.record_id)):
            if (hit.record_id not in by_id or hit.record_id in seen
                    or not math.isfinite(hit.score) or not self.min_score <= hit.score <= 1):
                continue
            seen.add(hit.record_id)
            chosen.append(by_id[hit.record_id])
            if len(chosen) == self.top_k:
                break
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
                or (plan.route == "name" and len(records) > 1) or len(records) > self.top_k):
            return NeedsClarificationResponse(
                answer="Please choose a specific entity and academic year to narrow the request.",
                clarification=Clarification(id="clar-course-program-selection", type="entity_selection",
                    options=[ClarificationOption(id=r.record_id, label=f"{record_code(r)} ({r.metadata_json.academic_year}) — {r.title}") for r in records[:20]],
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
            identity = f"{record_code(record)} ({metadata.academic_year}) — {record.title}"
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
                value = getattr(metadata, plan.fact, None)
                if not isinstance(value, str) or not value.strip():
                    return None
                projected[plan.fact] = value
                sentence = f"{identity}. Stored {plan.fact.replace('_', ' ')}: {value}"
            if UNSAFE_EVIDENCE.search(sentence) or len(sentence) > 3000:
                raise SynthesisError()
            evidence.append(projected)
            sentences.append(sentence)
        answer = "\n\n".join(sentences)
        if len(answer) > 3600:
            return None
        return RecordSynthesisContext(question, tuple(evidence), (answer, "Stored matches:\n" + answer))
