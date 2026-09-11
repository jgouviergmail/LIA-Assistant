"""The wake and the executor must agree on what a watch is waiting for.

A `mail_match` watch is read TWICE, by design and unavoidably:

- the push wake sweep reads the raw Gmail delta it already holds
  (``mail_watches.mail_matches``, over ``payload.headers``), to decide whether
  to bring the routine's run forward;
- the executor re-reads through the briefing projection
  (``_eval_mail_match``, over ``subject`` / ``sender_name`` / ``sender_email``),
  to decide whether to notify.

The shapes are different and neither can serve the other: the wake holds a
Gmail resource with no display projection, and the executor holds a projection
with no headers. Two readings of one question is exactly the drift this
codebase names everywhere — so it is pinned rather than hoped for.

This guard is the oracle: for the same logical mail and the same query, both
answers are the same. If someone widens one reading (the body, the snippet, a
fuzzy match) this file reddens, and the other reading must follow or the
divergence must be written down.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from src.domains.scheduled_actions.mail_watches import mail_matches

pytestmark = pytest.mark.unit

_EVALUATORS = "src.infrastructure.scheduler.condition_evaluators"

#: One logical mail, described the way each side actually receives it.
#: ``(label, subject, sender_name, sender_email, query)``
CASES: list[tuple[str, str, str, str, str]] = [
    ("subject match", "Re: le devis", "Marie", "marie@acme.fr", "devis"),
    ("sender name match", "Bonjour", "Marie Dupont", "m@acme.fr", "Dupont"),
    ("address match", "Bonjour", "Marie", "marie@acme.fr", "acme.fr"),
    ("full address match", "Bonjour", "Marie", "marie@acme.fr", "marie@acme.fr"),
    ("case is ignored", "LE DEVIS", "Marie", "m@acme.fr", "devis"),
    ("no match at all", "Newsletter", "Publicité", "news@vendor.com", "devis"),
    ("a word of the query only", "Re: le devis signé", "Marie", "m@acme.fr", "devis signé"),
    ("the query is longer than the subject", "Devis", "Marie", "m@acme.fr", "devis annuel"),
    ("punctuation inside the subject", "[URGENT] devis", "Marie", "m@acme.fr", "urgent"),
    ("an accent in the query", "Réunion annulée", "Marie", "m@acme.fr", "annulée"),
    ("a digit in the query", "Facture 2026-114", "Compta", "c@acme.fr", "2026-114"),
]


def _gmail(subject: str, name: str, email: str) -> dict[str, Any]:
    """What the wake holds: a ``format=metadata`` resource."""
    return {
        "id": "m-1",
        "labelIds": ["INBOX", "UNREAD"],
        "payload": {
            "headers": [
                {"name": "Subject", "value": subject},
                # Gmail's own From shape carries the name AND the address.
                {"name": "From", "value": f"{name} <{email}>"},
            ]
        },
    }


def _briefing(subject: str, name: str, email: str) -> Any:
    """What the executor holds: the briefing's display projection."""
    return SimpleNamespace(subject=subject, sender_name=name, sender_email=email)


async def _executor_says(subject: str, name: str, email: str, query: str) -> bool:
    """Run the REAL evaluator over the real projection."""
    from src.infrastructure.scheduler.condition_evaluators import _eval_mail_match

    data = SimpleNamespace(items=[_briefing(subject, name, email)])
    user = SimpleNamespace(language="fr")
    with (
        patch(f"{_EVALUATORS}.resolve_user_timezone", return_value=ZoneInfo("UTC")),
        patch("src.domains.briefing.fetchers.fetch_mails", AsyncMock(return_value=data)),
    ):
        verdict = await _eval_mail_match(user, {"type": "mail_match", "query": query})
    return verdict.met


@pytest.mark.parametrize(
    ("label", "subject", "name", "email", "query"),
    CASES,
    ids=[case[0] for case in CASES],
)
async def test_both_readings_agree(
    label: str, subject: str, name: str, email: str, query: str
) -> None:
    """One question, one answer, whichever side asks it."""
    wake = mail_matches(_gmail(subject, name, email), query)
    executor = await _executor_says(subject, name, email, query)

    assert wake == executor, (
        f"{label}: the wake says {wake} and the executor says {executor} — "
        "a watch would be armed and then refused, or missed and then fired"
    )


class TestTheCorpusIsWorthSomething:
    """A guard whose cases all answer the same thing proves nothing."""

    async def test_it_covers_both_verdicts(self) -> None:
        verdicts = {mail_matches(_gmail(s, n, e), q) for _, s, n, e, q in CASES}

        assert verdicts == {True, False}


class TestWhereTheyCannotAgree:
    """The one divergence, stated rather than discovered."""

    async def test_the_executor_only_ever_sees_unread_inbox_mail(self) -> None:
        """The briefing reads ``is:unread in:inbox``; the delta reads arrivals.

        A mail read between the wake and the executor's tick therefore leaves
        the executor's view entirely, and the armed watch settles as « not
        met ». That is the right outcome — the person has seen it — but it is a
        DIFFERENCE in the data, not in the predicate, which is why it is
        recorded here and not repaired in either reading.
        """
        message = _gmail("Re: le devis", "Marie", "m@acme.fr")

        assert mail_matches(message, "devis") is True
        # The executor, handed an empty inbox projection, says no.
        assert await _executor_says_nothing_is_unread("devis") is False


async def _executor_says_nothing_is_unread(query: str) -> bool:
    from src.infrastructure.scheduler.condition_evaluators import _eval_mail_match

    with (
        patch(f"{_EVALUATORS}.resolve_user_timezone", return_value=ZoneInfo("UTC")),
        patch(
            "src.domains.briefing.fetchers.fetch_mails",
            AsyncMock(return_value=SimpleNamespace(items=[])),
        ),
    ):
        verdict = await _eval_mail_match(
            SimpleNamespace(language="fr"), {"type": "mail_match", "query": query}
        )
    return verdict.met
