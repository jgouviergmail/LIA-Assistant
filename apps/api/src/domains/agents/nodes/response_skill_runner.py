"""The script-skill runner's task and the settlement of its result (response node).

Extracted from ``response_node`` (size-frozen) on 2026-09-20, when the runner was
given an ACTIVATED skill and a silent drop became a signal: the runner used to
spend its first round trip on ``activate_skill_tool``, receive the conversation
history whatever the skill, and — at zero iterations — see its prose result
discarded without a word (production 18:00: the tic-tac-toe runner, misled by an
earlier text game, ran no script and the turn showed no board).

The runner itself lives here too (``run_skill_runner``), shared by the response
node and ``activate_skill_tool``: a third-party skill (ADR-327) runs isolated on
its own skill, and ``settle_third_party_runner`` neutralises what it says.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from src.domains.shared.markdown_literal import untrusted_markdown
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

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


async def run_skill_runner(
    skill_name: str,
    task: str,
    *,
    config: RunnableConfig,
    location_query: str,
    third_party: bool,
) -> Any:
    """Run the skill runner sub-agent on one activated skill.

    A third-party skill (ADR-327) runs ISOLATED: the runner holds its own
    skill's script and resource tools and nothing else — no import tool —
    and those tools refuse every other skill while it runs
    (``skills.trust.isolated_to``).

    Args:
        skill_name: The activated skill.
        task: The task text (``skill_runner_task``).
        config: The caller's ``RunnableConfig`` (thread, callbacks, metadata).
        location_query: The text the person's position is resolved against.
        third_party: Whether the skill was written outside LIA.

    Returns:
        The ``ReactSubAgentResult``.
    """
    from src.core.constants import SKILLS_REACT_RECURSION_LIMIT
    from src.core.i18n import get_language_name
    from src.domains.agents.context.runtime_context import (
        runtime_context_if_running,
        runtime_language,
    )
    from src.domains.agents.registry.agent_registry import get_global_registry
    from src.domains.agents.services.skill_location_context import (
        resolve_user_location_for_prompt,
    )
    from src.domains.agents.tools.react_runner import ReactSubAgentRunner
    from src.domains.agents.tools.react_tool_wrapper import ReactToolWrapper
    from src.domains.skills.command_network import runner_network_line
    from src.domains.skills.sandbox_toolbox import render_toolbox
    from src.domains.skills.tools import skills_isolated_tools, skills_runner_tools
    from src.domains.skills.trust import isolated_to

    language = runtime_language()
    # ADR-137 follow-up: the sub-agent cannot resolve a position on its own —
    # feed it the canonical resolution so it never invents one.
    location = await resolve_user_location_for_prompt(config, location_query, language)
    # ``configurable`` carries thread plumbing ONLY: the runner derives the
    # sub-run's identity, timezone and language from the typed context (ADR-231).
    parent = SimpleNamespace(
        config={
            "configurable": {"thread_id": config.get("configurable", {}).get("thread_id", "")},
            "callbacks": config.get("callbacks"),
            "metadata": config.get("metadata", {}),
        },
        store=get_global_registry().get_store(),
    )
    # Wrapped so the runner collects the registry items (frames, images) the
    # tools emit: without the wrappers, rich skill outputs never reach the page.
    tools = [
        ReactToolWrapper(original_tool=t)
        for t in (skills_isolated_tools if third_party else skills_runner_tools)
    ]
    run = ReactSubAgentRunner(
        llm_type="mcp_react_agent", prompt_name="skill_react_agent_prompt"
    ).run(
        task=task,
        tools=tools,
        prompt_vars={
            "skills_catalog": (
                f"<available_skills><skill><name>{skill_name}</name></skill></available_skills>"
            ),
            "user_language": get_language_name(language),
            "user_location": location,
            # What the sandbox holds, from the declaration the image is proven
            # against (ADR-327 lot 2): the prompt promises nothing else.
            "sandbox_toolbox": render_toolbox(),
            # What a command reaches this turn (ADR-327 lot 3): offline, or the
            # hosts it needs no question for — never a connector for a skill
            # written elsewhere.
            "command_network": await runner_network_line(
                third_party=third_party, context=runtime_context_if_running()
            ),
        },
        parent_runtime=parent,
        thread_prefix="skill_react",
        recursion_limit=SKILLS_REACT_RECURSION_LIMIT,
        display_name="Skill Activation",
    )
    if not third_party:
        return await run
    with isolated_to(skill_name):
        return await run


def settle_third_party_runner(
    result: Any, run_id: str, skill_name: str
) -> tuple[str | None, dict[str, Any] | None, dict[str, Any] | None]:
    """What an isolated third-party runner produced, neutralised (ADR-327).

    Unlike ``settle_skill_runner``, a runner that called no tool may answer:
    a skill of instructions alone has nothing to run. Its words are drawn by
    ``untrusted_markdown`` — no image, no raw HTML — and nothing of it falls
    back into the response prompt: an empty answer is no answer.

    Args:
        result: The ``ReactSubAgentResult``.
        run_id: The turn's run id (logs).
        skill_name: The activated skill (logs).

    Returns:
        ``(final_message, react_result, registry_updates)``, all ``None`` when
        the runner said nothing.
    """
    from src.infrastructure.observability.metrics_registry import skill_runner_outcomes_total

    answer = (result.final_message or "").strip()
    outcome = "tools_called" if result.iteration_count else "no_tool_call"
    skill_runner_outcomes_total.labels(outcome=outcome).inc()
    logger.info(
        "skill_third_party_runner_settled",
        run_id=run_id,
        skill_name=skill_name,
        iterations=result.iteration_count,
        response_length=len(answer),
        duration_ms=result.duration_ms,
    )
    if not answer:
        return None, None, None
    neutral = untrusted_markdown(answer)
    react_result = {
        "final_message": neutral,
        "iteration_count": result.iteration_count,
        "mode": "react",
    }
    return neutral, react_result, result.accumulated_registry or None


def collected_data_block(state: Mapping[str, Any]) -> str:
    """The turn's collected data for the runner's task, or an empty string.

    What the plan executor or the skill bypass already fetched this turn, so
    the runner answers from it rather than fetching it again.
    """
    from src.domains.agents.constants import STATE_KEY_AGENT_RESULTS
    from src.domains.agents.context.runtime_context import runtime_timezone
    from src.domains.agents.formatters.agent_results import format_agent_results_for_prompt

    raw = state.get(STATE_KEY_AGENT_RESULTS, {})
    if not raw:
        return ""
    summary = format_agent_results_for_prompt(
        raw, current_turn_id=state.get("current_turn_id"), user_timezone=runtime_timezone()
    )
    if not summary:
        return ""
    return (
        f"\n\n<collected_data>\n{summary}\n</collected_data>\n"
        "Use this data to generate your response."
    )


async def run_and_settle(
    skill_name: str,
    *,
    state: Mapping[str, Any],
    config: RunnableConfig,
    run_id: str,
    user_id: str | None,
    request: str,
    history: str,
    third_party: bool,
    skill_sections: list[str],
) -> tuple[str | None, dict[str, Any] | None, dict[str, Any] | None]:
    """Activate a skill in Python, run the runner on it, and settle what it produced.

    The activation is Python's, not the model's: the runner used to spend its
    first round trip calling ``activate_skill_tool``, and a runner that never
    got past it answered in prose (production 2026-09-20). A runner that raises
    degrades to the passive injection of the instructions — never for a
    third-party skill, whose words stay out of the response prompt (ADR-327).

    Args:
        skill_name: The activated skill.
        state: The turn's state (its collected data).
        config: The node's ``RunnableConfig``.
        run_id: The turn's run id (logs).
        user_id: The person, or None for system skills only.
        request: What the skill answers.
        history: The conversation history for a dialogue skill, else ``""``.
        third_party: Whether the skill was written outside LIA.
        skill_sections: The passive sections, appended to on a degradation.

    Returns:
        ``(final_message, react_result, registry_updates)``, all None when the
        runner produced nothing usable.
    """
    from src.domains.skills.activation import activate_skill
    from src.infrastructure.observability.metrics_registry import skill_runner_outcomes_total

    instructions = activate_skill(skill_name, user_id=user_id) or ""
    try:
        task = skill_runner_task(
            skill_name,
            instructions,
            request,
            history=history,
            agent_data=collected_data_block(state),
        )
        result = await run_skill_runner(
            skill_name, task, config=config, location_query=request, third_party=third_party
        )
    except Exception as exc:
        # The type, never the message: an error text can quote the request (ADR-317).
        logger.warning("skill_react_agent_error", run_id=run_id, error_type=type(exc).__name__)
        skill_runner_outcomes_total.labels(outcome="error").inc()
        if instructions and not third_party:
            skill_sections.append(instructions)
        return None, None, None
    if third_party:
        return settle_third_party_runner(result, run_id, skill_name)
    return settle_skill_runner(result, run_id, skill_name, instructions, skill_sections)
