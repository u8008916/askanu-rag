"""Generalise the deployed record table for Scholarships.

Revision ID: 20260913_0002
Revises: 20260911_0001
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260913_0002"
down_revision: str | None = "20260911_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHOLARSHIP_KEYS = """ARRAY[
    'entity_type', 'featured', 'status', 'application_required',
    'study_stage', 'student_type', 'study_level', 'area_of_study',
    'value', 'selection_basis', 'opening_date', 'closing_date', 'eligibility'
]"""


def upgrade() -> None:
    # Rename the deployed table in place. PostgreSQL preserves every row,
    # column, value, index and constraint while the checks are generalized.
    op.rename_table("course_program_records", "source_records")
    op.execute(
        "ALTER TABLE source_records RENAME CONSTRAINT "
        "course_program_records_pkey TO source_records_pkey"
    )
    for old, new in (
        ("ck_course_program_records_required_text", "ck_source_records_required_text"),
        ("ck_course_program_records_status", "ck_source_records_status"),
        ("ck_course_program_records_index_status", "ck_source_records_index_status"),
        ("ck_course_program_records_content_hash", "ck_source_records_content_hash"),
    ):
        op.execute(f"ALTER TABLE source_records RENAME CONSTRAINT {old} TO {new}")
    for old, new in (
        ("ix_course_program_records_title", "ix_source_records_title"),
        ("ix_course_program_records_last_seen_at", "ix_source_records_last_seen_at"),
    ):
        op.execute(f"ALTER INDEX {old} RENAME TO {new}")

    op.drop_index("uq_course_program_records_identity", table_name="source_records")
    for name in (
        "ck_course_program_records_source",
        "ck_course_program_records_domain",
        "ck_course_program_records_entity_type",
        "ck_course_program_records_academic_year",
        "ck_course_program_records_normalized_code",
        "ck_course_program_records_entity_id",
        "ck_course_program_records_record_id",
    ):
        op.drop_constraint(name, "source_records", type_="check")

    op.create_check_constraint(
        "ck_source_records_source_domain",
        "source_records",
        "(source_id = 'courses_programs_and_courses' AND domain = 'courses') OR "
        "(source_id = 'scholarships_anu_finder' AND domain = 'scholarships')",
    )
    op.create_check_constraint(
        "ck_source_records_entity_type",
        "source_records",
        "jsonb_typeof(metadata_json) = 'object' AND "
        "((domain = 'courses' AND metadata_json ->> 'entity_type' IN "
        "('course', 'program')) OR (domain = 'scholarships' AND "
        "metadata_json ->> 'entity_type' = 'scholarship'))",
    )
    op.create_check_constraint(
        "ck_source_records_course_academic_year",
        "source_records",
        "domain <> 'courses' OR (metadata_json ? 'academic_year' AND "
        "metadata_json ->> 'academic_year' ~ '^[0-9]{4}$')",
    )
    op.create_check_constraint(
        "ck_source_records_course_normalized_code",
        "source_records",
        "domain <> 'courses' OR ((metadata_json ->> 'entity_type' = 'course' "
        "AND metadata_json ? 'course_code' AND metadata_json ->> 'course_code' "
        "~ '^[A-Z]{4}[0-9]{4}[A-Z]?$') OR (metadata_json ->> 'entity_type' = "
        "'program' AND metadata_json ? 'program_code' AND char_length("
        "metadata_json ->> 'program_code') > 0 AND metadata_json ->> "
        "'program_code' = upper(btrim(metadata_json ->> 'program_code'))))",
    )
    op.create_check_constraint(
        "ck_source_records_course_entity_id",
        "source_records",
        "domain <> 'courses' OR entity_id = (CASE WHEN metadata_json ->> "
        "'entity_type' = 'course' THEN metadata_json ->> 'course_code' ELSE "
        "metadata_json ->> 'program_code' END) || '_' || "
        "(metadata_json ->> 'academic_year')",
    )
    op.create_check_constraint(
        "ck_source_records_record_id",
        "source_records",
        "(domain = 'courses' AND record_id = 'courses:' || "
        "(metadata_json ->> 'entity_type') || ':' || entity_id) OR "
        "(domain = 'scholarships' AND record_id = "
        "'scholarships:scholarship:' || entity_id)",
    )
    op.create_check_constraint(
        "ck_source_records_scholarship_identity",
        "source_records",
        "domain <> 'scholarships' OR (char_length(entity_id) > 0 AND "
        "canonical_url ~ '^https://([A-Za-z0-9-]+\\.)*anu\\.edu\\.au/.+/.+$' "
        "AND canonical_url !~ '[?#]' AND right(canonical_url, 1) <> '/' AND "
        "reverse(split_part(reverse(canonical_url), '/', 1)) = entity_id)",
    )
    op.create_check_constraint(
        "ck_source_records_scholarship_metadata_keys",
        "source_records",
        f"domain <> 'scholarships' OR (metadata_json ?& {SCHOLARSHIP_KEYS} "
        f"AND metadata_json - {SCHOLARSHIP_KEYS} = '{{}}'::jsonb)",
    )
    op.create_check_constraint(
        "ck_source_records_scholarship_metadata_types",
        "source_records",
        "domain <> 'scholarships' OR ("
        "jsonb_typeof(metadata_json -> 'featured') IN ('boolean', 'null') AND "
        "jsonb_typeof(metadata_json -> 'status') IN ('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'application_required') IN "
        "('boolean', 'null') AND "
        "jsonb_typeof(metadata_json -> 'study_stage') = 'array' AND "
        "jsonb_typeof(metadata_json -> 'student_type') = 'array' AND "
        "jsonb_typeof(metadata_json -> 'study_level') = 'array' AND "
        "jsonb_typeof(metadata_json -> 'area_of_study') = 'array' AND "
        "NOT jsonb_path_exists(metadata_json, "
        "'$.study_stage[*] ? (@.type() != \"string\")') AND "
        "NOT jsonb_path_exists(metadata_json, "
        "'$.student_type[*] ? (@.type() != \"string\")') AND "
        "NOT jsonb_path_exists(metadata_json, "
        "'$.study_level[*] ? (@.type() != \"string\")') AND "
        "NOT jsonb_path_exists(metadata_json, "
        "'$.area_of_study[*] ? (@.type() != \"string\")') AND "
        "jsonb_typeof(metadata_json -> 'value') IN ('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'selection_basis') IN "
        "('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'opening_date') IN ('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'closing_date') IN ('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'eligibility') IN ('string', 'null') AND "
        "(metadata_json ->> 'opening_date' IS NULL OR metadata_json ->> "
        "'opening_date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$') AND "
        "(metadata_json ->> 'closing_date' IS NULL OR metadata_json ->> "
        "'closing_date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'))",
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_source_records_course_program_identity
        ON source_records (
            (metadata_json ->> 'entity_type'),
            (CASE WHEN metadata_json ->> 'entity_type' = 'course'
                  THEN metadata_json ->> 'course_code'
                  ELSE metadata_json ->> 'program_code' END),
            (metadata_json ->> 'academic_year')
        )
        WHERE domain = 'courses'
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_source_records_scholarship_identity
        ON source_records (source_id, entity_id)
        WHERE domain = 'scholarships'
        """
    )
    op.execute(
        """
        CREATE VIEW course_program_records AS
        SELECT record_id, source_id, entity_id, domain, title, content,
               canonical_url, status, effective_from, effective_to,
               collected_at, last_seen_at, content_hash, embedding_version,
               index_status, metadata_json
        FROM source_records
        WHERE source_id = 'courses_programs_and_courses' AND domain = 'courses'
        """
    )


