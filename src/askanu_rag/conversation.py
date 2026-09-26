"""Stateless, current-request conversation resolution for Courses/Programs."""

import re
from dataclasses import dataclass

from askanu_rag.course_queries import (
    ACADEMIC_YEAR_CANDIDATE_PATTERN,
    COURSE_CODE_CANDIDATE_PATTERN,
    PREREQUISITES_INTENT_PATTERN,
)
from askanu_rag.models import AskRequest, Clarification, ClarificationOption
from askanu_rag.retrieval.catalog import CatalogReader, record_code
from askanu_rag.retrieval.identifiers import normalize_course_code_reference


SELECTION_PATTERN = re.compile(
    r"^\s*(?:(?:the\s+)?(?P<ordinal>first|second)(?:\s+(?:one|option))?|"
    r"(?P<number>[12])|(?P<both>both|all)(?:\s+(?:ones|options))?)\s*[.!]?\s*$",
    re.IGNORECASE,
)
REFERENCE_PATTERN = re.compile(
    r"\b(?:it|that\s+(?:course|program)|this\s+(?:course|program)|"
    r"the\s+same\s+(?:course|program))\b",
    re.IGNORECASE,
)
COURSE_FOLLOW_UP_PATTERN = re.compile(
    r"\b(?:pre[-\s]?(?:requisites?|reqs?)|requisites?|offerings?|offered|sessions?|"
    r"semesters?|incompatibilit(?:y|ies)|assumed knowledge)\b",
    re.IGNORECASE,
)
OTHER_DOMAIN_PATTERN = re.compile(
    r"\b(?:scholarships?|accommodation|jobs?|events?|support|honours|degree plan)\b",
    re.IGNORECASE,
)
GUIDED_CARD_PROMPTS = {
    "what courses do i need for my degree?": (
        "clar-guided-degree-program",
        "program",
        "Which program or degree do you mean?",
    ),
    "what are the prerequisites for this course?": (
        "clar-guided-prerequisite-course",
        "course",
        "Which course do you mean?",
    ),
    "can i take this course in my study plan?": (
        "clar-guided-study-plan-course",
        "course",
        "Which course do you mean?",
    ),
}
HONOURS_GUIDED_PROMPT = "can i still qualify for honours?"


@dataclass(frozen=True)
class ConversationResolution:
    """A constrained query plus an optional safe, freshly rebuilt clarification."""

    question: str
    clarification: Clarification | None = None
    clarification_answer: str | None = None
    selected_record_id: str | None = None


def _course_refs(text: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            code
            for match in COURSE_CODE_CANDIDATE_PATTERN.finditer(text)
            if (code := normalize_course_code_reference(match.group(1))) is not None
        )
    )


def _years(text: str) -> tuple[str, ...]:
    spans = [match.span(1) for match in COURSE_CODE_CANDIDATE_PATTERN.finditer(text)]
    return tuple(
        dict.fromkeys(
            match.group(1)
            for match in ACADEMIC_YEAR_CANDIDATE_PATTERN.finditer(text)
            if not any(match.start() < end and match.end() > start for start, end in spans)
        )
    )


def _intent(texts: tuple[str, ...]) -> str:
    for text in texts:
        if PREREQUISITES_INTENT_PATTERN.search(text):
            return "prerequisites"
        if re.search(r"\b(?:offered|offerings?|semesters?|sessions?)\b", text, re.I):
            return "offerings"
        if re.search(r"\bincompatibilit(?:y|ies)\b", text, re.I):
            return "incompatibilities"
        if re.search(r"\bassumed knowledge\b", text, re.I):
            return "assumed knowledge"
    return "overview"


def _question_for(records, intent: str) -> str:
    identities = " and ".join(
        f"{record_code(record)} in {record.metadata_json.academic_year}"
        for record in records
    )
    if intent == "overview":
        return f"Tell me about {identities}"
    return f"What are the {intent} for {identities}?"


def _clarification(
    records,
    *,
    allow_multiple: bool,
    minimum_options: int = 2,
    clarification_id: str = "clar-current-session-course-selection",
) -> Clarification | None:
    unique = {record.record_id: record for record in records}
    if len(unique) < minimum_options:
        return None
    ordered = tuple(sorted(unique.values(), key=lambda item: item.record_id))
    return Clarification(
        id=clarification_id,
        type="entity_selection",
        options=[
            ClarificationOption(
                id=record.record_id,
                label=(
                    f"{record_code(record)} ({record.metadata_json.academic_year})"
                    f" — {record.title}"
                ),
            )
            for record in ordered[:20]
        ],
        allow_multiple=allow_multiple,
    )


