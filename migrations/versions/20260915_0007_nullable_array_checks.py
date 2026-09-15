"""Make nullable V6 array checks consistent with the validated model contract.

Revision ID: 20260915_0007
Revises: 20260915_0006
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260915_0007"
down_revision: str | None = "20260915_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SUBPLAN_ENTITY_TYPES = "('major', 'minor', 'specialisation')"

SUBPLAN_KEYS = """ARRAY[
    'entity_type', 'subplan_code', 'academic_year', 'career', 'units',
    'subplan_type', 'overview', 'learning_outcomes', 'requirements',
    'relevant_degrees', 'other_information'
]"""


JOB_METADATA_TYPES = """
domain <> 'jobs' OR (
    jsonb_typeof(metadata_json -> 'job_id') = 'string'
    AND jsonb_typeof(metadata_json -> 'category') IN ('string', 'null')
    AND jsonb_typeof(metadata_json -> 'employment_types') = 'array'
    AND NOT jsonb_path_exists(
        metadata_json,
        '$.employment_types[*] ? (@.type() != "string")'
    )
    AND jsonb_typeof(metadata_json -> 'location') IN ('string', 'null')
    AND jsonb_typeof(metadata_json -> 'classification') IN ('string', 'null')
    AND jsonb_typeof(metadata_json -> 'salary') IN ('string', 'null')
    AND jsonb_typeof(metadata_json -> 'closing_text') IN ('string', 'null')
    AND jsonb_typeof(metadata_json -> 'closing_date') IN ('string', 'null')
    AND jsonb_typeof(metadata_json -> 'closing_at') IN ('string', 'null')
    AND jsonb_typeof(metadata_json -> 'status') IN ('string', 'null')
    AND jsonb_typeof(metadata_json -> 'summary') IN ('string', 'null')
    AND jsonb_typeof(metadata_json -> 'role_requirements') IN ('array', 'null')
    AND (
        jsonb_typeof(metadata_json -> 'role_requirements') = 'null'
        OR NOT jsonb_path_exists(
            metadata_json,
            '$.role_requirements[*] ? (@.type() != "string")'
        )
    )
    AND (
        metadata_json ->> 'status' IS NULL
        OR metadata_json ->> 'status' IN ('current', 'closed')
    )
    AND (
        metadata_json ->> 'closing_date' IS NULL
        OR (
            metadata_json ->> 'closing_date'
                ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
            AND to_char(
                (metadata_json ->> 'closing_date')::date,
                'YYYY-MM-DD'
            ) = metadata_json ->> 'closing_date'
        )
    )
    AND (
        metadata_json ->> 'closing_at' IS NULL
        OR (
            metadata_json ->> 'closing_at'
                ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2}([.][0-9]+)?)?(Z|[+-][0-9]{2}:[0-9]{2})$'
            AND (metadata_json ->> 'closing_at')::timestamptz IS NOT NULL
        )
    )
)
"""


COURSES_OPTIONAL_METADATA_TYPES = """
domain <> 'courses' OR (
    (
        NOT metadata_json ? 'description'
        OR jsonb_typeof(metadata_json -> 'description') IN ('string', 'null')
    )
    AND (
        NOT metadata_json ? 'corequisites'
        OR jsonb_typeof(metadata_json -> 'corequisites') IN ('string', 'null')
    )
    AND (
        NOT metadata_json ? 'overview'
        OR jsonb_typeof(metadata_json -> 'overview') IN ('string', 'null')
    )
    AND (
        NOT metadata_json ? 'program_requirements'
        OR jsonb_typeof(metadata_json -> 'program_requirements')
            IN ('string', 'null')
    )
    AND (
        NOT metadata_json ? 'admission_requirements'
        OR jsonb_typeof(metadata_json -> 'admission_requirements')
            IN ('string', 'null')
    )
    AND (
        NOT metadata_json ? 'prerequisites'
        OR jsonb_typeof(metadata_json -> 'prerequisites') IN ('string', 'null')
    )
    AND (
        NOT metadata_json ? 'learning_outcomes'
        OR jsonb_typeof(metadata_json -> 'learning_outcomes')
            IN ('array', 'null')
    )
    AND (
        NOT metadata_json ? 'learning_outcomes'
        OR jsonb_typeof(metadata_json -> 'learning_outcomes') = 'null'
        OR NOT jsonb_path_exists(
            metadata_json,
            '$.learning_outcomes[*] ? (@.type() != "string")'
        )
    )
)
"""


SUBPLAN_METADATA = f"""
metadata_json ->> 'entity_type' NOT IN {SUBPLAN_ENTITY_TYPES}
OR (
    metadata_json ?& {SUBPLAN_KEYS}
    AND metadata_json - {SUBPLAN_KEYS} = '{{}}'::jsonb
    AND jsonb_typeof(metadata_json -> 'subplan_code') = 'string'
    AND jsonb_typeof(metadata_json -> 'academic_year') = 'string'
    AND jsonb_typeof(metadata_json -> 'career') IN ('string', 'null')
    AND jsonb_typeof(metadata_json -> 'units') IN ('string', 'null')
    AND jsonb_typeof(metadata_json -> 'subplan_type') IN ('string', 'null')
    AND jsonb_typeof(metadata_json -> 'overview') IN ('string', 'null')
    AND jsonb_typeof(metadata_json -> 'learning_outcomes') IN ('array', 'null')
    AND (
        jsonb_typeof(metadata_json -> 'learning_outcomes') = 'null'
        OR NOT jsonb_path_exists(
            metadata_json,
            '$.learning_outcomes[*] ? (@.type() != "string")'
        )
    )
    AND jsonb_typeof(metadata_json -> 'requirements') IN ('string', 'null')
    AND jsonb_typeof(metadata_json -> 'relevant_degrees') IN ('array', 'null')
    AND (
        jsonb_typeof(metadata_json -> 'relevant_degrees') = 'null'
        OR NOT jsonb_path_exists(
            metadata_json,
            '$.relevant_degrees[*] ? (@.type() != "string")'
        )
    )
    AND jsonb_typeof(metadata_json -> 'other_information') IN ('string', 'null')
)
"""


def upgrade() -> None:
    for name in (
        "ck_source_records_job_metadata_types",
        "ck_source_records_subplan_metadata",
        "ck_source_records_courses_optional_metadata_types",
    ):
        op.drop_constraint(name, "source_records", type_="check")

    op.create_check_constraint(
        "ck_source_records_job_metadata_types",
        "source_records",
        JOB_METADATA_TYPES,
    )
    op.create_check_constraint(
        "ck_source_records_subplan_metadata",
        "source_records",
        SUBPLAN_METADATA,
    )
    op.create_check_constraint(
        "ck_source_records_courses_optional_metadata_types",
        "source_records",
        COURSES_OPTIONAL_METADATA_TYPES,
    )


def downgrade() -> None:
    # Deliberately preserve the null-safe constraint semantics.
    #
    # Reinstating the known-invalid 0005/0006 predicates would reject records
    # that those revisions' validated Python contracts explicitly allow.
    # A further downgrade through 0006/0005 still removes/replaces the named
    # constraints as part of those revisions' own downgrade logic.
    pass
