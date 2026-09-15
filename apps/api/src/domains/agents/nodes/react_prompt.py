"""The ReAct system prompt — assembled from what the turn can actually run.

Extracted from ``react_nodes`` (file-size ratchet): the three functions that
turn the versioned ``react_agent_prompt`` into the turn's system message. The
prompt promises only the tools the turn carries — the ``<Computation>`` block
is rendered iff ``run_python_tool`` is bound AND the capability is switched on
(ADR-284, prompt audit 2026-09-12: the public demonstrator read a promise of a
tool it never registered).
"""

import re
from collections.abc import Sequence

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE, PYTHON_SANDBOX_TOOL_NAME
from src.core.i18n import get_language_name
from src.core.time_utils import get_prompt_datetime_formatted
from src.domains.agents.analysis.query_intelligence_helpers import get_qi_attr
from src.domains.agents.models import MessagesState
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled

__all__ = ["build_system_prompt", "sandbox_available"]


async def sandbox_available(tool_names: Sequence[str]) -> bool:
    """Can this turn actually run ``run_python_tool``?

    Bound for the turn AND switched on right now: the sandbox is a switchable
    capability (off on the public demonstrator, and an operator may flip it
    without a restart), and the tool refuses at call time when it is off. A
    prompt that promises it anyway makes the model announce a script it
    cannot run (prompt audit 2026-09-12, A.5).

    Args:
        tool_names: Names of the tools bound for this turn.

    Returns:
        True only when the tool is bound and the capability is enabled.
    """
    if PYTHON_SANDBOX_TOOL_NAME not in tool_names:
        return False
    return await is_capability_enabled(PlatformCapability.PYTHON_SANDBOX)


def _render_computation_block(computation: bool) -> str:
    """The ephemeral-Python section, with the budget ``python_sandbox_tools`` enforces.

    Args:
        computation: Whether the turn can run the sandbox (see ``_sandbox_available``).

    Returns:
        The rendered ``<Computation>`` block, or an empty string.
    """
    if not computation:
        return ""
    return load_prompt("react_computation_prompt").format(
        python_sandbox_max_runs_per_turn=settings.python_sandbox_max_runs_per_turn,
    )


def build_system_prompt(state: MessagesState, *, computation: bool = False) -> str:
    """Build the ReAct agent system prompt with context variables.

    Args:
        state: Current graph state.
        computation: Whether the turn can run the Python sandbox — the prompt
            promises the tool only then.

    Returns:
        Formatted system prompt string.
    """
    personality = state.get("personality_instruction") or "a helpful, friendly assistant"
    user_tz = state.get("user_timezone", DEFAULT_USER_DISPLAY_TIMEZONE)
    user_lang = state.get("user_language", "fr")

    # Cross-domain type links (same section the pipeline planner receives,
    # ontology ∪ live manifests). Without it, the ReAct LLM has no signal
    # that e.g. a route destination should come from a contact's exact
    # address rather than an approximate memory value.
    from src.domains.agents.semantic.expansion_service import (
        generate_semantic_dependencies_for_prompt,
    )

    domains = get_qi_attr(state, "domains", default=[]) or []
    semantic_deps = generate_semantic_dependencies_for_prompt(
        domains, include_jinja2_patterns=False
    )

    template = load_prompt("react_agent_prompt")
    prompt = template.format(
        personnalite=personality,
        current_datetime=get_prompt_datetime_formatted(),
        user_timezone=user_tz,
        # Human-readable name ("French") — clearer language directive for the
        # LLM than a raw code ("fr"); same convention as get_response_prompt.
        user_language=get_language_name(user_lang),
        semantic_dependencies=semantic_deps,
        computation_block=_render_computation_block(computation),
    )
    # An absent block leaves its two blank lines behind; the model reads one.
    return re.sub(r"(\r?\n){3,}", r"\1\1", prompt)
