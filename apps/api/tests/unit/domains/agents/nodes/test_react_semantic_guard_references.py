"""ReAct's guard reads the same person names as the pipeline (ADR-120 amendment)."""

from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.analysis.resolved_references import (
    ReferenceSource,
    ReferenceValueKind,
    ResolvedReferenceEntry,
)
from src.domains.agents.nodes.react_call_execution import _semantic_guard
from src.domains.agents.registry.catalogue import (
    CostProfile,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.agents.semantic.param_guard import SemanticParamViolation

pytestmark = pytest.mark.unit

MANIFEST = ToolManifest(
    name="get_places_tool",
    agent="place_agent",
    description="fixture",
    parameters=[
        ParameterSchema(
            name="location",
            type="string",
            description="v",
            semantic_type="physical_address",
            required=False,
        )
    ],
    outputs=[],
    cost=CostProfile(),
    permissions=PermissionProfile(),
    mutation_policy="read",
)
CONFIG = {"configurable": {}, "metadata": {"user_id": "u-1"}}


def _state(*entries: ResolvedReferenceEntry) -> dict[str, object]:
    return {"query_intelligence": {"resolved_references": [e.to_dict() for e in entries]}}


def _call(value: str) -> dict[str, object]:
    return {
        "name": "get_places_tool",
        "args": {"location": value},
        "id": "call_1",
        "type": "tool_call",
    }


async def test_city_reference_passes() -> None:
    city = ResolvedReferenceEntry(
        "montbéliard", "Montbéliard", ReferenceValueKind.PLACE, ReferenceSource.ANALYZER
    )
    with patch("src.domains.agents.semantic.param_guard.available_manifest", return_value=MANIFEST):
        assert await _semantic_guard(_call("Montbéliard"), _state(city), CONFIG) is None


async def test_person_name_is_refused_with_an_error_status() -> None:
    name = ResolvedReferenceEntry(
        "mon frère", "Marc Lemoine", ReferenceValueKind.PERSON_NAME, ReferenceSource.MEMORY
    )
    with patch("src.domains.agents.semantic.param_guard.available_manifest", return_value=MANIFEST):
        message = await _semantic_guard(_call("Marc Lemoine"), _state(name), CONFIG)
    assert message is not None and message.status == "error"


async def test_a_stale_state_copy_guards_nothing() -> None:
    state = {
        "query_intelligence": {"resolved_references": None},
        "resolved_references": {"mon frère": "Marc Lemoine"},
    }
    with patch("src.domains.agents.semantic.param_guard.available_manifest", return_value=MANIFEST):
        assert await _semantic_guard(_call("Marc Lemoine"), state, CONFIG) is None


async def test_the_value_kind_judgment_reads_the_turn_request() -> None:
    refused = SemanticParamViolation(
        "get_places_tool", "location", "physical_address", "06 12 34 56 78", "phone_number"
    )
    judge = AsyncMock(return_value=refused)
    state = {"query_intelligence": {"original_query": "Restaurants près de chez moi"}}
    with (
        patch("src.domains.agents.semantic.param_guard.available_manifest", return_value=MANIFEST),
        patch("src.domains.agents.semantic.argument_guard.judge_guarded_values", judge),
    ):
        message = await _semantic_guard(_call("06 12 34 56 78"), state, CONFIG)
    assert message is not None and message.status == "error"
    assert "a phone number" in str(message.content)
    assert judge.await_args.kwargs["request"] == "Restaurants près de chez moi"
