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

from typing import Any

from src.core.field_names import FIELD_STATUS
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
    status_messages = _format_status_messages(agent_results, current_turn_id)

    return status_messages


def _format_status_messages(
    agent_results: dict[str, Any],
    current_turn_id: int | None = None,
) -> str:
    """
    Format status messages for agent results.

    Handles:
    - connector_disabled, error statuses → error messages
    - user_rejected (HITL) → rejection messages
    - action success (no registry data) → confirmation messages

    NOTE: Data query successes (contacts, emails) are handled by {data_for_filtering},
    but ACTION successes (reminders, send email) need their confirmation message
    injected here so the LLM knows the action was completed.

    Args:
        agent_results: Dictionary of composite_key → AgentResult
        current_turn_id: Filter by turn ID if specified

    Returns:
        Formatted status messages string (or empty string if none)
    """
    summaries: list[str] = []

    for composite_key, result in agent_results.items():
        # Parse composite key "turn_id:agent_name"
        if ":" in composite_key:
            turn_id_str, agent_name = composite_key.split(":", 1)

            # Filter by turn if specified
            if current_turn_id is not None:
                try:
                    if int(turn_id_str) != current_turn_id:
                        continue
                except ValueError:
                    logger.warning("invalid_turn_id_in_key", composite_key=composite_key)
        else:
            agent_name = composite_key

        status = result.get(FIELD_STATUS, "unknown")

        if status == "success":
            # Check for user rejection (HITL)
            data = result.get("data")
            if data and isinstance(data, dict) and data.get("user_rejected"):
                message = data.get("message", "L'utilisateur a refusé cette action.")
                summaries.append(f"🚫 {agent_name}: {message}")
            # Check for ACTION success messages (reminders, send email, etc.)
            # These have no registry_updates but contain a confirmation message
            # that must be communicated to the LLM to avoid misleading responses.
            #
            # BugFix 2026-01-20: ALWAYS extract step messages, even when registry has items.
            # In multi-step plans, some steps may succeed with registry (calendar)
            # while others may fail (weather beyond forecast limit). The error messages
            # from failing steps must be communicated to the LLM regardless of registry.
            elif data and isinstance(data, dict):
                action_messages = _extract_action_success_messages(data)
                if action_messages:
                    summaries.extend(action_messages)
                    logger.debug(
                        "action_success_messages_extracted",
                        composite_key=composite_key,
                        messages_count=len(action_messages),
                    )

        elif status == "connector_disabled":
            error_msg = result.get("error", "Service non activé")
            summaries.append(f"⚠️ {agent_name}: {error_msg}")

        elif status == "error":
            error_msg = result.get("error", "Erreur inconnue")
            summaries.append(f"❌ {agent_name}: {error_msg}")

        else:
            summaries.append(f"❓ {agent_name}: Statut inconnu ({status})")

    return "\n".join(summaries)


def _extract_action_success_messages(data: dict[str, Any]) -> list[str]:
    """
    Extract action success confirmation messages from result data.

    Action tools (reminders, send email, etc.) return UnifiedToolOutput.action_success()
    with a confirmation message that must be communicated to the LLM.

    The message can be in:
    - data["step_results"][i]["result"] - from plan executor (str or list[str])
    - data["aggregated_results"][i]["result"] - aggregated format (str or list[str])
    - data["message"] - direct message field

    BugFix 2026-01-22: FOR_EACH aggregation now collects all "result" strings into a list.
    This function handles both str and list[str] for the "result" field.

    Args:
        data: Result data dict from agent execution

    Returns:
        List of action confirmation messages (e.g., ["🔔 Rappel créé pour..."])
    """
    messages: list[str] = []

    # Check step_results and aggregated_results (from plan_executor mapping)
    for key in ("step_results", "aggregated_results"):
        results_list = data.get(key, [])
        if isinstance(results_list, list):
            for item in results_list:
                if isinstance(item, dict):
                    # UnifiedToolOutput.action_success stores message in "result" key
                    # BugFix 2026-01-22: FOR_EACH aggregation may return list[str]
                    result_msg = item.get("result")
                    if result_msg:
                        if isinstance(result_msg, str):
                            # Single message (non-FOR_EACH or single iteration)
                            if result_msg not in messages:
                                messages.append(result_msg)
                        elif isinstance(result_msg, list):
                            # Multiple messages from FOR_EACH aggregation
                            for msg in result_msg:
                                if isinstance(msg, str) and msg not in messages:
                                    messages.append(msg)

    # Check direct message field (fallback)
    direct_msg = data.get("message")
    if direct_msg and isinstance(direct_msg, str) and direct_msg not in messages:
        messages.append(direct_msg)

    return messages
