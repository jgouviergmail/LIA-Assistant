"""The e-mail contract says the same thing on its three surfaces (ADR-287).

Measured on Docker dev, 2026-09-15, the same request answered from two folders:
in ReAct « recherche mes 5 derniers emails reçus » listed the inbox
(``in:inbox``), in the pipeline it listed everything but sent and drafts
(``-in:sent -in:draft``) — because the manifest mapped "received" to the latter
while the agent prompt made ``in:anywhere`` the default. And « fais un résumé
des 6 derniers emails de TLDR AI » fetched twenty messages under ``summary``,
fourteen paid model calls for messages nobody asked about. The manifest (read
by the planner and the ReAct model), the planner prompt and the agent prompt
now carry ONE scope rule and ONE count rule; this test keeps them from
drifting apart again.
"""

from __future__ import annotations

import pytest

from src.domains.agents.emails.get_emails_manifest import get_emails_catalogue_manifest
from src.domains.agents.prompts.prompt_loader import load_prompt

pytestmark = [pytest.mark.unit]


@pytest.fixture(scope="module")
def surfaces() -> dict[str, str]:
    return {
        "manifest": get_emails_catalogue_manifest.description,
        "planner": load_prompt("smart_planner_prompt"),
        "agent": load_prompt("emails_agent_prompt"),
    }


class TestOneScopeRule:
    @pytest.mark.parametrize("surface", ["manifest", "planner", "agent"])
    def test_recent_mail_is_the_inbox_on_every_surface(
        self, surfaces: dict[str, str], surface: str
    ) -> None:
        assert "in:inbox" in surfaces[surface], surface

    @pytest.mark.parametrize("surface", ["manifest", "planner", "agent"])
    def test_a_specific_message_may_be_archived(
        self, surfaces: dict[str, str], surface: str
    ) -> None:
        assert "in:anywhere" in surfaces[surface], surface

    def test_the_contradicted_rules_are_gone(self, surfaces: dict[str, str]) -> None:
        assert (
            "-in:sent -in:draft" not in surfaces["manifest"]
        ), "received is the inbox, not 'not sent'"
        assert "Always include `in:anywhere`" not in surfaces["agent"], "anywhere is for a needle"


class TestOneCountRule:
    @pytest.mark.parametrize("surface", ["manifest", "planner", "agent"])
    def test_max_results_is_the_number_asked(self, surfaces: dict[str, str], surface: str) -> None:
        text = surfaces[surface]
        assert "max_results" in text and "last 6 emails" in text, surface
        assert "paid model call" in text, f"{surface}: the cost of summary is stated"

    def test_the_manifest_parameter_says_it_too(self) -> None:
        """The planner reads parameter descriptions before the prose."""
        param = next(p for p in get_emails_catalogue_manifest.parameters if p.name == "max_results")
        assert "asked for" in param.description and "paid model call" in param.description
