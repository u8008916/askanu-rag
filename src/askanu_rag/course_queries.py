"""Deterministic Day 3 handling for standalone course prerequisite questions."""

import asyncio
import re
from dataclasses import dataclass
from typing import Final

from askanu_rag.models import (
    AskResponse,
    Clarification,
    ClarificationOption,
    CommonRecord,
    CourseMetadata,
    CourseProgramRecord,
    InsufficientEvidenceResponse,
    NeedsClarificationResponse,
    OkResponse,
    Source,
)
from askanu_rag.retrieval import CourseProgramReader, normalize_course_code
from askanu_rag.synthesis import (
    SynthesisClient,
    SynthesisError,
    assemble_context,
    validate_synthesis,
)

COURSE_CODE_CANDIDATE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Za-z0-9])([A-Za-z]{4}\s*\d{4}[A-Za-z]?)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
PREREQUISITES_INTENT_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:pre[-\s]?requisites?|requisites?)\b",
    re.IGNORECASE,
)
ACADEMIC_YEAR_CANDIDATE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<!\d)((?:19|20)\d{2})(?!\d)"
)


@dataclass(frozen=True)
class CoursePrerequisitesQuery:
    """A supported standalone prerequisite request after normalization."""

    course_code: str
    academic_year: str | None


def classify_course_prerequisites_query(
    question: str,
) -> CoursePrerequisitesQuery | None:
    """Recognize one exact course candidate and the prerequisites intent."""

    if PREREQUISITES_INTENT_PATTERN.search(question) is None:
        return None

    candidate_matches = list(COURSE_CODE_CANDIDATE_PATTERN.finditer(question))
    normalized_codes = {
        code
        for match in candidate_matches
        if (code := normalize_course_code(match.group(1))) is not None
    }
    if len(normalized_codes) != 1:
        return None

    course_spans = [match.span(1) for match in candidate_matches]
    years = {
        match.group(1)
        for match in ACADEMIC_YEAR_CANDIDATE_PATTERN.finditer(question)
        if not any(
            match.start() < course_end and match.end() > course_start
            for course_start, course_end in course_spans
        )
    }
    if len(years) > 1:
        # Do not erase conflicting explicit years and answer a different scope.
        return None
    academic_year = next(iter(years)) if len(years) == 1 else None
    return CoursePrerequisitesQuery(
        course_code=next(iter(normalized_codes)),
        academic_year=academic_year,
    )


def _source_from_record(record: CommonRecord) -> Source:
    # Kept separate so every response field is visibly mapped from stored evidence.
    return Source(
        record_id=record.record_id,
        source_id=record.source_id,
        title=record.title,
        url=record.canonical_url,
        domain=record.domain,
    )


class CourseQueryService:
    """Resolve supported course requests using exact structured evidence only."""

    def __init__(
        self,
        repository: CourseProgramReader,
        synthesis_client: SynthesisClient | None = None,
        timeout_seconds: float = 30,
    ) -> None:
        self._repository = repository
        self._synthesis_client = synthesis_client
        self._timeout_seconds = timeout_seconds

    async def answer(self, question: str, request_id: str) -> AskResponse | None:
        """Return a Day 3 response, or None when the question is outside its slice."""

        query = classify_course_prerequisites_query(question)
        if query is None:
            return None

        result = self._repository.find_course_by_code(
            query.course_code,
            query.academic_year,
        )
        if result is None:
            return InsufficientEvidenceResponse(
                answer=f"I could not find stored evidence for {query.course_code}.",
                request_id=request_id,
            )

        if isinstance(result, tuple):
            return NeedsClarificationResponse(
                answer=(
                    f"Which academic year do you mean for {query.course_code}?"
                ),
                clarification=Clarification(
                    id=f"clar-course-{query.course_code.lower()}-academic-year",
                    type="entity_selection",
                    options=[
                        ClarificationOption(
                            id=record.record_id,
                            label=(
                                f"{query.course_code} "
                                f"({record.metadata_json.academic_year})"
                            ),
                        )
                        for record in result
                    ],
                    allow_multiple=False,
                ),
                request_id=request_id,
            )

        metadata = result.metadata_json
        if not isinstance(metadata, CourseMetadata):
            raise ValueError("Course lookup returned a non-course record.")

        source = _source_from_record(result)
        if metadata.prerequisites is None or not metadata.prerequisites.strip():
            return InsufficientEvidenceResponse(
                answer=(
                    f"The stored evidence for {metadata.course_code} "
                    f"({metadata.academic_year}) does not establish its "
                    "prerequisites."
                ),
                sources=[source],
                request_id=request_id,
            )

        context = assemble_context(result, question)
        answer = context.allowed_answers[0]
        if self._synthesis_client is not None:
            try:
                raw = await asyncio.wait_for(
                    self._synthesis_client.synthesize(context),
                    timeout=self._timeout_seconds,
                )
                answer = validate_synthesis(raw, context)
            except Exception:
                raise SynthesisError() from None

        return OkResponse(
            answer=answer,
            sources=[source],
            request_id=request_id,
        )
