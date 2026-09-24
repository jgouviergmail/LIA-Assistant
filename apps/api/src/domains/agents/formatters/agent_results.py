"""
Agent results formatting for LLM prompts.

This module provides functions for formatting agent status messages
(errors, disabled connectors, rejections) for injection into LLM prompts.

Note: Data details are now injected via {data_for_filtering} using the
generic payload serializer. This module only handles status messages.

Usage:
    from src.domains.agents.formatters.agent_results import (
        format_agent_results_for_prompt,
    )
"""

from collections.abc import Iterable
from typing import Any

from src.core.field_names import (
    FIELD_FAILED_STEPS,
    FIELD_REACT_SYNTHESIS,
    FIELD_STATUS,
    FIELD_SUCCESS,
)
from src.core.i18n import normalize_language
from src.core.i18n_api_messages import APIMessages
from src.core.i18n_hitl import HitlMessages
from src.core.i18n_types import Language
from src.domains.agents.constants import AgentResultStatus
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.profiling import profile_performance

logger = get_logger(__name__)


@profile_performance(func_name="format_agent_results", log_threshold_ms=50.0)
def format_agent_results_for_prompt(
    agent_results: dict[str, Any],
    current_turn_id: int | None = None,
    data_registry: dict[str, Any] | None = None,
    user_timezone: str = "UTC",
    user_language: str = "en",
    override_action: str | None = None,
    user_viewport: str = "desktop",
    use_text_summary: bool = True,  # DEPRECATED - kept for compatibility
) -> str:
    """
    Format agent status messages for injection into response prompt.

    NOTE: Data details are now injected via {data_for_filtering} using the
    generic payload serializer. This function only handles status messages
    (errors, connector_disabled, user_rejected).

    Args:
        agent_results: Dictionary of composite_key → AgentResult.
        current_turn_id: Optional turn ID to filter results.
        data_registry: DEPRECATED - no longer used (data in {data_for_filtering}).
        user_timezone: User's IANA timezone. Default: "UTC".
        user_language: User's language code. Default: "en".
        override_action: Optional action override. Default: None.
        user_viewport: Device viewport type. Default: "desktop".
        use_text_summary: DEPRECATED - ignored.

    Returns:
        Status messages for errors/disabled connectors, or empty string if none.
    """
    # Deprecated params - kept for API compatibility
    del use_text_summary, data_registry, user_timezone, override_action, user_viewport

    if not agent_results:
        return ""

    # Only format status messages (errors, connector_disabled, user_rejected)
    # Data details are now in {data_for_filtering} via generate_data_for_filtering()
    status_messages = _format_status_messages(agent_results, current_turn_id, user_language)

    return status_messages


def _agent_name_for(composite_key: str, current_turn_id: int | None) -> str | None:
    """The agent behind a composite key, or None when the entry is another turn's.

    Args:
        composite_key: ``"<turn_id>:<agent_name>"``, or a bare agent name.
        current_turn_id: Keep only this turn's entries when given.

    Returns:
        The agent name, or None when the entry must be skipped. An unparseable
        turn id is KEPT and logged: dropping an entry because its key is
        malformed would lose what the tools said.
    """
    if ":" not in composite_key:
        return composite_key
    turn_id_str, agent_name = composite_key.split(":", 1)
    if current_turn_id is None:
        return agent_name
    try:
        belongs = int(turn_id_str) == current_turn_id
    except ValueError:
        logger.warning("invalid_turn_id_in_key", composite_key=composite_key)
        return agent_name
    return agent_name if belongs else None


def _react_lines_of(result: dict[str, Any]) -> list[str] | None:
    """What a ReAct entry states: the loop's answer, authoritative.

    The loop hands its final answer through ``data["react_synthesis"]`` rather
    than a status payload: the response model reformulates it instead of
    rebuilding an answer from the raw registry. What the turn DID is stated by
    its own directive, never here (ADR-263 §23): an act written as a data line
    beside the answer read as somebody else's caption.

    Args:
        result: One agent result entry.

    Returns:
        The answer as one line (none when it is empty), or None when the entry
        is not a ReAct one.
    """
    data = result.get("data")
    if not isinstance(data, dict) or FIELD_REACT_SYNTHESIS not in data:
        return None
    synthesis = data.get(FIELD_REACT_SYNTHESIS)
    return [str(synthesis)] if synthesis else []