def _guided_card_resolution(
    question: str, catalog: CatalogReader
) -> ConversationResolution | None:
    """Ask only for the identity missing from an App guided-card prompt."""

    normalized = " ".join(question.split()).casefold()
    if normalized == HONOURS_GUIDED_PROMPT:
        return ConversationResolution(
            question,
            Clarification(
                id="clar-guided-honours-scope",
                type="honours_information",
                options=[],
                allow_multiple=False,
            ),
            "I can help find official honours information, but I cannot assess "
            "eligibility. Which program or discipline are you exploring?",
        )
    definition = GUIDED_CARD_PROMPTS.get(normalized)
    if definition is None:
        return None
    clarification_id, entity_type, answer = definition
    records = tuple(
        record
        for record in catalog.all_records()
        if record.metadata_json.entity_type == entity_type
    )
    clarification = _clarification(
        records,
        allow_multiple=False,
        minimum_options=1,
        clarification_id=clarification_id,
    )
    if clarification is None:
        clarification = Clarification(
            id=clarification_id,
            type="entity_selection",
            options=[],
            allow_multiple=False,
        )
    return ConversationResolution(question, clarification, answer)


def _record_for_id(catalog: CatalogReader, record_id: str):
    return next(
        (
            record
            for record in catalog.all_records()
            if record.record_id == record_id
            and record.metadata_json.entity_type == "course"
        ),
        None,
    )


def _records_for_codes(catalog: CatalogReader, codes, years=()):
    code_set = set(codes)
    year_set = set(years)
    return tuple(
        record
        for record in catalog.all_records()
        if record.metadata_json.entity_type == "course"
        and record_code(record) in code_set
        and (not year_set or record.metadata_json.academic_year in year_set)
    )


def _resolve_pending(payload: AskRequest, catalog: CatalogReader):
    pending = payload.conversation_state.pending_clarification
    if pending is None or pending.type != "entity_selection":
        return None
    match = SELECTION_PATTERN.fullmatch(payload.question)
    direct_label = None
    invalid_selection = False
    if match is None:
        matches = [
            index
            for index, option in enumerate(pending.options)
            if payload.question.strip().casefold() == option.label.strip().casefold()
        ]
        if len(matches) != 1:
            invalid_selection = bool(
                re.fullmatch(
                    r"\s*(?:third|3|neither|none)(?:\s+(?:one|option))?\s*[.!]?\s*",
                    payload.question,
                    re.IGNORECASE,
                )
            )
            if not invalid_selection:
                return None
        else:
            direct_label = matches[0]

    stored = {record.record_id: record for record in catalog.all_records()}
    valid = [
        (index, stored[option.id])
        for index, option in enumerate(pending.options[:20])
        if option.id in stored
    ]
    safe_pending = _clarification(
        (record for _, record in valid),
        allow_multiple=pending.allow_multiple,
        minimum_options=1,
    )
    if invalid_selection:
        return ConversationResolution(
            payload.question,
            safe_pending,
            "That is not a valid option. Please choose from the current options."
            if safe_pending
            else None,
        )
    if direct_label is not None:
        wanted = (direct_label,)
    elif match.group("both"):
        if not pending.allow_multiple:
            return ConversationResolution(
                payload.question,
                safe_pending,
                "Please choose one option; this clarification does not allow multiple selections.",
            )
        wanted = tuple(range(len(pending.options)))
    else:
        position = match.group("ordinal") or match.group("number")
        wanted = (0 if position in ("first", "1") else 1,)
    selected = tuple(record for index, record in valid if index in wanted)
    if len(selected) != len(wanted):
        return ConversationResolution(
            payload.question,
            safe_pending,
            "That selection is no longer available. Please choose a current option."
            if safe_pending
            else None,
        )
    history_text = tuple(
        turn.content for turn in reversed(payload.history) if turn.role == "user"
    )
    intent = _intent((payload.question,) + history_text)
    if pending.id in {
        "clar-guided-prerequisite-course",
        "clar-guided-study-plan-course",
    }:
        intent = "prerequisites"
    return ConversationResolution(
        _question_for(selected, intent),
        selected_record_id=(
            selected[0].record_id
            if len(selected) == 1
            else None
        ),
    )


