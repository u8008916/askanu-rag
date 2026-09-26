"""Generic stable presentation paging over retained V7 ResultSets."""

from __future__ import annotations

from dataclasses import dataclass

from askanu_rag.models.contracts import ResultPage, ResultPageRequest
from askanu_rag.models.conversation_state import (
    ConversationState,
    QueryInterpretation,
    ResultSet,
    ResultSetStatus,
)


class ResultPageResolutionError(ValueError):
    """Untrusted paging state cannot be resolved safely."""


@dataclass(frozen=True)
class ResolvedResultPage:
    result_set: ResultSet
    start_ordinal: int
    limit: int


def resolve_result_page(
    state: ConversationState,
    interpretation: QueryInterpretation,
    requested: ResultPageRequest | None,
) -> ResolvedResultPage | None:
    """Resolve only server-retained page position and ordering metadata."""

    if requested is not None:
        result_set_id = requested.result_set_id
        start_ordinal = requested.start_ordinal
        limit = requested.limit
    elif (
        interpretation.intent is not None
        and interpretation.intent.operation == "continue_results"
        and interpretation.referenced_result_set_id is not None
    ):
        result_set_id = interpretation.referenced_result_set_id
        cursor = state.result_page
        if (
            state.focus is None
            or state.focus.result_set_id != result_set_id
            or cursor is None
            or cursor.result_set_id != result_set_id
        ):
            return None
        start_ordinal = cursor.next_ordinal
        limit = 5
    else:
        return None
    result_set = next(
        (
            item
            for item in state.result_sets
            if item.result_set_id == result_set_id
            and item.status == ResultSetStatus.RESULTS
        ),
        None,
    )
    if result_set is None or start_ordinal > len(
        result_set.ordered_canonical_ids
    ) + 1:
        return None
    return ResolvedResultPage(result_set, start_ordinal, limit)


def result_page_metadata(
    result_set: ResultSet,
    *,
    start_ordinal: int,
    returned: int,
) -> tuple[ResultPage, int]:
    """Describe a contiguous page and return the next server cursor."""

    continuation_ordinal = start_ordinal + returned
    has_more = continuation_ordinal <= len(result_set.ordered_canonical_ids)
    return (
        ResultPage(
            result_set_id=result_set.result_set_id,
            start_ordinal=start_ordinal,
            returned=returned,
            has_more=has_more,
            next_ordinal=continuation_ordinal if has_more else None,
        ),
        continuation_ordinal,
    )
