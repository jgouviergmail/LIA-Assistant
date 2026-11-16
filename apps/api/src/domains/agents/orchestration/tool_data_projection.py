"""A read tool's data, projected for the pipeline's response model (ADR-347).

The pipeline's response model read a step's ``message`` and the turn's registry
items, and nothing else: ``message`` was the model's channel and
``structured_data`` the orchestration's (ADR-074). ADR-286 gave the ReAct loop
a data block — what a tool's ``structured_data`` carries, paged item by item
under a token budget — and left the pipeline untouched. A read tool whose facts
lived in ``structured_data`` therefore handed the pipeline's answer a sentence
about them; the defect was patched three times, tool by tool, by copying the
data into ``message``. Measured 2026-10-14 on three model families: without the
block 0 of 9 answers gave the durations a route matrix had computed, with it 27
of 27 did, with no misattribution over 180 durations.

The projection runs where the tool's output still exists whole — in the
executor, right after the call — through the ReAct functions themselves
(:func:`extract_data_block`, :func:`mark_untrusted_data`), and stores a bounded
record in the step's data (``FIELD_TOOL_DATA``). Three things differ from
ReAct, each for a reason:

- only what the registry items do not already show is projected, compared by
  CONTENT: the response model reads those items through its own data section,
  and a mixed output's extras (an estimate, a cursor, a window) carry a key of
  their own while its items repeat the registry payloads;
- only a READ tool is projected, and only on the channel its manifest declares
  (``pipeline_data_channel``): an acting tool's words reach the answer as its
  confirmation;
- a FOR_EACH's items share one budget (``share``): N items must not cost N
  budgets in the one prompt they all reach.

Best-effort by construction: the projection sits inside the step's own
execution, and a failure here must never turn a step that succeeded into one
that failed — the step keeps its data, the response loses one block, the log
says why.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Final, TypedDict

import structlog
from langchain_core.messages import BaseMessage, ToolMessage

from src.core.config import settings
from src.core.field_names import FIELD_REACT_SYNTHESIS, FIELD_TOOL_DATA
from src.domains.agents.registry.catalogue import (
    ACTING_POLICIES,
    DEFAULT_PIPELINE_DATA_CHANNEL,
    ToolManifest,
)
from src.domains.agents.semantic.manifest_semantics import available_manifest
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.react_tool_wrapper import (
    extract_data_block,
    is_item_list,
    mark_untrusted_data,
)
from src.domains.agents.utils.message_filters import TOOL_CALL_NOT_RUN, current_turn_responses
from src.domains.agents.utils.react_budget import slot_tool_result_budget
from src.domains.agents.utils.state_cleanup import cleanup_dict_by_turn_id
from src.infrastructure.llm.message_text import coerce_content_to_text

logger = structlog.get_logger(__name__)

#: The slot whose window bounds a pipeline data block: the model that reads it.
RESPONSE_SLOT: Final = "response"

#: The slot whose window bounded the loop's own tool results (ADR-286).
LOOP_SLOT: Final = "react_agent"

#: The step payload list the response's data section reads (``formatters/tool_data``).
STEP_RESULTS_KEY: Final = "step_results"

#: The lists of step payloads an ``AgentResult``'s data carries (the mapper's).
_STEP_PAYLOAD_LISTS: Final = frozenset({STEP_RESULTS_KEY, "aggregated_results"})


class ToolDataRecord(TypedDict):
    """One tool call's data block, as the step's data carries it.

    Attributes:
        tool: The tool that produced it.
        text: The block, wrapped as external content unless provably internal.
        shown: Items that reached the block, complete.
        total: Items the tool returned (``1`` for data with no item list).
        key: The paged item list's key, ``None`` when there was none.
        truncated: Whether anything was left out or cut.
        budget_tokens: The budget that decided.
    """

    tool: str
    text: str
    shown: int
    total: int
    key: str | None
    truncated: bool
    budget_tokens: int


def tool_data_fields(
    result: object,
    *,
    manifest: ToolManifest | None,
    tool_name: str,
    share: int = 1,
) -> dict[str, list[ToolDataRecord]]:
    """The fields a step's data gains from its tool's output: one record, or nothing.

    Args:
        result: What the tool returned.
        manifest: Its manifest (``None`` when the executor had none).
        tool_name: The tool, for the record and the log.
        share: How many results share this step's budget — a FOR_EACH's items.

    Returns:
        ``{FIELD_TOOL_DATA: [record]}``, or ``{}`` when nothing is projected.
    """
    try:
        record = _record(result, manifest=manifest, tool_name=tool_name, share=share)
    except Exception as exc:
        # The projection sits inside the step's own execution: raising here
        # would turn a step that succeeded into a failure. Facts only (ADR-317).
        logger.error(
            "pipeline_tool_data_projection_failed",
            tool_name=tool_name,
            error_type=type(exc).__name__,
        )
        return {}
    return {FIELD_TOOL_DATA: [record]} if record is not None else {}


def without_tool_data(completed_steps: Mapping[str, object]) -> dict[str, object]:
    """``completed_steps`` as the state persists them: no record.

    The state copy is read for the steps' keys and their failures, never for
    their data blocks, and it is checkpointed on every turn.

    Args:
        completed_steps: The executor's step entries.

    Returns:
        The same entries, each without ``FIELD_TOOL_DATA``.
    """
    return {step_id: _entry_without_tool_data(entry) for step_id, entry in completed_steps.items()}


def previous_turns_without_tool_data(
    agent_results: Mapping[str, object], current_turn_id: int | None
) -> dict[str, object]:
    """The turn's ``agent_results`` with every OTHER turn's records removed.

    A record serves the response of its own turn alone; kept, every later turn
    would checkpoint it again until the entry ages out.

    Args:
        agent_results: The state's entries, keyed ``"turn:agent"``.
        current_turn_id: The turn whose records stay.

    Returns:
        The entries, the other turns' step payloads without ``FIELD_TOOL_DATA``.
    """
    current = f"{current_turn_id}:"
    return {
        key: value if key.startswith(current) else _result_without_tool_data(value)
        for key, value in agent_results.items()
    }


def merge_react_synthesis_result(
    agent_results: dict[str, Any] | None,
    react_message: str,
    current_turn: int,
    current_registry: dict[str, Any],
    tool_data: Sequence[ToolDataRecord] = (),
) -> dict[str, Any]:
    """Merge the ReAct final answer into agent_results without overwriting entries.

    The ReAct answer is keyed ``{turn}:react_agent``. When the Initiative node ran on
    the ReAct nominal path (react_finalize -> initiative -> response), it has already
    written ``{turn}:initiative`` into agent_results; a plain ``if not agent_results``
    guard would then skip the ReAct answer entirely, dropping the user-facing reply.
    This merge is idempotent on the react key, so graph re-entry never duplicates it.
    It is the response node's write on a ReAct turn — the executor's counterpart
    spreads :func:`previous_turns_without_tool_data` the same way on a pipeline turn.

    Args:
        agent_results: Existing agent_results map (possibly populated by Initiative).
        react_message: The ReAct loop's final answer text — empty when the loop
            delivered none (:func:`react_turn_tool_data`).
        current_turn: Current turn id (for the composite key).
        current_registry: Registry items for this turn (drives HTML cards / display).
        tool_data: The turn's read results a withheld answer leaves to the
            response, carried as one step payload the data section reads.

    Returns:
        A new dict holding the turn's entries, its ``{turn}:react_agent`` one
        included, whole, beside the most recent complete earlier turns, their
        pipeline data blocks removed, within what ``max_agent_results`` leaves —
        the bound every pipeline writer already applies. This is the write the
        checkpoint keeps on a ReAct turn: unbounded, each turn's answer and
        registry items rode every later save of the thread. The bound trims the
        history only: however small, it never drops the answer of the turn.
    """
    merged = dict(agent_results or {})
    react_key = f"{current_turn}:react_agent"
    if react_key not in merged:
        data: dict[str, Any] = {FIELD_REACT_SYNTHESIS: react_message}
        if tool_data:
            data[STEP_RESULTS_KEY] = [{FIELD_TOOL_DATA: list(tool_data)}]
        merged[react_key] = {"data": data, "registry_updates": current_registry}
    turn_prefix = f"{current_turn}:"
    own = {key: value for key, value in merged.items() if key.startswith(turn_prefix)}
    history = cleanup_dict_by_turn_id(
        previous_turns_without_tool_data(
            {key: value for key, value in merged.items() if key not in own}, current_turn
        ),
        max_results=max(settings.max_agent_results - len(own), 0),
        label="agent_results",
    )
    return {**history, **own}


def react_handover(
    react_result: Mapping[str, Any] | None,
    messages: Sequence[BaseMessage],
    registry: Mapping[str, object],
) -> tuple[str, list[ToolDataRecord]] | None:
    """What a ReAct turn hands its response: its answer, or the reads a withheld one leaves.

    Args:
        react_result: The loop's ``react_agent_result``, ``None`` on another turn.
        messages: The thread, the current turn last.
        registry: The turn's registry items.

    Returns:
        ``(answer, reads)``: the answer the loop delivered with no reads beside
        it, or an empty answer with the reads :func:`react_turn_tool_data`
        finds; ``None`` when the turn ran no loop, or answered nothing and read
        nothing a registry or a record could carry.
    """
    if not react_result:
        return None
    answer = str(react_result.get("final_message") or "")
    reads = [] if answer else react_turn_tool_data(messages, registry)
    if not (answer or registry or reads):
        return None
    return answer, reads


def react_turn_tool_data(
    messages: Sequence[BaseMessage], registry: Mapping[str, object]
) -> list[ToolDataRecord]:
    """The reads a ReAct turn leaves to the response when its answer is withheld.

    A requested result the coverage proved missing (ADR-336) or a budget exit
    (ADR-248, invariant 1) withholds the loop's answer so the response
    synthesises « from the actual tool results ». Those are the ones the loop
    itself read: this turn's tool messages (counted from the END, the reducer
    trims the head) that returned a result, as the loop read them — the
    message and its data block, already bounded and marked as external
    content. Never a failure (the failures directive states it, ADR-303), a
    call that never ran, or an act (stated by its own directive, ADR-263
    §23); and never a read whose items the turn's registry already shows,
    which the response reads through its own data section.

    Args:
        messages: The thread, the current turn last.
        registry: The turn's registry items, models or their checkpoint dumps.

    Returns:
        One record per read the response would otherwise never see, in turn order.
    """
    shown = _registry_tool_names(registry)
    records: list[ToolDataRecord] = []
    for message in current_turn_responses(list(messages)):
        if not _a_read_result(message) or message.name in shown:
            continue
        text = coerce_content_to_text(message.content).strip()
        if text:
            records.append(_message_record(str(message.name), text))
    return records


def _a_read_result(message: BaseMessage) -> bool:
    """A tool message holding what a read returned: run, succeeded, a read tool's."""
    if not isinstance(message, ToolMessage) or not message.name:
        return False
    if message.status == "error" or message.artifact == TOOL_CALL_NOT_RUN:
        return False
    manifest = available_manifest(message.name)
    return manifest is not None and manifest.mutation_policy not in ACTING_POLICIES


