"""Add the frozen V6 Courses-family and Subplan contract.

Revision ID: 20260915_0006
Revises: 20260915_0005
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260915_0006"
down_revision: str | None = "20260915_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COURSES_ENTITY_TYPES = "('course', 'program', 'major', 'minor', 'specialisation')"
SUBPLAN_ENTITY_TYPES = "('major', 'minor', 'specialisation')"
SUBPLAN_KEYS = """ARRAY[
    'entity_type', 'subplan_code', 'academic_year', 'career', 'units',
    'subplan_type', 'overview', 'learning_outcomes', 'requirements',
    'relevant_degrees', 'other_information'
]"""
VIEW_COLUMNS = """
record_id, source_id, entity_id, domain, title, content,
canonical_url, status, effective_from, effective_to,
collected_at, last_seen_at, content_hash, embedding_version,
index_status, metadata_json
"""


def _courses_code_expression() -> str:
    return """CASE
        WHEN metadata_json ->> 'entity_type' = 'course'
            THEN metadata_json ->> 'course_code'
        WHEN metadata_json ->> 'entity_type' = 'program'
            THEN metadata_json ->> 'program_code'
        ELSE metadata_json ->> 'subplan_code'
    END"""


def _create_entity_type_check(*, include_subplans: bool) -> None:
    course_types = COURSES_ENTITY_TYPES if include_subplans else "('course', 'program')"
    op.create_check_constraint(
        "ck_source_records_entity_type",
        "source_records",
        "jsonb_typeof(metadata_json) = 'object' AND "
        f"((domain = 'courses' AND metadata_json ->> 'entity_type' IN {course_types}) "
        "OR (domain = 'scholarships' AND metadata_json ->> 'entity_type' = "
        "'scholarship') OR (domain = 'jobs' AND metadata_json ->> 'entity_type' = "
        "'job') OR (domain = 'accommodation' AND metadata_json ->> "
        "'entity_type' = 'accommodation') OR (domain = 'support' AND "
        "metadata_json ->> 'entity_type' = 'support_service'))",
    )


def _create_courses_constraints(*, include_subplans: bool) -> None:
    if include_subplans:
        normalized_code = (
            "domain <> 'courses' OR ((metadata_json ->> 'entity_type' = 'course' "
            "AND metadata_json ? 'course_code' AND metadata_json ->> 'course_code' "
            "~ '^[A-Z]{4}[0-9]{4}[A-Z]?$') OR (metadata_json ->> 'entity_type' = "
            "'program' AND metadata_json ? 'program_code' AND char_length(metadata_json "
            "->> 'program_code') > 0 AND metadata_json ->> 'program_code' = "
            "upper(btrim(metadata_json ->> 'program_code'))) OR (metadata_json ->> "
            f"'entity_type' IN {SUBPLAN_ENTITY_TYPES} AND metadata_json ? "
            "'subplan_code' AND char_length(metadata_json ->> 'subplan_code') > 0 AND "
            "metadata_json ->> 'subplan_code' = upper(btrim(metadata_json ->> "
            "'subplan_code'))))"
        )
        code_expression = _courses_code_expression()
    else:
        normalized_code = (
            "domain <> 'courses' OR ((metadata_json ->> 'entity_type' = 'course' "
            "AND metadata_json ? 'course_code' AND metadata_json ->> 'course_code' "
            "~ '^[A-Z]{4}[0-9]{4}[A-Z]?$') OR (metadata_json ->> 'entity_type' = "
            "'program' AND metadata_json ? 'program_code' AND char_length(metadata_json "
            "->> 'program_code') > 0 AND metadata_json ->> 'program_code' = "
            "upper(btrim(metadata_json ->> 'program_code'))))"
        )
        code_expression = """CASE WHEN metadata_json ->> 'entity_type' = 'course'
            THEN metadata_json ->> 'course_code'
            ELSE metadata_json ->> 'program_code' END"""
    op.create_check_constraint(
        "ck_source_records_course_normalized_code",
        "source_records",
        normalized_code,
    )
    op.create_check_constraint(
        "ck_source_records_course_entity_id",
        "source_records",
        f"domain <> 'courses' OR entity_id = ({code_expression}) || '_' || "
        "(metadata_json ->> 'academic_year')",
    )


def _create_course_program_view() -> None:
    op.execute(
        f"""
        CREATE VIEW course_program_records AS
        SELECT {VIEW_COLUMNS}
        FROM source_records
        WHERE source_id = 'courses_programs_and_courses'
          AND domain = 'courses'
          AND metadata_json ->> 'entity_type' IN ('course', 'program')
        OFFSET 0
        """
    )


def upgrade() -> None:
    # Only the exact legacy uppercase-code URL shape is normalized. Unexpected
    # existing Courses URLs fail rather than being silently rewritten.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM source_records
                WHERE domain = 'courses'
                  AND metadata_json ->> 'entity_type' IN ('course', 'program')
                  AND canonical_url NOT IN (
                      'https://programsandcourses.anu.edu.au/' ||
                      (metadata_json ->> 'academic_year') || '/' ||
                      (metadata_json ->> 'entity_type') || '/' ||
                      lower(CASE
                          WHEN metadata_json ->> 'entity_type' = 'course'
                              THEN metadata_json ->> 'course_code'
                          ELSE metadata_json ->> 'program_code'
                      END),
                      'https://programsandcourses.anu.edu.au/' ||
                      (metadata_json ->> 'academic_year') || '/' ||
                      (metadata_json ->> 'entity_type') || '/' ||
                      (CASE
                          WHEN metadata_json ->> 'entity_type' = 'course'
                              THEN metadata_json ->> 'course_code'
                          ELSE metadata_json ->> 'program_code'
                      END)
                  )
            ) THEN
                RAISE EXCEPTION 'Cannot normalize unexpected Courses canonical URL';
            END IF;
        END
        $$
        """
    )
    op.execute(
        """
        UPDATE source_records
        SET canonical_url = 'https://programsandcourses.anu.edu.au/' ||
            (metadata_json ->> 'academic_year') || '/' ||
            (metadata_json ->> 'entity_type') || '/' ||
            lower(CASE
                WHEN metadata_json ->> 'entity_type' = 'course'
                    THEN metadata_json ->> 'course_code'
                ELSE metadata_json ->> 'program_code'
            END)
        WHERE domain = 'courses'
          AND metadata_json ->> 'entity_type' IN ('course', 'program')
        """
    )

    op.execute("DROP VIEW course_program_records")
    op.drop_index(
        "uq_source_records_course_program_identity", table_name="source_records"
    )
    for name in (
        "ck_source_records_entity_type",
        "ck_source_records_course_normalized_code",
        "ck_source_records_course_entity_id",
    ):
        op.drop_constraint(name, "source_records", type_="check")

    _create_entity_type_check(include_subplans=True)
    _create_courses_constraints(include_subplans=True)
    op.create_check_constraint(
        "ck_source_records_courses_canonical_url",
        "source_records",
        "domain <> 'courses' OR (canonical_url ~ "
        "'^https://programsandcourses[.]anu[.]edu[.]au/[0-9]{4}/"
        "(course|program|major|minor|specialisation)/"
        "[a-z0-9][a-z0-9._-]*$' AND canonical_url = "
        "'https://programsandcourses.anu.edu.au/' || "
        "(metadata_json ->> 'academic_year') || '/' || "
        "(metadata_json ->> 'entity_type') || '/' || lower(("
        + _courses_code_expression()
        + ")))",
    )
    op.create_check_constraint(
        "ck_source_records_subplan_metadata",
        "source_records",
        f"metadata_json ->> 'entity_type' NOT IN {SUBPLAN_ENTITY_TYPES} OR ("
        f"metadata_json ?& {SUBPLAN_KEYS} AND "
        f"metadata_json - {SUBPLAN_KEYS} = '{{}}'::jsonb AND "
        "jsonb_typeof(metadata_json -> 'subplan_code') = 'string' AND "
        "jsonb_typeof(metadata_json -> 'academic_year') = 'string' AND "
        "jsonb_typeof(metadata_json -> 'career') IN ('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'units') IN ('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'subplan_type') IN ('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'overview') IN ('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'learning_outcomes') IN ('array', 'null') AND "
        "(jsonb_typeof(metadata_json -> 'learning_outcomes') = 'null' OR "
        "NOT jsonb_path_exists(metadata_json, "
        "'$.learning_outcomes[*] ? (@.type() != \"string\")')) AND "
        "jsonb_typeof(metadata_json -> 'requirements') IN ('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'relevant_degrees') IN ('array', 'null') AND "
        "(jsonb_typeof(metadata_json -> 'relevant_degrees') = 'null' OR "
        "NOT jsonb_path_exists(metadata_json, "
        "'$.relevant_degrees[*] ? (@.type() != \"string\")')) AND "
        "jsonb_typeof(metadata_json -> 'other_information') IN ('string', 'null'))",
    )
    op.create_check_constraint(
        "ck_source_records_courses_optional_metadata_types",
        "source_records",
        "domain <> 'courses' OR ("
        "(NOT metadata_json ? 'description' OR jsonb_typeof(metadata_json -> "
        "'description') IN ('string', 'null')) AND "
        "(NOT metadata_json ? 'corequisites' OR jsonb_typeof(metadata_json -> "
        "'corequisites') IN ('string', 'null')) AND "
        "(NOT metadata_json ? 'overview' OR jsonb_typeof(metadata_json -> "
        "'overview') IN ('string', 'null')) AND "
        "(NOT metadata_json ? 'program_requirements' OR jsonb_typeof(metadata_json -> "
        "'program_requirements') IN ('string', 'null')) AND "
        "(NOT metadata_json ? 'admission_requirements' OR jsonb_typeof(metadata_json -> "
        "'admission_requirements') IN ('string', 'null')) AND "
        "(NOT metadata_json ? 'prerequisites' OR jsonb_typeof(metadata_json -> "
        "'prerequisites') IN ('string', 'null')) AND "
        "(NOT metadata_json ? 'learning_outcomes' OR jsonb_typeof(metadata_json -> "
        "'learning_outcomes') IN ('array', 'null')) AND "
        "(NOT metadata_json ? 'learning_outcomes' OR "
        "jsonb_typeof(metadata_json -> 'learning_outcomes') = 'null' OR "
        "NOT jsonb_path_exists(metadata_json, "
        "'$.learning_outcomes[*] ? (@.type() != \"string\")')))",
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX uq_source_records_courses_identity
        ON source_records (
            (metadata_json ->> 'entity_type'),
            ({_courses_code_expression()}),
            (metadata_json ->> 'academic_year')
        )
        WHERE domain = 'courses'
        """
    )
    _create_course_program_view()


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM source_records
                WHERE domain = 'courses'
                  AND metadata_json ->> 'entity_type' IN
                      ('major', 'minor', 'specialisation')
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade while Courses subplan records exist';
            END IF;
        END
        $$
        """
    )
    op.execute("DROP VIEW course_program_records")
    op.execute("DROP INDEX uq_source_records_courses_identity")
    for name in (
        "ck_source_records_courses_canonical_url",
        "ck_source_records_subplan_metadata",
        "ck_source_records_courses_optional_metadata_types",
        "ck_source_records_entity_type",
        "ck_source_records_course_normalized_code",
        "ck_source_records_course_entity_id",
    ):
        op.drop_constraint(name, "source_records", type_="check")

    _create_entity_type_check(include_subplans=False)
    _create_courses_constraints(include_subplans=False)
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
    _create_course_program_view()
