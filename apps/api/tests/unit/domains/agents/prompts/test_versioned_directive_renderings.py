"""The two texts ADR-323 moved out of Python render as the model will read them.

The five domain agents' context block and the rejected plan's notice used to be
French prose inside ``.py`` files; they are versioned prompts now
(``agent_context_domain_instructions``, ``response_plan_rejection_notice``).
A placeholder no producer fills, or a value re-read as a template, would reach
the model silently — so each is rendered here, whole.
"""

from __future__ import annotations

import pytest

from src.domains.agents.graphs.base_agent_builder import domain_context_instructions
from src.domains.agents.nodes.response_node import _format_rejection_details

pytestmark = pytest.mark.unit

#: The registry domains the five domain agents store their results under.
AGENT_DOMAINS = ("events", "contacts", "files", "emails", "tasks")


@pytest.mark.parametrize("domain", AGENT_DOMAINS)
def test_the_context_block_names_its_domain_everywhere(domain: str) -> None:
    block = domain_context_instructions(domain)

    assert block.startswith("## Multi-domain context")
    assert f'domain="{domain}"' in block
    assert f"$context.{domain}.0" in block
    assert f"$context.{domain}.current" in block
    # Every placeholder was filled: the text carries no brace of its own.
    assert "{" not in block and "}" not in block


def test_the_rejection_notice_relays_the_reason_its_writer_set() -> None:
    # The one reason the state's writer sets: the person cancelled the clarification.
    reason = "User cancelled during clarification"
    notice = _format_rejection_details(reason)

    assert notice.startswith("🚫 PLAN REJECTED BY THE USER")
    assert f"**Reason for the rejection:** {reason}" in notice
    assert "{reason}" not in notice


def test_a_reason_is_a_value_never_a_template() -> None:
    """A reason carrying braces reaches the model verbatim."""
    reason = "over budget {max} for {user}"

    directive = _format_rejection_details(reason)

    assert reason in directive
