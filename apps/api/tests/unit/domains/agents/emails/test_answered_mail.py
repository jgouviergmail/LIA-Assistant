"""The mails of a turn the person already answered, stated apart from the data (ADR-379).

Measured 2026-11-11: to an open question, the response model wrote its opening from the
requests it read in the mails' own words — « two mails ask for a reply » — although one of
the two carried ``reply_state: answered`` in its record; a block of its own, computed from
the turn's items, brought that from 17 wrong openings of 24 to 2. These tests hold what the
block is made of: the turn's answered mails, by their item id and the instant of the
answer, and nothing a correspondent wrote.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from src.core.mail_reply_state import REPLY_STATE_KEY, ReplyMessage, ReplyState, ReplyStatus
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
)
from src.domains.agents.emails.answered_mail import answered_mail_lines

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)
ANSWERED_AT = datetime(2026, 11, 10, 13, 40, tzinfo=UTC)


def _state(status: ReplyStatus) -> dict[str, Any]:
    settled = status in {"answered", "answer_drafted", "reply_received"}
    return ReplyState(
        status=status,
        message=(
            ReplyMessage(
                message_id="reply-1",
                at=ANSWERED_AT,
                correspondents="Marc Dupont",
                excerpt="Agreed, you can start the works.",
            )
            if settled
            else None
        ),
        observed_at=NOW,
        valid_until=NOW + timedelta(minutes=2),
    ).model_dump(mode="json")


def _mail(item_id: str, status: ReplyStatus | None) -> RegistryItem:
    payload: dict[str, Any] = {
        "id": item_id.removeprefix("email_"),
        "subject": "Quote for the roof: your agreement?",
        "from": "Marc Dupont <marc@example.org>",
        "snippet": "Could you confirm before Friday?",
    }
    if status is not None:
        payload[REPLY_STATE_KEY] = _state(status)
    return RegistryItem(
        id=item_id,
        type=RegistryItemType.EMAIL,
        payload=payload,
        meta=RegistryItemMeta(source="google_gmail", domain="email"),
    )


def _event(item_id: str) -> RegistryItem:
    return RegistryItem(
        id=item_id,
        type=RegistryItemType.EVENT,
        payload={"id": "e1", "summary": "Roof works"},
        meta=RegistryItemMeta(source="google_calendar", domain="event"),
    )


def test_it_names_each_answered_mail_by_its_item_and_the_instant_of_the_answer() -> None:
    registry = {
        "email_a": _mail("email_a", "answered"),
        "email_b": _mail("email_b", "unanswered"),
        "event_c": _event("event_c"),
        "email_d": _mail("email_d", "answered"),
    }

    assert answered_mail_lines(registry) == (
        "- [email_a] answered on 2026-11-10T13:40+00:00\n"
        "- [email_d] answered on 2026-11-10T13:40+00:00"
    )


@pytest.mark.parametrize(
    "status", ["answer_drafted", "unanswered", "reply_received", "awaiting_reply", None]
)
def test_a_mail_that_was_not_answered_is_not_named(status: ReplyStatus | None) -> None:
    assert answered_mail_lines({"email_a": _mail("email_a", status)}) == ""


@pytest.mark.parametrize("registry", [None, {}])
def test_a_turn_that_listed_nothing_says_nothing(registry: dict[str, Any] | None) -> None:
    assert answered_mail_lines(registry) == ""


def test_an_item_restored_from_a_checkpoint_reads_the_same() -> None:
    """The state survives a checkpoint as plain dicts: both shapes are one item."""
    item = _mail("email_a", "answered")

    assert answered_mail_lines({"email_a": item.model_dump(mode="json")}) == answered_mail_lines(
        {"email_a": item}
    )


def test_it_carries_nothing_a_correspondent_wrote() -> None:
    """The block is stated outside the data, where nothing marks a stranger's text as
    external: a subject, a name or a first line there would speak with the system's voice."""
    lines = answered_mail_lines({"email_a": _mail("email_a", "answered")})

    for written in ("Quote for the roof", "Marc Dupont", "Agreed, you can start", "Friday"):
        assert written not in lines
