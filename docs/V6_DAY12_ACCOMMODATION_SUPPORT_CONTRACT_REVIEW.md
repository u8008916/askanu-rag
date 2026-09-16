# V6 Day 12 Accommodation and Support contract review

**Status:** CONTRACT FROZEN BY QASIM — IMPLEMENTATION APPROVED.

Reviewed on 2026-09-16 against:

- scraper PR #26 local remote ref
  `refs/remotes/origin/will/v6-day12-accommodation-support` at `fb91311`;
- RAG `main` at `fba4fe6`; and
- Will's `docs/DAY_12_V6_ACCOMMODATION_SUPPORT_HANDOFF.md` and
  `day12-coverage-evidence.json` from that exact scraper ref.

The scraper checkout itself was not changed. Its local checked-out branch named
`origin/will/v6-day12-accommodation-support` points at `bf29b2f`, so this review
read the unambiguous remote ref above rather than the working-tree files.

## Review result and final decision

The original review found that the shared 16 top-level fields, `domain`, and
`source_id` agreed while the exact identity and `metadata_json` contracts did
not. PR #26 records were rejected by the old provisional RAG models and by the
resource checks introduced in migration `20260915_0005`.

This is a real shared-contract mismatch, not a nullable-field or parser-only
difference. Qasim has now frozen one exact serialized contract. This branch
implements that contract without compatibility aliases, union shapes, ignored
extras or inferred field conversions.

The historical direction is:

- old provisional RAG: Accommodation `entity_type = accommodation`;
- Will PR #26 proposal: Accommodation `entity_type = residence`; and
- final Qasim-frozen contract: Accommodation `entity_type = residence`.

A direct validation probe using the representative PR identities and exact PR
metadata keys produced:

```text
AccommodationRecord: REJECTED: metadata_json.entity_type must be accommodation
SupportRecord: REJECTED: metadata_json.source_authority is required
```

These were only the first historical strict-validation errors. They document
why an append-only alignment revision was required; they are not the current
post-implementation result.

## Accommodation mismatch

| Contract area | Will PR #26 proposal | Old provisional RAG |
|---|---|---|
| `metadata_json.entity_type` | `residence` | `accommodation` |
| `record_id` | `accommodation:residence:<slug>` | `accommodation:accommodation:<slug>` |
| canonical URL | exact `https://study.anu.edu.au/accommodation/our-residences/<slug>` | any URL under `https://study.anu.edu.au/accommodation` |
| authority | no metadata key; authority is represented by `source_id`/registry | required `source_authority = official_anu` |
| category/type | `category: string | null` | `accommodation_type: string | null` |
| catering | `catering_options: string[]` | `catering: string | null` |
| audience | `audiences: string[]` | `audience: string[]` |
| rooms/rates | `rooms: {name, rate, contract, inclusions, other_fees}[]` plus `advertised_rate` and `cost_period` | `room_types: string[]`, `advertised_rate`, top-level `rate_inclusions`, `rate_exclusions`, and `contract_term` |
| facilities | `features: string[]` | `facilities: string[]` |
| application | `application_text` plus validated `application_url` | `application_information: string | null` |
| contact | `{email, phone, location, hours}` | `string | null` |
| additional PR facts | `overview`, `accessibility`, nullable-only `vacancy_status` | none |

Before this implementation, Will's representative record
`accommodation:residence:yukeembruk` could not deserialize as the provisional
`AccommodationRecord`. The mismatch affected all 19 frozen residences and the
96 captured room variants.

## Support mismatch

| Contract area | Will PR #26 proposal | Old provisional RAG |
|---|---|---|
| `metadata_json.entity_type` | `support_service` | `support_service` (matches) |
| `record_id` | `support:service:<slug>` | `support:support_service:<slug>` |
| canonical URL | exact `https://anusa.com.au/student-assistance/<slug>/` | any URL under `https://anusa.com.au/student-assistance` |
| authority | no metadata key; authority is represented by `source_id`/registry | required `source_authority = approved_anusa` |
| category/purpose | `category: string | null` and `purpose: string | null` | `categories: string[]` |
| audience | `audiences: string[]` | `audience: string[]` |
| contact/location | `contact: {email, phone, location}` | `contact: string | null` plus `location: string | null` |
| access | `access: string | null` | `access_instructions: string | null` |
| service detail | `topics: {title, description, url}[]` and `referrals: {label, url}[]` | none |
| hours/cost | nullable strings | nullable strings (matches) |

Before this implementation, Will's representative record
`support:service:academic` could not deserialize as the provisional
`SupportRecord`. The mismatch affected all six frozen support categories,
including 29 captured topics and eight referrals.

## Qasim-frozen resolution

The final contract adopts Will's richer nested field intent and exact
Accommodation `residence` identity. Qasim explicitly overrides Will's Support
record ID proposal: the final value is
`support:support_service:<entity_id>`, not `support:service:<entity_id>`.

Final decisions:

1. Accommodation uses `entity_type = residence`,
   `accommodation:residence:<slug>` and the exact `/our-residences/<slug>` URL.
2. Support uses `entity_type = support_service`,
   `support:support_service:<slug>` and the exact trailing-slash category URL.
3. Both metadata objects use the strict richer nested shapes documented in
   `DATA_SCHEMA.md`; old provisional names are rejected.
4. `source_authority` is not stored in metadata. Authority is derived from the
   approved source ID, domain and canonical URL boundary.
5. `vacancy_status` remains a nullable, strictly source-backed field. Null means
   unknown and cannot be inferred from StarRez, applications, rooms, rates or
   dates.
6. Topic URLs remain within ANUSA Student Assistance. Referrals may be external
   navigation evidence but never become Topics or source-record entities.
7. Append-only migration `20260916_0008` replaces only the Day 12 checks and
   fails closed before replacement if existing rows cannot be safely accepted.
   Known provisional rows require manual review/reingestion; no lossy rewrite is
   performed.

## Implementation boundary

This branch implements the approved RAG model, repository, deterministic
retrieval, safety, capability and conversation changes locally. It does not run
a production migration, mutate Cloud SQL, deploy, edit the scraper, expand
Events, enable Rubric or fetch StarRez.
