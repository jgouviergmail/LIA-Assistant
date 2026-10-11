"""Actual pipeline guards must not resurrect registry proof across a mutation."""

from collections.abc import Mapping
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.tools import StructuredTool

from src.core.context import request_tool_manifests_ctx
from src.core.field_names import FIELD_RESOLVED_PERSON_NAMES
from src.domains.agents.data_registry.models import RegistryItem, RegistryItemMeta, RegistryItemType
from src.domains.agents.orchestration import parallel_executor as pe
from src.domains.agents.orchestration.plan_schemas import ExecutionStep, StepType
from src.domains.agents.places.catalogue_manifests import get_current_location_catalogue_manifest
from src.domains.agents.registry.catalogue import (
    CostProfile,
    PermissionProfile,
    ToolManifest,
    is_read_only_tool,
)
from src.domains.agents.semantic.plan_proof_scope import effective_source_cutoff, plan_proof_config
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.weather.catalogue_manifests import get_current_weather_catalogue_manifest
from src.infrastructure.mcp.registration import build_mcp_react_task_manifest


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation_fails", [False, True])
@pytest.mark.parametrize("read_during_mutation", [False, True])
@pytest.mark.parametrize("delegated_mutation", [False, True])
async def test_read_mutation_old_consumer_is_blocked_then_fresh_read_can_feed_consumer(
    mutation_fails: bool,
    read_during_mutation: bool,
    delegated_mutation: bool,
) -> None:
    calls: list[str] = []

    async def read_location() -> UnifiedToolOutput:
        calls.append("read")
        item = RegistryItem(
            id="location_nancy",
            type=RegistryItemType.LOCATION,
            payload={"locality": "Nancy", "formatted_address": "Nancy, France"},
            meta=RegistryItemMeta(
                source="geocoding",
                domain="locations",
                tool_name="get_current_location_tool",
                timestamp=datetime.now(UTC),
            ),
        )
        return UnifiedToolOutput.data_success(
            message="Observed location",
            registry_updates={item.id: item},
        )

    async def mutate_location() -> dict[str, object]:
        calls.append("mutation")
        if read_during_mutation:
            assert (await execute("read_during", "get_current_location_tool", {})).success
        if mutation_fails:
            raise RuntimeError("The invocation may have changed remote data before failing")
        return {"success": True, "data": {"changed": True}}

    async def read_weather(location: str) -> dict[str, object]:
        calls.append("weather")
        return {"success": True, "data": {"location": location}}

    mutation = ToolManifest(
        name="update_location_scope_test_tool",
        agent="place_agent",
        description="Mutation scope oracle",
        parameters=[],
        outputs=[],
        cost=CostProfile(),
        permissions=PermissionProfile(),
        tool_category="update",
        mutation_policy="gated",
    )
    if delegated_mutation:
        mutation = build_mcp_react_task_manifest(
            tool_name="mcp_read_location_scope_task",
            agent_name="place_agent",
            server_name="Location scope oracle",
            description="Delegated invocation may include a write",
            parameters=[],
            semantic_keywords=[],
        )
        assert mutation.delegates_execution
        assert is_read_only_tool(mutation)
    manifests = {
        manifest.name: manifest
        for manifest in [
            get_current_location_catalogue_manifest,
            get_current_weather_catalogue_manifest,
            mutation,
        ]
    }
    tools = {
        "get_current_location_tool": StructuredTool.from_function(
            coroutine=read_location, name="get_current_location_tool", description="Location oracle"
        ),
        mutation.name: StructuredTool.from_function(
            coroutine=mutate_location, name=mutation.name, description="Mutation oracle"
        ),
        "get_current_weather_tool": StructuredTool.from_function(
            coroutine=read_weather, name="get_current_weather_tool", description="Weather oracle"
        ),
    }
    registry = MagicMock()
    registry.get_tool.side_effect = tools.__getitem__
    caller_config = {
        "metadata": {"user_id": "00000000-0000-0000-0000-000000000001"},
        "configurable": {FIELD_RESOLVED_PERSON_NAMES: ["nancy"]},
    }
    config = plan_proof_config(caller_config)
    completed: dict = {}
    accumulated: dict = {}

    def manifest_for_step(**kwargs: object) -> tuple[ToolManifest, None]:
        step = kwargs["step"]
        assert isinstance(step, ExecutionStep)
        return manifests[step.tool_name], None

    async def execute(
        step_id: str, tool_name: str, parameters: Mapping[str, object]
    ) -> pe.StepResult:
        step = ExecutionStep(
            step_id=step_id,
            step_type=StepType.TOOL,
            tool_name=tool_name,
            agent_name="place_agent",
            parameters=dict(parameters),
        )
        result = await pe._execute_tool_step(
            step,
            completed,
            config,
            wave_id=0,
            store=None,
            accumulated_registry=accumulated,
        )
        pe._merge_single_step_result(completed, result, accumulated_registry=accumulated)
        return result

    token = request_tool_manifests_ctx.set(list(manifests.values()))
    try:
        with (
            patch.object(pe.ToolRegistry, "get_instance", return_value=registry),
            patch.object(pe, "_get_tool_manifest_for_step", side_effect=manifest_for_step),
        ):
            assert (await execute("read_before", "get_current_location_tool", {})).success
            assert effective_source_cutoff(config) is None
            assert (await execute("mutation", mutation.name, {})).success is not mutation_fails
            assert effective_source_cutoff(config) is not None
            assert not (
                await execute(
                    "old_weather",
                    "get_current_weather_tool",
                    {"location": "$steps.read_before.locations[0].locality"},
                )
            ).success
            expected = (
                ["read", "mutation", "read"] if read_during_mutation else ["read", "mutation"]
            )
            assert calls == expected
            assert (await execute("read_after", "get_current_location_tool", {})).success
            assert (
                await execute(
                    "fresh_weather",
                    "get_current_weather_tool",
                    {"location": "$steps.read_after.locations[0].locality"},
                )
            ).success
            assert calls == [*expected, "read", "weather"]
        assert effective_source_cutoff(caller_config) is None
        assert caller_config["configurable"] == {FIELD_RESOLVED_PERSON_NAMES: ["nancy"]}
    finally:
        request_tool_manifests_ctx.reset(token)