def downgrade() -> None:
    # Refuse rather than delete or hide Scholarship data during rollback.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM source_records WHERE domain <> 'courses') THEN
                RAISE EXCEPTION
                    'Cannot downgrade while non-course source_records exist';
            END IF;
        END
        $$
        """
    )
    op.execute("DROP VIEW course_program_records")
    op.execute("DROP INDEX uq_source_records_scholarship_identity")
    op.execute("DROP INDEX uq_source_records_course_program_identity")
    for name in (
        "ck_source_records_source_domain",
        "ck_source_records_entity_type",
        "ck_source_records_course_academic_year",
        "ck_source_records_course_normalized_code",
        "ck_source_records_course_entity_id",
        "ck_source_records_record_id",
        "ck_source_records_scholarship_identity",
        "ck_source_records_scholarship_metadata_keys",
        "ck_source_records_scholarship_metadata_types",
    ):
        op.drop_constraint(name, "source_records", type_="check")

    op.create_check_constraint(
        "ck_course_program_records_source",
        "source_records",
        "source_id = 'courses_programs_and_courses'",
    )
    op.create_check_constraint(
        "ck_course_program_records_domain",
        "source_records",
        "domain = 'courses'",
    )
    op.create_check_constraint(
        "ck_course_program_records_entity_type",
        "source_records",
        "jsonb_typeof(metadata_json) = 'object' AND metadata_json ? "
        "'entity_type' AND metadata_json ->> 'entity_type' IN "
        "('course', 'program')",
    )
    op.create_check_constraint(
        "ck_course_program_records_academic_year",
        "source_records",
        "metadata_json ? 'academic_year' AND metadata_json ->> "
        "'academic_year' ~ '^[0-9]{4}$'",
    )
    op.create_check_constraint(
        "ck_course_program_records_normalized_code",
        "source_records",
        "(metadata_json ->> 'entity_type' = 'course' AND metadata_json ? "
        "'course_code' AND metadata_json ->> 'course_code' ~ "
        "'^[A-Z]{4}[0-9]{4}[A-Z]?$') OR (metadata_json ->> 'entity_type' = "
        "'program' AND metadata_json ? 'program_code' AND char_length("
        "metadata_json ->> 'program_code') > 0 AND metadata_json ->> "
        "'program_code' = upper(btrim(metadata_json ->> 'program_code')))",
    )
    op.create_check_constraint(
        "ck_course_program_records_entity_id",
        "source_records",
        "entity_id = (CASE WHEN metadata_json ->> 'entity_type' = 'course' "
        "THEN metadata_json ->> 'course_code' ELSE metadata_json ->> "
        "'program_code' END) || '_' || (metadata_json ->> 'academic_year')",
    )
    op.create_check_constraint(
        "ck_course_program_records_record_id",
        "source_records",
        "record_id = 'courses:' || (metadata_json ->> 'entity_type') || ':' "
        "|| entity_id",
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_course_program_records_identity
        ON source_records (
            (metadata_json ->> 'entity_type'),
            (CASE WHEN metadata_json ->> 'entity_type' = 'course'
                  THEN metadata_json ->> 'course_code'
                  ELSE metadata_json ->> 'program_code' END),
            (metadata_json ->> 'academic_year')
        )
        """
    )

    for old, new in (
        ("ix_source_records_title", "ix_course_program_records_title"),
        ("ix_source_records_last_seen_at", "ix_course_program_records_last_seen_at"),
    ):
        op.execute(f"ALTER INDEX {old} RENAME TO {new}")
    for old, new in (
        ("ck_source_records_required_text", "ck_course_program_records_required_text"),
        ("ck_source_records_status", "ck_course_program_records_status"),
        ("ck_source_records_index_status", "ck_course_program_records_index_status"),
        ("ck_source_records_content_hash", "ck_course_program_records_content_hash"),
        ("source_records_pkey", "course_program_records_pkey"),
    ):
        op.execute(f"ALTER TABLE source_records RENAME CONSTRAINT {old} TO {new}")
    op.rename_table("source_records", "course_program_records")
