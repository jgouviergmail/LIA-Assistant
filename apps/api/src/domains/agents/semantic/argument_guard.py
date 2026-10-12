"""One door between a tool call and its guarded arguments, in both execution modes.

The deterministic person-name rule (``param_guard.check_semantic_params``)
decides first; only a call it lets through reaches the optional value-kind
judgment (``jev_value_kind.judge_guarded_values``), which may add a refusal and
never lifts one. The pipeline's parallel executor and the ReAct loop call this
function alone, so a refusal is counted and logged the same way in both.
"""

from collections.abc import Collection, Mapping
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig

from src.domains.agents.semantic.jev_value_kind import judge_guarded_values
from src.domains.agents.semantic.param_guard import SemanticParamViolation, check_semantic_params
from src.domains.agents.semantic.value_bindings import binding_scope_from_config
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import semantic_param_guard_blocks_total

logger = get_logger(__name__)


async def guard_tool_arguments(
    tool_name: str,
    args: Mapping[str, Any],
    config: RunnableConfig,
    *,
    person_names: Collection[str],
    request: str | None,
    execution_mode: Literal["pipeline", "react"],
) -> SemanticParamViolation | None:
    """Return the violation that must stop this call, or None.

    Args:
        tool_name: Tool about to be executed.
        args: Final arguments (after Jinja2 / $steps resolution).
        config: The call's config, carrying the binding evidence.
        person_names: The turn's normalized resolved person names.
        request: The person's words for the turn.
        execution_mode: The mode the refusal is counted under.

    Returns:
        The first violation, or None when the call may proceed.
    """
    scope = binding_scope_from_config(config)
    bindings, account, sources = scope
    violation = check_semantic_params(
        tool_name,
        args,
        person_names,
        value_bindings=bindings,
        account_id=account,
        known_sources=sources,
    ) or await judge_guarded_values(tool_name, args, request=request, scope=scope)
    if violation is None:
        return None
    semantic_param_guard_blocks_total.labels(
        tool_name=tool_name,
        semantic_type=violation.semantic_type,
        execution_mode=execution_mode,
    ).inc()
    # No PII at WARNING: the refused value is a name, an address or a number.
    logger.warning(
        "semantic_param_guard_blocked",
        tool_name=tool_name,
        param_name=violation.param_name,
        semantic_type=violation.semantic_type,
        value_kind=violation.value_kind,
        execution_mode=execution_mode,
    )
    return violation
