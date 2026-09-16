"""Freeze the Day 12 Accommodation and Support shared contracts.

Revision ID: 20260916_0008
Revises: 20260915_0007
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260916_0008"
down_revision: str | None = "20260915_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PROVISIONAL_ACCOMMODATION_KEYS = """ARRAY[
    'entity_type', 'source_authority', 'accommodation_type', 'location',
    'catering', 'audience', 'room_types', 'advertised_rate',
    'rate_inclusions', 'rate_exclusions', 'facilities',
    'application_information', 'eligibility', 'contract_term', 'contact'
]"""
PROVISIONAL_SUPPORT_KEYS = """ARRAY[
    'entity_type', 'source_authority', 'categories', 'contact', 'location',
    'hours', 'audience', 'access_instructions', 'cost'
]"""


ACCOMMODATION_VALIDATOR_SQL = r"""
CREATE FUNCTION askanu_day12_accommodation_metadata_valid(metadata_value JSONB)
RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $$
DECLARE
    item JSONB;
    application_destination TEXT;
BEGIN
    IF jsonb_typeof(metadata_value) <> 'object'
       OR NOT metadata_value ?& ARRAY[
           'entity_type', 'category', 'location', 'catering_options',
           'audiences', 'advertised_rate', 'cost_period', 'rooms', 'features',
           'overview', 'accessibility', 'application_text', 'application_url',
           'eligibility', 'contact', 'vacancy_status'
       ]
       OR metadata_value - ARRAY[
           'entity_type', 'category', 'location', 'catering_options',
           'audiences', 'advertised_rate', 'cost_period', 'rooms', 'features',
           'overview', 'accessibility', 'application_text', 'application_url',
           'eligibility', 'contact', 'vacancy_status'
       ] <> '{}'::jsonb
       OR metadata_value ->> 'entity_type' <> 'residence'
    THEN
        RETURN FALSE;
    END IF;

    IF jsonb_typeof(metadata_value -> 'category') NOT IN ('string', 'null')
       OR jsonb_typeof(metadata_value -> 'location') NOT IN ('string', 'null')
       OR jsonb_typeof(metadata_value -> 'advertised_rate') NOT IN ('string', 'null')
       OR jsonb_typeof(metadata_value -> 'cost_period') NOT IN ('string', 'null')
       OR jsonb_typeof(metadata_value -> 'overview') NOT IN ('string', 'null')
       OR jsonb_typeof(metadata_value -> 'accessibility') NOT IN ('string', 'null')
       OR jsonb_typeof(metadata_value -> 'application_text') NOT IN ('string', 'null')
       OR jsonb_typeof(metadata_value -> 'application_url') NOT IN ('string', 'null')
       OR jsonb_typeof(metadata_value -> 'eligibility') NOT IN ('string', 'null')
       OR jsonb_typeof(metadata_value -> 'vacancy_status') NOT IN ('string', 'null')
       OR jsonb_typeof(metadata_value -> 'catering_options') <> 'array'
       OR jsonb_typeof(metadata_value -> 'audiences') <> 'array'
       OR jsonb_typeof(metadata_value -> 'rooms') <> 'array'
       OR jsonb_typeof(metadata_value -> 'features') <> 'array'
       OR jsonb_typeof(metadata_value -> 'contact') <> 'object'
    THEN
        RETURN FALSE;
    END IF;

    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(metadata_value -> 'catering_options') value
        WHERE jsonb_typeof(value) <> 'string'
    ) OR EXISTS (
        SELECT 1 FROM jsonb_array_elements(metadata_value -> 'audiences') value
        WHERE jsonb_typeof(value) <> 'string'
    ) OR EXISTS (
        SELECT 1 FROM jsonb_array_elements(metadata_value -> 'features') value
        WHERE jsonb_typeof(value) <> 'string'
    ) THEN
        RETURN FALSE;
    END IF;

    FOR item IN SELECT value FROM jsonb_array_elements(metadata_value -> 'rooms')
    LOOP
        IF jsonb_typeof(item) <> 'object'
           OR NOT item ?& ARRAY['name', 'rate', 'contract', 'inclusions', 'other_fees']
           OR item - ARRAY['name', 'rate', 'contract', 'inclusions', 'other_fees']
               <> '{}'::jsonb
           OR jsonb_typeof(item -> 'name') <> 'string'
           OR jsonb_typeof(item -> 'rate') NOT IN ('string', 'null')
           OR jsonb_typeof(item -> 'contract') NOT IN ('string', 'null')
           OR jsonb_typeof(item -> 'inclusions') NOT IN ('string', 'null')
           OR jsonb_typeof(item -> 'other_fees') NOT IN ('string', 'null')
        THEN
            RETURN FALSE;
        END IF;
    END LOOP;

    item := metadata_value -> 'contact';
    IF NOT item ?& ARRAY['email', 'phone', 'location', 'hours']
       OR item - ARRAY['email', 'phone', 'location', 'hours'] <> '{}'::jsonb
       OR jsonb_typeof(item -> 'email') NOT IN ('string', 'null')
       OR jsonb_typeof(item -> 'phone') NOT IN ('string', 'null')
       OR jsonb_typeof(item -> 'location') NOT IN ('string', 'null')
       OR jsonb_typeof(item -> 'hours') NOT IN ('string', 'null')
    THEN
        RETURN FALSE;
    END IF;

    application_destination := metadata_value ->> 'application_url';
    IF application_destination IS NOT NULL
       AND application_destination !~
           '^https://([A-Za-z0-9-]+[.])+starrezhousing[.]com/[^[:space:]]*$'
    THEN
        RETURN FALSE;
    END IF;

    RETURN TRUE;
