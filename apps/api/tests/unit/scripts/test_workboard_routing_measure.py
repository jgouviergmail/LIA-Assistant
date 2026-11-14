"""The routing measurement offers what its corpus expects, and judges every board tool.

The script is a paid, on-demand measurement (ADR-155: never a gate), so nothing
ran it when the corpus grew: it kept offering the model six capabilities while
two families expected a seventh, and it told « a board tool » by a suffix the
new tool's name does not carry. A measurement that cannot be right for a
family, or that scores a confusion as a success, is a number nobody should
read — these tests hold its two deterministic halves.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.workboard.measure_routing import CORPUS_PATH, _catalogue, _verdict, _workboard_tools

pytestmark = pytest.mark.unit


def _families() -> list[dict[str, object]]:
    return json.loads(Path(CORPUS_PATH).read_text(encoding="utf-8"))["families"]


def test_the_model_is_offered_every_tool_the_corpus_expects() -> None:
    expected = {family["expect_tool"] for family in _families() if family["expect_tool"]}
    catalogue = _catalogue()

    assert expected <= _workboard_tools()
    for tool in expected:
        assert f"- {tool}: " in catalogue, f"{tool} is expected and never offered"


def test_the_offer_is_the_whole_ticket_agent_and_nothing_it_does_not_ship() -> None:
    from src.domains.agents.workboard.catalogue_manifests import TICKET_AGENT_MANIFEST

    assert _workboard_tools() == set(TICKET_AGENT_MANIFEST.tools)


def test_a_sentence_for_a_neighbour_that_lands_on_ANY_board_tool_is_wrong() -> None:
    """The category reader included: its name does not end like the six others."""
    negative = {"name": "negative_reminder", "expect_tool": None}

    for tool in _workboard_tools():
        assert _verdict(negative, tool) == "wrong", tool
    assert _verdict(negative, "create_reminder_tool") == "exact"
    assert _verdict(negative, None) == "exact"


def test_a_board_sentence_is_exact_only_on_the_tool_it_names() -> None:
    family = {"name": "list_the_categories", "expect_tool": "list_ticket_categories_tool"}

    assert _verdict(family, "list_ticket_categories_tool") == "exact"
    assert _verdict(family, "list_tickets_tool") == "wrong"
    assert _verdict(family, None) == "wrong"
