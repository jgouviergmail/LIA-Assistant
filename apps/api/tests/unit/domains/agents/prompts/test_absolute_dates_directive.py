"""Every prompt that writes tool parameters from the person's words resolves dates.

Measured on 2026-09-23 (ADR-310): « demain » reached the weather tool as a word,
and the initiative checked the agenda of the wrong day. The house directive
already lived in six prompts (query analyzer, telephony, memory extraction,
meeting synthesis, health agent, compaction); the three that write tool
parameters during a turn carry it too, in their STATIC part, so it costs no
cache read.
"""

from __future__ import annotations

import pytest

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.domains.agents.prompts.prompt_loader import load_prompt

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "name", ["react_agent_prompt", "initiative_prompt", "smart_planner_prompt"]
)
def test_the_static_part_resolves_relative_dates(name: str) -> None:
    static = load_prompt(name).split(DYNAMIC_CONTEXT_MARKER, 1)[0]
    assert "in any language" in static and "ISO 8601" in static, name


def test_the_initiative_checks_the_day_the_action_targets() -> None:
    """The initiative anchored on the date a weather result carried (the 24th)
    while the route targeted the 25th."""
    static = load_prompt("initiative_prompt").split(DYNAMIC_CONTEXT_MARKER, 1)[0]
    assert "the day the executed action targets" in static
