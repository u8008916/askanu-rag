"""Add the frozen V6 Events contract to shared source_records.

Revision ID: 20260919_0009
Revises: 20260916_0008
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260919_0009"
down_revision: str | None = "20260916_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EVENT_KEYS = """ARRAY[
    'entity_type', 'source_event_id', 'start_at', 'end_at', 'timezone',
    'organiser_name', 'venue_name', 'address', 'latitude', 'longitude',
    'category', 'tags', 'registration_url', 'source_status',
    'cancellation_status', 'audience'
]"""

EVENT_METADATA_VALIDATOR_SQL = rf"""
CREATE FUNCTION askanu_v6_event_metadata_valid(metadata_value JSONB)
RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $$
DECLARE
    field_name TEXT;
BEGIN
    IF jsonb_typeof(metadata_value) <> 'object'
       OR NOT metadata_value ?& ARRAY['entity_type', 'source_event_id', 'start_at']
       OR metadata_value - {EVENT_KEYS} <> '{{}}'::jsonb
       OR metadata_value ->> 'entity_type' <> 'event'
       OR jsonb_typeof(metadata_value -> 'source_event_id') <> 'string'
       OR btrim(metadata_value ->> 'source_event_id') = ''
       OR jsonb_typeof(metadata_value -> 'start_at') <> 'string'
       OR metadata_value ->> 'start_at' !~
          '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}T[0-9]{{2}}:[0-9]{{2}}(:[0-9]{{2}}([.][0-9]+)?)?(Z|[+-][0-9]{{2}}:[0-9]{{2}})$'
       OR (metadata_value ? 'end_at'
           AND jsonb_typeof(metadata_value -> 'end_at') NOT IN ('string', 'null'))
       OR (jsonb_typeof(metadata_value -> 'end_at') = 'string'
           AND metadata_value ->> 'end_at' !~
             '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}T[0-9]{{2}}:[0-9]{{2}}(:[0-9]{{2}}([.][0-9]+)?)?(Z|[+-][0-9]{{2}}:[0-9]{{2}})$')
       OR (jsonb_typeof(metadata_value -> 'timezone') = 'string'
           AND metadata_value ->> 'timezone' !~
             '^[A-Za-z_+-]+(/[A-Za-z0-9_+-]+)+$')
       OR (metadata_value ? 'latitude'
           AND jsonb_typeof(metadata_value -> 'latitude') NOT IN ('number', 'null'))
       OR (metadata_value ? 'longitude'
           AND jsonb_typeof(metadata_value -> 'longitude') NOT IN ('number', 'null'))
       OR (metadata_value ? 'tags'
           AND jsonb_typeof(metadata_value -> 'tags') NOT IN ('array', 'null'))
       OR (jsonb_typeof(metadata_value -> 'tags') = 'array'
           AND jsonb_path_exists(metadata_value, '$.tags[*] ? (@.type() != "string")'))
       OR (metadata_value ? 'audience'
           AND jsonb_typeof(metadata_value -> 'audience') NOT IN ('string', 'array', 'null'))
       OR (jsonb_typeof(metadata_value -> 'audience') = 'array'
           AND jsonb_path_exists(metadata_value, '$.audience[*] ? (@.type() != "string")'))
    THEN
        RETURN FALSE;
    END IF;

    FOREACH field_name IN ARRAY ARRAY[
        'timezone', 'organiser_name', 'venue_name', 'address', 'category',
        'registration_url', 'source_status', 'cancellation_status'
    ]
    LOOP
        IF metadata_value ? field_name
           AND jsonb_typeof(metadata_value -> field_name) NOT IN ('string', 'null')
        THEN
            RETURN FALSE;
        END IF;
        IF jsonb_typeof(metadata_value -> field_name) = 'string'
           AND btrim(metadata_value ->> field_name) = ''
        THEN
            RETURN FALSE;
        END IF;
    END LOOP;

    IF (jsonb_typeof(metadata_value -> 'tags') = 'array' AND EXISTS (
        SELECT 1 FROM jsonb_array_elements_text(metadata_value -> 'tags') value
        WHERE btrim(value) = ''
    )) OR (jsonb_typeof(metadata_value -> 'audience') = 'array' AND EXISTS (
        SELECT 1 FROM jsonb_array_elements_text(metadata_value -> 'audience') value
        WHERE btrim(value) = ''
    )) OR (jsonb_typeof(metadata_value -> 'audience') = 'string'
           AND btrim(metadata_value ->> 'audience') = '')
    THEN
        RETURN FALSE;
    END IF;

    RETURN TRUE;