EXCEPTION WHEN OTHERS THEN
    RETURN FALSE;
END;
$$
"""


SUPPORT_VALIDATOR_SQL = r"""
CREATE FUNCTION askanu_day12_support_metadata_valid(metadata_value JSONB)
RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $$
DECLARE
    item JSONB;
    nested_url TEXT;
BEGIN
    IF jsonb_typeof(metadata_value) <> 'object'
       OR NOT metadata_value ?& ARRAY[
           'entity_type', 'category', 'purpose', 'audiences', 'contact',
           'hours', 'access', 'cost', 'topics', 'referrals'
       ]
       OR metadata_value - ARRAY[
           'entity_type', 'category', 'purpose', 'audiences', 'contact',
           'hours', 'access', 'cost', 'topics', 'referrals'
       ] <> '{}'::jsonb
       OR metadata_value ->> 'entity_type' <> 'support_service'
    THEN
        RETURN FALSE;
    END IF;

    IF jsonb_typeof(metadata_value -> 'category') NOT IN ('string', 'null')
       OR jsonb_typeof(metadata_value -> 'purpose') NOT IN ('string', 'null')
       OR jsonb_typeof(metadata_value -> 'hours') NOT IN ('string', 'null')
       OR jsonb_typeof(metadata_value -> 'access') NOT IN ('string', 'null')
       OR jsonb_typeof(metadata_value -> 'cost') NOT IN ('string', 'null')
       OR jsonb_typeof(metadata_value -> 'audiences') <> 'array'
       OR jsonb_typeof(metadata_value -> 'contact') <> 'object'
       OR jsonb_typeof(metadata_value -> 'topics') <> 'array'
       OR jsonb_typeof(metadata_value -> 'referrals') <> 'array'
    THEN
        RETURN FALSE;
    END IF;

    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(metadata_value -> 'audiences') value
        WHERE jsonb_typeof(value) <> 'string'
    ) THEN
        RETURN FALSE;
    END IF;

    item := metadata_value -> 'contact';
    IF NOT item ?& ARRAY['email', 'phone', 'location']
       OR item - ARRAY['email', 'phone', 'location'] <> '{}'::jsonb
       OR jsonb_typeof(item -> 'email') NOT IN ('string', 'null')
       OR jsonb_typeof(item -> 'phone') NOT IN ('string', 'null')
       OR jsonb_typeof(item -> 'location') NOT IN ('string', 'null')
    THEN
        RETURN FALSE;
    END IF;

    FOR item IN SELECT value FROM jsonb_array_elements(metadata_value -> 'topics')
    LOOP
        IF jsonb_typeof(item) <> 'object'
           OR NOT item ?& ARRAY['title', 'description', 'url']
           OR item - ARRAY['title', 'description', 'url'] <> '{}'::jsonb
           OR jsonb_typeof(item -> 'title') <> 'string'
           OR jsonb_typeof(item -> 'description') NOT IN ('string', 'null')
           OR jsonb_typeof(item -> 'url') <> 'string'
        THEN
            RETURN FALSE;
        END IF;
        nested_url := item ->> 'url';
        IF nested_url !~
           '^https://(www[.])?anusa[.]com[.]au/student-assistance/[^?#[:space:]]+/?$'
        THEN
            RETURN FALSE;
        END IF;
    END LOOP;

    FOR item IN SELECT value FROM jsonb_array_elements(metadata_value -> 'referrals')
    LOOP
        IF jsonb_typeof(item) <> 'object'
           OR NOT item ?& ARRAY['label', 'url']
           OR item - ARRAY['label', 'url'] <> '{}'::jsonb
           OR jsonb_typeof(item -> 'label') <> 'string'
           OR jsonb_typeof(item -> 'url') <> 'string'
        THEN
            RETURN FALSE;
        END IF;
        nested_url := item ->> 'url';
        IF nested_url !~ '^https?://[^[:space:]]+$'
           OR nested_url ~ '^https?://(www[.])?anusa[.]com[.]au([/:]|$)'
        THEN
            RETURN FALSE;
        END IF;
    END LOOP;

    RETURN TRUE;
