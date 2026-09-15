"""Add V6 resource contracts and shared retrieval-unit embeddings.

Revision ID: 20260915_0005
Revises: 20260914_0004
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260915_0005"
down_revision: str | None = "20260914_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JOB_KEYS_V1 = """ARRAY[
    'entity_type', 'job_id', 'category', 'employment_types', 'location',
    'classification', 'salary', 'closing_text', 'closing_date', 'closing_at',
    'status', 'summary'
]"""
JOB_KEYS_V2 = """ARRAY[
    'entity_type', 'job_id', 'category', 'employment_types', 'location',
    'classification', 'salary', 'closing_text', 'closing_date', 'closing_at',
    'status', 'summary', 'role_requirements'
]"""
ACCOMMODATION_KEYS = """ARRAY[
    'entity_type', 'source_authority', 'accommodation_type', 'location',
    'catering', 'audience',
    'room_types', 'advertised_rate', 'rate_inclusions', 'rate_exclusions',
    'facilities', 'application_information', 'eligibility', 'contract_term',
    'contact'
]"""
SUPPORT_KEYS = """ARRAY[
    'entity_type', 'source_authority', 'categories', 'contact', 'location',
    'hours', 'audience',
    'access_instructions', 'cost'
]"""


def _create_shared_checks(*, include_resources: bool) -> None:
    source_domain = (
        "(source_id = 'courses_programs_and_courses' AND domain = 'courses') OR "
        "(source_id = 'scholarships_anu_finder' AND domain = 'scholarships') OR "
        "(source_id = 'jobs_anu_search' AND domain = 'jobs')"
    )
    entity_type = (
        "jsonb_typeof(metadata_json) = 'object' AND "
        "((domain = 'courses' AND metadata_json ->> 'entity_type' IN "
        "('course', 'program')) OR (domain = 'scholarships' AND "
        "metadata_json ->> 'entity_type' = 'scholarship') OR (domain = 'jobs' "
        "AND metadata_json ->> 'entity_type' = 'job')"
    )
    record_id = (
        "(domain = 'courses' AND record_id = 'courses:' || "
        "(metadata_json ->> 'entity_type') || ':' || entity_id) OR "
        "(domain = 'scholarships' AND record_id = "
        "'scholarships:scholarship:' || entity_id) OR "
        "(domain = 'jobs' AND record_id = 'jobs:job:' || entity_id)"
    )
    if include_resources:
        source_domain += (
            " OR (source_id = 'accommodation_anu_study' AND "
            "domain = 'accommodation') OR "
            "(source_id = 'support_anusa_student_assistance' AND "
            "domain = 'support')"
        )
        entity_type += (
            " OR (domain = 'accommodation' AND metadata_json ->> "
            "'entity_type' = 'accommodation') OR (domain = 'support' AND "
            "metadata_json ->> 'entity_type' = 'support_service')"
        )
        record_id += (
            " OR (domain = 'accommodation' AND record_id = "
            "'accommodation:accommodation:' || entity_id) OR "
            "(domain = 'support' AND record_id = "
            "'support:support_service:' || entity_id)"
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


def _job_type_check(keys: str) -> str:
    role_check = ""
    if "role_requirements" in keys:
        role_check = (
            "jsonb_typeof(metadata_json -> 'role_requirements') IN "
            "('array', 'null') AND NOT jsonb_path_exists(metadata_json, "
            "'$.role_requirements[*] ? (@.type() != \"string\")') AND "
        )
    return (
        "domain <> 'jobs' OR ("
        "jsonb_typeof(metadata_json -> 'job_id') = 'string' AND "
        "jsonb_typeof(metadata_json -> 'category') IN ('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'employment_types') = 'array' AND "
        "NOT jsonb_path_exists(metadata_json, "
        "'$.employment_types[*] ? (@.type() != \"string\")') AND "
        "jsonb_typeof(metadata_json -> 'location') IN ('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'classification') IN ('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'salary') IN ('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'closing_text') IN ('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'closing_date') IN ('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'closing_at') IN ('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'status') IN ('string', 'null') AND "
        "jsonb_typeof(metadata_json -> 'summary') IN ('string', 'null') AND "
        + role_check
        + "(metadata_json ->> 'status' IS NULL OR metadata_json ->> 'status' "
        "IN ('current', 'closed')) AND (metadata_json ->> 'closing_date' IS NULL "
        "OR (metadata_json ->> 'closing_date' ~ "
        "'^[0-9]{4}-[0-9]{2}-[0-9]{2}$' AND to_char((metadata_json ->> "
        "'closing_date')::date, 'YYYY-MM-DD') = metadata_json ->> "
        "'closing_date')) AND (metadata_json ->> 'closing_at' IS NULL OR "
        "(metadata_json ->> 'closing_at' ~ "
        "'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}"
        "(:[0-9]{2}([.][0-9]+)?)?(Z|[+-][0-9]{2}:[0-9]{2})$' AND "
        "(metadata_json ->> 'closing_at')::timestamptz IS NOT NULL)))"
    )


def upgrade() -> None:
    # Upgrade every existing Jobs row to the approved nullable v2 shape before
    # reinstating the exact-key check. No requirement text is inferred.
    op.drop_constraint(
        "ck_source_records_job_metadata_keys", "source_records", type_="check"
    )
    op.drop_constraint(
        "ck_source_records_job_metadata_types", "source_records", type_="check"
    )
    op.execute(
        """
        UPDATE source_records
        SET metadata_json = jsonb_set(
            metadata_json, '{role_requirements}', 'null'::jsonb, true
        )
        WHERE domain = 'jobs' AND NOT metadata_json ? 'role_requirements'
        """
    )
    op.create_check_constraint(
        "ck_source_records_job_metadata_keys",
        "source_records",
        f"domain <> 'jobs' OR (metadata_json ?& {JOB_KEYS_V2} "
        f"AND metadata_json - {JOB_KEYS_V2} = '{{}}'::jsonb)",
    )
    op.create_check_constraint(
        "ck_source_records_job_metadata_types",
        "source_records",
        _job_type_check(JOB_KEYS_V2),
    )

    for name in (
        "ck_source_records_source_domain",
        "ck_source_records_entity_type",
        "ck_source_records_record_id",
    ):
        op.drop_constraint(name, "source_records", type_="check")
    _create_shared_checks(include_resources=True)

    op.create_check_constraint(
        "ck_source_records_accommodation_identity",
        "source_records",
        "domain <> 'accommodation' OR (entity_id ~ "
        "'^[a-z0-9]+(-[a-z0-9]+)*$' AND canonical_url ~ "
        "'^https://study[.]anu[.]edu[.]au/accommodation(?:/[^?#[:space:]]*)?$')",
    )
    op.create_check_constraint(
        "ck_source_records_accommodation_metadata",
        "source_records",
        f"domain <> 'accommodation' OR (metadata_json ?& {ACCOMMODATION_KEYS} "
        f"AND metadata_json - {ACCOMMODATION_KEYS} = '{{}}'::jsonb "
        "AND metadata_json ->> 'source_authority' = 'official_anu' "
        "AND jsonb_typeof(metadata_json -> 'accommodation_type') IN "
        "('string', 'null') AND jsonb_typeof(metadata_json -> 'location') IN "
        "('string', 'null') AND jsonb_typeof(metadata_json -> 'catering') IN "
        "('string', 'null') "
        "AND jsonb_typeof(metadata_json -> 'audience') = 'array' "
        "AND NOT jsonb_path_exists(metadata_json, "
        "'$.audience[*] ? (@.type() != \"string\")') "
        "AND jsonb_typeof(metadata_json -> 'room_types') = 'array' "
        "AND NOT jsonb_path_exists(metadata_json, "
        "'$.room_types[*] ? (@.type() != \"string\")') "
        "AND jsonb_typeof(metadata_json -> 'advertised_rate') IN "
        "('string', 'null') "
        "AND jsonb_typeof(metadata_json -> 'rate_inclusions') = 'array' "
        "AND NOT jsonb_path_exists(metadata_json, "
        "'$.rate_inclusions[*] ? (@.type() != \"string\")') "
        "AND jsonb_typeof(metadata_json -> 'rate_exclusions') = 'array' "
        "AND NOT jsonb_path_exists(metadata_json, "
        "'$.rate_exclusions[*] ? (@.type() != \"string\")') "
        "AND jsonb_typeof(metadata_json -> 'facilities') = 'array' "
        "AND NOT jsonb_path_exists(metadata_json, "
        "'$.facilities[*] ? (@.type() != \"string\")') "
        "AND jsonb_typeof(metadata_json -> 'application_information') IN "
        "('string', 'null') AND jsonb_typeof(metadata_json -> 'eligibility') IN "
        "('string', 'null') AND jsonb_typeof(metadata_json -> 'contract_term') IN "
        "('string', 'null') AND jsonb_typeof(metadata_json -> 'contact') IN "
        "('string', 'null'))",
    )
    op.create_check_constraint(
        "ck_source_records_support_identity",
        "source_records",
        "domain <> 'support' OR (entity_id ~ '^[a-z0-9]+(-[a-z0-9]+)*$' "
        "AND canonical_url ~ "
        "'^https://anusa[.]com[.]au/student-assistance(?:/[^?#[:space:]]*)?/?$')",
    )
    op.create_check_constraint(
        "ck_source_records_support_metadata",
        "source_records",
        f"domain <> 'support' OR (metadata_json ?& {SUPPORT_KEYS} "
        f"AND metadata_json - {SUPPORT_KEYS} = '{{}}'::jsonb "
        "AND metadata_json ->> 'source_authority' = 'approved_anusa' "
        "AND jsonb_typeof(metadata_json -> 'categories') = 'array' "
        "AND NOT jsonb_path_exists(metadata_json, "
        "'$.categories[*] ? (@.type() != \"string\")') "
        "AND jsonb_typeof(metadata_json -> 'audience') = 'array' "
        "AND NOT jsonb_path_exists(metadata_json, "
        "'$.audience[*] ? (@.type() != \"string\")') "
        "AND jsonb_typeof(metadata_json -> 'contact') IN ('string', 'null') "
        "AND jsonb_typeof(metadata_json -> 'location') IN ('string', 'null') "
        "AND jsonb_typeof(metadata_json -> 'hours') IN ('string', 'null') "
        "AND jsonb_typeof(metadata_json -> 'access_instructions') IN "
        "('string', 'null') AND jsonb_typeof(metadata_json -> 'cost') IN "
        "('string', 'null'))",
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_source_records_accommodation_identity
        ON source_records (source_id, entity_id)
        WHERE domain = 'accommodation'
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_source_records_support_identity
        ON source_records (source_id, entity_id)
        WHERE domain = 'support'
        """
    )

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE source_record_embeddings (
            source_record_id TEXT NOT NULL
                REFERENCES source_records(record_id) ON DELETE CASCADE,
            retrieval_unit_id TEXT NOT NULL,
            source_content_hash CHAR(64) NOT NULL,
            retrieval_content_hash CHAR(64) NOT NULL,
            embedding_model TEXT NOT NULL,
            embedding_version TEXT NOT NULL,
            embedding vector NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_source_record_embeddings PRIMARY KEY (
                source_record_id, retrieval_unit_id, retrieval_content_hash,
                embedding_model, embedding_version
            ),
            CONSTRAINT ck_source_record_embeddings_required_text CHECK (
                char_length(btrim(retrieval_unit_id)) > 0 AND
                char_length(btrim(embedding_model)) > 0 AND
                char_length(btrim(embedding_version)) > 0
            ),
            CONSTRAINT ck_source_record_embeddings_source_hash CHECK (
                source_content_hash ~ '^[0-9a-f]{64}$'
            ),
            CONSTRAINT ck_source_record_embeddings_content_hash CHECK (
                retrieval_content_hash ~ '^[0-9a-f]{64}$'
            ),
            CONSTRAINT ck_source_record_embeddings_vector CHECK (
                vector_dims(embedding) > 0
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_source_record_embeddings_current_lookup
        ON source_record_embeddings (
            source_record_id, embedding_model, embedding_version,
            source_content_hash
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM source_records
                WHERE domain IN ('accommodation', 'support')
            ) THEN
                RAISE EXCEPTION
                    'Cannot downgrade while Accommodation/Support records exist';
            END IF;
        END
        $$
        """
    )
    op.execute("DROP TABLE source_record_embeddings")
    # Keep the extension: it may predate this revision or be used elsewhere.
    op.execute("DROP INDEX uq_source_records_support_identity")
    op.execute("DROP INDEX uq_source_records_accommodation_identity")
    for name in (
        "ck_source_records_accommodation_identity",
        "ck_source_records_accommodation_metadata",
        "ck_source_records_support_identity",
        "ck_source_records_support_metadata",
    ):
        op.drop_constraint(name, "source_records", type_="check")
    for name in (
        "ck_source_records_source_domain",
        "ck_source_records_entity_type",
        "ck_source_records_record_id",
    ):
        op.drop_constraint(name, "source_records", type_="check")
    _create_shared_checks(include_resources=False)

    op.drop_constraint(
        "ck_source_records_job_metadata_keys", "source_records", type_="check"
    )
    op.drop_constraint(
        "ck_source_records_job_metadata_types", "source_records", type_="check"
    )
    op.execute(
        """
        UPDATE source_records
        SET metadata_json = metadata_json - 'role_requirements'
        WHERE domain = 'jobs'
        """
    )
    op.create_check_constraint(
        "ck_source_records_job_metadata_keys",
        "source_records",
        f"domain <> 'jobs' OR (metadata_json ?& {JOB_KEYS_V1} "
        f"AND metadata_json - {JOB_KEYS_V1} = '{{}}'::jsonb)",
    )
    op.create_check_constraint(
        "ck_source_records_job_metadata_types",
        "source_records",
        _job_type_check(JOB_KEYS_V1),
    )
