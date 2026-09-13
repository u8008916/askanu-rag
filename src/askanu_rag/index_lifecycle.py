"""Pure indexing lifecycle policy at the future worker adapter boundary.

This module deliberately performs no database writes and no embedding work. It
turns the frozen record/index states into explicit decisions that a reviewed
worker can consume later without confusing sparse local ranking with embedding
success.
"""

from dataclasses import dataclass
from enum import Enum

from askanu_rag.models import CommonRecord, IndexStatus


class IndexAction(str, Enum):
    NONE = "NONE"
    INDEX_CONTENT_CHANGE = "INDEX_CONTENT_CHANGE"
    RETRY = "RETRY"
    REINDEX_VERSION = "REINDEX_VERSION"
    APPLY_SUCCESS = "APPLY_SUCCESS"
    APPLY_FAILURE = "APPLY_FAILURE"
    DISCARD_STALE_RESULT = "DISCARD_STALE_RESULT"


class LifecycleContractError(ValueError):
    """A record/result combination violates the frozen lifecycle contract."""


@dataclass(frozen=True)
class IndexDecision:
    action: IndexAction
    index_status: IndexStatus
    embedding_version: str | None
    reason: str


@dataclass(frozen=True)
class IndexTaskIdentity:
    """Immutable identity captured when an indexing task is created."""

    record_id: str
    content_hash: str
    target_version: str


def index_is_stale(
    record: CommonRecord, *, target_version: str | None = None
) -> bool:
    """Return whether a persistent index is unusable for this record/request.

    ``last_seen_at`` is intentionally absent: observing a source does not prove
    that its content was embedded. NEW/CHANGED records clear the version at the
    ingestion boundary, while FAILED/PENDING and version mismatch are explicit
    evidence that the persistent index is not usable for current content/target.
    """

    if record.index_status != "INDEXED" or not record.embedding_version:
        return True
    return target_version is not None and record.embedding_version != target_version


def plan_index_action(
    record: CommonRecord,
    *,
    explicit_retry: bool = False,
    target_version: str | None = None,
) -> IndexDecision:
    """Translate the existing stored state into one non-mutating worker action."""

    if record.status in ("NEW", "CHANGED"):
        if record.index_status != "PENDING" or record.embedding_version is not None:
            raise LifecycleContractError(
                "NEW/CHANGED records must be PENDING with no embedding version."
            )
        return IndexDecision(
            IndexAction.INDEX_CONTENT_CHANGE,
            "PENDING",
            None,
            "New or changed current content requires indexing.",
        )

    if record.status == "MISSING":
        return IndexDecision(
            IndexAction.NONE,
            record.index_status,
            record.embedding_version,
            "Missing observation preserves last-known-good state and emits no work.",
        )

    # UNCHANGED never creates a second content-change signal. Retry/version
    # rollout is an explicit indexing-owner action and remains distinguishable.
    if explicit_retry and record.index_status in ("PENDING", "FAILED"):
        return IndexDecision(
            IndexAction.RETRY,
            record.index_status,
            record.embedding_version,
            "Explicit retry of an unchanged incomplete/failed record.",
        )
    if (
        explicit_retry
        and target_version is not None
        and record.index_status == "INDEXED"
        and record.embedding_version != target_version
    ):
        return IndexDecision(
            IndexAction.REINDEX_VERSION,
            record.index_status,
            record.embedding_version,
            "Explicit target-version rollout; no source content change occurred.",
        )
    return IndexDecision(
        IndexAction.NONE,
        record.index_status,
        record.embedding_version,
        "Unchanged content preserves index state/version and emits no work.",
    )


def resolve_index_result(
    current: CommonRecord,
    task: IndexTaskIdentity,
    *,
    succeeded: bool,
    produced_version: str | None = None,
) -> IndexDecision:
    """Validate a worker result without allowing an old task to win a race.

    The caller may persist APPLY_SUCCESS/APPLY_FAILURE using a compare-and-set on
    ``record_id`` plus ``content_hash``. No such writer exists in today's RAG.
    """

    if task.record_id != current.record_id or task.content_hash != current.content_hash:
        return IndexDecision(
            IndexAction.DISCARD_STALE_RESULT,
            current.index_status,
            current.embedding_version,
            "Task identity no longer matches current stored content.",
        )
    if succeeded:
        if not produced_version or produced_version != task.target_version:
            raise LifecycleContractError(
                "Successful indexing must report the task target version."
            )
        return IndexDecision(
            IndexAction.APPLY_SUCCESS,
            "INDEXED",
            produced_version,
            "Matching task completed successfully.",
        )
    return IndexDecision(
        IndexAction.APPLY_FAILURE,
        "FAILED",
        current.embedding_version,
        "Matching task failed; never report current content as indexed.",
    )