def _success_summaries(
    *, agent_name: str, result: dict[str, Any], language: Language, composite_key: str
) -> list[str]:
    """What a SUCCESSFUL entry contributes to the response prompt.

    A refusal the person expressed through HITL is reported as their decision;
    otherwise the action confirmations are extracted, which a multi-step plan
    needs even when some of its steps failed — those speak through the runtime
    failures directive, never here (ADR-303).

    Args:
        agent_name: The agent behind the entry.
        result: The entry.
        language: Backend-canonical language for the fallback wording.
        composite_key: For the debug trace only.

    Returns:
        Zero or more lines.
    """
    data = result.get("data")
    if not isinstance(data, dict) or not data:
        return []
    if data.get("user_rejected"):
        message = data.get("message", HitlMessages.get_user_refused_action(language))
        return [f"🚫 {agent_name}: {message}"]
    action_messages = _extract_action_success_messages(data)
    if action_messages:
        logger.debug(
            "action_success_messages_extracted",
            composite_key=composite_key,
            messages_count=len(action_messages),
        )
    return action_messages


def _error_summaries(*, agent_name: str, result: dict[str, Any], language: Language) -> list[str]:
    """What a FAILED entry contributes — nothing when the directive states it.

    A plan aggregate carrying ``failed_steps`` is stated by the runtime
    failures directive, with each code and the exact total. One fact, one
    channel (ADR-303).

    Args:
        agent_name: The agent behind the entry.
        result: The entry.
        language: Backend-canonical language.

    Returns:
        Zero or one line.
    """
    if result.get(FIELD_FAILED_STEPS):
        return []
    return [APIMessages.agent_error_line(agent_name, result.get("error"), language)]


def _format_status_messages(
    agent_results: dict[str, Any],
    current_turn_id: int | None = None,
    user_language: str = "en",
) -> str:
    """Format status messages for agent results.

    Data query successes (contacts, emails) are handled by
    ``{data_for_filtering}``; ACTION successes (reminders, sent mail) need
    their confirmation injected here so the model knows what was done.

    Args:
        agent_results: Dictionary of composite_key → AgentResult.
        current_turn_id: Filter by turn ID if specified.
        user_language: The person's language code; normalised once here
            because every i18n table below is keyed on the backend-canonical
            spelling (CLAUDE.md, one chokepoint).

    Returns:
        Formatted status messages string (empty when there is nothing to say).
    """
    summaries: list[str] = []
    language = normalize_language(user_language)

    for composite_key, result in agent_results.items():
        agent_name = _agent_name_for(composite_key, current_turn_id)
        if agent_name is None:
            continue

        react_lines = _react_lines_of(result)
        if react_lines is not None:
            summaries.extend(react_lines)
            continue

        status = result.get(FIELD_STATUS)
        if status == AgentResultStatus.SUCCESS.value:
            summaries.extend(
                _success_summaries(
                    agent_name=agent_name,
                    result=result,
                    language=language,
                    composite_key=composite_key,
                )
            )
        elif status == AgentResultStatus.ERROR.value:
            summaries.extend(
                _error_summaries(agent_name=agent_name, result=result, language=language)
            )
        else:
            # Unreachable by construction: AgentResult validates the Literal and
            # the vocabulary guard pins every reader. Never a sentence the model
            # could repeat to the person — an invented diagnosis is worse than
            # silence (measured in production, 2026-09-17 and every other
            # morning since 2026-09-10).
            logger.warning(
                "agent_result_status_unknown",
                composite_key=composite_key,
                status=str(status),
            )

    return "\n".join(summaries)


def _wrap_subagent_analysis(*, analysis_text: str, expertise: str) -> str:
    """Wrap a sub-agent's full analysis in a deterministic delivery tag.

    The ``response_node`` prompt's ``<SubAgentDeliveryOverride>`` block keys
    off this tag to switch to verbatim restitution (see
    ``response_system_prompt_base.txt``). The tag is the deterministic
    signal — the LLM no longer has to detect a sub-agent analysis via
    heuristics on length / markdown structure / voice.

    Args:
        analysis_text: Full markdown-formatted expert text from
            ``structured_data["analysis"]`` (set by ``delegate_to_sub_agent_tool``).
        expertise: Persona / role of the sub-agent
            (``structured_data["expertise"]``). Truncated and sanitised before
            being interpolated into the tag attribute.

    Returns:
        Tag-wrapped string ready to be injected into the response_node prompt.
    """
    safe_expertise = ((expertise or "expert").replace('"', "'").replace("\n", " ").strip())[:120]
    return (
        f'<SubAgentAnalysis expertise="{safe_expertise}">\n'
        f"{analysis_text}\n"
        f"</SubAgentAnalysis>"
    )


