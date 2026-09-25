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
    "runs_spent",
    "seed_turn",
]

#: Runs already spent this turn. The ContextVar is only a per-INVOCATION
#: carrier: a `.set()` inside one task is invisible in a sibling task (measured
#: 2026-08-29), and a graph runner may invoke each node in its own task. The
#: source of truth is graph STATE; ``seed_turn`` loads it at the top of every
#: invocation and ``runs_spent`` hands the new total back for persistence.
_runs_this_turn: ContextVar[int] = ContextVar("python_sandbox_runs", default=0)

#: The turn's collected data, handed to the script on stdin so the model
#: references what the tools already returned instead of re-typing it.
_turn_data: ContextVar[dict[str, Any] | None] = ContextVar("python_sandbox_data", default=None)

#: What ran this turn, for the ADMIN debug panel only (owner arbitration): the
#: code the model wrote is never shown on the answer surface.
_turn_scripts: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "python_sandbox_scripts", default=None
)


def seed_turn(*, runs_spent: int, items: dict[str, Any]) -> None:
    """Load this node invocation's carriers from graph state.

    Args:
        runs_spent: Script runs already consumed this turn (from state).
        items: Data collected so far this turn (from the turn registry).
    """
    _runs_this_turn.set(int(runs_spent or 0))
    _turn_data.set(items or {})
    _turn_scripts.set(None)


def runs_spent() -> int:
    """Script runs consumed so far this turn, for persistence back into state."""
    return int(_runs_this_turn.get() or 0)


def reset_turn_budget() -> None:
    """Start a turn with a full budget, no carried-over data and no history."""
    seed_turn(runs_spent=0, items={})


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


async def _refuse_if_not_runnable(context: Any) -> UnifiedToolOutput | None:
    """The three refusals every run meets first: the switch, the mode, the budget.

    Args:
        context: The typed runtime context, or None outside a graph run.

    Returns:
        The refusal to return as is, or None when the run may proceed.
    """
    # The deployment ceiling AND the operator's switch (B7): an administrator
    # who wants model-written code off should not have to redeploy.
    from src.domains.feature_switches.registry import (
        PlatformCapability,
        is_capability_enabled,
    )

    if not await is_capability_enabled(PlatformCapability.PYTHON_SANDBOX):
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
    budget = int(getattr(get_settings(), "python_sandbox_max_runs_per_turn", 0))
    if _runs_this_turn.get() >= budget:
        return UnifiedToolOutput(
            success=False,
            message=(
                f"Script budget for this turn is spent ({budget} runs). "
                "Answer with what you already have, and say what is missing."
            ),
            error_code=ToolErrorCode.RATE_LIMIT_EXCEEDED,
        )
    return None


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
    hosts: list[str] | None = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Run a short Python script in a fresh sandbox and return its stdout.

    Four jobs: calculate what a model does badly (joins, dates, statistics),
    diagnose a service a tool failed on (probe it over HTTPS, report status
    and latency), fill a gap with a temporary client when no tool exists and
    correct your own code from the traceback, transform a payload (CSV, XLSX,
    XML, RSS, HTML, ICS). The turn's data arrives on stdin as JSON; the
    libraries, bounds and reachable hosts are in <Computation>.

    Args:
        code: The Python source to run. It reads its input from stdin as JSON
            and reaches only the hosts declared in `hosts`.
        purpose: One short sentence on what this computes (shown to admins).
        hosts: Bare lowercase hostnames the script will reach over HTTPS
            (ADR-298). Empty: the run is offline. A host of the person's
            connectors or the operator's list is reachable at once; any other
            host is asked of the person before the run.
        runtime: LangChain tool runtime (injected).

    Returns:
        The script's stdout, or the failure with its traceback so it can be fixed.
    """
    context = getattr(runtime, "context", None)
    user_id = getattr(context, "user_id", None)
    refusal = await _refuse_if_not_runnable(context)
    if refusal is not None:
        return refusal
    spent = _runs_this_turn.get()

    network: dict[str, Any] = {}
    if hosts:
        from src.domains.agents.python_sandbox.egress.tool_path import run_with_network

        network_result = await run_with_network(
            hosts, code=code, purpose=purpose, context=context, items=_turn_data.get() or {}
        )
        if isinstance(network_result, UnifiedToolOutput):
            # A question or a refusal started no container: it costs no run.
            return network_result
        result, network = network_result
    else:
        from src.domains.skills.executor import SkillScriptExecutor

        result = await SkillScriptExecutor.execute_source(
            source=code,
            payload={"items": _turn_data.get() or {}},
            label="ephemeral",
            user_id=str(user_id) if user_id else None,
        )

    # Charged once a container actually ran, whatever it printed.
    _runs_this_turn.set(spent + 1)
    _record_script(purpose=purpose, code=code, result=result)
    logger.info(
        "ephemeral_script_executed",
        purpose_length=len(purpose),
        success=result.success,
        run_index=spent + 1,
        code_bytes=len(code.encode("utf-8")),
        network=bool(network),
        user_id=str(user_id) if user_id else None,
    )
    return _shape_output(result, network=network, code=code, purpose=purpose)


def _record_script(*, purpose: str, code: str, result: Any) -> None:
    """Keep the run for the ADMIN debug panel — never for the answer surface."""
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


def _shape_output(
    result: Any, *, network: dict[str, Any], code: str, purpose: str
) -> UnifiedToolOutput:
    """The tool's answer to the model, from the script's result.

    Args:
        result: The executor's result.
        network: What a network run adds (hosts, ``turn_data_shared``,
            authorizations) — empty for an air-gapped run.
        code: The script, for the debug metadata.
        purpose: The stated purpose, for the debug metadata.

    Returns:
        The output, the stdout marked untrusted.
    """
    if not result.success:
        return UnifiedToolOutput(
            success=False,
            message=f"The script failed: {result.error}",
            error_code=ToolErrorCode.INVALID_INPUT,
            # A traceback quotes what the script handled: as untrusted as stdout.
            structured_data={"content_trust": "untrusted", "traceback": result.error, **network},
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
            # A network run says which hosts it could reach and whether the
            # turn's data travelled (ADR-298) — so the loop knows why its
            # script read an empty stdin.
            **network,
        },
        # The code is admin-facing only (owner arbitration): it travels in the
        # debug metadata, never in the answer surface.
        metadata={"code": code, "purpose": purpose},
    )