def _message_record(tool: str, text: str) -> ToolDataRecord:
    """A read as the loop received it: its own cut, if any, is stated inside it."""
    return ToolDataRecord(
        tool=tool,
        text=text,
        shown=1,
        total=1,
        key=None,
        truncated=False,
        budget_tokens=slot_tool_result_budget(LOOP_SLOT),
    )


def _registry_tool_names(registry: Mapping[str, object]) -> set[str]:
    """The tools whose items the registry shows, whether models or their dumps."""
    names: set[str] = set()
    for item in registry.values():
        meta = item.get("meta") if isinstance(item, dict) else getattr(item, "meta", None)
        name = meta.get("tool_name") if isinstance(meta, dict) else getattr(meta, "tool_name", None)
        if isinstance(name, str) and name:
            names.add(name)
    return names


def _result_without_tool_data(result: object) -> object:
    data = result.get("data") if isinstance(result, dict) else None
    if not isinstance(result, dict) or not isinstance(data, dict):
        return result
    stripped = {
        key: (
            [_entry_without_tool_data(entry) for entry in value]
            if key in _STEP_PAYLOAD_LISTS and isinstance(value, list)
            else value
        )
        for key, value in data.items()
    }
    return {**result, "data": stripped}


def _entry_without_tool_data(entry: object) -> object:
    """One step payload without its records, in either shape the section reads them."""
    if not isinstance(entry, dict):
        return entry
    nested = entry.get("data")
    if isinstance(nested, dict) and FIELD_TOOL_DATA in nested:
        entry = {**entry, "data": _without_records(nested)}
    return _without_records(entry) if FIELD_TOOL_DATA in entry else entry


