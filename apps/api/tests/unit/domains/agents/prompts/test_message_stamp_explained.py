"""Every prompt that reads a stamped history says what the stamp is (lot 17).

The measurement (``scripts/agents/measure_message_timestamps.py``) adopted the
stamps WITH this sentence; a reader handed stamps it was never told about is a
reader the measurement does not cover. ReAct and the response read it in their
STATIC part, so it costs no cache read; the analyzer, the compaction summarizer
and a dialogue skill's runner read it beside the history they are shown.
"""

from __future__ import annotations

import pytest

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.domains.agents.prompts.prompt_loader import load_prompt

pytestmark = pytest.mark.unit

SENTENCE = "A message may start with the date and time it was written, in brackets"


@pytest.mark.parametrize("name", ["react_agent_prompt", "response_system_prompt_base"])
def test_the_loops_read_it_in_their_static_part(name: str) -> None:
    static = load_prompt(name).split(DYNAMIC_CONTEXT_MARKER, 1)[0]
    assert SENTENCE in static


def test_react_resolves_an_earlier_relative_date_against_its_own_moment() -> None:
    static = load_prompt("react_agent_prompt").split(DYNAMIC_CONTEXT_MARKER, 1)[0]
    assert "against the moment it was said" in static


@pytest.mark.parametrize("name", ["query_analyzer_prompt", "compaction_prompt"])
def test_the_history_readers_beside_the_loops_read_it(name: str) -> None:
    assert SENTENCE.lower() in load_prompt(name).lower()


def test_a_dialogue_skill_runner_reads_it_with_its_history() -> None:
    lines = dict(parse_prompt_sections(read_prompt_file("skill_runner_lines"), 2))
    assert SENTENCE in lines["history_note"]
    assert SENTENCE not in lines["task"]


@pytest.mark.parametrize(
    "name",
    [
        "memory_extraction_prompt",
        "interest_extraction_prompt",
        "open_loop_extraction_prompt",
        "journal_introspection_prompt",
    ],
)
def test_the_four_extractions_read_it_beside_their_exchange(name: str) -> None:
    """Their exchange is stamped in the person's zone (ADR-381 amendment): they are told so."""
    assert SENTENCE.lower() in load_prompt(name).lower()
