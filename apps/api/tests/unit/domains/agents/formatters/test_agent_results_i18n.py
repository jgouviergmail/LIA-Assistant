"""The HITL user-rejection summary must be localized, never hardcoded French.

``format_agent_results_for_prompt`` builds the status summaries fed to the
response node. When a HITL action is rejected and the result carries no explicit
message, the fallback used to be a hardcoded French sentence — leaking French
into a non-FR user's flow. It now resolves via ``HitlMessages`` in the user's
language.
"""

from __future__ import annotations

import pytest

from src.core.i18n_hitl import HitlMessages
from src.domains.agents.formatters.agent_results import format_agent_results_for_prompt

pytestmark = [pytest.mark.unit]


def test_get_user_refused_action_is_localized() -> None:
    assert HitlMessages.get_user_refused_action("de") == "Der Benutzer hat diese Aktion abgelehnt."
    assert "用户" in HitlMessages.get_user_refused_action("zh")  # frontend spelling → zh-CN


def test_rejection_fallback_localized_de() -> None:
    results = {"3:reminder_agent": {"status": "success", "data": {"user_rejected": True}}}
    out = format_agent_results_for_prompt(results, current_turn_id=3, user_language="de")
    assert "Der Benutzer hat diese Aktion abgelehnt" in out
    assert "L'utilisateur" not in out


def test_rejection_explicit_message_preserved() -> None:
    """An explicit (already-localized) message is preserved, not overridden."""
    results = {
        "3:reminder_agent": {
            "status": "success",
            "data": {
                "user_rejected": True,
                "message": "Kein Problem, was möchtest du stattdessen?",
            },
        }
    }
    out = format_agent_results_for_prompt(results, current_turn_id=3, user_language="de")
    assert "Kein Problem" in out
