"""The doors a chat card passes before any proposal is read (ADR-375).

The card is the chat's own surface of the habit proposals: it obeys the same
three switches as the inbox (the deployment and the operator through the
habits capability, the person's « learn my habits »), plus the chat card's own
instance switch. Each closed door is proven to close BEFORE the database is
touched — a card nobody may see costs nothing.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from src.domains.habits import chat_proposal
from src.domains.habits.chat_proposal import chat_keys, claim_chat_proposal
from src.domains.habits.learning_gate import CLOSED, LearningGate
from src.domains.habits.models import ProposalKind

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)


class TestChatKeys:
    def test_a_domain_matches_its_automation_and_its_missing_connector(self) -> None:
        assert chat_keys("email") == (
            (ProposalKind.AUTOMATE_NEED.value, "email"),
            (ProposalKind.CONNECT_SOURCE.value, "email"),
        )
        assert chat_keys("event") == (
            (ProposalKind.AUTOMATE_NEED.value, "event"),
            (ProposalKind.CONNECT_SOURCE.value, "calendar"),
        )

    def test_a_domain_no_connector_serves_matches_its_automation_only(self) -> None:
        assert chat_keys("weather") == ((ProposalKind.AUTOMATE_NEED.value, "weather"),)

    def test_a_turn_with_no_domain_matches_nothing(self) -> None:
        assert chat_keys(None) == ()


def _settings(*, chat_card: bool = True) -> Any:
    return SimpleNamespace(
        recurrence_suggestion_enabled=chat_card,
        habits_proposal_chat_gap_hours=24,
        habits_proposal_chat_repeat_days=7,
    )


@pytest.fixture
def doors(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Open doors by default; a database that must not be reached."""
    state: dict[str, Any] = {"capability": True, "gate": LearningGate(allowed=True), "opened": 0}

    async def capability() -> bool:
        return bool(state["capability"])

    async def gate(_user_id: Any) -> LearningGate:
        return state["gate"]  # type: ignore[no-any-return]

    @asynccontextmanager
    async def no_database() -> AsyncIterator[Any]:
        state["opened"] += 1
        raise AssertionError("a closed door must close before any session opens")
        yield  # pragma: no cover

    monkeypatch.setattr(chat_proposal, "habits_capability_enabled", capability)
    monkeypatch.setattr(chat_proposal, "read_learning_gate", gate)
    monkeypatch.setattr(chat_proposal, "get_db_context", no_database)
    return state


class TestTheDoors:
    async def test_the_chat_cards_instance_switch_closes_it(self, doors: dict[str, Any]) -> None:
        shown = await claim_chat_proposal(
            uuid4(), "weather", settings=_settings(chat_card=False), now=NOW
        )
        assert (shown, doors["opened"]) == (None, 0)

    async def test_the_habits_capability_closes_it(self, doors: dict[str, Any]) -> None:
        doors["capability"] = False
        shown = await claim_chat_proposal(uuid4(), "weather", settings=_settings(), now=NOW)
        assert (shown, doors["opened"]) == (None, 0)

    async def test_the_persons_learning_switch_closes_it(self, doors: dict[str, Any]) -> None:
        doors["gate"] = CLOSED
        shown = await claim_chat_proposal(uuid4(), "weather", settings=_settings(), now=NOW)
        assert (shown, doors["opened"]) == (None, 0)