EXCEPTION WHEN OTHERS THEN
    RETURN FALSE;
END;
$$
"""


PRE_MIGRATION_GUARD_SQL = f"""
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM source_records
        WHERE domain IN ('accommodation', 'support')
          AND NOT (
            (
              domain = 'accommodation'
              AND source_id = 'accommodation_anu_study'
              AND entity_id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'
              AND (
                (
                  metadata_json ->> 'entity_type' = 'accommodation'
                  AND metadata_json ?& {PROVISIONAL_ACCOMMODATION_KEYS}
                  AND metadata_json - {PROVISIONAL_ACCOMMODATION_KEYS} = '{{}}'::jsonb
                  AND record_id = 'accommodation:accommodation:' || entity_id
                )
                OR (
                  askanu_day12_accommodation_metadata_valid(metadata_json)
                  AND record_id = 'accommodation:residence:' || entity_id
                  AND canonical_url =
                    'https://study.anu.edu.au/accommodation/our-residences/' || entity_id
                )
              )
            )
            OR (
              domain = 'support'
              AND source_id = 'support_anusa_student_assistance'
              AND entity_id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'
              AND (
                (
                  metadata_json ->> 'entity_type' = 'support_service'
                  AND metadata_json ?& {PROVISIONAL_SUPPORT_KEYS}
                  AND metadata_json - {PROVISIONAL_SUPPORT_KEYS} = '{{}}'::jsonb
                  AND record_id = 'support:support_service:' || entity_id
                )
                OR (
                  askanu_day12_support_metadata_valid(metadata_json)
                  AND record_id = 'support:support_service:' || entity_id
                  AND canonical_url =
                    'https://anusa.com.au/student-assistance/' || entity_id || '/'
                )
              )
            )
          )
    ) THEN
        RAISE EXCEPTION
          'Unexpected Accommodation/Support rows require manual contract review';
    END IF;

    IF EXISTS (
        SELECT 1 FROM source_records
        WHERE domain = 'accommodation'
          AND metadata_json ->> 'entity_type' = 'accommodation'
    ) OR EXISTS (
        SELECT 1 FROM source_records
        WHERE domain = 'support'
          AND metadata_json ? 'source_authority'
    ) THEN
        RAISE EXCEPTION
          'Known provisional Accommodation/Support rows require manual reingestion; no lossy auto-conversion is permitted';
    END IF;
