"""Structural scenario oracles: these tests make no claim about LLM decisions."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from typing import Literal
from uuid import UUID

import pytest

from src.core.context import UserMCPToolsContext, request_tool_manifests_ctx, user_mcp_tools_ctx
from src.domains.agents.models import MessagesState, create_initial_state
from src.domains.agents.nodes.initiative_semantic_bridges import build_semantic_candidate_lines
from src.domains.agents.nodes.jev_initiative_context import InitiativeSemanticContext
from src.domains.agents.nodes.jev_initiative_evidence import InitiativeEvidence
from src.domains.agents.nodes.react_prompt import build_system_prompt
from src.domains.agents.orchestration.condition_evaluator import ReferenceResolver
from src.domains.agents.registry.catalogue import (
    CostProfile,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.agents.semantic.core_types import load_core_types
from src.domains.agents.semantic.expansion_service import (
    SemanticExpansionService,
    generate_jinja2_suggestions,
    generate_semantic_dependencies_for_prompt,
    get_semantic_provider_tool_names,
)
from src.domains.agents.semantic.manifest_semantics import (
    available_manifest,
    required_parameter_semantic_types,
)
from src.domains.agents.semantic.param_guard import check_semantic_params
from src.domains.agents.semantic.type_registry import TypeRegistry
from src.domains.agents.services.catalogue.closure import resolve_closure_additions


def _contract(
    name: str,
    domain: str,
    *,
    parameters: list[ParameterSchema] | None = None,
    outputs: list[OutputFieldSchema] | None = None,
    mutation_policy: Literal["read", "confirm"] = "read",
) -> ToolManifest:
    return ToolManifest(
        name=name,
        agent=f"{domain}_agent",
        description="Declared contract for a deterministic semantic scenario",
        parameters=parameters or [],
        outputs=outputs or [],
        cost=CostProfile(),
        permissions=PermissionProfile(),
        mutation_policy=mutation_policy,
    )


def _email_source(name: str = "lookup_people") -> ToolManifest:
    return _contract(
        name,
        "contact",
        outputs=[
            OutputFieldSchema(
                "people[].email", "string", "Canonical email", semantic_type="email_address"
            )
        ],
    )


def _react_state() -> MessagesState:
    state = create_initial_state(UUID(int=0), "semantic-scenario", "semantic-scenario")
    state["query_intelligence"] = {"domains": ["contact", "email"]}
    return state


def _recipient_payload(*, required_leaf: bool) -> ParameterSchema:
    return ParameterSchema(
        "payload",
        "object",
        True,
        "The request payload",
        schema={
            "type": "object",
            "properties": {
                "to": {"type": "string", "x-semantic-type": "email_address"},
                "note": {"type": "string", "x-semantic-type": "Text"},
            },
            "required": ["to"] if required_leaf else [],
        },
    )


@contextmanager
def _request(manifests: list[ToolManifest]) -> Iterator[None]:
    token = request_tool_manifests_ctx.set(manifests)
    try:
        yield
    finally:
        request_tool_manifests_ctx.reset(token)


def test_explicit_empty_registry_is_populated_without_substituting_the_global_registry() -> None:
    registry = TypeRegistry()
    service = SemanticExpansionService(registry)
    assert service.registry is registry
    assert registry.get("Contact") is not None


@pytest.mark.asyncio
async def test_multiple_entity_evidence_resolves_two_distinct_sources_without_a_mutation() -> None:
    registry = TypeRegistry()
    load_core_types(registry)
    service = SemanticExpansionService(registry)
    assert await service.expand_domains_evidence_driven(
        ["route"],
        {"CalendarEvent", "Contact"},
        {"event_start_datetime", "email_address"},
        max_added_domains=2,
    ) == ["route", "event", "contact"]


def test_required_nested_recipient_has_a_read_only_source_in_closed_catalogue() -> None:
    consumer = _contract(
        "send_nested",
        "email",
        parameters=[_recipient_payload(required_leaf=True)],
        mutation_policy="confirm",
    )
    result = resolve_closure_additions([consumer], [_email_source(), consumer])
    assert result.additions == ["lookup_people"]
    assert result.consumers == {consumer.name}


def test_optional_nested_recipient_does_not_force_a_lookup() -> None:
    consumer = _contract(
        "write_note", "email", parameters=[_recipient_payload(required_leaf=False)]
    )
    result = resolve_closure_additions([consumer], [_email_source(), consumer])
    assert result.additions == []
    assert result.consumers == set()


def test_mutation_and_self_requiring_provider_cannot_discover_an_existing_handle() -> None:
    required_id = ParameterSchema("id", "string", True, "Message", semantic_type="message_id")
    output_id = OutputFieldSchema("id", "string", "Message", semantic_type="message_id")
    consumer = _contract("reply", "email", parameters=[required_id], mutation_policy="confirm")
    mutation = _contract("send_new", "email", outputs=[output_id], mutation_policy="confirm")
    circular = _contract("get_existing", "email", parameters=[required_id], outputs=[output_id])
    discovery = _contract("search_messages", "email", outputs=[output_id])
    result = resolve_closure_additions([consumer, mutation], [circular, mutation, discovery])
    assert result.additions == [discovery.name]


@pytest.mark.parametrize(
    ("produced", "consumed"),
    [
        ("email_address", "message_id"),
        ("contact_id", "event_id"),
        ("distance", "radius_meters"),
        ("Date", "datetime"),
        ("unix_timestamp", "datetime"),
        ("latitude", "longitude"),
        ("QuantitativeValue", "QuantitativeValue"),
        ("Text", "Text"),
    ],
)
def test_related_ids_units_dates_and_generic_roots_never_authorize_value_substitution(
    produced: str, consumed: str
) -> None:
    source = _contract(
        "source",
        "contact",
        outputs=[OutputFieldSchema("value", "string", "Source value", semantic_type=produced)],
    )
    consumer = _contract(
        "consume",
        "event",
        parameters=[ParameterSchema("value", "string", True, "Target", semantic_type=consumed)],
    )
    with _request([source, consumer]):
        assert (
            generate_jinja2_suggestions(
                consumer.name, "value", ["lookup"], step_tool_mapping={"lookup": source.name}
            )
            == []
        )
        assert get_semantic_provider_tool_names(["contact", "event"]) == set()


def test_singleton_array_suggestion_resolves_to_an_actual_array_in_the_executor() -> None:
    source = _email_source()
    consumer = _contract(
        "invite",
        "event",
        parameters=[
            ParameterSchema("attendees", "array", True, "Emails", semantic_type="email_address")
        ],
    )
    with _request([source, consumer]):
        suggestions = generate_jinja2_suggestions(
            consumer.name, "attendees", ["lookup"], step_tool_mapping={"lookup": source.name}
        )
    proposed = {"attendees": json.loads(suggestions[0])}
    actual = ReferenceResolver().resolve_args(
        proposed,
        {"lookup": {"people": [{"email": "ada@example.com"}, {"email": "grace@example.com"}]}},
    )
    assert actual == {"attendees": ["ada@example.com"]}


def test_account_contract_scope_blocks_a_source_from_another_account() -> None:
    source = _email_source()
    consumer = _contract(
        "send",
        "email",
        parameters=[ParameterSchema("to", "string", True, "Email", semantic_type="email_address")],
    )
    with _request([consumer]):
        assert (
            generate_jinja2_suggestions(
                consumer.name, "to", ["lookup"], step_tool_mapping={"lookup": source.name}
            )
            == []
        )
        assert get_semantic_provider_tool_names(["contact", "email"]) == set()


@pytest.mark.parametrize("keyword", ["allOf", "anyOf", "oneOf"])
def test_common_nested_email_contract_guard_rejects_a_resolved_person_name(keyword: str) -> None:
    email_branch = _recipient_payload(required_leaf=True).schema
    branches = [email_branch, email_branch]
    payload = {"to": "Ada Lovelace"}
    if keyword != "allOf":
        branches = [
            {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "x-semantic-type": "email_address"},
                    "kind": {"type": "string", "const": kind},
                },
                "required": ["to", "kind"],
            }
            for kind in ("meeting", "message")
        ]
        payload["kind"] = "meeting"
    parameter = ParameterSchema("payload", "object", True, "Recipients", schema={keyword: branches})
    consumer = _contract("send_nested", "email", parameters=[parameter], mutation_policy="confirm")
    with _request([consumer]):
        violation = check_semantic_params(consumer.name, {"payload": payload}, {"ada lovelace"})
    assert violation is not None
    assert violation.param_name == "payload.to"
    assert violation.semantic_type == "email_address"


@pytest.mark.parametrize("keyword", ["anyOf", "oneOf"])
def test_person_alternative_does_not_inherit_email_guard_or_required_email(keyword: str) -> None:
    parameter = ParameterSchema(
        "payload",
        "object",
        True,
        "Person name or address",
        schema={
            keyword: [
                {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "x-semantic-type": semantic_type},
                        "kind": {"type": "string", "const": kind},
                    },
                    "required": ["to", "kind"],
                }
                for semantic_type, kind in (("email_address", "email"), ("person_name", "person"))
            ]
        },
    )
    consumer = _contract("resolve_recipient", "email", parameters=[parameter])
    assert required_parameter_semantic_types(parameter) == set()
    with _request([consumer]):
        assert (
            check_semantic_params(
                consumer.name,
                {"payload": {"to": "Ada Lovelace", "kind": "person"}},
                {"ada lovelace"},
            )
            is None
        )
        assert (
            check_semantic_params(
                consumer.name,
                {"payload": {"to": "Ada Lovelace", "kind": "email"}},
                {"ada lovelace"},
            )
            is not None
        )


def test_ambiguous_scalar_union_never_blocks_a_permitted_person_name() -> None:
    parameter = ParameterSchema(
        "value",
        "string",
        True,
        "Name or email",
        schema={
            "anyOf": [
                {"type": "string", "x-semantic-type": "email_address"},
                {"type": "string", "x-semantic-type": "person_name"},
            ]
        },
    )
    consumer = _contract("resolve_recipient", "email", parameters=[parameter])
    with _request([consumer]):
        assert (
            check_semantic_params(consumer.name, {"value": "Ada Lovelace"}, {"ada lovelace"})
            is None
        )


def test_split_allof_required_constraint_applies_to_annotated_property() -> None:
    parameter = ParameterSchema(
        "payload",
        "object",
        True,
        "Required recipient from conjoined schemas",
        schema={
            "allOf": [
                {
                    "type": "object",
                    "properties": {"to": {"type": "string", "x-semantic-type": "email_address"}},
                },
                {"type": "object", "required": ["to"]},
            ]
        },
    )
    assert required_parameter_semantic_types(parameter) == {"email_address"}


@pytest.mark.parametrize("minimum", [0, 1])
def test_array_items_are_required_only_when_an_element_is_required(minimum: int) -> None:
    parameter = ParameterSchema(
        "payload",
        "object",
        True,
        "Recipient list",
        schema={
            "type": "object",
            "properties": {
                "attendees": {
                    "type": "array",
                    "minItems": minimum,
                    "items": {"type": "string", "x-semantic-type": "email_address"},
                }
            },
            "required": ["attendees"],
        },
    )
    assert required_parameter_semantic_types(parameter) == ({"email_address"} if minimum else set())


def test_nullable_nested_email_is_not_a_required_source() -> None:
    parameter = ParameterSchema(
        "payload",
        "object",
        True,
        "Optional actual recipient",
        schema={
            "type": "object",
            "properties": {
                "to": {
                    "anyOf": [
                        {"type": "string", "x-semantic-type": "email_address"},
                        {"type": "null"},
                    ]
                }
            },
            "required": ["to"],
        },
    )
    assert required_parameter_semantic_types(parameter) == set()


@pytest.mark.parametrize(
    ("minimum", "expected"),
    [(0, set()), (1, {"person_name"}), (3, {"person_name", "email_address", "phone_number"})],
)
def test_tuple_array_requires_only_guaranteed_positions(minimum: int, expected: set[str]) -> None:
    parameter = ParameterSchema(
        "recipient",
        "array",
        True,
        "Recipient tuple",
        schema={
            "type": "array",
            "minItems": minimum,
            "prefixItems": [
                {"type": "string", "x-semantic-type": "person_name"},
                {"type": "string", "x-semantic-type": "email_address"},
            ],
            "items": {"type": "string", "x-semantic-type": "phone_number"},
        },
    )
    assert required_parameter_semantic_types(parameter) == expected
    consumer = _contract("resolve_tuple", "email", parameters=[parameter])
    with _request([consumer]):
        assert (
            check_semantic_params(consumer.name, {"recipient": ["Ada Lovelace"]}, {"ada lovelace"})
            is None
        )
        violation = check_semantic_params(
            consumer.name, {"recipient": ["Ada Lovelace", "Ada Lovelace"]}, {"ada lovelace"}
        )
        assert violation is not None
        assert violation.param_name == "recipient[1]"


def test_runtime_dependencies_do_not_claim_a_disabled_ontology_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.config import settings

    monkeypatch.setattr(settings, "semantic_linking_enabled", True)
    consumer = _contract(
        "route_only",
        "route",
        parameters=[
            ParameterSchema(
                "destination", "string", True, "Destination", semantic_type="physical_address"
            )
        ],
    )
    with _request([consumer]):
        dependencies = generate_semantic_dependencies_for_prompt(
            ["contact", "route"], include_jinja2_patterns=False
        )
    assert "physical_address:" not in dependencies


def test_available_contact_contract_without_an_address_cannot_supply_an_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.config import settings

    monkeypatch.setattr(settings, "semantic_linking_enabled", True)
    names_only = _contract(
        "contact_names",
        "contact",
        outputs=[OutputFieldSchema("name", "string", "Name", semantic_type="person_name")],
    )
    consumer = _contract(
        "route",
        "route",
        parameters=[
            ParameterSchema("to", "string", True, "Destination", semantic_type="physical_address")
        ],
    )
    with _request([names_only, consumer]):
        assert "physical_address:" not in generate_semantic_dependencies_for_prompt(
            ["contact", "route"], include_jinja2_patterns=False
        )


def test_initiative_does_not_claim_an_address_in_a_names_only_source_contract() -> None:
    registry = TypeRegistry()
    load_core_types(registry)
    source = _contract(
        "contact_names",
        "contact",
        outputs=[OutputFieldSchema("name", "string", "Name", semantic_type="person_name")],
    )
    consumer = _contract(
        "route",
        "route",
        parameters=[
            ParameterSchema("to", "string", True, "Destination", semantic_type="physical_address")
        ],
    )
    native = InitiativeSemanticContext()
    with _request([source, consumer]):
        lines = build_semantic_candidate_lines(
            registry, ["contact"], [consumer], InitiativeEvidence(), native
        )
    assert lines == []
    assert native.bridges == []
    assert native.complete


@pytest.mark.parametrize("bound", [[], ["lookup_people"], ["send"], ["lookup_people", "send"]])
def test_react_semantic_prompt_reflects_the_catalogue_actually_bound(
    bound: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.core.config import settings

    monkeypatch.setattr(settings, "semantic_linking_enabled", True)
    source = _email_source()
    consumer = _contract(
        "send",
        "email",
        parameters=[ParameterSchema("to", "string", True, "Email", semantic_type="email_address")],
    )
    with _request([source, consumer]):
        prompt = build_system_prompt(_react_state(), tool_names=bound)
    assert ("email_address:" in prompt) == ({source.name, consumer.name} <= set(bound))


def test_iterative_individual_contracts_reach_react_without_entering_planner_catalogue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.config import settings

    monkeypatch.setattr(settings, "semantic_linking_enabled", True)
    source = _email_source("mcp_user_12345678_lookup")
    consumer = _contract(
        "mcp_user_12345678_send",
        "email",
        parameters=[ParameterSchema("to", "string", True, "Email", semantic_type="email_address")],
    )
    task = _contract("mcp_user_12345678_task", "mcp_people")
    server_key = str(UUID("12345678-2222-3333-4444-555555555555"))
    source = replace(source, mcp_origin="user", mcp_server_key=server_key)
    consumer = replace(consumer, mcp_origin="user", mcp_server_key=server_key)
    task = replace(task, delegates_execution=True, mcp_origin="user", mcp_server_key=server_key)
    context = UserMCPToolsContext(
        tool_manifests=[task],
        reactive_tool_manifests={source.name: source, consumer.name: consumer},
    )
    token = user_mcp_tools_ctx.set(context)
    try:
        with _request([task]):
            assert available_manifest(consumer.name) is consumer
            assert (
                check_semantic_params(consumer.name, {"to": "Ada Lovelace"}, {"ada lovelace"})
                is not None
            )
            prompt = build_system_prompt(
                _react_state(),
                tool_names=[source.name, consumer.name],
            )
            assert "email_address:" in prompt
        with _request([]):
            assert available_manifest(consumer.name) is None
            prompt = build_system_prompt(
                _react_state(),
                tool_names=[source.name, consumer.name],
            )
            assert "email_address:" not in prompt
        assert context.tool_manifests == [task]
    finally:
        user_mcp_tools_ctx.reset(token)
