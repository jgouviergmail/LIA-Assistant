"""Production prompt/catalogue/schema seams with explicitly controlled inputs."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool

from scripts.semantic_simulation.corpus import Scenario
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.context import request_tool_manifests_ctx
from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.models import create_initial_state
from src.domains.agents.nodes.react_observed_gaps import requested_outcome_block
from src.domains.agents.nodes.react_prompt import build_system_prompt
from src.domains.agents.prompts import get_smart_planner_prompt
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.registry.semantic_inventory import collect_static_manifests
from src.domains.agents.semantic.expansion_service import generate_semantic_dependencies_for_prompt
from src.domains.agents.services.planner.human_message import build_planner_human_message
from src.domains.agents.services.smart_catalogue_service import SmartCatalogueService
from src.domains.agents.tools.calendar_tools import create_event_tool, get_events_tool
from src.domains.agents.tools.emails_tools import get_emails_tool
from src.domains.agents.tools.google_contacts_tools import get_contacts_tool
from src.domains.agents.tools.routes_tools import get_route_tool
from src.domains.agents.tools.tasks_tools import create_task_tool
from src.domains.agents.tools.weather_tools import get_weather_forecast_tool


def _native_tools(candidates: tuple[object, ...]) -> tuple[BaseTool, ...]:
    """Decorator annotations remain callables; runtime must expose real tools."""
    tools: list[BaseTool] = []
    for candidate in candidates:
        if not isinstance(candidate, BaseTool):
            raise TypeError("The semantic probe requires bound native BaseTool objects")
        tools.append(candidate)
    return tuple(tools)


TOOLS = _native_tools(
    (
        get_contacts_tool,
        get_emails_tool,
        create_event_tool,
        create_task_tool,
        get_events_tool,
        get_route_tool,
        get_weather_forecast_tool,
    )
)


@contextmanager
def _bound_contracts(manifests: list[ToolManifest]) -> Iterator[None]:
    token = request_tool_manifests_ctx.set(manifests)
    try:
        yield
    finally:
        request_tool_manifests_ctx.reset(token)


def registry_for_probe() -> AgentRegistry:
    registry = AgentRegistry()
    names = {tool.name for tool in TOOLS}
    for manifest in collect_static_manifests():
        if manifest.name in names:
            registry.register_tool_manifest(manifest)
    return registry


def manifests_for_case(registry: AgentRegistry, scenario: Scenario) -> list[ToolManifest]:
    """Include contact lookup as a distractor in cases that require no lookup."""
    names = {scenario.action, "get_contacts_tool"}
    if "email" in scenario.domains:
        names.add("get_emails_tool")
    if scenario.required_read:
        names.add(scenario.required_read)
    return [registry.get_tool_manifest(name) for name in sorted(names)]


def planner_messages(
    scenario: Scenario,
    manifests: list[ToolManifest],
    registry: AgentRegistry,
    intelligence: QueryIntelligence | None = None,
) -> list[BaseMessage]:
    service = SmartCatalogueService(registry)

    catalogue = json.dumps([service._manifest_to_dict(m) for m in manifests], ensure_ascii=False)
    intelligence = intelligence or QueryIntelligence(
        original_query=scenario.query,
        english_query=scenario.query,
        immediate_intent="create" if scenario.action.startswith("create_") else "search",
        immediate_confidence=1.0,
        user_goal=(
            UserGoal.TAKE_ACTION
            if scenario.action.startswith("create_")
            else UserGoal.FIND_INFORMATION
        ),
        goal_reasoning="Controlled semantic simulation input; analyzer not evaluated.",
        domains=list(scenario.domains),
        primary_domain=scenario.domains[-1],
        user_language="fr",
    )
    with _bound_contracts(manifests):
        dependencies = generate_semantic_dependencies_for_prompt(
            list(scenario.domains), manifests=manifests
        )
    prompt = get_smart_planner_prompt(
        user_goal=intelligence.user_goal.value,
        intent=intelligence.immediate_intent,
        domains=", ".join(scenario.domains),
        anticipated_needs="(none)",
        catalogue=catalogue,
        original_query=scenario.query,
        user_timezone=DEFAULT_USER_DISPLAY_TIMEZONE,
        user_language="fr",
        semantic_dependencies=dependencies,
        primary_domain=scenario.domains[-1],
        is_multi_domain=True,
    )
    return [
        SystemMessage(content=prompt),
        HumanMessage(content=build_planner_human_message(intelligence)),
    ]


def react_messages(
    scenario: Scenario,
    manifests: list[ToolManifest] | None = None,
    intelligence: QueryIntelligence | None = None,
) -> list[BaseMessage]:
    state = create_initial_state(
        user_id=UUID("11111111-2222-3333-4444-555555555555"),
        session_id="offline-boundary",
        run_id="semantic-simulation",
        user_timezone=DEFAULT_USER_DISPLAY_TIMEZONE,
        user_language="fr",
    )
    state["query_intelligence"] = {"domains": list(scenario.domains)}
    if intelligence is not None:
        state["query_intelligence"] = intelligence.to_serializable_dict()
    selected = (
        manifests if manifests is not None else manifests_for_case(registry_for_probe(), scenario)
    )
    with _bound_contracts(selected):
        prompt = build_system_prompt(state, tool_names=[manifest.name for manifest in selected])
        coverage = requested_outcome_block(state)
        if coverage:
            prompt += "\n\n" + coverage
    return [SystemMessage(content=prompt), HumanMessage(content=scenario.query)]