def _step_payload(item: dict[str, Any]) -> dict[str, Any]:
    """The tool's own fields of one step result, whichever shape it arrived in.

    ``parallel_executor`` writes the whole ``UnifiedToolOutput`` envelope —
    ``{"success", "data": <structured_data>, "message", …}`` — while a FOR_EACH
    aggregate and the legacy paths hand the structured fields FLAT. Readers
    looked only at the flat shape, so on the real pipeline payload every
    action confirmation and every sub-agent analysis was dropped: measured
    2026-09-22, a plan that created a reminder reached the response prompt
    EMPTY (ADR-303).

    The envelope's ``message`` is merged in as ``result`` when the structured
    data names none, because that is the only place an action's words live for
    a tool that returns no ``result`` key.

    Args:
        item: One entry of ``step_results`` / ``aggregated_results``.

    Returns:
        The tool's fields, flat. Never the envelope's bookkeeping keys.
    """
    nested = item.get("data")
    if not isinstance(nested, dict):
        return item
    payload = {**nested}
    if "result" not in payload and item.get("message"):
        payload["result"] = item["message"]
    return payload


def _append_unique(messages: list[str], candidates: Iterable[str]) -> None:
    """Append what is not already there, order preserved.

    Args:
        messages: The accumulator, mutated in place.
        candidates: Words to add; empty ones and duplicates are dropped.
    """
    for candidate in candidates:
        if candidate and candidate not in messages:
            messages.append(candidate)


def _step_messages(item: dict[str, Any]) -> list[str]:
    """The words ONE step contributes to the response prompt.

    A sub-agent analysis REPLACES the regular extraction rather than adding to
    it: its ``result`` is a 200-character summary of the very text being
    wrapped, so appending both would say the same thing twice. The wrapping is
    a deterministic tag (``<SubAgentAnalysis>``) set from a signal the tool
    itself publishes, never a heuristic over length or markdown.

    Args:
        item: One step payload, already flattened by ``_step_payload``.

    Returns:
        Zero, one or several confirmation messages, in the order the tool
        produced them (a FOR_EACH aggregation carries a list).
    """
    if item.get("type") == "sub_agent_analysis" and item.get("analysis"):
        return [
            _wrap_subagent_analysis(
                analysis_text=str(item["analysis"]),
                expertise=str(item.get("expertise") or "expert"),
            )
        ]
    # UnifiedToolOutput.action_success stores the confirmation under "result";
    # a FOR_EACH aggregation stores one per iteration.
    result_msg = item.get("result")
    if isinstance(result_msg, str):
        return [result_msg]
    if isinstance(result_msg, list):
        return [msg for msg in result_msg if isinstance(msg, str)]
    return []


def _extract_action_success_messages(data: dict[str, Any]) -> list[str]:
    """Action confirmation messages carried by a result payload.

    Action tools (reminders, send email, …) return
    ``UnifiedToolOutput.action_success()`` with a confirmation the model must
    be able to restitute. It can live in ``step_results``/``aggregated_results``
    entries or directly under ``message``.

    Args:
        data: Result data dict from agent execution.

    Returns:
        The confirmations, deduplicated, in encounter order. Sub-agent
        analyses come back wrapped in ``<SubAgentAnalysis>`` tags.
    """
    messages: list[str] = []

    for key in ("step_results", "aggregated_results"):
        results_list = data.get(key, [])
        if not isinstance(results_list, list):
            continue
        for raw_item in results_list:
            if not isinstance(raw_item, dict):
                continue
            if raw_item.get(FIELD_SUCCESS) is False:
                # A failed step speaks through the runtime failures directive,
                # never here: its ``message`` is the error text, and reading it
                # as a confirmation is how « échec » became « fait » (ADR-303).
                continue
            _append_unique(messages, _step_messages(_step_payload(raw_item)))

    direct_msg = data.get("message")
    if isinstance(direct_msg, str):
        _append_unique(messages, [direct_msg])

    return messages
