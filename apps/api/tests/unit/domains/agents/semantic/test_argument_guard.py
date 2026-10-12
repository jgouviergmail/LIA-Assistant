"""The guard's one door: the deterministic rule decides first, JEV may only add a refusal."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.agents.semantic import argument_guard as module
from src.domains.agents.semantic.param_guard import SemanticParamViolation

pytestmark = pytest.mark.unit

ARGS = {"destination": "Marc Lemoine"}
CONFIG = {"configurable": {}, "metadata": {"user_id": "u-1"}}
BY_NAME = SemanticParamViolation(
    "get_route_tool", "destination", "physical_address", "Marc Lemoine"
)
BY_KIND = SemanticParamViolation(
    "get_route_tool", "destination", "physical_address", "Marc Lemoine", "person_name"
)


async def _guard(
    deterministic: SemanticParamViolation | None, judged: SemanticParamViolation | None
) -> tuple[SemanticParamViolation | None, AsyncMock, MagicMock]:
    judge = AsyncMock(return_value=judged)
    metric = MagicMock()
    with (
        patch.object(module, "check_semantic_params", return_value=deterministic),
        patch.object(module, "judge_guarded_values", judge),
        patch.object(module, "semantic_param_guard_blocks_total", metric),
    ):
        violation = await module.guard_tool_arguments(
            "get_route_tool",
            ARGS,
            CONFIG,
            person_names={"marc lemoine"},
            request="Itinéraire vers chez mon frère",
            execution_mode="react",
        )
    return violation, judge, metric


async def test_a_deterministic_refusal_never_pays_for_a_judgment() -> None:
    violation, judge, metric = await _guard(BY_NAME, None)
    assert violation is BY_NAME
    judge.assert_not_awaited()
    metric.labels.assert_called_once_with(
        tool_name="get_route_tool", semantic_type="physical_address", execution_mode="react"
    )


async def test_a_judged_refusal_is_counted_like_any_other() -> None:
    violation, judge, metric = await _guard(None, BY_KIND)
    assert violation is BY_KIND
    assert judge.await_args.kwargs["request"] == "Itinéraire vers chez mon frère"
    metric.labels.return_value.inc.assert_called_once()


async def test_a_clean_call_proceeds_uncounted() -> None:
    violation, _, metric = await _guard(None, None)
    assert violation is None
    metric.labels.assert_not_called()
