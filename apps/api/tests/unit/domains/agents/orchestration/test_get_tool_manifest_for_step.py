"""Characterization tests for _get_tool_manifest_for_step fallback resolution.

These drive the real pipeline helper (not a simulation) through its
user-MCP/hallucinated-suffix fallback branch, guarding the DRY refactor that
delegates resolution to the shared ``resolve_tool_manifest_named``.
"""

import time
from types import SimpleNamespace

from src.core.constants import MCP_USER_TOOL_NAME_PREFIX
from src.core.context import UserMCPToolsContext, user_mcp_tools_ctx
from src.domains.agents.orchestration.parallel_executor import _get_tool_manifest_for_step
from src.domains.agents.orchestration.plan_schemas import ExecutionStep, StepType


def _tool_step(tool_name: str) -> ExecutionStep:
    return ExecutionStep(
        step_id="step_1",
        step_type=StepType.TOOL,
        agent_name="mcp_agent",
        tool_name=tool_name,
        parameters={},
        description="test step",
    )


def test_fallback_resolves_user_mcp_manifest_and_canonicalizes_name() -> None:
    """A user MCP manifest (ContextVar only) reached via a hallucinated suffix.

    The helper must resolve it through the shared resolver, return the manifest,
    and correct ``step.tool_name`` to the canonical name.
    """
    canonical = f"{MCP_USER_TOOL_NAME_PREFIX}_770baa3e_get_indicator"
    manifest = SimpleNamespace(name=canonical)

    ctx = UserMCPToolsContext()
    ctx.tool_manifests = [manifest]
    step = _tool_step(f"{canonical}_tool")  # hallucinated "_tool" suffix

    token = user_mcp_tools_ctx.set(ctx)
    try:
        resolved_manifest, error_result = _get_tool_manifest_for_step(
            step=step, resolved_args={}, start_time=time.time(), wave_id=0
        )
    finally:
        user_mcp_tools_ctx.reset(token)

    assert error_result is None
    assert resolved_manifest is manifest
    assert step.tool_name == canonical  # suffix corrected


def test_fallback_not_found_returns_error_result() -> None:
    """An unknown tool (not registered, no ContextVar) yields a NOT_FOUND error."""
    step = _tool_step("totally_unknown_tool_zzz")

    resolved_manifest, error_result = _get_tool_manifest_for_step(
        step=step, resolved_args={}, start_time=time.time(), wave_id=0
    )

    assert resolved_manifest is None
    assert error_result is not None
    assert error_result.success is False
