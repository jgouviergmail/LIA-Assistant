"""Unit tests for ReAct synthesis rendering in ``format_agent_results_for_prompt``.

ADR-070 (ReAct execution mode): when a turn is handled by the autonomous ReAct
loop, ``response_node`` injects the agent's final answer into agent_results as
``{"data": {"react_synthesis": <text>}}`` (with ``registry_updates`` for HTML
cards). This entry carries NO ``status`` key.

Before the fix, ``_format_status_messages`` read ``status`` (absent → "unknown")
and emitted ``"❓ react_agent: Statut inconnu (unknown)"`` — silently dropping the
answer. The response LLM then had no authoritative answer to reformulate and
reconstructed one from the raw registry + conversation history, leaking the
agent's internal reasoning structure (PLAN / OBSERVATION / ...) into the reply.

These tests pin the corrected behaviour: the ``react_synthesis`` text is surfaced
verbatim as the authoritative summary, and the misleading "Statut inconnu" message
is never produced for ReAct entries.
"""

from __future__ import annotations

import pytest

from src.domains.agents.formatters.agent_results import format_agent_results_for_prompt

_SYNTHESIS = "Ton frangin Alexandre habite au 36 Boulevard Léon Gambetta, 68100 Mulhouse."


@pytest.mark.unit
class TestReactSynthesisRendering:
    """``format_agent_results_for_prompt`` surfaces ``react_synthesis`` text."""

    def test_react_synthesis_is_surfaced_verbatim(self):
        """The synthesis text is returned as the summary (not "Statut inconnu")."""
        agent_results = {
            "4:react_agent": {
                "data": {"react_synthesis": _SYNTHESIS},
                "registry_updates": {"contact_b55521": object()},
            }
        }

        summary = format_agent_results_for_prompt(agent_results, current_turn_id=4)

        assert summary == _SYNTHESIS
        assert "Statut inconnu" not in summary

    def test_react_synthesis_respects_current_turn_filter(self):
        """Only the current turn's synthesis is surfaced; other turns are skipped."""
        agent_results = {
            "3:react_agent": {"data": {"react_synthesis": "Réponse du tour précédent."}},
            "4:react_agent": {"data": {"react_synthesis": _SYNTHESIS}},
        }

        summary = format_agent_results_for_prompt(agent_results, current_turn_id=4)

        assert summary == _SYNTHESIS
        assert "tour précédent" not in summary

    def test_react_entry_never_yields_statut_inconnu(self):
        """A ReAct entry (no ``status`` key) must not fall through to "Statut inconnu"."""
        agent_results = {"4:react_agent": {"data": {"react_synthesis": _SYNTHESIS}}}

        summary = format_agent_results_for_prompt(agent_results, current_turn_id=4)

        assert "❓" not in summary
        assert "inconnu" not in summary

    def test_empty_react_synthesis_does_not_crash(self):
        """An empty/None synthesis is treated defensively (no synthesis surfaced)."""
        agent_results = {"4:react_agent": {"data": {"react_synthesis": ""}}}

        summary = format_agent_results_for_prompt(agent_results, current_turn_id=4)

        # Empty synthesis is not surfaced; the entry has no status so it does not
        # masquerade as a real answer — the important invariant is no crash and no
        # leaked synthesis text.
        assert summary == "" or "Statut inconnu" in summary
