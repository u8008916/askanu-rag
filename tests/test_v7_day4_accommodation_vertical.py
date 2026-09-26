"""V7 Day 4 Accommodation acceptance and trace evidence.

Natural-language variation is deliberate: the flows use "options", "places to
live", "cook for myself", "budget", "first two", "second one", "rooms left",
and "return to accommodation" rather than one repeated trigger sentence.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from askanu_rag.main import create_app
from askanu_rag.models import (
    AnswerState,
    AccommodationRoom,
    AskResponse,
    ConstraintSemanticType,
    Domain,
    EntityKind,
    OkResponse,
    PublicComparisonField,
    PublicComparisonItem,
    PublicComparisonValue,
    PublicResultItem,
    ResultSetStatus,
)
from askanu_rag.retrieval import (
    CourseProgramRepository,
    load_course_program_records,
)
from askanu_rag.retrieval.vector import VectorHit
from test_resources import accommodation


def _residence(
    entity_id: str,
    title: str,
    *,
    rate: str | None,
    catering: list[str],
    location: str | None = "Acton campus",
    cost_period: str | None = "2027 Indicative costs",
    advertised_rate: str | None = None,
):
    displayed_rate = advertised_rate if advertised_rate is not None else rate
    record = accommodation(entity_id, title=title, advertised_rate=displayed_rate)
    rooms = [
        room.model_copy(update={"rate": rate})
        for room in record.metadata_json.rooms
    ]
    metadata = record.metadata_json.model_copy(
        update={
            "advertised_rate": displayed_rate,
            "cost_period": cost_period,
            "catering_options": catering,
            "location": location,
            "rooms": rooms,
        }
    )
    return record.model_copy(update={"metadata_json": metadata})


ALPHA = _residence(
    "alpha-hall", "Alpha Hall", rate="$300.00", catering=["Self-catered"]
)
BRAVO = _residence(
    "bravo-hall",
    "Bravo Hall",
    rate="$450.00",
    catering=["Catered meal plan"],
    location=None,
)
CHARLIE = _residence(
    "charlie-lodge",
    "Charlie Lodge",
    rate="$550.00",
    catering=["Self-catered"],
)
MYSTERY = _residence(
    "mystery-house", "Mystery House", rate=None, catering=[]
)

PRODUCER_380 = _residence(
    "producer-hall",
    "Producer Hall",
    rate="$380.00",
    advertised_rate="Rates from A$300/week",
    cost_period="2027 Indicative costs",
    catering=["Self-catered"],
)
PRODUCER_380 = PRODUCER_380.model_copy(
    update={
        "metadata_json": PRODUCER_380.metadata_json.model_copy(
            update={
                "rooms": [
                    AccommodationRoom(
                        name="Standard",
                        rate="$380.00",
                        contract="44 weeks",
                        inclusions="Internet included",
                        other_fees="Refundable Deposit: $1,300",
                    )
                ]
            }
        )
    }
)


class Conversation:
    def __init__(self, records, *, vector=None):
        self.traces = []
        self.client = TestClient(
            create_app(
                CourseProgramRepository(records),
                resource_trace_sink=self.traces.append,
                vector_retriever=vector,
            )
        )
        self.state = {}
        self.history: list[dict[str, str]] = []

    def ask(self, question: str, **request_fields):
        request_body = {
            "question": question,
            "history": self.history,
            "conversation_state": self.state,
        }
        request_body.update(request_fields)
        response = self.client.post(
            "/api/v1/ask",
            json=request_body,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        self.state = body["conversation_state"]
        turn = len(self.history) + 1
        self.history.extend(
            (
                {"turn_id": f"t{turn}", "role": "user", "content": question},
                {
                    "turn_id": f"t{turn + 1}",
                    "role": "assistant",
                    "content": body["answer"],
                },
            )
        )
        self.history = self.history[-10:]
        return body


def _latest_result(body):
    return body["conversation_state"]["result_sets"][0]


def test_broad_discovery_is_bounded_typed_and_traced() -> None:
    conversation = Conversation((ALPHA, BRAVO, CHARLIE, MYSTERY))

    body = conversation.ask("Show me the accommodation options at ANU")

    assert body["status"] == "ok"
    result = _latest_result(body)
    assert result["domain"] == "accommodation"
    assert result["entity_kind"] == "residence"
    assert result["status"] == "RESULTS"
    assert result["ordered_canonical_ids"] == [
        "alpha-hall",
        "bravo-hall",
        "charlie-lodge",
        "mystery-house",
    ]
    assert body["answer_state"] == "PARTIAL"
    assert [item["canonical_id"] for item in body["items"]] == result[
        "ordered_canonical_ids"
    ]
    assert all(item["type"] == "result" for item in body["items"])
    assert body["items"][0]["result_set_id"] == result["result_set_id"]
    assert body["items"][0]["ordinal"] == 1
    assert body["items"][0]["fields"] == {
        "category": "Residence hall",
        "location": "Acton campus",
        "catering_options": ["Self-catered"],
        "advertised_rate": "$300.00",
        "cost_period": "2027 Indicative costs",
        "audiences": ["Undergraduate students"],
        "features": ["Quiet study spaces", "Shared kitchen"],
    }
    trace = conversation.traces[-1]
    assert trace.interpretation.domain == Domain.ACCOMMODATION
    assert trace.interpretation.intent.name == "discover"
    assert trace.retrieval_plan.domain == Domain.ACCOMMODATION
    assert trace.retrieval_plan.steps[-1].strategy.value == "deterministic_discovery"
    assert trace.result_set.entity_kind == EntityKind.RESIDENCE
    assert trace.evidence_bundle.answer_state == AnswerState.PARTIAL
    assert all(url.startswith("https://study.anu.edu.au/") for url in trace.canonical_sources)


def test_source_backed_preference_filter_preserves_unknown_population() -> None:
    conversation = Conversation((ALPHA, BRAVO, CHARLIE, MYSTERY))

    body = conversation.ask("Which places to live let me cook for myself?")

    assert body["status"] == "ok"
    assert _latest_result(body)["ordered_canonical_ids"] == [
        "alpha-hall",
        "charlie-lodge",
    ]
    trace = conversation.traces[-1]
    assert trace.result_set.status == ResultSetStatus.RESULTS
    assert trace.evidence_bundle.answer_state == AnswerState.PARTIAL
    assert any(
        item.reason == "incomplete_population"
        for item in trace.evidence_bundle.missing_evidence
    )


def test_max_price_refinement_creates_child_and_preserves_parent() -> None:
    conversation = Conversation((ALPHA, BRAVO, CHARLIE, MYSTERY))
    broad = conversation.ask("List the accommodation options")
    parent_id = _latest_result(broad)["result_set_id"]

    refined = conversation.ask("Keep it to a maximum $350")

    child = _latest_result(refined)
    assert child["ordered_canonical_ids"] == ["alpha-hall"]
    assert child["parent_result_set_id"] == parent_id
    assert any(
        item["semantic_type"] == ConstraintSemanticType.MAX_PRICE.value
        and item["value"] == 350
        for item in child["constraints"]["items"]
    )
    assert any(
        item["result_set_id"] == parent_id
        for item in refined["conversation_state"]["result_sets"]
    )


@pytest.mark.parametrize(
    ("phrase", "semantic_type", "matches"),
    (
        ("under $380", ConstraintSemanticType.MAX_PRICE_EXCLUSIVE, False),
        ("below $380", ConstraintSemanticType.MAX_PRICE_EXCLUSIVE, False),
        ("less than $380", ConstraintSemanticType.MAX_PRICE_EXCLUSIVE, False),
        ("up to $380", ConstraintSemanticType.MAX_PRICE, True),
        ("maximum $380", ConstraintSemanticType.MAX_PRICE, True),
        ("max $380", ConstraintSemanticType.MAX_PRICE, True),
        ("no more than $380", ConstraintSemanticType.MAX_PRICE, True),
    ),
)
def test_price_bound_wording_preserves_strictness_at_exact_boundary(
    phrase: str,
    semantic_type: ConstraintSemanticType,
    matches: bool,
) -> None:
    conversation = Conversation((PRODUCER_380,))

    body = conversation.ask(f"Find accommodation {phrase}")

    result = _latest_result(body)
    assert result["ordered_canonical_ids"] == (["producer-hall"] if matches else [])
    assert result["status"] == ("RESULTS" if matches else "EMPTY")
    constraint = result["constraints"]["items"][0]
    assert constraint["semantic_type"] == semantic_type.value
    assert constraint["value"] == 380
    assert constraint["scope"]["domain"] == "accommodation"
    if matches:
        room = conversation.traces[-1].qualifying_rooms[0]
        assert (
            room.name,
            room.rate,
            room.cost_period,
            room.contract,
            room.inclusions,
            room.other_fees,
        ) == (
            "Standard",
            "$380.00",
            "2027 Indicative costs",
            "44 weeks",
            "Internet included",
            "Refundable Deposit: $1,300",
        )
        assert (
            "Standard has a published room rate of $380.00 for the "
            "2027 Indicative costs period"
        ) in body["answer"]


def test_advertised_rate_never_substitutes_for_named_room_rate() -> None:
    record = _residence(
        "advertised-low",
        "Advertised Low Hall",
        rate="$470.00",
        catering=["Self-catered"],
    )
    metadata = record.metadata_json.model_copy(
        update={"advertised_rate": "Rates from A$380/week"}
    )
    record = record.model_copy(update={"metadata_json": metadata})
    conversation = Conversation((record,))

    body = conversation.ask("Find accommodation under $450")

    assert _latest_result(body)["status"] == "EMPTY"
    assert body["sources"] == []
    assert conversation.traces[-1].qualifying_rooms == ()


def test_qualifying_room_preserves_its_complete_paired_context() -> None:
    record = _residence(
        "paired-context",
        "Paired Context Hall",
        rate="$420.00",
        catering=["Self-catered"],
    )
    metadata = record.metadata_json.model_copy(
        update={
            "advertised_rate": "Rates from A$999/week",
            "rooms": [
                AccommodationRoom(
                    name="Budget single",
                    rate="$420.00",
                    contract="44-week agreement",
                    inclusions="Utilities and internet",
                    other_fees="A$250 refundable deposit",
                ),
                AccommodationRoom(
                    name="Premium studio",
                    rate="$500.00",
                    contract="52-week agreement",
                    inclusions="Utilities only",
                    other_fees="A$500 deposit",
                ),
            ],
        }
    )
    record = record.model_copy(update={"metadata_json": metadata})
    conversation = Conversation((record,))

    body = conversation.ask("Find accommodation under $450")

    assert body["status"] == "ok"
    assert "Rates from A$999/week" in body["answer"]  # display only
    assert "Budget single has a published room rate" in body["answer"]
    assert "$420.00" in body["answer"]
    assert "2027 Indicative costs" in body["answer"]
    assert "44-week agreement" in body["answer"]
    assert "Utilities and internet" in body["answer"]
    assert "A$250 refundable deposit" in body["answer"]
    assert "Premium studio" not in body["answer"]
    assert "52-week agreement" not in body["answer"]
    assert "total" not in body["answer"].casefold()
    trace = conversation.traces[-1]
    assert len(trace.qualifying_rooms) == 1
    assert trace.qualifying_rooms[0].name == "Budget single"
    assert trace.qualifying_rooms[0].rate == "$420.00"
    assert trace.qualifying_rooms[0].cost_period == "2027 Indicative costs"
    assert trace.qualifying_rooms[0].contract == "44-week agreement"
    assert trace.qualifying_rooms[0].inclusions == "Utilities and internet"
    assert trace.qualifying_rooms[0].other_fees == "A$250 refundable deposit"
    assert "Rates from A$999/week" not in trace.evidence_bundle.selected_evidence[0].evidence_text


def test_public_result_exposes_exact_producer_shaped_qualifying_room() -> None:
    conversation = Conversation((PRODUCER_380,))

    body = conversation.ask("accommodation under $450")

    assert body["items"][0]["qualifying_evidence"] == {
        "type": "room_rate",
        "room_name": "Standard",
        "rate": "$380.00",
        "cost_period": "2027 Indicative costs",
        "contract": "44 weeks",
        "inclusions": "Internet included",
        "other_fees": "Refundable Deposit: $1,300",
    }
    unfiltered = Conversation((PRODUCER_380,)).ask(
        "Show me accommodation options"
    )
    assert unfiltered["items"][0]["qualifying_evidence"] is None


@pytest.mark.parametrize(
    "room_rate",
    ("From $380.00", "$380/month", "$380-$420", None),
)
def test_ambiguous_nonweekly_nonaud_or_missing_room_rate_is_incomplete(
    room_rate: str | None,
) -> None:
    record = _residence(
        "unknown-price",
        "Unknown Price Hall",
        rate=room_rate,
        catering=["Self-catered"],
    )
    metadata = record.metadata_json.model_copy(
        update={"advertised_rate": "Rates from A$300/week"}
    )
    record = record.model_copy(update={"metadata_json": metadata})
    conversation = Conversation((record,))

    body = conversation.ask("Find accommodation under $450")

    assert body["status"] == "insufficient_evidence"
    assert _latest_result(body)["status"] == "INCOMPLETE"
    assert conversation.traces[-1].evidence_bundle.answer_state == AnswerState.UNKNOWN
    assert conversation.traces[-1].qualifying_rooms == ()


def test_missing_cost_period_makes_structured_room_rate_incomplete() -> None:
    record = _residence(
        "missing-period",
        "Missing Period Hall",
        rate="$380.00",
        cost_period=None,
        advertised_rate="Rates from A$300/week",
        catering=["Self-catered"],
    )
    conversation = Conversation((record,))

    body = conversation.ask("Find accommodation up to $380")

    assert body["status"] == "insufficient_evidence"
    assert _latest_result(body)["status"] == "INCOMPLETE"
    assert body["answer_state"] == "UNKNOWN"
    assert conversation.traces[-1].qualifying_rooms == ()


@pytest.mark.parametrize("question", ("Find accommodation budget $380", "Find accommodation < $380"))
def test_unapproved_price_wording_does_not_create_a_numeric_constraint(
    question: str,
) -> None:
    conversation = Conversation((PRODUCER_380,))

    body = conversation.ask(question)

    assert all(
        item["semantic_type"]
        not in {"max_price", "max_price_exclusive"}
        for item in _latest_result(body)["constraints"]["items"]
    )


def test_price_filter_preserves_source_order_without_cheapest_ranking() -> None:
    first = _residence(
        "first-published",
        "First Published Hall",
        rate="$430.00",
        catering=["Self-catered"],
    )
    second = _residence(
        "second-published",
        "Second Published Hall",
        rate="$400.00",
        catering=["Self-catered"],
    )
    conversation = Conversation((first, second))

    body = conversation.ask("Find accommodation under $450")

    assert _latest_result(body)["ordered_canonical_ids"] == [
        "first-published",
        "second-published",
    ]
    assert "cheapest" not in body["answer"].casefold()


def test_truthful_empty_requires_complete_evaluation() -> None:
    conversation = Conversation((ALPHA, BRAVO, CHARLIE))

    body = conversation.ask("Find accommodation under $100")

    assert body["status"] == "insufficient_evidence"
    assert "completely evaluated" in body["answer"]
    assert _latest_result(body)["status"] == "EMPTY"
    assert conversation.traces[-1].evidence_bundle.answer_state == AnswerState.DERIVED


def test_missing_price_evidence_is_incomplete_not_empty() -> None:
    conversation = Conversation((MYSTERY,))

    body = conversation.ask("Are there housing options below $100?")

    assert body["status"] == "insufficient_evidence"
    assert "cannot truthfully report no matches" in body["answer"]
    assert _latest_result(body)["status"] == "INCOMPLETE"
    trace = conversation.traces[-1]
    assert trace.evidence_bundle.answer_state == AnswerState.UNKNOWN


def test_compare_first_two_uses_retained_order_and_preserves_missingness() -> None:
    conversation = Conversation((ALPHA, BRAVO, CHARLIE))
    conversation.ask("What accommodation options are there?")

    body = conversation.ask("Could you compare the first two?")

    assert [source["record_id"] for source in body["sources"]] == [
        ALPHA.record_id,
        BRAVO.record_id,
    ]
    assert "Bravo Hall" in body["answer"]
    assert "Residence location: not published" in body["answer"]
    comparison = body["items"][0]
    assert comparison["type"] == "comparison"
    assert [item["canonical_id"] for item in comparison["records"]] == [
        "alpha-hall",
        "bravo-hall",
    ]
    location = next(
        field for field in comparison["fields"] if field["name"] == "location"
    )
    advertised = next(
        field
        for field in comparison["fields"]
        if field["name"] == "advertised_rate"
    )
    assert [value["value"] for value in advertised["values"]] == [
        "$300.00",
        "$450.00",
    ]
    assert location["values"] == [
        {
            "record_id": ALPHA.record_id,
            "value": "Acton campus",
            "state": "published",
        },
        {
            "record_id": BRAVO.record_id,
            "value": None,
            "state": "not_published",
        },
    ]
    trace = conversation.traces[-1]
    assert trace.interpretation.intent.name == "compare"
    assert trace.selected_canonical_ids == ("alpha-hall", "bravo-hall")
    assert trace.evidence_bundle.answer_state == AnswerState.PARTIAL


def test_second_result_stays_stable_and_drives_fact_followups() -> None:
    class ReorderingVector:
        calls = 0

        def search(self, _question, *, allowed_records, **_kwargs):
            self.calls += 1
            return tuple(
                VectorHit(record, 0.99 - index / 100, ("whole",))
                for index, record in enumerate(reversed(allowed_records))
            )

    vector = ReorderingVector()
    conversation = Conversation((ALPHA, BRAVO, CHARLIE), vector=vector)
    conversation.ask("Give me some accommodation choices")

    cost = conversation.ask("How much is the second one?")
    catering = conversation.ask("What catering arrangement does it have?")
    application = conversation.ask("Where do I submit its housing application?")

    for body in (cost, catering, application):
        assert body["sources"][0]["record_id"] == BRAVO.record_id
        selected = body["conversation_state"]["recent_entities"][0]
        assert selected["kind"] == "residence"
        assert selected["canonical_id"] == "bravo-hall"
    assert "$450.00" in cost["answer"]
    assert "Catered meal plan" in catering["answer"]
    assert "starrezhousing.com" in application["answer"]
    assert application["actions"] == [
        {
            "type": "application",
            "label": "Apply now",
            "url": "https://anu.starrezhousing.com/StarRezPortalX",
            "record_id": BRAVO.record_id,
            "source_id": "accommodation_anu_study",
        }
    ]
    assert "standalone course prerequisite" not in application["answer"]
    assert vector.calls == 0, "retained ordinals must not rerun ranking"


def test_current_availability_is_partial_unknown_with_official_next_action() -> None:
    conversation = Conversation((ALPHA, BRAVO))
    conversation.ask("Show accommodation options")
    conversation.ask("How much is the first one?")

    body = conversation.ask("Are there any rooms available?")

    assert body["status"] == "insufficient_evidence"
    assert "unknown" in body["answer"]
    assert "starrezhousing.com" in body["answer"]
    assert "is available" not in body["answer"].casefold()
    assert "rooms are available" not in body["answer"].casefold()
    assert body["answer_state"] == "UNKNOWN"
    assert body["actions"][0]["type"] == "application"
    trace = conversation.traces[-1]
    assert trace.evidence_bundle.answer_state == AnswerState.UNKNOWN
    assert any(
        item.field == "vacancy_status"
        for item in trace.evidence_bundle.missing_evidence
    )


def test_qualifying_price_evidence_does_not_change_vacancy_unknown() -> None:
    conversation = Conversation((PRODUCER_380,))
    price = conversation.ask("Find accommodation up to $380")
    assert price["status"] == "ok"

    vacancy = conversation.ask("Is there a room available right now?")

    assert vacancy["status"] == "insufficient_evidence"
    assert vacancy["answer_state"] == "UNKNOWN"
    assert "unknown" in vacancy["answer"].casefold()
    assert "is available" not in vacancy["answer"].casefold()


def test_clicked_result_is_revalidated_and_drives_typed_followup() -> None:
    conversation = Conversation((ALPHA, BRAVO))
    broad = conversation.ask("Show accommodation options")
    card = broad["items"][1]

    body = conversation.ask(
        "How much does it cost?",
        selected_result={
            "result_set_id": card["result_set_id"],
            "canonical_id": card["canonical_id"],
            "ordinal": card["ordinal"],
        },
    )

    assert body["sources"][0]["record_id"] == BRAVO.record_id
    assert "$450.00" in body["answer"]
    assert body["conversation_state"]["selected_result"] == {
        "result_set_id": card["result_set_id"],
        "canonical_id": "bravo-hall",
        "ordinal": 2,
    }
    assert body["conversation_state"]["recent_entities"][0]["kind"] == "residence"


def test_clicked_result_rejects_ordinal_mismatch_and_foreign_identity() -> None:
    conversation = Conversation((ALPHA, BRAVO))
    broad = conversation.ask("Show accommodation options")
    result = _latest_result(broad)
    request = {
        "question": "How much does it cost?",
        "history": conversation.history,
        "conversation_state": conversation.state,
        "selected_result": {
            "result_set_id": result["result_set_id"],
            "canonical_id": "bravo-hall",
            "ordinal": 1,
        },
    }

    mismatch = conversation.client.post("/api/v1/ask", json=request)
    assert mismatch.status_code == 400

    tampered_state = dict(conversation.state)
    tampered_sets = [dict(item) for item in tampered_state["result_sets"]]
    tampered_sets[0]["ordered_canonical_ids"] = ["foreign-hall", "bravo-hall"]
    tampered_state["result_sets"] = tampered_sets
    request["conversation_state"] = tampered_state
    request["selected_result"] = {
        "result_set_id": result["result_set_id"],
        "canonical_id": "foreign-hall",
        "ordinal": 1,
    }

    foreign = conversation.client.post("/api/v1/ask", json=request)
    assert foreign.status_code == 400
    assert foreign.json()["sources"] == []


def test_accommodation_clarification_supports_natural_both() -> None:
    conversation = Conversation((ALPHA, BRAVO))
    clarification = conversation.ask("Tell me about accommodation")

    assert clarification["status"] == "needs_clarification"
    assert clarification["clarification"]["allow_multiple"] is True
    assert len(clarification["clarification"]["options"]) == 2

    body = conversation.ask("both")

    assert [source["record_id"] for source in body["sources"]] == [
        ALPHA.record_id,
        BRAVO.record_id,
    ]
    assert [item["canonical_id"] for item in body["items"]] == [
        "alpha-hall",
        "bravo-hall",
    ]
    assert body["conversation_state"]["pending_clarification"] is None


def test_structured_clarification_selection_is_current_and_tamper_safe() -> None:
    conversation = Conversation((ALPHA, BRAVO))
    clarification = conversation.ask("Tell me about accommodation")
    pending = clarification["clarification"]
    selection = {
        "clarification_id": pending["id"],
        "option_ids": [option["id"] for option in pending["options"]],
    }

    body = conversation.ask("Use those options", clarification_selection=selection)

    assert [source["record_id"] for source in body["sources"]] == [
        ALPHA.record_id,
        BRAVO.record_id,
    ]

    fresh = Conversation((ALPHA, BRAVO))
    clarification = fresh.ask("Tell me about accommodation")
    pending = clarification["clarification"]
    invalid = fresh.client.post(
        "/api/v1/ask",
        json={
            "question": "Use those options",
            "history": fresh.history,
            "conversation_state": fresh.state,
            "clarification_selection": {
                "clarification_id": pending["id"],
                "option_ids": ["accommodation:residence:foreign-hall"],
            },
        },
    )
    assert invalid.status_code == 400
    assert invalid.json()["sources"] == []

    stale_state = dict(fresh.state)
    stale_pending = dict(stale_state["pending_clarification"])
    stale_options = [dict(option) for option in stale_pending["options"]]
    stale_options[0] = {
        "id": "accommodation:residence:stale-hall",
        "label": "Stale Hall",
    }
    stale_pending["options"] = stale_options
    stale_state["pending_clarification"] = stale_pending
    stale = fresh.client.post(
        "/api/v1/ask",
        json={
            "question": "Use that option",
            "history": fresh.history,
            "conversation_state": stale_state,
            "clarification_selection": {
                "clarification_id": pending["id"],
                "option_ids": ["accommodation:residence:stale-hall"],
            },
        },
    )
    assert stale.status_code == 200
    assert stale.json()["status"] == "needs_clarification"
    assert all(
        option["id"] != "accommodation:residence:stale-hall"
        for option in stale.json()["clarification"]["options"]
    )


def test_course_switch_then_return_recovers_typed_residence() -> None:
    course = load_course_program_records("fixtures/day5_course_program_records.json")[0]
    conversation = Conversation((ALPHA, BRAVO, course))
    conversation.ask("What are my accommodation options?")
    conversation.ask("What is the weekly rate for the second one?")

    course_body = conversation.ask("What are the prerequisites for COMP1110?")
    returned = conversation.ask("Return to accommodation")

    assert course_body["sources"][0]["domain"] == "courses"
    assert returned["sources"][0]["record_id"] == BRAVO.record_id
    assert returned["conversation_state"]["recent_entities"][0]["kind"] == "residence"
    trace = conversation.traces[-1]
    assert trace.interpretation.intent.operation == "return_topic"
    assert trace.interpretation.entity.kind == EntityKind.RESIDENCE
    assert trace.selected_canonical_ids == ("bravo-hall",)


def _twelve_residences():
    return tuple(
        _residence(
            f"page-{index}-hall",
            f"Page {index} Hall",
            rate=f"${300 + index}.00",
            catering=["Self-catered" if index % 2 else "Catered meal plan"],
        )
        for index in range(1, 13)
    )


def _next_page_request(body):
    page = body["result_page"]
    assert page["next_ordinal"] is not None
    return {
        "result_set_id": page["result_set_id"],
        "start_ordinal": page["next_ordinal"],
        "limit": 5,
    }


def test_stable_result_continuation_pages_twelve_without_reranking() -> None:
    records = _twelve_residences()
    conversation = Conversation(records)

    first = conversation.ask("Show me accommodation options")
    second = conversation.ask(
        "Show more", result_page=_next_page_request(first)
    )
    third = conversation.ask(
        "Show me more", result_page=_next_page_request(second)
    )
    terminal = conversation.ask("What else?")

    result_set = _latest_result(first)
    result_set_id = result_set["result_set_id"]
    pages = (first, second, third)
    assert [item["ordinal"] for item in first["items"]] == [1, 2, 3, 4, 5]
    assert [item["ordinal"] for item in second["items"]] == [6, 7, 8, 9, 10]
    assert [item["ordinal"] for item in third["items"]] == [11, 12]
    assert [page["result_page"]["result_set_id"] for page in pages] == [
        result_set_id,
        result_set_id,
        result_set_id,
    ]
    assert third["result_page"] == {
        "result_set_id": result_set_id,
        "start_ordinal": 11,
        "returned": 2,
        "has_more": False,
        "next_ordinal": None,
    }
    assert terminal["items"] == []
    assert terminal["result_page"] == {
        "result_set_id": result_set_id,
        "start_ordinal": 13,
        "returned": 0,
        "has_more": False,
        "next_ordinal": None,
    }
    all_ids = [
        item["canonical_id"] for page in pages for item in page["items"]
    ]
    assert all_ids == result_set["ordered_canonical_ids"]
    assert len(all_ids) == len(set(all_ids)) == 12


@pytest.mark.parametrize("phrase", ("show more", "show me more", "what else?"))
def test_natural_continuation_variants_use_the_retained_cursor(phrase: str) -> None:
    conversation = Conversation(_twelve_residences())
    first = conversation.ask("Show me accommodation options")

    second = conversation.ask(phrase)

    assert [item["ordinal"] for item in second["items"]] == [6, 7, 8, 9, 10]
    assert second["result_page"]["result_set_id"] == first["result_page"][
        "result_set_id"
    ]


def test_natural_continuation_rejects_missing_cursor() -> None:
    conversation = Conversation(_twelve_residences())
    first = conversation.ask("Show me accommodation options")
    state_without_cursor = {
        **conversation.state,
        "result_page": None,
    }

    response = conversation.client.post(
        "/api/v1/ask",
        json={
            "question": "show more",
            "history": conversation.history,
            "conversation_state": state_without_cursor,
        },
    )

    assert first["result_page"]["next_ordinal"] == 6
    assert response.status_code == 400


def test_natural_continuation_rejects_cursor_for_different_result_set() -> None:
    conversation = Conversation(_twelve_residences())
    first = conversation.ask("Show me accommodation options")
    active_result_set = conversation.state["result_sets"][0]
    other_result_set_id = "rs:accommodation:other"
    other_result_set = {
        **active_result_set,
        "result_set_id": other_result_set_id,
    }
    state_with_wrong_cursor = {
        **conversation.state,
        "result_sets": [active_result_set, other_result_set],
        "result_page": {
            "result_set_id": other_result_set_id,
            "next_ordinal": 6,
        },
    }

    response = conversation.client.post(
        "/api/v1/ask",
        json={
            "question": "show more",
            "history": conversation.history,
            "conversation_state": state_with_wrong_cursor,
        },
    )

    assert first["result_page"]["result_set_id"] == active_result_set[
        "result_set_id"
    ]
    assert response.status_code == 400


def test_page_two_click_keeps_original_result_set_ordinal() -> None:
    conversation = Conversation(_twelve_residences())
    first = conversation.ask("Show me accommodation options")
    second = conversation.ask(
        "Show me more", result_page=_next_page_request(first)
    )
    seventh = second["items"][1]

    body = conversation.ask(
        "How much does it cost?",
        selected_result={
            "result_set_id": seventh["result_set_id"],
            "canonical_id": seventh["canonical_id"],
            "ordinal": seventh["ordinal"],
        },
    )

    assert seventh["ordinal"] == 7
    assert body["conversation_state"]["selected_result"]["ordinal"] == 7
    assert body["sources"][0]["record_id"] == seventh["record_id"]


def test_refined_child_result_set_owns_its_continuation() -> None:
    conversation = Conversation(_twelve_residences())
    first = conversation.ask("Show me accommodation options")
    parent_id = first["result_page"]["result_set_id"]

    refined = conversation.ask("self-catered")
    child = _latest_result(refined)
    continued = conversation.ask("Show more")

    assert child["parent_result_set_id"] == parent_id
    assert refined["result_page"]["result_set_id"] == child["result_set_id"]
    assert continued["result_page"]["result_set_id"] == child["result_set_id"]
    assert continued["result_page"]["start_ordinal"] == 6
    assert all(
        item["canonical_id"] in child["ordered_canonical_ids"]
        for item in continued["items"]
    )


def test_result_page_rejects_unknown_stale_invalid_oversized_and_injected_ids() -> None:
    conversation = Conversation(_twelve_residences())
    first = conversation.ask("Show me accommodation options")
    valid = _next_page_request(first)

    for bad_page in (
        {**valid, "result_set_id": "rs:foreign:1"},
        {**valid, "start_ordinal": 1},
        {**valid, "start_ordinal": 0},
        {**valid, "limit": 6},
    ):
        response = conversation.client.post(
            "/api/v1/ask",
            json={
                "question": "Show more",
                "history": conversation.history,
                "conversation_state": conversation.state,
                "result_page": bad_page,
            },
        )
        assert response.status_code == 400

    refined = conversation.ask("self-catered")
    stale_parent = conversation.client.post(
        "/api/v1/ask",
        json={
            "question": "Show more",
            "history": conversation.history,
            "conversation_state": conversation.state,
            "result_page": valid,
        },
    )
    assert refined["result_page"]["result_set_id"] != valid["result_set_id"]
    assert stale_parent.status_code == 400

    tampered_state = dict(conversation.state)
    tampered_sets = [dict(item) for item in tampered_state["result_sets"]]
    tampered_sets[0]["ordered_canonical_ids"][5] = "client-created-hall"
    tampered_state["result_sets"] = tampered_sets
    injected = conversation.client.post(
        "/api/v1/ask",
        json={
            "question": "Show more",
            "history": conversation.history,
            "conversation_state": tampered_state,
            "result_page": _next_page_request(refined),
        },
    )
    assert injected.status_code == 400


def test_public_item_union_validates_real_shapes_and_rejects_malformed_items() -> None:
    result = PublicResultItem(
        record_id=ALPHA.record_id,
        source_id=ALPHA.source_id,
        canonical_id=ALPHA.entity_id,
        title=ALPHA.title,
        url=ALPHA.canonical_url,
        domain="accommodation",
        result_set_id="rs:test:1",
        ordinal=1,
    )
    comparison = PublicComparisonItem(
        result_set_id="rs:test:1",
        records=[result],
        fields=[
            PublicComparisonField(
                name="location",
                label="Location",
                values=[
                    PublicComparisonValue(
                        record_id=ALPHA.record_id,
                        value="Acton campus",
                        state="published",
                    )
                ],
            )
        ],
    )
    adapter = TypeAdapter(AskResponse)

    result_response = adapter.validate_python(
        OkResponse(answer="result", items=[result], request_id="req-result")
    )
    comparison_response = adapter.validate_python(
        OkResponse(
            answer="comparison",
            items=[comparison],
            request_id="req-comparison",
        )
    )

    assert isinstance(result_response.items[0], PublicResultItem)
    assert isinstance(comparison_response.items[0], PublicComparisonItem)
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "status": "ok",
                "answer": "bad",
                "items": [{"type": "result", "record_id": "missing-fields"}],
                "request_id": "req-bad",
            }
        )
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "status": "ok",
                "answer": "bad discriminator",
                "items": [{"type": "invented"}],
                "request_id": "req-bad-type",
            }
        )


def test_openapi_exposes_the_public_item_discriminator() -> None:
    schema = create_app().openapi()
    item_schema = schema["components"]["schemas"]["OkResponse"]["properties"][
        "items"
    ]["items"]

    assert item_schema["discriminator"] == {
        "propertyName": "type",
        "mapping": {
            "comparison": "#/components/schemas/PublicComparisonItem",
            "job": "#/components/schemas/PublicJobItem",
            "result": "#/components/schemas/PublicResultItem",
        },
    }


def test_day4_structured_api_golden_flow() -> None:
    course = load_course_program_records(
        "fixtures/day5_course_program_records.json"
    )[0]
    conversation = Conversation((*_twelve_residences(), course))

    page_one = conversation.ask("Show me accommodation options")
    page_two = conversation.ask(
        "Show me more", result_page=_next_page_request(page_one)
    )
    refined = conversation.ask("self-catered")
    priced = conversation.ask("under $450")
    compared = conversation.ask("compare first two")
    selected = conversation.ask("tell me about the second one")
    cost = conversation.ask("how much does it cost?")
    vacancy = conversation.ask("is there availability?")
    application = conversation.ask("how do I apply?")
    course_body = conversation.ask("What are the prerequisites for COMP1110?")
    returned = conversation.ask("back to accommodation")

    assert [item["ordinal"] for item in page_one["items"]] == [1, 2, 3, 4, 5]
    assert [item["ordinal"] for item in page_two["items"]] == [6, 7, 8, 9, 10]
    assert page_one["result_page"]["result_set_id"] == page_two["result_page"][
        "result_set_id"
    ]
    refined_set = _latest_result(refined)
    priced_set = _latest_result(priced)
    assert refined_set["parent_result_set_id"] == page_one["result_page"][
        "result_set_id"
    ]
    assert priced_set["parent_result_set_id"] == refined_set["result_set_id"]
    assert all(
        item["qualifying_evidence"]["type"] == "room_rate"
        for item in priced["items"]
    )
    assert compared["items"][0]["type"] == "comparison"
    second_record_id = compared["items"][0]["records"][1]["record_id"]
    assert selected["sources"][0]["record_id"] == second_record_id
    assert cost["sources"][0]["record_id"] == second_record_id
    assert "$" in cost["answer"]
    assert vacancy["status"] == "insufficient_evidence"
    assert vacancy["answer_state"] == "UNKNOWN"
    assert application["actions"][0]["type"] == "application"
    assert application["actions"][0]["record_id"] == second_record_id
    assert course_body["sources"][0]["domain"] == "courses"
    assert returned["sources"][0]["record_id"] == second_record_id
    assert conversation.traces[-1].interpretation.intent.operation == "return_topic"
