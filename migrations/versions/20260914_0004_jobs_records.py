"""Add the frozen Jobs normalized record contract.

Revision ID: 20260914_0004
Revises: 20260914_0003
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260914_0004"
down_revision: str | None = "20260914_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JOB_KEYS = """ARRAY[
    'entity_type', 'job_id', 'category', 'employment_types', 'location',
    'classification', 'salary', 'closing_text', 'closing_date', 'closing_at',
    'status', 'summary'
]"""


def _create_shared_checks(*, include_jobs: bool) -> None:
    source_domain = (
        "(source_id = 'courses_programs_and_courses' AND domain = 'courses') OR "
        "(source_id = 'scholarships_anu_finder' AND domain = 'scholarships')"
    )
    entity_type = (
        "jsonb_typeof(metadata_json) = 'object' AND "
        "((domain = 'courses' AND metadata_json ->> 'entity_type' IN "
        "('course', 'program')) OR (domain = 'scholarships' AND "
        "metadata_json ->> 'entity_type' = 'scholarship')"
    )
    record_id = (
        "(domain = 'courses' AND record_id = 'courses:' || "
        "(metadata_json ->> 'entity_type') || ':' || entity_id) OR "
        "(domain = 'scholarships' AND record_id = "
        "'scholarships:scholarship:' || entity_id)"
    )
    if include_jobs:
        source_domain += (
            " OR (source_id = 'jobs_anu_search' AND domain = 'jobs')"
        )
        entity_type += (
            " OR (domain = 'jobs' AND metadata_json ->> 'entity_type' = 'job')"
        )
        record_id += (
            " OR (domain = 'jobs' AND record_id = 'jobs:job:' || entity_id)"
        )
    op.create_check_constraint(
        "ck_source_records_source_domain", "source_records", source_domain
    )
    op.create_check_constraint(
        "ck_source_records_entity_type", "source_records", entity_type + ")"
    )
    op.create_check_constraint(
        "ck_source_records_record_id", "source_records", record_id
    )


def upgrade() -> None:
    for name in (
        "ck_source_records_source_domain",
        "ck_source_records_entity_type",
        "ck_source_records_record_id",
    ):
        op.drop_constraint(name, "source_records", type_="check")
    _create_shared_checks(include_jobs=True)

    op.create_check_constraint(
        "ck_source_records_job_identity",
        "source_records",
        "domain <> 'jobs' OR (entity_id ~ '^[0-9]+$' AND "
        "metadata_json ? 'job_id' AND metadata_json ->> 'job_id' = entity_id)",
    )
    op.create_check_constraint(
        "ck_source_records_job_canonical_url",
        "source_records",
        "domain <> 'jobs' OR canonical_url ~ "
        "'^https://jobs[.]anu[.]edu[.]au/jobs/[^/?#[:space:]]+$'",
    )
    op.create_check_constraint(
        "ck_source_records_job_effective_dates",
        "source_records",
        "domain <> 'jobs' OR "
        "(effective_from IS NULL AND effective_to IS NULL)",
    )
    op.create_check_constraint(
        "ck_source_records_job_metadata_keys",
        "source_records",
        f"domain <> 'jobs' OR (metadata_json ?& {JOB_KEYS} "
        f"AND metadata_json - {JOB_KEYS} = '{{}}'::jsonb)",
    )
    op.create_check_constraint(
        "ck_source_records_job_metadata_types",
        "source_records",
        "domain <> 'jobs' OR ("
        "jsonb_typeof(metadata_json -> 'job_id') = 'string' AND "
        "jsonb_typeof(metadata_json -> 'category') IN ('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'employment_types') = 'array' AND "
        "NOT jsonb_path_exists(metadata_json, "
        "'$.employment_types[*] ? (@.type() != \"string\")') AND "
        "jsonb_typeof(metadata_json -> 'location') IN ('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'classification') IN "
        "('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'salary') IN ('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'closing_text') IN "
        "('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'closing_date') IN "
        "('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'closing_at') IN ('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'status') IN ('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'summary') IN ('string', 'null') AND "
        "(metadata_json ->> 'status' IS NULL OR "
        "metadata_json ->> 'status' IN ('current', 'closed')) AND "
        "(metadata_json ->> 'closing_date' IS NULL OR "
        "(metadata_json ->> 'closing_date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' "
        "AND to_char((metadata_json ->> 'closing_date')::date, 'YYYY-MM-DD') = "
        "metadata_json ->> 'closing_date')) AND "
        "(metadata_json ->> 'closing_at' IS NULL OR "
        "(metadata_json ->> 'closing_at' ~ "
        "'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}"
        "(:[0-9]{2}([.][0-9]+)?)?(Z|[+-][0-9]{2}:[0-9]{2})$' AND "
        "(metadata_json ->> 'closing_at')::timestamptz IS NOT NULL)))",
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_source_records_job_identity
        ON source_records (source_id, entity_id)
        WHERE domain = 'jobs'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM source_records WHERE domain = 'jobs') THEN
                RAISE EXCEPTION 'Cannot downgrade while Jobs source_records exist';
            END IF;
        END
        $$
        """
    )
    op.execute("DROP INDEX uq_source_records_job_identity")
    for name in (
        "ck_source_records_job_identity",
        "ck_source_records_job_canonical_url",
        "ck_source_records_job_effective_dates",
        "ck_source_records_job_metadata_keys",
        "ck_source_records_job_metadata_types",
        "ck_source_records_source_domain",
        "ck_source_records_entity_type",
        "ck_source_records_record_id",
    ):
        op.drop_constraint(name, "source_records", type_="check")
    _create_shared_checks(include_jobs=False)
