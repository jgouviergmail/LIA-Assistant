"""Tests for format_agent_results_for_prompt (response prompt injection).

Rewritten for the current contract (2026-07 audit, wave 2): the function only
injects STATUS messages (errors, disabled connectors, HITL rejections, action
confirmations, ReAct synthesis). Data-query successes flow to the LLM through
``{data_for_filtering}`` and therefore produce an EMPTY string here.
"""

from src.domains.agents.formatters.agent_results import format_agent_results_for_prompt


class TestFormatAgentResultsForPrompt:
    """Contract tests for the status-only formatter."""

    # ------------------------------------------------------------------
    # Empty / data-success paths produce no prompt injection
    # ------------------------------------------------------------------

    def test_empty_agent_results_returns_empty_string(self):
        """No agent results -> nothing to inject."""
        assert format_agent_results_for_prompt({}) == ""

    def test_data_success_returns_empty_string(self):
        """Data-query successes are injected via {data_for_filtering}, not here."""
        agent_results = {
            "1:contacts_agent": {
                "status": "success",
                "data": {"registry_updates": {"contact_abc": {"id": "abc"}}},
            }
        }

        assert format_agent_results_for_prompt(agent_results, current_turn_id=1) == ""

    # ------------------------------------------------------------------
    # Status messages (errors, disabled, unknown)
    # ------------------------------------------------------------------

    def test_error_status_is_reported(self):
        """Errors must reach the LLM so the reply does not pretend success."""
        agent_results = {
            "1:calendar_agent": {"status": "error", "error": "Calendar API unavailable"}
        }

        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=1)

        assert "❌" in formatted
        assert "calendar_agent" in formatted
        assert "Calendar API unavailable" in formatted

    def test_connector_disabled_status_is_reported(self):
        """Disabled connectors surface as warnings."""
        agent_results = {
            "1:emails_agent": {"status": "connector_disabled", "error": "Gmail non activé"}
        }

        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=1)

        assert "⚠️" in formatted
        assert "Gmail non activé" in formatted

    def test_unknown_status_is_flagged(self):
        """Unknown statuses are flagged rather than silently dropped."""
        agent_results = {"1:mystery_agent": {"status": "half-done"}}

        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=1)

        assert "❓" in formatted
        assert "half-done" in formatted

    # ------------------------------------------------------------------
    # Turn filtering
    # ------------------------------------------------------------------

    def test_turn_id_filtering_excludes_other_turns(self):
        """Only the current turn's statuses are injected."""
        agent_results = {
            "1:old_agent": {"status": "error", "error": "old failure"},
            "2:new_agent": {"status": "error", "error": "new failure"},
        }

        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=2)

        assert "new failure" in formatted
        assert "old failure" not in formatted

    def test_no_turn_filter_includes_all_results(self):
        """Without current_turn_id every status is included."""
        agent_results = {
            "1:old_agent": {"status": "error", "error": "old failure"},
            "2:new_agent": {"status": "error", "error": "new failure"},
        }

        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=None)

        assert "old failure" in formatted
        assert "new failure" in formatted

    def test_key_without_turn_id_is_included(self):
        """Legacy keys without 'turn:' prefix are kept (backward compatibility)."""
        agent_results = {"legacy_agent": {"status": "error", "error": "legacy failure"}}

        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=3)

        assert "legacy failure" in formatted

    def test_invalid_turn_id_in_key_is_kept_defensively(self):
        """A malformed turn prefix logs a warning but does not drop the status."""
        agent_results = {"not_a_number:agent_x": {"status": "error", "error": "still visible"}}

        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=7)

        assert "still visible" in formatted

    # ------------------------------------------------------------------
    # HITL rejection / action confirmations / ReAct synthesis
    # ------------------------------------------------------------------

    def test_user_rejected_action_is_reported(self):
        """HITL rejections must be surfaced so the LLM acknowledges them."""
        agent_results = {
            "1:emails_agent": {
                "status": "success",
                "data": {"user_rejected": True, "message": "Envoi annulé par l'utilisateur"},
            }
        }

        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=1)

        assert "🚫" in formatted
        assert "Envoi annulé par l'utilisateur" in formatted

    def test_action_success_message_is_extracted_from_step_results(self):
        """Action confirmations (no registry data) reach the LLM."""
        agent_results = {
            "1:reminders_agent": {
                "status": "success",
                "data": {
                    "step_results": [{"result": "🔔 Rappel créé pour demain à 10h"}],
                },
            }
        }

        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=1)

        assert "🔔 Rappel créé pour demain à 10h" in formatted

    def test_for_each_action_messages_list_is_flattened(self):
        """FOR_EACH aggregations return list[str] results — all are injected."""
        agent_results = {
            "1:emails_agent": {
                "status": "success",
                "data": {
                    "step_results": [{"result": ["Email 1 envoyé", "Email 2 envoyé"]}],
                },
            }
        }

        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=1)

        assert "Email 1 envoyé" in formatted
        assert "Email 2 envoyé" in formatted

    def test_react_synthesis_is_passed_through_verbatim(self):
        """ADR-070: the ReAct final answer is the authoritative response text."""
        agent_results = {
            "1:react": {
                "data": {"react_synthesis": "Voici la synthèse finale du raisonnement."},
            }
        }

        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=1)

        assert formatted == "Voici la synthèse finale du raisonnement."

    def test_sub_agent_analysis_is_wrapped_in_delivery_tag(self):
        """Sub-agent analyses are wrapped for verbatim restitution."""
        agent_results = {
            "1:sub_agent": {
                "status": "success",
                "data": {
                    "step_results": [
                        {
                            "type": "sub_agent_analysis",
                            "analysis": "Analyse complète de l'expert.",
                            "expertise": "cardiologue",
                            "result": "Analyse complète de...",  # truncated summary
                        }
                    ],
                },
            }
        }

        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=1)

        assert '<SubAgentAnalysis expertise="cardiologue">' in formatted
        assert "Analyse complète de l'expert." in formatted
        # The truncated summary must not be duplicated alongside the full text
        assert formatted.count("Analyse complète de") == 1
