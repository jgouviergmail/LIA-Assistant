"""Independent requested-result oracles, including empty, opaque and pending outputs."""

import json
from datetime import date

import msgpack
import pytest

from src.core.context import request_tool_manifests_ctx
from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.analysis.query_intelligence_helpers import (
    reconstruct_query_intelligence,
)
from src.domains.agents.analysis.requested_outcomes import (
    GoalFieldExpectation,
    GoalRequirement,
    anchored_requirements,
)
from src.domains.agents.registry.semantic_inventory import collect_static_manifests
from src.domains.agents.services.outcome_evidence import (
    observe_requested_outcome,
    requested_outcome_coverage,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def available():
    token = request_tool_manifests_ctx.set(collect_static_manifests())
    yield
    request_tool_manifests_ctx.reset(token)


def _goal(**changes: object) -> GoalRequirement:
    return GoalRequirement.model_validate(
        {
            "domain": "contact",
            "label": "contacts",
            "source_quote": "liste mes contacts",
            **changes,
        }
    )


def _coverage(
    goal: GoalRequirement, data: dict[str, object], tool: str = "get_contacts_tool"
) -> str:
    evidence = observe_requested_outcome(tool, {}, {"success": True, "structured_data": data})
    assert evidence is not None
    return requested_outcome_coverage([goal], [evidence], timezone="Pacific/Honolulu")[0].status


def test_unasked_history_and_unavailable_domains_do_not_become_goals() -> None:
    goal = _goal()
    assert anchored_requirements([goal], "Liste mes contacts", ["contact"]) == (goal,)
    assert anchored_requirements([goal], "Quelle météo ?", ["contact", "weather"]) == ()
    assert anchored_requirements([goal], "Liste mes contacts", []) == ()
    invented = _goal(
        expected_fields=[{"field": "name", "expected_value": "Ada", "source_quote": "Ada"}]
    )
    assert anchored_requirements([invented], "Liste mes contacts", ["contact"]) == ()


@pytest.mark.parametrize(
    "changes",
    [
        {"min_count": 100},
        {"requires_complete": True},
        {
            "expected_fields": [
                {
                    "field": "name",
                    "expected_value": "urgent",
                    "source_quote": "mes contacts",
                }
            ]
        },
        {
            "expected_fields": [
                {
                    "field": "date",
                    "expected_value": "2026-10-08",
                    "operator": "on_date",
                    "source_quote": "mes contacts",
                }
            ]
        },
    ],
)
def test_a_neighboring_quote_cannot_corroborate_invented_constraints(
    changes: dict[str, object],
) -> None:
    assert anchored_requirements([_goal(**changes)], "Liste mes contacts", ["contact"]) == ()


def test_literal_localized_date_is_checked_against_its_actual_calendar_value() -> None:
    goal = _goal(
        source_quote="8 octobre 2026",
        expected_fields=[
            {
                "field": "date",
                "expected_value": "2026-10-08",
                "operator": "on_date",
                "source_quote": "8 octobre 2026",
            }
        ],
    )
    assert anchored_requirements([goal], "Contacts le 8 octobre 2026", ["contact"]) == (goal,)
    forged = goal.model_copy(
        update={
            "expected_fields": (
                goal.expected_fields[0].model_copy(update={"expected_value": "2026-10-09"}),
            )
        }
    )
    assert anchored_requirements([forged], "Contacts le 8 octobre 2026", ["contact"]) == ()


def test_requirements_survive_real_msgpack_checkpoint_round_trip() -> None:
    original = QueryIntelligence(
        original_query="Liste mes contacts",
        english_query="List my contacts",
        immediate_intent="list",
        immediate_confidence=1,
        user_goal=UserGoal.FIND_INFORMATION,
        goal_reasoning="Explicit request",
        domains=["contact"],
        requested_outcomes=(_goal(),),
    )
    checkpoint = msgpack.unpackb(msgpack.packb(original.to_serializable_dict()), raw=False)
    reconstructed = reconstruct_query_intelligence(checkpoint)
    assert reconstructed.requested_outcomes == original.requested_outcomes
    checkpoint.pop("requested_outcomes")
    assert reconstruct_query_intelligence(checkpoint).requested_outcomes == ()


def test_empty_collection_can_answer_a_list_but_not_three_requested_items() -> None:
    assert _coverage(_goal(collection_key="contacts"), {"contacts": []}) == "satisfied"
    assert _coverage(_goal(collection_key="contacts", min_count=3), {"contacts": []}) == "missing"


def test_constraints_must_hold_on_the_same_item() -> None:
    goal = _goal(
        collection_key="contacts",
        expected_fields=[
            {"field": "name", "expected_value": "Ada", "source_quote": "Ada"},
            {
                "field": "email",
                "expected_value": "ada@example.test",
                "source_quote": "ada@example.test",
            },
        ],
    )
    assert (
        _coverage(
            goal,
            {
                "contacts": [
                    {"name": "Ada", "email": "other@example.test"},
                    {"name": "Other", "email": "ada@example.test"},
                ]
            },
        )
        == "missing"
    )
    assert (
        _coverage(goal, {"contacts": [{"name": "Ada", "email": "ada@example.test"}]}) == "satisfied"
    )


@pytest.mark.parametrize(
    "data,status",
    [
        ({"contacts": []}, "unknown"),
        ({"contacts": [], "next_page_token": "opaque"}, "partial"),
        ({"contacts": [], "retrieval_complete": True}, "satisfied"),
    ],
)
def test_exhaustiveness_needs_positive_provider_evidence(
    data: dict[str, object], status: str
) -> None:
    assert _coverage(_goal(collection_key="contacts", requires_complete=True), data) == status


def test_date_is_civil_while_timestamp_is_compared_in_the_users_timezone() -> None:
    goal = _goal(
        expected_fields=[
            GoalFieldExpectation(
                field="date",
                expected_value="2026-10-08",
                operator="on_date",
                source_quote="8 octobre",
            )
        ]
    )
    assert _coverage(goal, {"date": "2026-10-08"}) == "satisfied"
    assert _coverage(goal, {"date": "2026-10-08T01:00:00Z"}) == "missing"
    assert _coverage(goal, {"date": "2026-10-08T23:00:00Z"}) == "satisfied"


def test_a_draft_is_pending_and_opaque_fields_do_not_prove_completion() -> None:
    goal = _goal(
        domain="event",
        kind="action",
        operation="create",
        expected_fields=[{"field": "summary", "expected_value": "Revue", "source_quote": "Revue"}],
    )
    assert (
        _coverage(goal, {"draft_id": "opaque", "summary": "Revue"}, "create_event_tool")
        == "pending_confirmation"
    )
    assert _coverage(goal, {"event_id": "opaque"}, "create_event_tool") == "pending_confirmation"
    direct_goal = _goal(
        domain="reminder",
        kind="action",
        operation="create",
        expected_fields=[{"field": "content", "expected_value": "Revue", "source_quote": "Revue"}],
    )
    assert (
        _coverage(direct_goal, {"reminder_id": "opaque"}, "create_reminder_tool")
        == "pending_confirmation"
    )
    assert (
        _coverage(direct_goal, {"content": "Revue"}, "create_reminder_tool")
        == "pending_confirmation"
    )


@pytest.mark.parametrize(
    "value,quote",
    [("ada@example.com", "ada@example.com.fr"), ("Ann", "Anna"), ("12", "1234")],
)
def test_a_literal_prefix_cannot_select_another_recipient_or_entity(value: str, quote: str) -> None:
    goal = _goal(
        source_quote=quote,
        expected_fields=[{"field": "name", "expected_value": value, "source_quote": quote}],
    )
    assert anchored_requirements([goal], quote, ["contact"]) == ()


def test_relative_date_uses_server_request_day_and_survives_next_day_resume() -> None:
    goal = _goal(
        source_quote="demain",
        expected_fields=[
            {
                "field": "date",
                "expected_value": "2026-10-07",
                "operator": "on_date",
                "source_quote": "demain",
                "reference_date": "2099-01-01",
            }
        ],
    )
    assert anchored_requirements([goal], "Demain", ["contact"]) == ()
    accepted = anchored_requirements(
        [goal], "Demain", ["contact"], reference_date=date(2026, 10, 6)
    )
    assert accepted[0].expected_fields[0].reference_date == "2026-10-06"
    assert (
        anchored_requirements(
            accepted,
            "Demain",
            ["contact"],
            reference_date=date(2026, 10, 7),
            trusted_checkpoint=True,
        )
        == accepted
    )


def test_partial_metadata_wins_over_data_claiming_complete() -> None:
    goal = _goal(
        source_quote="tous mes contacts",
        collection_key="contacts",
        requires_complete=True,
    )
    observation = observe_requested_outcome(
        "get_contacts_tool",
        {},
        {
            "success": True,
            "structured_data": {"contacts": [], "complete": True},
            "metadata": {"partial": True},
        },
    )
    assert requested_outcome_coverage([goal], [observation], timezone="UTC")[0].status == "partial"


def test_runtime_evidence_does_not_duplicate_a_large_canonical_payload() -> None:
    goal = _goal(collection_key="contacts", min_count=1)
    raw = {
        "success": True,
        "structured_data": {"contacts": [{"name": "Ada", "body": "x" * 2_000_000}]},
    }
    assert observe_requested_outcome("get_contacts_tool", {}, raw, requirements=()) is None
    observation = observe_requested_outcome("get_contacts_tool", {}, raw, requirements=[goal])
    assert observation is not None and len(json.dumps(observation)) < 1024
    assert len(raw["structured_data"]["contacts"][0]["body"]) == 2_000_000
    assert (
        requested_outcome_coverage([goal], [observation], timezone="UTC")[0].status == "satisfied"
    )
    changed = goal.model_copy(update={"min_count": 2})
    assert (
        requested_outcome_coverage([changed], [observation], timezone="UTC")[0].status == "unknown"
    )


def test_disabled_tool_and_invalid_json_never_produce_usable_evidence() -> None:
    assert observe_requested_outcome("unknown_tool", {}, {"success": True}) is None
    assert observe_requested_outcome("get_contacts_tool", {}, "not json") is None
    token = request_tool_manifests_ctx.set([])
    try:
        assert observe_requested_outcome("get_contacts_tool", {}, {"success": True}) is None
    finally:
        request_tool_manifests_ctx.reset(token)


def test_creating_an_event_never_satisfies_a_requested_deletion() -> None:
    goal = _goal(domain="event", kind="action", operation="delete")
    assert _coverage(goal, {"summary": "Revue"}, "create_event_tool") == "missing"


def test_a_business_pending_status_is_not_an_approval_request() -> None:
    assert (
        _coverage(_goal(collection_key="contacts"), {"status": "pending", "contacts": []})
        == "satisfied"
    )


def test_verified_later_read_resolves_the_previous_failure() -> None:
    goal = _goal(collection_key="contacts", min_count=1)
    failed = observe_requested_outcome("get_contacts_tool", {}, {"success": False})
    good = observe_requested_outcome(
        "get_contacts_tool",
        {},
        {"success": True, "data": {"contacts": [{"name": "Ada"}]}},
    )
    assert requested_outcome_coverage([goal], [failed], timezone="UTC")[0].status == "failed"
    assert (
        requested_outcome_coverage([goal], [failed, good], timezone="UTC")[0].status == "satisfied"
    )
