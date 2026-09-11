"""Create the shared course/program record and ingestion-run tables.

Revision ID: 20260911_0001
Revises: None
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260911_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "course_program_records",
        sa.Column("record_id", sa.Text(), primary_key=True),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding_version", sa.Text(), nullable=True),
        sa.Column("index_status", sa.Text(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            "source_id = 'courses_programs_and_courses'",
            name="ck_course_program_records_source",
        ),
        sa.CheckConstraint(
            "domain = 'courses'",
            name="ck_course_program_records_domain",
        ),
        sa.CheckConstraint(
            "char_length(title) > 0 AND char_length(content) > 0 "
            "AND char_length(canonical_url) > 0",
            name="ck_course_program_records_required_text",
        ),
        sa.CheckConstraint(
            "status IN ('NEW', 'CHANGED', 'UNCHANGED', 'MISSING')",
            name="ck_course_program_records_status",
        ),
        sa.CheckConstraint(
            "index_status IN ('PENDING', 'INDEXED', 'FAILED')",
            name="ck_course_program_records_index_status",
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_course_program_records_content_hash",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(metadata_json) = 'object' "
            "AND metadata_json ? 'entity_type' "
            "AND metadata_json ->> 'entity_type' IN ('course', 'program')",
            name="ck_course_program_records_entity_type",
        ),
        sa.CheckConstraint(
            "metadata_json ? 'academic_year' "
            "AND metadata_json ->> 'academic_year' ~ '^[0-9]{4}$'",
            name="ck_course_program_records_academic_year",
        ),
        sa.CheckConstraint(
            "(metadata_json ->> 'entity_type' = 'course' "
            "AND metadata_json ? 'course_code' "
            "AND metadata_json ->> 'course_code' ~ '^[A-Z]{4}[0-9]{4}[A-Z]?$') "
            "OR (metadata_json ->> 'entity_type' = 'program' "
            "AND metadata_json ? 'program_code' "
            "AND char_length(metadata_json ->> 'program_code') > 0 "
            "AND metadata_json ->> 'program_code' = "
            "upper(btrim(metadata_json ->> 'program_code')))",
            name="ck_course_program_records_normalized_code",
        ),
        sa.CheckConstraint(
            "entity_id = (CASE WHEN metadata_json ->> 'entity_type' = 'course' "
            "THEN metadata_json ->> 'course_code' "
            "ELSE metadata_json ->> 'program_code' END) || '_' || "
            "(metadata_json ->> 'academic_year')",
            name="ck_course_program_records_entity_id",
        ),
        sa.CheckConstraint(
            "record_id = 'courses:' || (metadata_json ->> 'entity_type') || ':' "
            "|| entity_id",
            name="ck_course_program_records_record_id",
        ),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_course_program_records_identity
        ON course_program_records (
            (metadata_json ->> 'entity_type'),
            (CASE WHEN metadata_json ->> 'entity_type' = 'course'
                  THEN metadata_json ->> 'course_code'
                  ELSE metadata_json ->> 'program_code' END),
            (metadata_json ->> 'academic_year')
        )
        """
    )
    op.create_index(
        "ix_course_program_records_title",
        "course_program_records",
        ["title"],
        unique=False,
    )
    op.create_index(
        "ix_course_program_records_last_seen_at",
        "course_program_records",
        ["last_seen_at"],
        unique=False,
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("run_id", sa.Text(), primary_key=True),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "records_seen",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "records_added",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "records_changed",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "records_unchanged",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "records_missing",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "char_length(btrim(run_id)) > 0 "
            "AND char_length(btrim(source_id)) > 0",
            name="ck_ingestion_runs_required_identity",
        ),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'SUCCESS', 'FAILED', 'SUSPICIOUS_ZERO')",
            name="ck_ingestion_runs_status",
        ),
        sa.CheckConstraint(
            "records_seen >= 0 AND records_added >= 0 "
            "AND records_changed >= 0 AND records_unchanged >= 0 "
            "AND records_missing >= 0",
            name="ck_ingestion_runs_non_negative_counts",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="ck_ingestion_runs_timestamp_order",
        ),
    )
    op.create_index(
        "ix_ingestion_runs_source_started_at",
        "ingestion_runs",
        ["source_id", "started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("ingestion_runs")
    op.drop_table("course_program_records")
