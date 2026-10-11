"""Available request contracts must drive native and MCP tool chaining."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace

import pytest

from src.core.context import request_tool_manifests_ctx
from src.domains.agents.registry.catalogue import (
    CostProfile,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.agents.registry.semantic_inventory import collect_static_manifests
from src.domains.agents.semantic.expansion_service import (
    collect_manifest_param_consumers,
    generate_jinja2_suggestions,
    get_semantic_provider_tool_names,
)
from src.domains.agents.semantic.param_guard import (
    check_semantic_params,
    strip_placeholder_arguments,
)
from src.domains.agents.services.catalogue.closure import resolve_closure_additions


def _source(name: str = "mcp_user_people", domain: str = "mcp_people") -> ToolManifest:
    return ToolManifest(
        name=name,
        agent=f"{domain}_agent",
        description="Read a verified user-owned tool contract",
        parameters=[],
        outputs=[
            OutputFieldSchema("result.people[].email", "string", "Email", False, "email_address")
        ],
        cost=CostProfile(),
        permissions=PermissionProfile(),
        mutation_policy="read",
    )


def _consumer() -> ToolManifest:
    return replace(
        _source("mcp_user_send", "mcp_mail"),
        parameters=[
            ParameterSchema("to", "string", True, "Recipient", semantic_type="email_address")
        ],
        outputs=[],
        mutation_policy="confirm",
    )


@contextmanager
def _request(manifests: list[ToolManifest]) -> Iterator[None]:
    token = request_tool_manifests_ctx.set(manifests)
    try:
        yield
    finally:
        request_tool_manifests_ctx.reset(token)


def test_user_mcp_contracts_generate_real_step_references() -> None:
    with _request([_source(), _consumer()]):
        suggestions = generate_jinja2_suggestions(
            "mcp_user_send",
            "to",
            ["lookup"],
            step_tool_mapping={"lookup": "mcp_user_people"},
        )
    assert suggestions == ["$steps.lookup.result.people[0].email"]


def test_explicit_empty_request_cannot_resurrect_global_tools() -> None:
    with _request([]):
        assert generate_jinja2_suggestions("send_email_tool", "to", ["get_contacts"]) == []


def test_related_types_do_not_authorize_an_email_as_a_message_handle() -> None:
    consumer = replace(
        _consumer(),
        parameters=[ParameterSchema("id", "string", True, "Message", semantic_type="message_id")],
    )
    with _request([_source(), consumer]):
        assert (
            generate_jinja2_suggestions(
                consumer.name,
                "id",
                ["lookup"],
                step_tool_mapping={"lookup": "mcp_user_people"},
            )
            == []
        )


def test_all_available_read_only_sources_are_protected_without_editorial_links() -> None:
    sources = [_source(f"source_{number}") for number in range(5)]
    mutation = replace(_source("create_person"), mutation_policy="confirm")
    with _request([*sources, mutation, _consumer()]):
        protected = get_semantic_provider_tool_names(["mcp_people", "mcp_mail"])
    assert protected == {source.name for source in sources}


def test_source_is_not_protected_for_same_domain_or_unavailable_consumer() -> None:
    with _request([_source(), replace(_consumer(), agent="mcp_people_agent")]):
        assert get_semantic_provider_tool_names(["mcp_people", "mcp_mail"]) == set()
    with _request([_source()]):
        assert get_semantic_provider_tool_names(["mcp_people", "mcp_mail"]) == set()


def test_nested_annotations_inform_consumers_without_substituting_a_whole_object() -> None:
    consumer = replace(
        _consumer(),
        parameters=[
            ParameterSchema(
                "payload",
                "object",
                True,
                "Recipients",
                schema={
                    "properties": {
                        "recipients": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "x-semantic-type": "email_address",
                            },
                        }
                    }
                },
            )
        ],
    )
    assert collect_manifest_param_consumers([consumer]) == {"email_address": {consumer.name}}
    with _request([_source(), consumer]):
        assert get_semantic_provider_tool_names(["mcp_people", "mcp_mail"]) == {"mcp_user_people"}
        assert (
            generate_jinja2_suggestions(
                consumer.name,
                "payload",
                ["lookup"],
                step_tool_mapping={"lookup": "mcp_user_people"},
            )
            == []
        )


def test_inventory_covers_split_manifest_modules() -> None:
    names = {manifest.name for manifest in collect_static_manifests()}
    assert {
        "get_person_overview_tool",
        "send_email_to_me_tool",
        "get_lia_preferences_tool",
    } <= names
    assert "get_email_attachment_tool" in names


def test_person_name_guard_reads_user_mcp_nested_contract() -> None:
    consumer = replace(
        _consumer(),
        parameters=[
            ParameterSchema(
                "payload",
                "object",
                True,
                "Recipients",
                schema={
                    "properties": {
                        "recipients": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "x-semantic-type": "email_address",
                            },
                        },
                        "notes": {"type": "string"},
                    }
                },
            )
        ],
    )
    with _request([consumer]):
        violation = check_semantic_params(
            consumer.name,
            {"payload": {"recipients": ["Marc Lemoine"], "notes": "Marc Lemoine"}},
            {"marc lemoine"},
        )
        assert violation is not None
        assert violation.param_name == "payload.recipients[0]"
        assert violation.semantic_type == "email_address"
        assert (
            check_semantic_params(
                consumer.name,
                {
                    "payload": {
                        "recipients": ["marc@example.com"],
                        "notes": "Marc Lemoine",
                    }
                },
                {"marc lemoine"},
            )
            is None
        )


def test_placeholder_guard_reads_available_user_mcp_contract() -> None:
    consumer = replace(
        _consumer(),
        parameters=[
            ParameterSchema("to", "string", False, "Recipient", semantic_type="email_address")
        ],
    )
    with _request([consumer]):
        assert strip_placeholder_arguments(consumer.name, {"to": "null"}) == {}
    with _request([]):
        assert strip_placeholder_arguments(consumer.name, {"to": "null"}) == {"to": "null"}


def test_placeholder_guard_preserves_literal_content_after_semantic_annotation() -> None:
    consumer = replace(
        _consumer(),
        parameters=[
            ParameterSchema("notes", "string", False, "User content", semantic_type="Text")
        ],
    )
    with _request([consumer]):
        for value in ("N/A", "none", "null"):
            assert strip_placeholder_arguments(consumer.name, {"notes": value}) == {"notes": value}


def test_scalar_parameter_receives_an_array_element_not_a_json_array() -> None:
    source = replace(
        _source(),
        outputs=[
            OutputFieldSchema(
                "result.people[].emails",
                "array",
                "Email addresses",
                semantic_type="email_address",
            )
        ],
    )
    with _request([source, _consumer()]):
        assert generate_jinja2_suggestions(
            "mcp_user_send", "to", ["lookup"], step_tool_mapping={"lookup": source.name}
        ) == ["$steps.lookup.result.people[0].emails[0]"]


def test_array_parameter_does_not_receive_a_scalar_without_explicit_wrapping() -> None:
    consumer = replace(
        _consumer(),
        parameters=[
            ParameterSchema("to", "array", True, "Recipients", semantic_type="email_address")
        ],
    )
    with _request([_source(), consumer]):
        suggestions = generate_jinja2_suggestions(
            consumer.name, "to", ["lookup"], step_tool_mapping={"lookup": _source().name}
        )
        assert json.loads(suggestions[0]) == ["$steps.lookup.result.people[0].email"]


def test_object_cannot_feed_a_scalar_even_when_annotated_with_the_same_type() -> None:
    source = replace(
        _source(),
        outputs=[
            OutputFieldSchema(
                "result.people", "object", "Wrong shape", semantic_type="email_address"
            )
        ],
    )
    with _request([source, _consumer()]):
        assert (
            generate_jinja2_suggestions(
                "mcp_user_send",
                "to",
                ["lookup"],
                step_tool_mapping={"lookup": source.name},
            )
            == []
        )


def test_heterogeneous_schema_union_does_not_publish_a_certain_email_dependency() -> None:
    consumer = replace(
        _consumer(),
        parameters=[
            ParameterSchema(
                "value",
                "string",
                True,
                "Email or name",
                schema={
                    "anyOf": [
                        {"type": "string", "x-semantic-type": "email_address"},
                        {"type": "string"},
                    ]
                },
            )
        ],
    )
    assert collect_manifest_param_consumers([consumer]) == {}


@pytest.mark.parametrize("semantic_type", ["Text", "QuantitativeValue"])
def test_generic_value_classes_do_not_join_unrelated_domain_values(
    semantic_type: str,
) -> None:
    source = replace(
        _source(),
        outputs=[OutputFieldSchema("result.value", "string", "Value", semantic_type=semantic_type)],
    )
    consumer = replace(
        _consumer(),
        parameters=[ParameterSchema("to", "string", True, "Value", semantic_type=semantic_type)],
    )
    with _request([source, consumer]):
        assert not generate_jinja2_suggestions(
            consumer.name, "to", ["lookup"], step_tool_mapping={"lookup": source.name}
        )
        assert not get_semantic_provider_tool_names(["mcp_people", "mcp_mail"])
        assert not resolve_closure_additions([consumer], [source, consumer], {})