EXCEPTION WHEN OTHERS THEN
    RETURN FALSE;
END;
$$
"""


def _create_global_checks(*, include_events: bool) -> None:
    source_domain = (
        "(source_id = 'courses_programs_and_courses' AND domain = 'courses') OR "
        "(source_id = 'scholarships_anu_finder' AND domain = 'scholarships') OR "
        "(source_id = 'jobs_anu_search' AND domain = 'jobs') OR "
        "(source_id = 'accommodation_anu_study' AND domain = 'accommodation') OR "
        "(source_id = 'support_anusa_student_assistance' AND domain = 'support')"
    )
    entity_type = (
        "jsonb_typeof(metadata_json) = 'object' AND ((domain = 'courses' AND "
        "metadata_json ->> 'entity_type' IN ('course', 'program', 'major', "
        "'minor', 'specialisation')) OR (domain = 'scholarships' AND "
        "metadata_json ->> 'entity_type' = 'scholarship') OR (domain = 'jobs' "
        "AND metadata_json ->> 'entity_type' = 'job') OR (domain = "
        "'accommodation' AND metadata_json ->> 'entity_type' = 'residence') OR "
        "(domain = 'support' AND metadata_json ->> 'entity_type' = "
        "'support_service')"
    )
    record_id = (
        "(domain = 'courses' AND record_id = 'courses:' || "
        "(metadata_json ->> 'entity_type') || ':' || entity_id) OR "
        "(domain = 'scholarships' AND record_id = "
        "'scholarships:scholarship:' || entity_id) OR "
        "(domain = 'jobs' AND record_id = 'jobs:job:' || entity_id) OR "
        "(domain = 'accommodation' AND record_id = "
        "'accommodation:residence:' || entity_id) OR "
        "(domain = 'support' AND record_id = "
        "'support:support_service:' || entity_id)"
    )
    if include_events:
        source_domain += (
            " OR (source_id IN ('events_anu_official', 'rubric_unified_search') "
            "AND domain = 'events')"
        )
        entity_type += (
            " OR (domain = 'events' AND metadata_json ->> 'entity_type' = 'event')"
        )
        record_id += (
            " OR (domain = 'events' AND record_id = 'events:event:' || entity_id)"
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
    op.execute(EVENT_METADATA_VALIDATOR_SQL)
    for name in (
        "ck_source_records_source_domain",
        "ck_source_records_entity_type",
        "ck_source_records_record_id",
    ):
        op.drop_constraint(name, "source_records", type_="check")
    _create_global_checks(include_events=True)
    op.create_check_constraint(
        "ck_source_records_event_metadata",
        "source_records",
        "domain <> 'events' OR askanu_v6_event_metadata_valid(metadata_json)",
    )
    op.create_check_constraint(
        "ck_source_records_event_canonical_url",
        "source_records",
        "domain <> 'events' OR ((source_id = 'events_anu_official' AND "
        "canonical_url ~ '^https://www[.]anu[.]edu[.]au/events/[^[:space:]]+$') OR "
        "(source_id = 'rubric_unified_search' AND canonical_url ~ "
        "'^https://campus[.]hellorubric[.]com/[?]([^#[:space:]]*&)?"
        "eid=[^&#[:space:]]+(&[^#[:space:]]*)?(#[^[:space:]]*)?$'))",
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_source_records_event_source_identity
        ON source_records (source_id, entity_id)
        WHERE domain = 'events'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM source_records WHERE domain = 'events') THEN
                RAISE EXCEPTION
                  'Cannot downgrade the Events contract while Event records exist';
            END IF;
        END
        $$
        """
    )
    op.execute("DROP INDEX uq_source_records_event_source_identity")
    op.drop_constraint(
        "ck_source_records_event_canonical_url", "source_records", type_="check"
    )
    op.drop_constraint(
        "ck_source_records_event_metadata", "source_records", type_="check"
    )
    for name in (
        "ck_source_records_source_domain",
        "ck_source_records_entity_type",
        "ck_source_records_record_id",
    ):
        op.drop_constraint(name, "source_records", type_="check")
    _create_global_checks(include_events=False)
    op.execute("DROP FUNCTION askanu_v6_event_metadata_valid(JSONB)")
