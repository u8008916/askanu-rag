"""Make the Courses/Programs compatibility view structurally read-only.

Revision ID: 20260914_0003
Revises: 20260913_0002
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260914_0003"
down_revision: str | None = "20260913_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VIEW_COLUMNS = """
record_id, source_id, entity_id, domain, title, content,
canonical_url, status, effective_from, effective_to,
collected_at, last_seen_at, content_hash, embedding_version,
index_status, metadata_json
"""

COURSE_PROGRAM_FILTER = """
source_id = 'courses_programs_and_courses' AND domain = 'courses'
"""


def _create_course_program_view(*, structurally_read_only: bool) -> None:
    # PostgreSQL classifies a view with a top-level OFFSET as non-updatable.
    # OFFSET 0 preserves the exact rows, columns, values and unordered SELECT
    # semantics while preventing automatic INSERT/UPDATE/DELETE rewriting.
    structural_guard = "OFFSET 0" if structurally_read_only else ""
    op.execute(
        f"""
        CREATE VIEW course_program_records AS
        SELECT {VIEW_COLUMNS}
        FROM source_records
        WHERE {COURSE_PROGRAM_FILTER}
        {structural_guard}
        """
    )


def upgrade() -> None:
    op.execute("DROP VIEW course_program_records")
    _create_course_program_view(structurally_read_only=True)


def downgrade() -> None:
    op.execute("DROP VIEW course_program_records")
    _create_course_program_view(structurally_read_only=False)
