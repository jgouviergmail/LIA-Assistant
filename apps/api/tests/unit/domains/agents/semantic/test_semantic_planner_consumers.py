"""The router and planner consume the same account-scoped semantic contracts."""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from src.core.config import settings
from src.core.context import request_tool_manifests_ctx
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType
from src.domains.agents.registry.catalogue import (
    CostProfile,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.agents.semantic.planner_links import dependencies_with_plan_sources
from src.domains.agents.services.query_analyzer_service import QueryAnalyzerService


def _contracts() -> list[ToolManifest]:
    return [
        ToolManifest(
            name="mcp_user_people",
            agent="mcp_people_agent",
            description="Read contacts",
            parameters=[],
            outputs=[
                OutputFieldSchema(
                    "result.people[].email", "string", "Email", semantic_type="email_address"
                )
            ],
            cost=CostProfile(),
            permissions=PermissionProfile(),
            mutation_policy="read",
        ),
        ToolManifest(
            name="mcp_user_send",
            agent="mcp_mail_agent",
            description="Send mail",
            parameters=[
                ParameterSchema("to", "string", True, "Recipient", semantic_type="email_address")
            ],
            outputs=[],
            cost=CostProfile(),
            permissions=PermissionProfile(),
            mutation_policy="confirm",
        ),
    ]


@contextmanager
def _request(manifests: list[ToolManifest]) -> Iterator[None]:
    token = request_tool_manifests_ctx.set(manifests)
    try:
        yield
    finally:
        request_tool_manifests_ctx.reset(token)


def test_replanning_publishes_available_parameter_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "semantic_linking_enabled", True)
    plan = ExecutionPlan(
        user_id="user",
        steps=[
            ExecutionStep(
                step_id="lookup",
                step_type=StepType.TOOL,
                tool_name="mcp_user_people",
                agent_name="mcp_people_agent",
            ),
            ExecutionStep(
                step_id="send",
                step_type=StepType.TOOL,
                tool_name="mcp_user_send",
                agent_name="mcp_mail_agent",
                depends_on=["lookup"],
            ),
        ],
    )
    with _request(_contracts()):
        rendered = dependencies_with_plan_sources("dependencies", plan)
    assert rendered.startswith("dependencies\n")
    assert '"send.to": ["$steps.lookup.result.people[0].email"]' in rendered
    assert dependencies_with_plan_sources("dependencies", None) == "dependencies"
    with _request([]):
        assert dependencies_with_plan_sources("dependencies", plan) == "dependencies"


@pytest.mark.asyncio
async def test_analyzer_expands_from_account_mcp_requirements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "semantic_expansion_evidence_driven_enabled", False)
    analyzer = QueryAnalyzerService.__new__(QueryAnalyzerService)
    with _request(_contracts()):
        expanded = await analyzer._expand_domains_for_semantic_types(
            ["mcp_mail"], has_person_reference=True, reasoning_trace=[]
        )
    assert expanded == ["mcp_mail", "contact"]
    with _request([]):
        assert await analyzer._expand_domains_for_semantic_types(
            ["mcp_mail"], has_person_reference=True, reasoning_trace=[]
        ) == ["mcp_mail"]
