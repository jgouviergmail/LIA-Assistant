"""Prompt-cache hygiene guards for the versioned prompt templates.

The provider-agnostic caching contract (see docs and ``factory.py`` /
``responses_adapter.py``) rests on ONE convention: every system prompt that
embeds per-request dynamic content separates its static prefix from the
dynamic tail with the canonical ``DYNAMIC_CONTEXT_MARKER``. The infra layers
then handle provider specifics (Anthropic ``cache_control`` split, OpenAI
``prompt_cache_key``); implicit prefix caches (DeepSeek, Qwen, Gemini) benefit
from the stable prefix with no provider-specific code at all.

These guards are SHRINK-ONLY:
- a prompt listed in ``MARKER_REQUIRED`` must keep its marker;
- a prompt with a marker must not grow a new active placeholder before it
  (unless listed in ``ALLOWED_BEFORE_MARKER`` with a justification).
Add entries when adding prompts; never remove one to absorb a regression.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.domains.agents.prompts import get_smart_planner_prompt

pytestmark = [pytest.mark.unit]

PROMPTS_V1 = Path(__file__).parents[5] / "src" / "domains" / "agents" / "prompts" / "v1"

# str.format()-style active placeholder: single braces around an identifier.
# {{escaped}} braces and [[SENTINEL]] tokens do not match.
_PLACEHOLDER_RE = re.compile(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})")

# System prompts that embed per-request dynamic content and therefore MUST
# carry the canonical marker. Shrink-only: only ever add entries.
MARKER_REQUIRED: tuple[str, ...] = (
    # Pipeline core
    "smart_planner_prompt",
    "query_analyzer_prompt",
    "response_system_prompt_base",
    "semantic_validator_prompt",
    "compaction_prompt",
    # ReAct loops
    "react_agent_prompt",
    "subagent_react_prompt",
    "skill_react_agent_prompt",
    "mcp_react_agent_prompt",
    # HITL
    "hitl_classifier_prompt",
    "hitl_draft_critique_prompt",
    "hitl_plan_approval_question_prompt",
    "hitl_question_generator_prompt",
    # Background intelligence
    "memory_extraction_prompt",
    "interest_extraction_prompt",
    "initiative_prompt",
    "heartbeat_decision_prompt",
    "heartbeat_message_prompt",
    # Domain agents (all share the <Context> tail pattern)
    "brave_agent_prompt",
    "browser_agent_prompt",
    "calendar_agent_prompt",
    "contacts_agent_prompt",
    "drive_agent_prompt",
    "emails_agent_prompt",
    "health_agent_prompt",
    "hue_agent_prompt",
    "perplexity_agent_prompt",
    "places_agent_prompt",
    "query_agent_prompt",
    "routes_agent_prompt",
    "tasks_agent_prompt",
    "weather_agent_prompt",
    "web_fetch_agent_prompt",
    "web_search_agent_prompt",
    "wikipedia_agent_prompt",
)

# Placeholders deliberately allowed BEFORE the marker, per prompt.
# Each entry fragments the cache prefix by that value — acceptable only when
# the value is stable across a user's consecutive requests (identity blocks).
ALLOWED_BEFORE_MARKER: dict[str, frozenset[str]] = {
    # Personality opens the prompt (identity-first design); stable per user.
    "response_system_prompt_base": frozenset({"personnalite", "user_language"}),
    "react_agent_prompt": frozenset({"personnalite", "user_language"}),
    # Expert identity must be established up front; stable per delegated task type.
    "subagent_react_prompt": frozenset({"expertise"}),
    # Server identity; low cardinality, stable per MCP server.
    "mcp_react_agent_prompt": frozenset({"server_name"}),
    # Registry-derived domain list; stable per user (varies with MCP servers).
    "query_agent_prompt": frozenset({"available_domains"}),
    # Personality block in the static header; stable per user.
    "hitl_draft_critique_prompt": frozenset({"personnalite"}),
    # Registry-derived, invariant at runtime for a given deployment.
    # `semantic_broad_batch` is settings-driven and equally invariant: it
    # replaced a hardcoded "20–50" that no tool bound could contradict
    # (production 2026-07-31). One value per deployment fragments nothing.
    "smart_planner_prompt": frozenset({"result_keys_list", "semantic_broad_batch"}),
    # Settings-driven cap, invariant at runtime for a given deployment.
    "initiative_prompt": frozenset({"max_actions"}),
    # Personality block in the static header; stable per user.
    "heartbeat_message_prompt": frozenset({"personality_instruction"}),
}

# Prompts whose pre-marker braces are verbatim DISPLAY TEMPLATES for the LLM
# (filled by targeted .replace(), never .format()); the placeholder scan does
# not apply to them.
VERBATIM_TEMPLATE_PROMPTS: frozenset[str] = frozenset({"hitl_draft_critique_prompt"})


def _read(name: str) -> str:
    return (PROMPTS_V1 / f"{name}.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", MARKER_REQUIRED)
def test_marker_present(name: str) -> None:
    """Every dynamic system prompt separates static prefix from dynamic tail."""
    text = _read(name)
    assert DYNAMIC_CONTEXT_MARKER in text, (
        f"{name}.txt lost its '{DYNAMIC_CONTEXT_MARKER}' marker — without it the "
        "static prefix is not cacheable (and Anthropic would skip cache_control)."
    )


@pytest.mark.parametrize("name", MARKER_REQUIRED)
def test_no_unexpected_placeholder_before_marker(name: str) -> None:
    """No per-request placeholder may sneak into the static (cached) prefix."""
    if name in VERBATIM_TEMPLATE_PROMPTS:
        pytest.skip("pre-marker braces are verbatim display templates for the LLM")
    text = _read(name)
    static = text[: text.find(DYNAMIC_CONTEXT_MARKER)]
    found = set(_PLACEHOLDER_RE.findall(static))
    allowed = ALLOWED_BEFORE_MARKER.get(name, frozenset())
    unexpected = found - allowed
    assert not unexpected, (
        f"{name}.txt has placeholder(s) {sorted(unexpected)} BEFORE the dynamic "
        "marker: every request gets a different cache prefix (systematic cache "
        "miss). Move them below the marker, or justify an ALLOWED_BEFORE_MARKER "
        "entry if the value is stable per user."
    )


def test_planner_static_prefix_stable_across_requests() -> None:
    """Two different requests must produce a byte-identical static prefix."""

    def build(query: str, terms: list[str]) -> str:
        return get_smart_planner_prompt(
            user_goal="find_information",
            intent="search",
            domains="email",
            anticipated_needs="none",
            catalogue='{"tools": []}',
            original_query=query,
            context="",
            references="",
            user_language="fr",
            semantic_filter_terms=terms,
        )

    p1 = build("mes 3 mails urgents", ["urgent"])
    p2 = build("agenda de demain", [])
    pos1, pos2 = p1.find(DYNAMIC_CONTEXT_MARKER), p2.find(DYNAMIC_CONTEXT_MARKER)
    assert pos1 > 0 and pos2 > 0
    assert p1[:pos1] == p2[:pos2], "planner static prefix varies across requests"
    # The static prefix must not leak any per-request value. (Needles must be
    # distinctive: plain words like "urgent" legitimately appear in the static
    # INDEXABLE vs SEMANTIC examples.)
    for needle in ("mes 3 mails urgents", "agenda de demain", '{"tools": []}'):
        assert needle not in p1[:pos1]