def resolve_current_session(
    payload: AskRequest,
    catalog: CatalogReader,
    *,
    resolved_course_code: str | None = None,
    resolved_course_record_id: str | None = None,
) -> ConversationResolution:
    """Resolve only entity/constraint meaning; facts always come from retrieval."""

    question = payload.question
    current_codes = _course_refs(question)
    current_years = _years(question)
    pending_clarification = payload.conversation_state.pending_clarification

    # A clarification option label may itself contain a course code, for
    # example ``COMP1100 (2026) — Programming as Problem Solving``. Give the
    # existing pending resolver one opportunity to recognize an exact current
    # option before treating that code as an unrelated explicit new request.
    #
    # `_resolve_pending` returns None for ordinary explicit requests that do
    # not exactly select a pending option, so a genuine correction such as
    # ``Actually, tell me about COMP1110`` still supersedes stale clarification.
    if current_codes and pending_clarification is not None:
        pending_selection = _resolve_pending(payload, catalog)
        if pending_selection is not None:
            return pending_selection

    guided_resolution = _guided_card_resolution(question, catalog)
    if guided_resolution is not None:
        return guided_resolution

    # A current explicit entity, correction or topic switch always defeats stale
    # pending/history. Multiple requested years remain visible as clarification.
    if current_codes:
        if len(current_years) > 1:
            records = _records_for_codes(catalog, current_codes, current_years)
            clarification = _clarification(records, allow_multiple=True)
            if clarification:
                return ConversationResolution(
                    question,
                    clarification,
                    "Please choose the academic year or years you want to compare.",
                )
        return ConversationResolution(question)
    if OTHER_DOMAIN_PATTERN.search(question):
        return ConversationResolution(question)

    pending = _resolve_pending(payload, catalog)
    if pending is not None:
        return pending

    # A previously clarified exact source record outranks expansion of the
    # bare course code back to every academic year. State supplies identity
    # only; every fact is still re-read from the approved repository record.
    if resolved_course_record_id is not None and (
        REFERENCE_PATTERN.search(question)
        or COURSE_FOLLOW_UP_PATTERN.search(question)
    ):
        selected_record = _record_for_id(catalog, resolved_course_record_id)
        if (
            selected_record is not None
            and (
                resolved_course_code is None
                or record_code(selected_record) == resolved_course_code
            )
        ):
            history_text = tuple(
                turn.content
                for turn in reversed(payload.history)
                if turn.role == "user"
            )
            return ConversationResolution(
                _question_for(
                    (selected_record,),
                    _intent((question,) + history_text),
                ),
                selected_record_id=selected_record.record_id,
            )

    # If no exact record selection exists, the retained course identity still
    # supplies the bounded code-level reference introduced by Acceptance Fix 01.
    if resolved_course_code is not None and (
        REFERENCE_PATTERN.search(question)
        or COURSE_FOLLOW_UP_PATTERN.search(question)
    ):
        records = _records_for_codes(
            catalog,
            (resolved_course_code,),
            current_years,
        )
        clarification = _clarification(records, allow_multiple=False)
        if clarification:
            return ConversationResolution(
                question,
                clarification,
                "Which academic year do you mean?",
            )
        if len(records) == 1:
            history_text = tuple(
                turn.content
                for turn in reversed(payload.history)
                if turn.role == "user"
            )
            return ConversationResolution(
                _question_for(
                    records,
                    _intent((question,) + history_text),
                )
            )

    if not (
        REFERENCE_PATTERN.search(question) or COURSE_FOLLOW_UP_PATTERN.search(question)
    ):
        return ConversationResolution(question)

    user_turns = [turn for turn in payload.history if turn.role == "user"]
    if not user_turns:
        return ConversationResolution(question)

    latest_codes = _course_refs(user_turns[-1].content)
    latest_years = _years(user_turns[-1].content)
    if len(latest_codes) == 1:
        codes, years = latest_codes, latest_years
    elif len(latest_codes) > 1:
        records = _records_for_codes(catalog, latest_codes, latest_years)
        clarification = _clarification(records, allow_multiple=False)
        return ConversationResolution(
            question,
            clarification,
            "Which previously mentioned course do you mean?" if clarification else None,
        )
    else:
        all_codes = tuple(
            dict.fromkeys(
                code for turn in user_turns for code in _course_refs(turn.content)
            )
        )
        if len(all_codes) != 1:
            records = _records_for_codes(catalog, all_codes)
            clarification = _clarification(records, allow_multiple=False)
            return ConversationResolution(
                question,
                clarification,
                "Which previously mentioned course do you mean?"
                if clarification
                else None,
            )
        codes, years = all_codes, ()

    # An explicit current year is authoritative. Otherwise only a year from the
    # reliably selected reference turn is inherited.
    years = current_years or years
    records = _records_for_codes(catalog, codes, years)
    clarification = _clarification(records, allow_multiple=False)
    if clarification:
        return ConversationResolution(
            question,
            clarification,
            "Which academic year do you mean?",
        )
    if len(records) != 1:
        return ConversationResolution(question)
    history_text = tuple(
        turn.content for turn in reversed(user_turns)
    )
    return ConversationResolution(
        _question_for(records, _intent((question,) + history_text))
    )
