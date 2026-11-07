"""The text ADR-323 moved out of Python renders as the model will read it.

The rejected plan's notice used to be French prose inside a ``.py`` file; it is a
versioned prompt now (``response_plan_rejection_notice``). A placeholder no producer
fills, or a value re-read as a template, would reach the model silently — so it is
rendered here, whole.
"""

from __future__ import annotations

import pytest

from src.domains.agents.nodes.response_node import _format_rejection_details

pytestmark = pytest.mark.unit


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
