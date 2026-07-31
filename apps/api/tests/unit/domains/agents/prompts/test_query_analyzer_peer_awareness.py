"""Contract of the CONNECTED USERS block in the query analyzer prompt.

The awareness layer of the 2026-07-30 peer-routing fix lives in the prompt, so
it is only as durable as the coupling between the template and its builder. A
placeholder silently dropped from the template would leave the analyzer blind
again — and the failure mode is a *plausible wrong answer*, never an exception,
which is exactly the class of regression that survives a green suite.
"""

import pytest

from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.services.analysis.peer_directory import (
    PEER_CONFUSABLE_DOMAINS,
    PEER_DIRECTORY_EMPTY,
    PEER_DOMAIN,
    format_peer_directory,
)

PROMPT = load_prompt("query_analyzer_prompt", version="v1")

# Every placeholder the builder fills — the template must declare exactly these.
EXPECTED_PLACEHOLDERS = {
    "current_datetime",
    "available_domains",
    "available_skills",
    "connected_peers",
    "memory_facts",
    "conversation_history",
    "user_location",
    "window_size",
    "user_query",
}


def _placeholders(template: str) -> set[str]:
    """Field names `str.format` would require, ignoring escaped braces."""
    from string import Formatter

    return {name for _, name, _, _ in Formatter().parse(template) if name}


def test_template_declares_exactly_the_builder_placeholders():
    """A drift in either direction breaks the turn — both are caught here."""
    assert _placeholders(PROMPT) == EXPECTED_PLACEHOLDERS


def test_prompt_states_the_peer_routing_rule():
    """The rule is the fix; a reworded prompt that drops it is a regression."""
    lowered = PROMPT.lower()
    assert "connected users" in lowered
    assert f"`{PEER_DOMAIN}`" in lowered
    # It must say WHY event/contact cannot answer, not merely mention peer.
    assert "not address-book contacts" in lowered


def test_rule_names_every_domain_the_correction_can_fire_on():
    """Prompt and deterministic gate must describe the same confusion."""
    lowered = PROMPT.lower()
    for domain in PEER_CONFUSABLE_DOMAINS - {"task"}:
        assert f"`{domain}`" in lowered


@pytest.mark.parametrize(
    "peers",
    [
        [],
        ["Jérôme G"],
        ["Ann {x} Lee"],  # user-controlled free text, rendered through str.format
        [f"Peer {i}" for i in range(200)],
    ],
)
def test_prompt_renders_for_any_directory(peers):
    """`full_name` is free text: no directory content may break the render."""
    rendered = PROMPT.format(
        current_datetime="2026-07-30",
        available_domains="- **peer**: connections",
        available_skills="(none)",
        connected_peers=format_peer_directory(peers),
        memory_facts="None",
        conversation_history="None",
        user_location="Not available",
        window_size=5,
        user_query="Jerome G est-il dispo ?",
    )
    assert "CONNECTED USERS" in rendered
    assert "{connected_peers}" not in rendered


def test_empty_directory_renders_the_sentinel_not_a_hole():
    """An empty section reads as a truncated prompt; "(none)" reads as a fact."""
    assert PEER_DIRECTORY_EMPTY in format_peer_directory([])
