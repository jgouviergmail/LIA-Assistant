"""One ReAct call: guards, approval, bounded invocation and atomic outcome booking."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

import structlog
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.messages.tool import ToolCall
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.errors import GraphInterrupt

from src.core.config import get_settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.i18n import resolve_language
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.agents.data_registry.models import RegistryItem
from src.domains.agents.effects.gate import (
    ERROR_CONFIRMATION_IMPOSSIBLE,
    UNATTENDED_REFUSAL_MESSAGE,
    turn_has_nobody_to_ask,
)
from src.domains.agents.effects.runtime import note_refusal
from src.domains.agents.effects.scope import current_turn_source, effect_scope, react_call_scope
from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.react_observed_gaps import requested_requirements
from src.domains.agents.nodes.react_read_reuse import read_evidence
from src.domains.agents.nodes.react_result_reading import (
    activated_skill_of,
    call_artifact,
    is_productive_result,
    tool_message_metadata,
    tool_message_status,
)
from src.domains.agents.registry.catalogue import is_read_only_tool
from src.domains.agents.semantic.argument_guard import guard_tool_arguments
from src.domains.agents.semantic.manifest_semantics import available_manifest
from src.domains.agents.semantic.param_guard import (
    config_with_binding_evidence,
    turn_person_names,
    turn_request,
)
from src.domains.agents.semantic.registry_value_bindings import registry_source_observations
from src.domains.agents.services.connector_error_notice import emit_connector_notice_for_exception
from src.domains.agents.services.hitl.protocols import HitlInteractionType
from src.domains.agents.services.outcome_evidence import observe_requested_outcome
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.python_sandbox_tools import drain_turn_scripts, runs_spent, seed_turn
from src.domains.agents.tools.react_tool_wrapper import ReactToolWrapper, item_counts
from src.domains.agents.tools.tool_resolution import classify_unresolved_tool_call
from src.domains.agents.utils.loop_guard import (
    compute_call_digest,
    register_call,
    repeated_call_message,
)
from src.domains.agents.utils.message_filters import tool_call_not_run
from src.domains.agents.utils.react_budget import TIMEOUT_ATTRIBUTION_MARGIN, tool_timeout_message
from src.domains.agents.utils.react_execution_contracts import ReadEvidence
from src.infrastructure.observability.metrics_react import (
    react_agent_hitl_interrupts_total,
    react_agent_tools_called_total,
    react_repeated_calls_total,
    react_unknown_tool_calls_total,
)

logger = structlog.get_logger(__name__)


class Invoke(Protocol):
    async def __call__(
        self,
        wrapper: ReactToolWrapper,
        injected_args: Mapping[str, object],
        *,
        timeout: float,
        state: Mapping[str, object],
        tool_name: str,
    ) -> object: ...


class RuntimeBuilder(Protocol):
    def __call__(
        self,
        tool: BaseTool,
        args: dict[str, object],
        config: RunnableConfig,
        store: object,
    ) -> dict[str, object]: ...


@dataclass(frozen=True)
class CallPorts:
    wrappers: Callable[[list[str], dict[str, bool]], list[ReactToolWrapper]]
    invoke: Invoke
    runtime: RuntimeBuilder
    interrupt: Callable[[object], object]
    timeout: Callable[[str, int | None], float]
    draft: Callable[[object, str], object]
    result_budget: int
    store: object


@dataclass
class Executed:
    message: ToolMessage
    seconds: float = 0.0
    registry: dict[str, object] = field(default_factory=dict)
    draft: dict[str, object] | None = None
    activated_skill: str | None = None
    productive: bool = False
    evidence: ReadEvidence = field(default_factory=lambda: {"outcome": "failed"})
    requested_evidence: dict[str, object] | None = None
    source_valid_after: str | None = None


def _mapping(value: object) -> dict[str, object]:
    return {str(key): item for key, item in value.items()} if isinstance(value, Mapping) else {}


async def _semantic_guard(
    call: ToolCall, state: MessagesState, config: RunnableConfig
) -> ToolMessage | None:
    violation = await guard_tool_arguments(
        call["name"],
        call["args"],
        config_with_binding_evidence(config, state),
        person_names=turn_person_names(state),
        request=turn_request(state),
        execution_mode="react",
    )
    if violation is None:
        return None
    return ToolMessage(
        content=f"ERROR: {violation.llm_message()}",
        tool_call_id=call["id"],
        name=call["name"],
        status="error",
    )


def _repetition_guard(
    call: ToolCall,
    state: MessagesState,
) -> tuple[dict[str, int], ToolMessage | None, bool]:
    settings = get_settings()
    digests, verdict = register_call(
        dict(state.get("react_call_digests") or {}),
        compute_call_digest(call["name"], call["args"], settings.secret_key),
        block_threshold=settings.react_repeated_call_block_threshold,
        terminal_threshold=settings.react_repeated_call_terminal_threshold,
    )
    if verdict == "allow":
        return digests, None, False
    react_repeated_calls_total.labels(tool_name=call["name"], verdict=verdict).inc()
    logger.warning("react_repeated_call_blocked", tool_name=call["name"], verdict=verdict)
    return (
        digests,
        tool_call_not_run(repeated_call_message(verdict), call["id"], call["name"]),
        verdict == "terminal",
    )


def _recovery_guard(call: ToolCall, state: MessagesState) -> ToolMessage | None:
    if not state.get("react_recovery_passes"):
        return None
    manifest = available_manifest(call["name"])
    if manifest is not None and not manifest.delegates_execution and is_read_only_tool(manifest):
        return None
    return tool_call_not_run(
        "Recovery passes may read evidence only. This action was not executed; "
        "report the unresolved action without retrying a pending or attempted write.",
        call["id"],
        call["name"],
    )


def _approve(call: ToolCall, state: MessagesState, ports: CallPorts) -> ToolMessage | None:
    if not state.get("react_hitl_map", {}).get(call["name"], False):
        return None
    if turn_has_nobody_to_ask():
        # N10: a question nobody can answer would wait on the person's thread
        # and read their next message as its answer. Refuse as the gate does.
        note_refusal(call["name"], ERROR_CONFIRMATION_IMPOSSIBLE, source=current_turn_source())
        return tool_call_not_run(UNATTENDED_REFUSAL_MESSAGE, call["id"], call["name"])
    decision = ports.interrupt(
        {
            "action_requests": [
                {"type": "tool_confirmation", "tool_name": call["name"], "tool_args": call["args"]}
            ],
            "generate_question_streaming": True,
            "user_language": resolve_language(state.get("user_language")),
            "user_timezone": state.get("user_timezone", DEFAULT_USER_DISPLAY_TIMEZONE),
            "hitl_type": HitlInteractionType.TOOL_CONFIRMATION.value,
        }
    )
    action = decision.get("action") if isinstance(decision, Mapping) else None
    approved = action in ("confirm", "approve")
    react_agent_hitl_interrupts_total.labels(
        tool_name=call["name"], decision="approve" if approved else "reject"
    ).inc()
    if approved:
        return None
    return tool_call_not_run(
        f"Action '{call['name']}' was declined by the user.", call["id"], call["name"]
    )


def _unknown(call: ToolCall) -> Executed:
    reason = classify_unresolved_tool_call(call["name"])
    react_unknown_tool_calls_total.labels(reason=reason).inc()
    logger.warning("react_tool_call_unresolved", tool_name=call["name"], reason=reason)
    return Executed(
        ToolMessage(
            content=f"Tool '{call['name']}' not found.",
            tool_call_id=call["id"],
            name=call["name"],
            status="error",
        )
    )


def _observe(call: ToolCall, state: MessagesState, raw: object) -> dict[str, object] | None:
    return observe_requested_outcome(
        call["name"],
        call["args"],
        raw,
        requirements=requested_requirements(state),
        timezone=state.get("user_timezone") or DEFAULT_USER_DISPLAY_TIMEZONE,
    )


def _process(
    call: ToolCall, raw: object, wrapper: ReactToolWrapper, ports: CallPorts, state: MessagesState
) -> Executed:
    wrapper._accumulated_registry.clear()
    content, block = wrapper._render_result(raw, budget_tokens=ports.result_budget)
    draft = ports.draft(raw, call["name"])
    status = tool_message_status(raw)
    answer = ToolMessage(
        content=content,
        tool_call_id=call["id"],
        name=call["name"],
        status="error" if status == "error" else "success",
        artifact=call_artifact(raw),
        # Beside the failure's code, what the read returned (integers only): the
        # live trace shows it under the call's line.
        response_metadata={**tool_message_metadata(raw), **item_counts(block)},
    )
    return Executed(
        answer,
        registry=_mapping(wrapper._accumulated_registry),
        draft=_mapping(draft) if draft is not None else None,
        activated_skill=activated_skill_of(raw),
        productive=is_productive_result(raw),
        evidence=read_evidence(raw),
        requested_evidence=_observe(call, state, raw),
    )


def _timeout(call: ToolCall, bound: float, elapsed: float, state: MessagesState) -> Executed:
    logger.warning(
        "react_execute_tools_timeout",
        tool_name=call["name"],
        timeout_seconds=bound,
        elapsed_seconds=round(elapsed, 1),
        enforced_by="react_budget" if elapsed >= bound * TIMEOUT_ATTRIBUTION_MARGIN else "tool",
    )
    return Executed(
        ToolMessage(
            content=tool_timeout_message(call["name"], bound_s=bound, elapsed_s=elapsed),
            tool_call_id=call["id"],
            name=call["name"],
            status="error",
        ),
        requested_evidence=_observe(
            call,
            state,
            {"success": False, "error_code": ToolErrorCode.TIMEOUT.value},
        ),
    )


def _failure(call: ToolCall, error: Exception, state: MessagesState) -> Executed:
    logger.warning(
        "react_execute_tools_error",
        tool_name=call["name"],
        error=str(error),
        error_type=type(error).__name__,
    )
    emit_connector_notice_for_exception(error, tool_name=call["name"])
    return Executed(
        ToolMessage(
            content=f"Error executing {call['name']}: {error!s}",
            tool_call_id=call["id"],
            name=call["name"],
            status="error",
        ),
        requested_evidence=_observe(
            call,
            state,
            {"success": False, "error_code": ToolErrorCode.INTERNAL_ERROR.value},
        ),
    )


async def _invoke(
    call: ToolCall,
    state: MessagesState,
    config: RunnableConfig,
    ports: CallPorts,
) -> Executed:
    wrappers = ports.wrappers(
        state.get("react_tool_names") or [], state.get("react_hitl_map") or {}
    )
    wrapper = next((value for value in wrappers if value.name == call["name"]), None)
    if wrapper is None:
        return _unknown(call)
    tool_timeout = ports.timeout(call["name"], None)
    started = time.perf_counter()
    invocation_state = _invocation_state(call, state)
    source_valid_after = (
        invocation_state.get("semantic_source_valid_after")
        if invocation_state is not state
        else None
    )
    invocation_config = config_with_binding_evidence(config, invocation_state)
    try:
        injected = ports.runtime(
            wrapper._original_tool, dict(call["args"]), invocation_config, ports.store
        )
        approved = state.get("react_hitl_map", {}).get(call["name"], False)
        with effect_scope(react_call_scope(invocation_config, call["id"], approved=approved)):
            raw = await ports.invoke(
                wrapper,
                injected,
                timeout=tool_timeout,
                state=invocation_state,
                tool_name=call["name"],
            )
        result = _process(call, raw, wrapper, ports, state)
    except GraphInterrupt:
        raise
    except TimeoutError:
        result = _timeout(call, tool_timeout, time.perf_counter() - started, state)
    except Exception as error:
        result = _failure(call, error, state)
    result.seconds = time.perf_counter() - started
    result.source_valid_after = source_valid_after
    react_agent_tools_called_total.labels(tool_name=call["name"]).inc()
    return result


def _mutation(call: ToolCall) -> bool:
    manifest = available_manifest(call["name"])
    return manifest is None or manifest.delegates_execution or not is_read_only_tool(manifest)


def _invocation_state(call: ToolCall, state: MessagesState) -> MessagesState:
    """Invalidate possible mutable effects before delegating, preserving canonical records."""
    if not _mutation(call):
        return state
    invocation = state.copy()
    invocation["react_read_results"] = {}
    invocation["semantic_value_bindings"] = []
    invocation["semantic_source_observations"] = {}
    invocation["semantic_source_valid_after"] = datetime.now(UTC).isoformat()
    return invocation


def _draft_update(outcome: Executed, state: MessagesState) -> dict[str, object]:
    result: dict[str, object] = {
        "pending_draft_critique": outcome.draft,
        "pending_drafts_queue": [],
        "pending_drafts_grouped": False,
        "confirmed_drafts": [],
    }
    if outcome.draft is not None:
        result["react_agent_result"] = {
            "final_message": "",
            "iteration_count": state.get("react_iteration", 0),
            "mode": "react",
        }
    return result


def _book(
    outcome: Executed, state: MessagesState, digests: dict[str, int], terminal: bool
) -> dict[str, object]:
    requested = list(state.get("requested_outcome_evidence") or [])
    if outcome.requested_evidence is not None:
        requested.append(outcome.requested_evidence)
    result: dict[str, object] = {
        "messages": [outcome.message],
        "react_call_digests": digests,
        "react_execution_evidence": outcome.evidence,
        "requested_outcome_evidence": requested,
        "react_script_runs": runs_spent(),
    }
    if outcome.seconds:
        result["react_tool_seconds"] = (
            float(state.get("react_tool_seconds") or 0.0) + outcome.seconds
        )
    if outcome.productive:
        result["react_productive_iterations"] = (
            int(state.get("react_productive_iterations") or 0) + 1
        )
    if terminal:
        result["react_iteration"] = get_settings().react_agent_max_iterations
    if outcome.source_valid_after is not None:
        result["semantic_source_valid_after"] = outcome.source_valid_after
    if outcome.registry:
        result["registry"] = outcome.registry
        result["current_turn_registry"] = {
            **(state.get("current_turn_registry") or {}),
            **outcome.registry,
        }
    return result


def _sandbox_update(state: MessagesState, outcome: Executed) -> dict[str, object]:
    result: dict[str, object] = {}
    scripts = drain_turn_scripts()
    if scripts:
        result["react_scripts"] = list(state.get("react_scripts") or []) + scripts
    if outcome.activated_skill:
        result["react_activated_skills"] = [
            *(state.get("react_activated_skills") or []),
            outcome.activated_skill,
        ]
    return result


def _semantic_source_update(outcome: Executed, state: MessagesState) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or not outcome.registry:
        return {}
    observed = registry_source_observations(
        outcome.registry, str(context.user_id), valid_after=state.get("semantic_source_valid_after")
    )
    sources = dict(state.get("semantic_source_observations") or {})
    sources.update({ref: value.model_dump(mode="json") for ref, value in observed.items()})
    return {"semantic_source_observations": sources}


def _sandbox_items(registry: Mapping[str, object]) -> dict[str, object]:
    """Keep actual canonical records as JSON data rather than BaseModel repr strings."""
    return {
        key: value.model_dump(mode="json") if isinstance(value, RegistryItem) else value
        for key, value in registry.items()
    }


async def execute_call(
    state: MessagesState, config: RunnableConfig, ports: CallPorts
) -> dict[str, object]:
    """One call per invocation, with no mutable wrapper shared across tasks."""
    request = state["messages"][-1]
    if not isinstance(request, AIMessage) or not request.tool_calls:
        return {}
    call = request.tool_calls[0]
    seed_turn(
        runs_spent=int(state.get("react_script_runs") or 0),
        items=_sandbox_items(state.get("current_turn_registry") or {}),
    )
    digests, refused, terminal = _repetition_guard(call, state)
    refused = refused or _recovery_guard(call, state) or await _semantic_guard(call, state, config)
    if refused is None:
        refused = _approve(call, state, ports)
    outcome = (
        Executed(refused) if refused is not None else await _invoke(call, state, config, ports)
    )
    result = _book(outcome, state, digests, terminal)
    result.update(_draft_update(outcome, state))
    result.update(_sandbox_update(state, outcome))
    result.update(_semantic_source_update(outcome, state))
    return result
