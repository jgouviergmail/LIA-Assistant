"""The script-skill runner's task and the settlement of its result (response node).

Extracted from ``response_node`` (size-frozen) on 2026-09-20, when the runner was
given an ACTIVATED skill and a silent drop became a signal: the runner used to
spend its first round trip on ``activate_skill_tool``, receive the conversation
history whatever the skill, and — at zero iterations — see its prose result
discarded without a word (production 18:00: the tic-tac-toe runner, misled by an
earlier text game, ran no script and the turn showed no board).
"""

from __future__ import annotations

from typing import Any

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def skill_runner_task(
    skill_name: str,
    instructions: str,
    last_user_message: str,
    *,
    history: str,
    agent_data: str,
) -> str:
    """The task handed to the script-skill runner: the activated skill, then the context.

    S5: the windowed history lets a fresh runner sub-agent resume a multi-turn
    skill dialogue (clarify → answer → generate). The caller passes it for a
    skill that declares ``dialogue`` ONLY: on a one-shot script skill the same
    block carried an earlier text game, the model took the request for a reply
    within it and ran no script (production 2026-09-20, 18:00).

    Args:
        skill_name: The activated skill.
        instructions: What ``activate_skill`` returned for it.
        last_user_message: The request the skill answers.
        history: The conversation history, or an empty string.
        agent_data: The ``<collected_data>`` block, or an empty string.

    Returns:
        The task text.
    """
    history_block = ""
    if history.strip():
        history_block = (
            f"\n\n<conversation_history>\n{history}\n</conversation_history>\n"
            "The skill runs a multi-step dialogue: use this history to resume it "
            "(e.g. treat the latest user message as the answer to a question you "
            "asked earlier)."
        )
    return (
        f"Skill '{skill_name}' is activated. Follow its instructions to respond to: "
        f"{last_user_message}\n\n<skill_instructions>\n{instructions}\n</skill_instructions>"
        f"{history_block}{agent_data}"
    )


def settle_skill_runner(
    result: Any,
    run_id: str,
    skill_name: str,
    instructions: str,
    skill_sections: list[str],
) -> tuple[str | None, dict[str, Any] | None, dict[str, Any] | None]:
    """What the script-skill runner produced, said and counted.

    A runner that called NO tool answered in prose about a widget that does
    not exist (production 2026-09-20: misled by an earlier text game, and the
    result was dropped in silence): it is logged, counted, and the
    instructions reach the response the passive way. A runner that ran its
    tools hands back its final message, the ``react_agent_result`` shape and
    the registry items its wrappers accumulated.

    Args:
        result: The ``ReactSubAgentResult``.
        run_id: The turn's run id (logs).
        skill_name: The activated skill (logs).
        instructions: What ``activate_skill`` returned, for the passive fallback.
        skill_sections: The passive sections, appended to on a silent runner.

    Returns:
        ``(final_message, react_result, registry_updates)`` — the first two
        ``None`` when the runner called no tool.
    """
    from src.infrastructure.observability.metrics_registry import skill_runner_outcomes_total

    if result.iteration_count == 0:
        logger.warning(
            "skill_runner_no_tool_call",
            run_id=run_id,
            skill_name=skill_name,
            response_length=len(result.final_message or ""),
            duration_ms=result.duration_ms,
        )
        skill_runner_outcomes_total.labels(outcome="no_tool_call").inc()
        if instructions:
            skill_sections.append(instructions)
        return None, None, None
    if not result.final_message:
        return None, None, None
    skill_runner_outcomes_total.labels(outcome="tools_called").inc()
    # Normalize onto the ONE shape `react_result` carries everywhere else —
    # the ``react_agent_result`` state contract (MessagesState: dict | None).
    # The runner returns a `ReactSubAgentResult` dataclass; assigning it raw
    # made two incompatible shapes travel under one `Any`-typed name, and
    # `_build_response_system_prompt` — which reads
    # `react_result.get("final_message")` — crashed with AttributeError on run
    # ``117ce96f`` (2026-07-21), taking the whole turn down to a 98-character
    # fallback.
    react_result = {
        "final_message": result.final_message,
        "iteration_count": result.iteration_count,
        "mode": "react",
    }
    logger.info(
        "skill_react_agent_activated",
        run_id=run_id,
        skill_name=skill_name,
        iterations=result.iteration_count,
        response_length=len(result.final_message),
        duration_ms=result.duration_ms,
    )
    registry = result.accumulated_registry or None
    if registry:
        logger.info(
            "skill_react_registry_propagated",
            run_id=run_id,
            skill_name=skill_name,
            registry_items=len(registry),
        )
    return result.final_message, react_result, registry
