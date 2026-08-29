"""Ephemeral Python in the sandbox — the agent's calculator, not its habit.

A language model is unreliable at arithmetic over many rows, at joining records
on a key, at durations across timezones, at deduplication. It produces a
plausible answer and no way to check it. A short script produces a verifiable
one, and the script is visible to an administrator.

This tool is a COMPLEMENT: most turns never touch it. It exists for the moment
the agent judges that computing beats guessing.

Three refusals live here, and one lives in the executor:

- **outside ReAct** — the pipeline plans ahead and uses skills and plugins
  (owner arbitration, ADR-249). Model-authored code belongs in the loop that
  can read its own traceback and repair it;
- **flag off** — the self-hoster's emergency switch;
- **turn budget spent** — a prompt-injected repair loop must not spin the host;
- *(executor)* **legacy sandbox refused** — model-authored code never runs in
  the in-process path that only isolates when the API runs as root.

What comes back is DATA, never instructions: the stdout of code an LLM wrote
over third-party content is marked untrusted before it re-enters the context.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Annotated, Any

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import get_settings
from src.core.constants import EXECUTION_MODE_REACT, PYTHON_SANDBOX_AGENT_NAME
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.tool_registry import registered_tool
from src.domains.agents.utils.rate_limiting import rate_limit
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

logger = structlog.get_logger(__name__)

__all__ = [
    "drain_turn_scripts",
    "reset_turn_budget",
    "run_python_tool",
    "set_turn_data",
]

#: Runs already spent this turn. Per-request state never lives on a module-level
#: tool instance (systemic rule) — a ContextVar is the endorsed carrier.
_runs_this_turn: ContextVar[int] = ContextVar("python_sandbox_runs", default=0)

#: The turn's collected data, handed to the script on stdin so the model
#: references what the tools already returned instead of re-typing it.
_turn_data: ContextVar[dict[str, Any] | None] = ContextVar("python_sandbox_data", default=None)

#: What ran this turn, for the ADMIN debug panel only (owner arbitration): the
#: code the model wrote is never shown on the answer surface.
_turn_scripts: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "python_sandbox_scripts", default=None
)


def reset_turn_budget() -> None:
    """Start a turn with a full budget, no carried-over data and no history."""
    _runs_this_turn.set(0)
    _turn_data.set(None)
    _turn_scripts.set(None)


def drain_turn_scripts() -> list[dict[str, Any]]:
    """What the sandbox ran this turn, for the admin debug surface.

    Returns:
        One entry per run: purpose, code, verdict and the head of the output.
    """
    return list(_turn_scripts.get() or [])


def set_turn_data(items: dict[str, Any]) -> None:
    """Publish the turn's collected registry items to the sandbox tool.

    Args:
        items: Registry items collected so far this turn, by id.
    """
    _turn_data.set(items or {})


@registered_tool
@track_tool_metrics(
    tool_name="run_python",
    agent_name=PYTHON_SANDBOX_AGENT_NAME,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: get_settings().python_sandbox_rate_limit_calls,
    window_seconds=lambda: get_settings().python_sandbox_rate_limit_window,
    scope="user",
)
async def run_python_tool(
    code: str,
    purpose: str,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Run a short Python script in an isolated sandbox and return its stdout.

    Args:
        code: The Python source to run. It reads its input from stdin as JSON.
        purpose: One short sentence on what this computes (shown to admins).
        runtime: LangChain tool runtime (injected).

    Returns:
        The script's stdout, or the failure with its traceback so it can be fixed.
    """
    settings = get_settings()
    context = getattr(runtime, "context", None)
    user_id = getattr(context, "user_id", None)

    if not getattr(settings, "python_sandbox_tool_enabled", False):
        return UnifiedToolOutput(
            success=False,
            message="Ephemeral Python execution is disabled on this instance.",
            error_code=ToolErrorCode.CONFIGURATION_ERROR,
        )

    if getattr(context, "execution_mode", "") != EXECUTION_MODE_REACT:
        # The pipeline plans ahead and cannot read a traceback to repair a
        # script; it uses skills and plugins instead (ADR-249).
        return UnifiedToolOutput(
            success=False,
            message="Ephemeral Python execution is only available in ReAct mode.",
            error_code=ToolErrorCode.FORBIDDEN,
        )

    spent = _runs_this_turn.get()
    budget = int(getattr(settings, "python_sandbox_max_runs_per_turn", 0))
    if spent >= budget:
        return UnifiedToolOutput(
            success=False,
            message=(
                f"Script budget for this turn is spent ({budget} runs). "
                "Answer with what you already have, and say what is missing."
            ),
            error_code=ToolErrorCode.RATE_LIMIT_EXCEEDED,
        )
    _runs_this_turn.set(spent + 1)

    from src.domains.skills.executor import SkillScriptExecutor

    result = await SkillScriptExecutor.execute_source(
        source=code,
        payload={"items": _turn_data.get() or {}},
        label="ephemeral",
        user_id=str(user_id) if user_id else None,
    )

    recorded = list(_turn_scripts.get() or [])
    recorded.append(
        {
            "purpose": purpose,
            "code": code,
            "success": bool(result.success),
            "output_head": (result.output or result.error or "")[:500],
        }
    )
    _turn_scripts.set(recorded)

    logger.info(
        "ephemeral_script_executed",
        purpose=purpose[:120],
        success=result.success,
        run_index=spent + 1,
        code_bytes=len(code.encode("utf-8")),
        user_id=str(user_id) if user_id else None,
    )

    if not result.success:
        return UnifiedToolOutput(
            success=False,
            message=f"The script failed: {result.error}",
            error_code=ToolErrorCode.INVALID_INPUT,
            structured_data={"traceback": result.error},
            metadata={"code": code, "purpose": purpose},
        )

    return UnifiedToolOutput(
        success=True,
        message="Script executed.",
        structured_data={
            # The stdout of model-authored code over third-party content is
            # DATA, never instructions — it is marked before re-entering the
            # context, like every other untrusted payload.
            "content_trust": "untrusted",
            "stdout": result.output,
        },
        # The code is admin-facing only (owner arbitration): it travels in the
        # debug metadata, never in the answer surface.
        metadata={"code": code, "purpose": purpose},
    )
