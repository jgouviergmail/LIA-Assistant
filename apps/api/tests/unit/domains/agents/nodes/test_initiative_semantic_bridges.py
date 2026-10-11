"""Generic value shapes never become proactive connection candidates."""

import pytest

from src.core.context import request_tool_manifests_ctx
from src.domains.agents.nodes.initiative_semantic_bridges import build_semantic_candidate_lines
from src.domains.agents.nodes.jev_initiative_context import InitiativeSemanticContext
from src.domains.agents.nodes.jev_initiative_evidence import InitiativeEvidence
from src.domains.agents.registry.catalogue import (
    CostProfile,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.agents.semantic.semantic_type import SemanticType, TypeCategory
from src.domains.agents.semantic.type_registry import TypeRegistry

pytestmark = pytest.mark.unit


def _manifest(name: str, value_type: str, *, produces: bool = False) -> ToolManifest:
    return ToolManifest(
        name=name,
        agent="email_agent" if produces else "ticket_agent",
        description="Test contract",
        parameters=(
            []
            if produces
            else [ParameterSchema("value", "string", False, "Value", semantic_type=value_type)]
        ),
        outputs=(
            [OutputFieldSchema("value", "string", "Value", semantic_type=value_type)]
            if produces
            else []
        ),
        cost=CostProfile(),
        permissions=PermissionProfile(),
        mutation_policy="read",
    )


def test_generic_shapes_do_not_reach_rendered_or_native_candidates() -> None:
    registry = TypeRegistry()
    types = ("Text", "QuantitativeValue", "email_address")
    for type_name in types:
        registry.register(
            SemanticType(
                name=type_name,
                category=TypeCategory.CONTENT,
                source_domains=["email"],
                used_in_tools=[f"consume_{type_name}"],
            )
        )
    adjacent = [_manifest(f"consume_{type_name}", type_name) for type_name in types]
    sources = [_manifest(f"produce_{type_name}", type_name, produces=True) for type_name in types]
    native = InitiativeSemanticContext()
    evidence = InitiativeEvidence()
    token = request_tool_manifests_ctx.set([*sources, *adjacent])
    try:
        lines = build_semantic_candidate_lines(registry, ["email"], adjacent, evidence, native)
    finally:
        request_tool_manifests_ctx.reset(token)
    assert len(lines) == 1 and "email_address" in lines[0]
    assert [bridge["semantic_type"] for bridge in native.bridges] == ["email_address"]
    assert native.complete
    assert not evidence.omissions
