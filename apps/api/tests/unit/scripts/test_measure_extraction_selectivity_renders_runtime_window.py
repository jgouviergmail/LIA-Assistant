"""The selectivity battery measures the prompt the extractors actually send (ADR-374).

The memory and interest extractors read the person's last message and the three
before it. The battery rendered every turn of a scenario, so a five-message
exchange reached the measured prompt whole and the runtime never sent it; its
interest renderer also imported ``get_language_name`` from a module that does not
define it, so the battery no longer ran at all.
"""

import importlib
from collections.abc import Iterator

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.shared.extraction_targets import extraction_window

pytestmark = pytest.mark.unit

battery = importlib.import_module("scripts.measure_extraction_selectivity")


def _deep_dive() -> object:
    return next(s for s in battery.INTEREST_SCENARIOS if s.id == "pos_deep_dive")


def _user_lines(prompt: str) -> Iterator[str]:
    return (line for line in prompt.splitlines() if line.startswith("USER:"))


def test_the_interest_prompt_holds_the_runtime_window_only() -> None:
    prompt = battery._render_interest_prompt(
        str(load_prompt("interest_extraction_prompt")), _deep_dive(), "2026-11-08 10:00"
    )
    assert len(list(_user_lines(prompt))) == 2
    assert "quelles régions sont incontournables" not in prompt
    assert "culture quechua" in prompt


def test_the_memory_prompt_holds_the_runtime_window_only() -> None:
    prompt = battery._render_memory_prompt(
        str(load_prompt("memory_extraction_prompt")), _deep_dive(), "2026-11-08 10:00"
    )
    assert len(list(_user_lines(prompt))) == 2


def _history(size: int) -> list[BaseMessage]:
    return [
        HumanMessage(content=f"user {i}") if i % 2 == 0 else AIMessage(content=f"ai {i}")
        for i in range(size)
    ]


@pytest.mark.parametrize(("size", "last", "kept"), [(5, 4, 4), (2, 0, 1), (9, 8, 4), (9, 4, 4)])
def test_the_window_ends_at_the_person_and_keeps_four(size: int, last: int, kept: int) -> None:
    messages = _history(size)
    window = extraction_window(messages, last)
    assert window[-1] is messages[last]
    assert len(window) == kept
