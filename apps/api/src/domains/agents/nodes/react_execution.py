"""Checkpoint boundaries and bounded batches for the native ReAct executor.

An interruptible/exclusive call is always alone in a node invocation. Completed
reads therefore reach the checkpointer before a later approval can suspend the
graph. Parallel calls get independent wrappers via the singleton execution seam.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.messages.tool import ToolCall
from langchain_core.runnables import RunnableConfig

from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.react_read_reuse import (
    bound_read_cache,
    cache_entry,
    cached_answer,
    normalized_call,
    read_signature,
)
from src.domains.agents.registry.catalogue import is_read_only_tool
from src.domains.agents.semantic.manifest_semantics import available_manifest
from src.domains.agents.utils.react_execution_contracts import (
    CachedRead,
    ReadEvidence,
    ReadObservation,
)

# A fixed upper bound also applies when an old checkpoint/config has no setting.
MAX_PARALLEL_READS = 4
ExecuteCall = Callable[[MessagesState, RunnableConfig], Awaitable[Mapping[str, object]]]


def latest_answered_calls(messages: Sequence[BaseMessage]) -> set[str]:
    answered: set[str] = set()
    for message in reversed(messages):
        if isinstance(message, (AIMessage, HumanMessage)):
            break
        if isinstance(message, ToolMessage):
            answered.add(message.tool_call_id)
    return answered


def pending_calls(state: MessagesState) -> tuple[AIMessage | None, list[ToolCall]]:
    """Only the latest model request is live; previous turns never buy work."""
    messages = state.get("messages") or []
    answered: set[str] = set()
    for message in reversed(messages):
        if isinstance(message, ToolMessage):
            answered.add(message.tool_call_id)
        if isinstance(message, HumanMessage):
            break
        if isinstance(message, AIMessage):
            calls = [
                normalized_call(call)
                for call in message.tool_calls
                if call.get("id") and call["id"] not in answered
            ]
            return message, calls
    return None, []


def _parallel_read(call: ToolCall, state: MessagesState) -> bool:
    manifest = available_manifest(call["name"])
    return bool(
        manifest is not None
        and not manifest.delegates_execution
        and manifest.concurrency_safe
        and manifest.exclusive_scope is None
        and is_read_only_tool(manifest)
        and not state.get("react_hitl_map", {}).get(call["name"], False)
    )


def _segment(calls: list[ToolCall], state: MessagesState) -> list[ToolCall]:
    if not calls or not _parallel_read(calls[0], state):
        return calls[:1]
    selected: list[ToolCall] = []
    signatures: set[str] = set()
    for call in calls[:MAX_PARALLEL_READS]:
        signature = read_signature(call)
        if not _parallel_read(call, state) or signature in signatures:
            break
        signatures.add(signature)
        selected.append(call)
    return selected


def _mapping(value: object) -> dict[str, object]:
    return {str(key): item for key, item in value.items()} if isinstance(value, Mapping) else {}


def _messages(value: object) -> list[BaseMessage]:
    if not isinstance(value, list):
        return []
    return [message for message in value if isinstance(message, BaseMessage)]


def _evidence(update: Mapping[str, object], message: ToolMessage) -> ReadEvidence:
    evidence = update.get("react_execution_evidence")
    if isinstance(evidence, Mapping) and evidence.get("outcome") in {
        "obtained",
        "failed",
        "empty",
        "partial",
    }:
        outcome = evidence["outcome"]
        if outcome == "obtained":
            return {"outcome": "obtained"}
        if outcome == "partial":
            return {"outcome": "partial"}
        if outcome == "empty":
            return {"outcome": "empty"}
    return {"outcome": "failed" if message.status == "error" else "empty"}


async def _execute_one(
    call: ToolCall,
    request: AIMessage,
    state: MessagesState,
    config: RunnableConfig,
    execute: ExecuteCall,
) -> Mapping[str, object]:
    reuse = cached_answer(call, state.get("react_read_results") or {})
    if reuse is not None:
        message, registry = reuse
        return {"messages": [message], "registry": registry, "react_execution_reused": True}
    singleton = state.copy()
    singleton["messages"] = [
        *state["messages"],
        AIMessage(content=request.content, id=request.id, tool_calls=[call]),
    ]
    return await execute(singleton, config)


def _book_read(
    call: ToolCall,
    update: Mapping[str, object],
    cache: dict[str, CachedRead],
    observations: dict[str, ReadObservation],
) -> None:
    if _invalidates_proof(call):
        # Mutations and opaque delegations may invalidate previous reads.
        cache.clear()
        return
    if call["args"].get("force_refresh") or call["args"].get("use_cache") is False:
        cache.clear()
    if update.get("react_execution_reused"):
        return
    answers = [
        message for message in _messages(update.get("messages")) if isinstance(message, ToolMessage)
    ]
    if not answers or answers[0].artifact is not None:
        return
    signature = read_signature(call)
    evidence = _evidence(update, answers[0])
    observations[signature] = ReadObservation(
        tool_name=call["name"], signature=signature, outcome=evidence["outcome"]
    )
    entry = cache_entry(call, answers[0], _mapping(update.get("registry")), evidence)
    if entry is not None:
        cache[signature] = entry


def _collect_updates(
    calls: list[ToolCall],
    updates: list[Mapping[str, object]],
    cache: dict[str, CachedRead],
    observations: dict[str, ReadObservation],
) -> tuple[list[BaseMessage], dict[str, object], dict[str, object], bool]:
    messages: list[BaseMessage] = []
    registry: dict[str, object] = {}
    result: dict[str, object] = {}
    productive = False
    for call, update in zip(calls, updates, strict=True):
        messages.extend(_messages(update.get("messages")))
        registry.update(_mapping(update.get("registry")))
        _book_read(call, update, cache, observations)
        productive = productive or "react_productive_iterations" in update
        result.update(
            {
                key: value
                for key, value in update.items()
                if key
                not in {
                    "messages",
                    "registry",
                    "current_turn_registry",
                    "react_read_results",
                    "react_execution_evidence",
                    "react_execution_reused",
                    "react_productive_iterations",
                    "react_call_digests",
                    "react_tool_seconds",
                    "semantic_source_observations",
                }
            }
        )
    return messages, registry, result, productive


def _requested_evidence(
    updates: list[Mapping[str, object]],
    state: MessagesState,
) -> list[dict[str, object]]:
    previous = state.get("requested_outcome_evidence") or []
    evidence = list(previous)
    for update in updates:
        added = update.get("requested_outcome_evidence")
        if isinstance(added, list):
            evidence.extend(
                _mapping(item) for item in added[len(previous) :] if isinstance(item, Mapping)
            )
    return evidence


def _spent_seconds(updates: list[Mapping[str, object]], previous: float) -> float:
    return sum(
        max(0.0, float(seconds) - previous)
        for update in updates
        if isinstance(seconds := update.get("react_tool_seconds"), (int, float))
    )


def _call_digests(updates: list[Mapping[str, object]], state: MessagesState) -> dict[str, int]:
    digests = dict(state.get("react_call_digests") or {})
    for update in updates:
        for key, value in _mapping(update.get("react_call_digests")).items():
            if isinstance(value, int):
                digests[key] = max(digests.get(key, 0), value)
    return digests


def _source_observations(
    calls: list[ToolCall], updates: list[Mapping[str, object]], state: MessagesState
) -> dict[str, object]:
    if any(_invalidates_proof(call) for call in calls):
        return {}
    sources: dict[str, object] = dict(state.get("semantic_source_observations") or {})
    for update in updates:
        sources.update(_mapping(update.get("semantic_source_observations")))
    return sources


def _invalidates_proof(call: ToolCall) -> bool:
    manifest = available_manifest(call["name"])
    return manifest is None or manifest.delegates_execution or not is_read_only_tool(manifest)


def _progress_update(
    request: AIMessage, state: MessagesState, productive: bool
) -> dict[str, object]:
    generation = request.id or ":".join(call["id"] for call in request.tool_calls)
    if productive and state.get("react_last_productive_message_id") != generation:
        return {
            "react_productive_iterations": int(state.get("react_productive_iterations") or 0) + 1,
            "react_last_productive_message_id": generation,
        }
    return {}


def _merge(
    calls: list[ToolCall],
    updates: list[Mapping[str, object]],
    request: AIMessage,
    state: MessagesState,
) -> dict[str, object]:
    cache = dict(state.get("react_read_results") or {})
    observations = dict(state.get("react_read_observations") or {})
    messages, registry, result, productive = _collect_updates(calls, updates, cache, observations)
    result.update(
        messages=messages,
        react_read_results=bound_read_cache(cache),
        react_read_observations=observations,
    )
    result["requested_outcome_evidence"] = _requested_evidence(updates, state)
    previous_seconds = float(state.get("react_tool_seconds") or 0.0)
    spent_seconds = _spent_seconds(updates, previous_seconds)
    if spent_seconds:
        result["react_tool_seconds"] = previous_seconds + spent_seconds
    result["react_call_digests"] = _call_digests(updates, state)
    result["semantic_source_observations"] = _source_observations(calls, updates, state)
    if any(_invalidates_proof(call) for call in calls):
        result["semantic_value_bindings"] = []
    result.update(_progress_update(request, state, productive))
    if registry:
        result["registry"] = registry
        result["current_turn_registry"] = {**(state.get("current_turn_registry") or {}), **registry}
    return result


async def execute_checkpointed_batch(
    state: MessagesState, config: RunnableConfig, execute: ExecuteCall
) -> dict[str, object]:
    """One bounded segment; graph routing checkpoints it before the next segment."""
    request, calls = pending_calls(state)
    if request is None or not calls:
        return {}
    selected = _segment(calls, state)
    # Safe calls cannot interrupt; the exclusive branch is a singleton and its
    # GraphInterrupt bubbles normally. Each call catches its own errors/timeouts.
    updates = await asyncio.gather(
        *(_execute_one(call, request, state, config, execute) for call in selected)
    )
    return _merge(selected, updates, request, state)
