"""The native decision sees complete authorized retrieved data, with no generative caps."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.field_names import FIELD_DISPLAY_ONLY
from src.domains.agents.data_registry.models import RegistryItem, RegistryItemMeta, RegistryItemType
from src.domains.agents.nodes import jev_initiative as gate
from src.domains.agents.nodes.initiative_node import _format_execution_summary
from src.domains.agents.nodes.jev_initiative_context import (
    InitiativeSemanticContext,
    canonical_initiative_context,
)
from src.domains.agents.nodes.jev_initiative_evidence import (
    InitiativeEvidence,
    named_initiative_state,
)
from src.domains.agents.orchestration.schemas import AgentResult
from src.domains.agents.weather.catalogue_manifests import get_weather_forecast_catalogue_manifest
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.typesafe_client import ChoiceAnswer, TypeSafeClient

pytestmark = pytest.mark.unit
ARGUMENTS = {
    "execution_summary": "Generative summary",
    "available_tools": "Generative tool rendering",
    "memory_facts": "Generative memories",
    "user_interests": "Generative interests",
    "semantic_dependencies": "Dependencies",
    "connection_candidates": "Candidates",
    "user_language": "fr",
    "user_timezone": "UTC",
    "original_query": "Synthetic query",
    "current_datetime": "2026-10-04",
    "max_actions": 2,
}


def build_context(registry, evidence, *, agent_results=None, **kwargs):
    return canonical_initiative_context(
        arguments=ARGUMENTS,
        registry=registry,
        agent_results=agent_results or {},
        current_turn_id=4,
        memory_facts=["Full retrieved memory"],
        interest_profile={
            "enabled": True,
            "interests": [{"topic": "Synthetic", "status": "active"}],
        },
        manifests=[get_weather_forecast_catalogue_manifest],
        evidence=evidence,
        **kwargs,
    )


def test_full_sources_survive_all_generative_projection_caps() -> None:
    payload = {
        "body": "x" * 151 + "required survey",
        "attendees": ["first", "second"],
        "details": {"required_file": "missing"},
        "organizer": {"name": "synthetic"},
        **{f"field_{i}": i for i in range(9)},
    }
    registry = {"a": {"id": "a", "type": "event", "payload": payload, "meta": {"turn_id": 4}}}
    projection = InitiativeEvidence()
    _format_execution_summary({}, registry, 4, projection)
    assert projection.omissions
    evidence = InitiativeEvidence()
    context = build_context(registry, evidence)
    assert context["retrieved_turn_results"]["registry"]["a"]["payload"] == payload
    assert "execution_summary" not in context
    assert not evidence.omissions
    assert context["memory_facts"] == ["Full retrieved memory"]
    assert context["user_interests"]["interests"][0]["topic"] == "Synthetic"
    assert context["available_tools"][0]["parameters"]


def test_card_only_fields_are_removed_before_serialization_even_when_nested_or_opaque() -> None:
    item = {
        "id": "a",
        "type": RegistryItemType.EMAIL.value,
        "payload": {"subject": "Visible", FIELD_DISPLAY_ONLY: {"body": object()}},
        "meta": {
            "turn_id": 4,
            "source": "synthetic",
            "display": {"body": object(), "truncated": True},
        },
    }
    original_display = item["meta"]["display"]
    evidence = InitiativeEvidence()
    context = build_context(
        {"a": item},
        evidence,
        agent_results={"4:email": {"status": "success", "data": {"registry_updates": {"a": item}}}},
    )
    rendered = json.dumps(context["retrieved_turn_results"])
    assert '"display"' not in rendered and '"truncated"' not in rendered
    assert not evidence.omissions
    assert item["meta"]["display"] is original_display
    assert FIELD_DISPLAY_ONLY in item["payload"]


@pytest.mark.parametrize("as_tuple", [False, True])
def test_nested_business_payload_meta_display_remains_complete(as_tuple) -> None:
    business = {
        "payload": {"duration": 3, FIELD_DISPLAY_ONLY: {"private": object()}},
        "meta": {"display": {"unit": "hours", "instruction": "Bring a printed survey"}},
    }
    values = (business,) if as_tuple else [business]
    evidence = InitiativeEvidence()
    context = build_context(
        {"a": {"payload": {"values": values}, "meta": {"turn_id": 4}}}, evidence
    )
    assert context["retrieved_turn_results"]["registry"]["a"]["payload"]["values"] == [
        {
            "payload": {"duration": 3},
            "meta": {"display": {"unit": "hours", "instruction": "Bring a printed survey"}},
        }
    ]
    assert not evidence.omissions
    assert FIELD_DISPLAY_ONLY in business["payload"]


@pytest.mark.parametrize("external_type", ["external", ["external"], "EVENT"])
def test_business_envelope_without_registry_provenance_keeps_display(external_type) -> None:
    business = {
        "id": "external-id",
        "type": external_type,
        "payload": {"required_file": "survey"},
        "meta": {"display": {"status": "missing"}},
    }
    evidence = InitiativeEvidence()
    context = build_context(
        {"a": {"payload": {"details": business}, "meta": {"turn_id": 4}}}, evidence
    )
    assert context["retrieved_turn_results"]["registry"]["a"]["payload"]["details"] == business
    assert not evidence.omissions


def test_typed_registry_and_agent_result_keep_business_metadata_and_current_failures() -> None:
    item = RegistryItem(
        id="a",
        type=RegistryItemType.EVENT,
        payload={"summary": "Synthetic"},
        meta=RegistryItemMeta(
            source="synthetic", domain="event", turn_id=4, display={"private": "CARD_ONLY"}
        ),
    )
    failed = AgentResult(agent_name="event_agent", status="error", error="Synthetic failure")
    evidence = InitiativeEvidence()
    context = build_context(
        {"a": item}, evidence, agent_results={"3:old": failed, "4:current": failed}
    )
    results = context["retrieved_turn_results"]
    assert list(results["agent_results"]) == ["4:current"]
    assert results["agent_results"]["4:current"]["error"] == "Synthetic failure"
    assert "failed_steps" in results["agent_results"]["4:current"]
    assert results["registry"]["a"]["meta"]["domain"] == "event"
    assert "CARD_ONLY" not in json.dumps(context)
    assert not evidence.omissions


def test_stale_registry_is_excluded_even_when_current_view_claims_it() -> None:
    evidence = InitiativeEvidence()
    context = build_context(
        {
            "old": {"payload": {"title": "Old"}, "meta": {"turn_id": 3}},
            "now": {"payload": {"title": "Now"}, "meta": {"turn_id": 4}},
        },
        evidence,
        registry_is_current=True,
    )
    assert list(context["retrieved_turn_results"]["registry"]) == ["now"]
    assert not evidence.omissions


@pytest.mark.parametrize(
    "value",
    [
        object(),
        float("nan"),
        float("inf"),
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_opaque_and_nonfinite_authorized_values_fail_closed_without_stringification(value) -> None:
    evidence = InitiativeEvidence()
    context = build_context({"a": {"payload": {"value": value}, "meta": {"turn_id": 4}}}, evidence)
    assert context == {"retrieved_turn_results": {"unavailable": True}}
    assert evidence.omissions == {"not_serializable": 1}


def test_finite_decimal_preserves_exact_known_application_encoding() -> None:
    evidence = InitiativeEvidence()
    context = build_context(
        {"a": {"payload": {"amount": Decimal("0.0100")}, "meta": {"turn_id": 4}}}, evidence
    )
    assert context["retrieved_turn_results"]["registry"]["a"]["payload"]["amount"] == "0.0100"
    assert not evidence.omissions


def test_known_application_datetime_is_encoded_without_an_opaque_fallback() -> None:
    evidence = InitiativeEvidence()
    context = build_context(
        {"a": {"payload": {"date": datetime(2026, 10, 4, tzinfo=UTC)}, "meta": {"turn_id": 4}}},
        evidence,
    )
    assert (
        context["retrieved_turn_results"]["registry"]["a"]["payload"]["date"]
        == "2026-10-04T00:00:00+00:00"
    )
    assert not evidence.omissions


@pytest.mark.parametrize("truncated", [False, True])
def test_only_explicit_source_truncation_limits_retrieved_scope(truncated) -> None:
    evidence = InitiativeEvidence()
    build_context(
        {"a": {"payload": {"truncated": truncated, "has_more": True}, "meta": {"turn_id": 4}}},
        evidence,
    )
    assert evidence.omissions == ({"source_truncated": 1} if truncated else {})


@pytest.mark.parametrize("as_tuple", [False, True])
def test_nested_card_scope_cannot_be_bypassed_with_tuple(as_tuple) -> None:
    evidence = InitiativeEvidence()
    nested = {
        "id": "nested",
        "type": RegistryItemType.EVENT.value,
        "payload": {"title": "Visible", FIELD_DISPLAY_ONLY: {"private": object()}},
        "meta": {"source": "synthetic", "display": {"private": object()}},
    }
    values = (nested,) if as_tuple else [nested]
    context = build_context(
        {"a": {"payload": {"values": values}, "meta": {"turn_id": 4}}}, evidence
    )
    assert context["retrieved_turn_results"]["registry"]["a"]["payload"]["values"] == [
        {
            "id": "nested",
            "type": RegistryItemType.EVENT.value,
            "payload": {"title": "Visible"},
            "meta": {"source": "synthetic"},
        }
    ]
    assert not evidence.omissions


async def test_generative_projection_loss_does_not_disable_full_native_source() -> None:
    evidence = InitiativeEvidence()
    context = build_context(
        {"a": {"payload": {"body": "x" * 1000}, "meta": {"turn_id": 4}}}, evidence
    )
    state = named_initiative_state(ARGUMENTS, evidence, context=context)
    answer = ChoiceAnswer(
        type="choice",
        choice="possible_utility",
        confidence=1,
        probabilities={"possible_utility": 1},
    )
    with patch.object(
        gate,
        "choose_with_jev",
        AsyncMock(return_value=DecisionAttempt(outcome="success", answer=answer)),
    ) as native:
        assert (
            await gate.choose_empty_initiative(
                "Unchanged generative prompt",
                str(uuid4()),
                "run",
                state=state,
                omissions=evidence.omissions,
            )
            is None
        )
    native.assert_awaited_once()
    assert native.call_args.kwargs["state"] == state


def test_native_bridges_keep_all_consumers_and_lines_before_generative_caps(monkeypatch) -> None:
    from unittest.mock import MagicMock

    from src.core.constants import (
        SEMANTIC_CANDIDATES_MAX_LINES,
        SEMANTIC_CANDIDATES_MAX_TOOLS_PER_TYPE,
    )
    from src.domains.agents.nodes import initiative_node as node
    from src.domains.agents.semantic import expansion_service

    names = [f"tool_{i}" for i in range(SEMANTIC_CANDIDATES_MAX_TOOLS_PER_TYPE + 2)]
    manifests = []
    for name in names:
        manifest = MagicMock(agent="contact_agent", parameters=[])
        manifest.name = name
        manifests.append(manifest)
    definition = MagicMock(source_domains=["email"], used_in_tools=names)
    registry = MagicMock()
    registry.get_by_domain.return_value = {
        f"type_{i}" for i in range(SEMANTIC_CANDIDATES_MAX_LINES + 2)
    }
    registry.get.return_value = definition
    monkeypatch.setattr(node.settings, "semantic_linking_enabled", True)
    monkeypatch.setattr(
        expansion_service, "get_expansion_service", lambda: MagicMock(registry=registry)
    )
    monkeypatch.setattr(
        expansion_service,
        "generate_semantic_dependencies_for_prompt",
        lambda *a, **k: "Generated dependencies",
    )
    projection = InitiativeEvidence()
    native = InitiativeSemanticContext()
    _, rendered = node._build_semantic_context(["email"], manifests, projection, native)
    assert "more candidate types omitted" in rendered
    assert len(native.bridges) == SEMANTIC_CANDIDATES_MAX_LINES + 2
    assert all(bridge["consumer_tools"] == names for bridge in native.bridges)
    evidence = InitiativeEvidence()
    context = build_context({}, evidence, semantic_context=native)
    assert context["connection_candidates"] == native.bridges
    assert not evidence.omissions
    assert projection.omissions["semantic_bridges_omitted"] > 0


@pytest.mark.parametrize("failed", [False, True])
def test_disabled_semantic_feature_is_known_but_failed_loading_is_incomplete(
    monkeypatch, failed
) -> None:
    from src.domains.agents.nodes import initiative_node as node
    from src.domains.agents.semantic import expansion_service

    monkeypatch.setattr(node.settings, "semantic_linking_enabled", failed)
    monkeypatch.setattr(
        expansion_service,
        "generate_semantic_dependencies_for_prompt",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("synthetic")),
    )
    native = InitiativeSemanticContext()
    node._build_semantic_context(["email"], [], InitiativeEvidence(), native)
    evidence = InitiativeEvidence()
    context = build_context({}, evidence, semantic_context=native)
    assert context["semantic_dependencies"]["enabled"] is failed
    assert evidence.omissions == ({"context_unavailable": 1} if failed else {})


async def test_oversized_complete_native_source_is_rejected_before_http() -> None:
    evidence = InitiativeEvidence()
    context = build_context(
        {"a": {"payload": {"body": "x" * 40000}, "meta": {"turn_id": 4}}}, evidence
    )
    state = named_initiative_state(ARGUMENTS, evidence, context=context)
    import httpx

    from src.domains.agents.prompts.prompt_loader import load_prompt
    from src.infrastructure.llm.typesafe_client import ChoiceQuestion, TypeSafeError

    assert not evidence.omissions
    async with httpx.AsyncClient() as client:
        with patch.object(client, "stream") as http:
            with pytest.raises(TypeSafeError) as caught:
                await TypeSafeClient(client, "synthetic-key").choose(
                    model="jev-1.13.0",
                    state=state,
                    question=ChoiceQuestion.model_validate_json(
                        load_prompt("jev_initiative_question")
                    ),
                    timeout_seconds=1,
                )
    assert caught.value.code == "request_too_large"
    assert caught.value.usage is None
    http.assert_not_called()