def _without_records(mapping: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in mapping.items() if key != FIELD_TOOL_DATA}


def beyond_the_registry(
    data: Mapping[str, object], registry_updates: Mapping[str, object] | None
) -> dict[str, object]:
    """What ``structured_data`` carries that the registry items do not already show.

    An item list whose items are registry payloads is dropped, item by item and
    by content — a key name proves nothing (the weather tools publish their
    days as ``forecasts`` while the registry files them under ``weathers``).
    Everything else is kept as it is.

    Args:
        data: The tool's ``structured_data``.
        registry_updates: The registry items the same output produced.

    Returns:
        The data the response model would otherwise never read.
    """
    shown = {_fingerprint(payload) for payload in _payloads(registry_updates)}
    remainder: dict[str, object] = {}
    for key, value in data.items():
        if shown and is_item_list(value):
            value = [item for item in value if _fingerprint(item) not in shown]
            if not value:
                continue
        remainder[key] = value
    return remainder


def _record(
    result: object, *, manifest: ToolManifest | None, tool_name: str, share: int
) -> ToolDataRecord | None:
    if not isinstance(result, UnifiedToolOutput) or not _projects(result, manifest):
        return None
    data = beyond_the_registry(result.structured_data, result.registry_updates)
    if not data:
        return None
    budget = max(1, slot_tool_result_budget(RESPONSE_SLOT) // max(1, share))
    block = extract_data_block(result, budget, data=data)
    if block is None:
        return None
    return ToolDataRecord(
        tool=tool_name,
        text=mark_untrusted_data(result, block.text, surface="pipeline"),
        shown=block.shown,
        total=block.total,
        key=block.key,
        truncated=block.truncated,
        budget_tokens=block.budget_tokens,
    )


def _projects(result: UnifiedToolOutput, manifest: ToolManifest | None) -> bool:
    """A successful read whose manifest leaves its data to the data block."""
    return (
        result.success
        and bool(result.structured_data)
        and manifest is not None
        and manifest.mutation_policy not in ACTING_POLICIES
        and manifest.pipeline_data_channel == DEFAULT_PIPELINE_DATA_CHANNEL
    )


def _payloads(registry_updates: Mapping[str, object] | None) -> list[object]:
    """The registry payloads, whether the items are models or their dumps."""
    payloads: list[object] = []
    for item in (registry_updates or {}).values():
        payload = getattr(item, "payload", None)
        if payload is None and isinstance(item, dict):
            payload = item.get("payload")
        if payload:
            payloads.append(payload)
    return payloads


def _fingerprint(value: object) -> str:
    """A canonical rendering, so two equal payloads compare equal whatever their key order."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
