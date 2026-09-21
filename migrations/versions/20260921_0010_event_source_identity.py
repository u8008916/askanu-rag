"""Enforce the frozen Event source identity relationships.

Revision ID: 20260921_0010
Revises: 20260919_0009
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260921_0010"
down_revision: str | None = "20260919_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT_NAME = "ck_source_records_event_source_identity"
CONSTRAINT_SQL = (
    "domain <> 'events' OR ((source_id = 'events_anu_official' AND "
    "entity_id = metadata_json ->> 'source_event_id') OR "
    "(source_id = 'rubric_unified_search' AND entity_id = 'rubric-' || "
    "(metadata_json ->> 'source_event_id') AND substring(canonical_url "
    "FROM '[?&]eid=([^&#[:space:]]+)') = "
    "metadata_json ->> 'source_event_id'))"
)


def upgrade() -> None:
    op.create_check_constraint(
        CONSTRAINT_NAME,
        "source_records",
        CONSTRAINT_SQL,
    )


def downgrade() -> None:
    op.drop_constraint(
        CONSTRAINT_NAME,
        "source_records",
        type_="check",
    )