END
$$
"""


def _create_global_checks(*, frozen: bool) -> None:
    accommodation_type = "residence" if frozen else "accommodation"
    accommodation_record = (
        "'accommodation:residence:'" if frozen
        else "'accommodation:accommodation:'"
    )
    op.create_check_constraint(
        "ck_source_records_entity_type",
        "source_records",
        "jsonb_typeof(metadata_json) = 'object' AND "
        "((domain = 'courses' AND metadata_json ->> 'entity_type' IN "
        "('course', 'program', 'major', 'minor', 'specialisation')) OR "
        "(domain = 'scholarships' AND metadata_json ->> 'entity_type' = "
        "'scholarship') OR (domain = 'jobs' AND metadata_json ->> "
        "'entity_type' = 'job') OR (domain = 'accommodation' AND "
        f"metadata_json ->> 'entity_type' = '{accommodation_type}') OR "
        "(domain = 'support' AND metadata_json ->> 'entity_type' = "
        "'support_service'))",
    )
    op.create_check_constraint(
        "ck_source_records_record_id",
        "source_records",
        "(domain = 'courses' AND record_id = 'courses:' || "
        "(metadata_json ->> 'entity_type') || ':' || entity_id) OR "
        "(domain = 'scholarships' AND record_id = "
        "'scholarships:scholarship:' || entity_id) OR "
        "(domain = 'jobs' AND record_id = 'jobs:job:' || entity_id) OR "
        f"(domain = 'accommodation' AND record_id = {accommodation_record} "
        "|| entity_id) OR (domain = 'support' AND record_id = "
        "'support:support_service:' || entity_id)",
    )


def _create_frozen_resource_checks() -> None:
    op.create_check_constraint(
        "ck_source_records_accommodation_identity",
        "source_records",
        "domain <> 'accommodation' OR (entity_id ~ "
        "'^[a-z0-9]+(-[a-z0-9]+)*$' AND canonical_url = "
        "'https://study.anu.edu.au/accommodation/our-residences/' || entity_id)",
    )
    op.create_check_constraint(
        "ck_source_records_accommodation_metadata",
        "source_records",
        "domain <> 'accommodation' OR "
        "askanu_day12_accommodation_metadata_valid(metadata_json)",
    )
    op.create_check_constraint(
        "ck_source_records_support_identity",
        "source_records",
        "domain <> 'support' OR (entity_id ~ "
        "'^[a-z0-9]+(-[a-z0-9]+)*$' AND canonical_url = "
        "'https://anusa.com.au/student-assistance/' || entity_id || '/')",
    )
    op.create_check_constraint(
        "ck_source_records_support_metadata",
        "source_records",
        "domain <> 'support' OR "
        "askanu_day12_support_metadata_valid(metadata_json)",
    )


def _create_provisional_resource_checks() -> None:
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
        f"domain <> 'accommodation' OR (metadata_json ?& "
        f"{PROVISIONAL_ACCOMMODATION_KEYS} AND metadata_json - "
        f"{PROVISIONAL_ACCOMMODATION_KEYS} = '{{}}'::jsonb AND "
        "metadata_json ->> 'source_authority' = 'official_anu')",
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
        f"domain <> 'support' OR (metadata_json ?& {PROVISIONAL_SUPPORT_KEYS} "
        f"AND metadata_json - {PROVISIONAL_SUPPORT_KEYS} = '{{}}'::jsonb "
        "AND metadata_json ->> 'source_authority' = 'approved_anusa')",
    )


RESOURCE_CHECKS = (
    "ck_source_records_entity_type",
    "ck_source_records_record_id",
    "ck_source_records_accommodation_identity",
    "ck_source_records_accommodation_metadata",
    "ck_source_records_support_identity",
    "ck_source_records_support_metadata",
)


def upgrade() -> None:
    op.execute(ACCOMMODATION_VALIDATOR_SQL)
    op.execute(SUPPORT_VALIDATOR_SQL)
    # This read-only gate runs before any existing constraint is replaced. It
    # permits already-frozen rows, refuses unknown rows, and separately refuses
    # known provisional rows because their nested facts cannot be converted
    # losslessly.
    op.execute(PRE_MIGRATION_GUARD_SQL)

    for name in RESOURCE_CHECKS:
        op.drop_constraint(name, "source_records", type_="check")
    _create_global_checks(frozen=True)
    _create_frozen_resource_checks()


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
                  'Cannot downgrade frozen Day 12 contracts while Accommodation/Support records exist';
            END IF;
        END
        $$
        """
    )
    for name in RESOURCE_CHECKS:
        op.drop_constraint(name, "source_records", type_="check")
    _create_global_checks(frozen=False)
    _create_provisional_resource_checks()
    op.execute("DROP FUNCTION askanu_day12_support_metadata_valid(JSONB)")
    op.execute("DROP FUNCTION askanu_day12_accommodation_metadata_valid(JSONB)")
