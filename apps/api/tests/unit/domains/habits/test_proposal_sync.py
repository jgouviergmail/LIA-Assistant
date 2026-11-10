"""The nightly life of a proposal (ADR-375).

One candidate opens or refreshes its row; a proposal no longer true is
withdrawn — unless its kind could not be judged tonight (held); a dismissed or
accepted one reopens only once its date has passed; a refusal stays a refusal.
The repository's conditional statements are proven on PostgreSQL
(``tests/integration/domains/habits/test_proposals_pg.py``); this double keeps
their semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.domains.habits.models import ProposalKind, ProposalStatus
from src.domains.habits.proposal_rules import ProposalCandidate, ProposalEvaluation
from src.domains.habits.proposal_sync import sync_proposals

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 8, 3, 10, tzinfo=UTC)
USER = uuid4()


@dataclass
class _Row:
    kind: str
    key: str
    payload: dict[str, Any]
    status: str = ProposalStatus.OPEN.value
    resurface_after: datetime | None = None
    id: UUID = field(default_factory=uuid4)


class _Repo:
    def __init__(self, rows: list[_Row] | None = None) -> None:
        self.rows = {row.id: row for row in rows or []}

    async def list_for_user(self, user_id: UUID) -> list[_Row]:
        return list(self.rows.values())

    async def open(self, user_id: UUID, kind: str, key: str, payload: dict[str, Any]) -> bool:
        if any((r.kind, r.key) == (kind, key) for r in self.rows.values()):
            return False
        row = _Row(kind=kind, key=key, payload=payload)
        self.rows[row.id] = row
        return True

    async def refresh_open(self, proposal_id: UUID, payload: dict[str, Any]) -> bool:
        row = self.rows[proposal_id]
        if row.status != ProposalStatus.OPEN.value:
            return False
        row.payload = payload
        return True

    async def reopen(self, proposal_id: UUID, payload: dict[str, Any], *, now: datetime) -> bool:
        row = self.rows[proposal_id]
        if (
            row.status not in ("dismissed", "accepted")
            or row.resurface_after is None
            or row.resurface_after > now
        ):
            return False
        row.status, row.payload, row.resurface_after = ProposalStatus.OPEN.value, payload, None
        return True

    async def withdraw_open(self, proposal_id: UUID) -> bool:
        if self.rows[proposal_id].status != ProposalStatus.OPEN.value:
            return False
        del self.rows[proposal_id]
        return True


def _candidate(
    kind: ProposalKind = ProposalKind.AUTOMATE_NEED, key: str = "event", **payload: Any
) -> ProposalCandidate:
    return ProposalCandidate(kind, key, {"domain": key, **payload})


async def _sync(
    repo: _Repo, *candidates: ProposalCandidate, held: frozenset[ProposalKind] = frozenset()
) -> Any:
    return await sync_proposals(
        repo,  # type: ignore[arg-type]
        USER,
        ProposalEvaluation(candidates=tuple(candidates), held=held),
        now=NOW,
    )


def _count(outcome: Any, kind: str, transition: str) -> int:
    return outcome.transitions.get((kind, transition), 0)


async def test_a_new_candidate_opens_its_proposal() -> None:
    repo = _Repo()
    outcome = await _sync(repo, _candidate(days=12))
    (row,) = repo.rows.values()
    assert (row.kind, row.key, row.payload) == (
        "automate_need",
        "event",
        {"domain": "event", "days": 12},
    )
    assert _count(outcome, "automate_need", "opened") == 1


async def test_an_open_proposal_follows_its_facts() -> None:
    repo = _Repo([_Row("automate_need", "event", {"domain": "event", "days": 12})])
    outcome = await _sync(repo, _candidate(days=14))
    assert next(iter(repo.rows.values())).payload["days"] == 14
    assert _count(outcome, "automate_need", "refreshed") == 1


async def test_unchanged_facts_write_nothing() -> None:
    repo = _Repo([_Row("automate_need", "event", {"domain": "event", "days": 12})])
    outcome = await _sync(repo, _candidate(days=12))
    assert outcome.transitions == {}


async def test_a_proposal_no_longer_true_is_withdrawn() -> None:
    repo = _Repo([_Row("automate_need", "event", {})])
    outcome = await _sync(repo)
    assert repo.rows == {}
    assert _count(outcome, "automate_need", "withdrawn") == 1


async def test_a_held_kind_keeps_what_was_open() -> None:
    """Doubt never withdraws: a kind LIA could not judge tonight stays open."""
    repo = _Repo([_Row("automate_need", "event", {})])
    outcome = await _sync(repo, held=frozenset({ProposalKind.AUTOMATE_NEED}))
    assert len(repo.rows) == 1
    assert _count(outcome, "automate_need", "held") == 1


@pytest.mark.parametrize("status", ["dismissed", "accepted"])
async def test_a_decided_proposal_reopens_once_its_date_has_passed(status: str) -> None:
    due = _Row(
        "automate_need", "event", {}, status=status, resurface_after=NOW - timedelta(minutes=1)
    )
    waiting = _Row(
        "automate_need", "email", {}, status=status, resurface_after=NOW + timedelta(days=1)
    )
    repo = _Repo([due, waiting])
    outcome = await _sync(repo, _candidate(key="event"), _candidate(key="email"))
    assert (due.status, waiting.status) == ("open", status)
    assert _count(outcome, "automate_need", "reopened") == 1


async def test_a_decided_proposal_that_stopped_being_true_is_left_as_decided() -> None:
    row = _Row(
        "automate_need", "event", {}, status="dismissed", resurface_after=NOW + timedelta(days=3)
    )
    repo = _Repo([row])
    await _sync(repo)
    assert row.status == "dismissed" and row.id in repo.rows


async def test_a_refusal_stays_a_refusal() -> None:
    row = _Row("automate_need", "event", {}, status="refused")
    repo = _Repo([row])
    outcome = await _sync(repo, _candidate())
    assert row.status == "refused" and outcome.transitions == {}


async def test_two_kinds_with_one_key_are_two_proposals() -> None:
    repo = _Repo()
    await _sync(
        repo,
        _candidate(ProposalKind.EXTEND_NOTIFICATION_WINDOW, "heartbeat"),
        _candidate(ProposalKind.REVIEW_NOTIFICATIONS, "heartbeat"),
    )
    assert {(r.kind, r.key) for r in repo.rows.values()} == {
        ("extend_notification_window", "heartbeat"),
        ("review_notifications", "heartbeat"),
    }
