"""The response's tool data section: this turn's read steps, in their own data (ADR-347).

The executor projects what a read tool's ``structured_data`` carries beyond its
registry items into the step's data (``orchestration/tool_data_projection``);
this module reads those records back from the turn's ``agent_results`` and
renders them after the agent results, in the system message that opens the
turn's data (``current_turn_data``). The section is joined to the summary only
inside the response chain: the summary itself is also the text a confirmed
draft's fast path SHOWS the person, and a data block must never reach a chat
bubble.

Each record was already bounded by the response slot's budget when it was
projected; the section as a whole is bounded by the same budget. When the
records do not all fit, the smallest are kept — the cut falls on the largest
blocks, never on the many small ones — and the dropped tools are named, with
their count, because a block nobody mentions reads as data that does not
exist. Every cut is stated to the model and counted.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from functools import cache
from typing import Final

from src.core.field_names import FIELD_TOOL_DATA
from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.domains.agents.constants import STATE_KEY_AGENT_RESULTS, STATE_KEY_CURRENT_TURN_ID
from src.domains.agents.orchestration.tool_data_projection import RESPONSE_SLOT
from src.domains.agents.utils.react_budget import slot_tool_result_budget
from src.domains.agents.utils.token_utils import count_tokens
from src.infrastructure.observability.metrics_pipeline import pipeline_tool_data_truncated_total

#: The lines file holding the section's scaffolds (shared with the response node).
_LINES: Final = "response_prompt_lines"


def with_tool_data_section(summary: str, state: Mapping[str, object]) -> str:
    """The turn's data as the response model reads it: the summary, then the blocks.

    Args:
        summary: The agent-results summary (status lines, confirmations).
        state: The graph state, for the turn's agent results and turn id.

    Returns:
        The summary followed by the tool data section, or either alone.
    """
    agent_results = state.get(STATE_KEY_AGENT_RESULTS)
    section = tool_data_section(
        agent_results if isinstance(agent_results, Mapping) else {},
        state.get(STATE_KEY_CURRENT_TURN_ID),
    )
    return "\n\n".join(part for part in (summary, section) if part)


def tool_data_section(agent_results: Mapping[str, object], current_turn_id: object) -> str:
    """Render this turn's data blocks under the response slot's budget.

    Args:
        agent_results: The state's entries, keyed ``"turn:agent"``.
        current_turn_id: The turn whose blocks are rendered; every entry when None.

    Returns:
        The section, or ``""`` when the turn's read steps projected nothing.
    """
    records = list(_turn_records(agent_results, current_turn_id))
    if not records:
        return ""
    kept, dropped = _fit(records, slot_tool_result_budget(RESPONSE_SLOT))
    lines = _lines()
    parts = [lines["tool_data_header"]]
    for record in kept:
        parts.append(f"{lines['tool_data_block'].format(tool=record['tool'])}\n{record['text']}")
        if record.get("truncated"):
            parts.append(_cut_line(lines, record))
            pipeline_tool_data_truncated_total.labels(tool_name=record["tool"], reason="cut").inc()
    if dropped:
        tools = sorted({str(record["tool"]) for record in dropped})
        parts.append(lines["tool_data_dropped"].format(count=len(dropped), tools=", ".join(tools)))
        for record in dropped:
            pipeline_tool_data_truncated_total.labels(
                tool_name=record["tool"], reason="dropped"
            ).inc()
    return "\n\n".join(parts)


def _turn_records(
    agent_results: Mapping[str, object], current_turn_id: object
) -> Iterator[dict[str, object]]:
    """Every record of the turn's step payloads, in plan order."""
    prefix = f"{current_turn_id}:"
    for key, result in agent_results.items():
        if current_turn_id is not None and not key.startswith(prefix):
            continue
        data = result.get("data") if isinstance(result, dict) else None
        steps = data.get("step_results") if isinstance(data, dict) else None
        for step in steps if isinstance(steps, list) else ():
            yield from _records_of(step)


def _records_of(step: object) -> Iterator[dict[str, object]]:
    """The well-formed records one step payload carries, whichever shape it arrived in."""
    if not isinstance(step, dict):
        return
    records = step.get(FIELD_TOOL_DATA)
    nested = step.get("data")
    if records is None and isinstance(nested, dict):
        records = nested.get(FIELD_TOOL_DATA)
    for record in records if isinstance(records, list) else ():
        if (
            isinstance(record, dict)
            and isinstance(record.get("tool"), str)
            and isinstance(record.get("text"), str)
        ):
            yield record


def _fit(
    records: list[dict[str, object]], budget: int
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Keep the smallest records within the budget (at least one), in plan order.

    Args:
        records: The turn's records, in plan order.
        budget: Tokens the section may occupy.

    Returns:
        The kept records in plan order, and the dropped ones.
    """
    sizes = [count_tokens(str(record["text"])) for record in records]
    chosen: set[int] = set()
    used = 0
    for index in sorted(range(len(records)), key=sizes.__getitem__):
        if chosen and used + sizes[index] > budget:
            break
        chosen.add(index)
        used += sizes[index]
    kept = [record for index, record in enumerate(records) if index in chosen]
    dropped = [record for index, record in enumerate(records) if index not in chosen]
    return kept, dropped


def _cut_line(lines: dict[str, str], record: dict[str, object]) -> str:
    """What the model is told about a block the projection cut."""
    if record.get("key") is None:
        return lines["tool_data_cut_whole"].format(
            tool=record["tool"], budget_tokens=record.get("budget_tokens")
        )
    return lines["tool_data_cut"].format(
        tool=record["tool"], shown=record.get("shown"), total=record.get("total"), key=record["key"]
    )


@cache
def _lines() -> dict[str, str]:
    return dict(parse_prompt_sections(read_prompt_file(_LINES), 2))
