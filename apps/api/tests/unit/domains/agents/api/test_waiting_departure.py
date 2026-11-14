"""How a departure decides, with its persistence substituted (ADR-384).

The SQL, Redis and producer contracts are proven on real services in
``tests/integration/domains/conversations/test_waiting_departure.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from src.core.conversation_execution import (
    ExecutionKind,
    ExecutionPhase,
    RunAdmission,
    RunBusy,
    RunEnd,
)
from src.core.conversation_target import ConversationKind, ConversationRef
from src.domains.agents.api import waiting_departure
from src.domains.agents.api.waiting_departure import Candidate, Departure

pytestmark = pytest.mark.unit

OWNER = uuid4()


def _candidate(text: str = "and the bakery", version: int = 1) -> Candidate:
    return Candidate(uuid4(), version, uuid4(), 0, text, None)


def _target(candidate: Candidate) -> ConversationRef:
    return ConversationRef(OWNER, candidate.conversation_id, ConversationKind.MAIN, 0, uuid4())


def _admission(target: ConversationRef) -> RunAdmission:
    return RunAdmission(
        uuid4(), target, ExecutionKind.GRAPH, "run", "stream", uuid4(), uuid4(), 1, True, True
    )


class Harness:
    """Records what a departure did with its substituted collaborators."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.claims: list[bool] = []
        self.started: list[tuple[RunAdmission, Candidate]] = []
        self.released: list[RunAdmission] = []
        self.announced: list[bool] = []
        self.reserved = 0
        self.pending: set[UUID] = set()
        self.busy = False
        self.user: Any = SimpleNamespace(id=OWNER, is_active=True)
        repository = MagicMock()
        repository.claim = AsyncMock(side_effect=self._claim)
        db = MagicMock()
        db.get = AsyncMock(side_effect=lambda *_: self.user)

        @asynccontextmanager
        async def session() -> AsyncIterator[Any]:
            yield db

        async def resolve(_owner: UUID, candidate: Candidate) -> tuple[ConversationRef, Any] | None:
            if not self.user.is_active:
                return None
            return _target(candidate), self.user

        async def pending(runtime_id: str) -> str | None:
            return "question" if UUID(runtime_id) in self.pending else None

        async def reserve(target: ConversationRef, **_: object) -> RunAdmission | RunBusy:
            self.reserved += 1
            if self.busy:
                return RunBusy(target, ExecutionKind.GRAPH, ExecutionPhase.RUNNING, "r", "s")
            return _admission(target)

        async def release(admission: RunAdmission, *, announce: bool = True) -> None:
            self.released.append(admission)
            self.announced.append(announce)

        monkeypatch.setattr(waiting_departure, "get_db_context", session)
        monkeypatch.setattr(waiting_departure, "WaitingMessageRepository", lambda _db: repository)
        monkeypatch.setattr(waiting_departure, "_resolve", resolve)
        monkeypatch.setattr(waiting_departure, "pending_run_id", pending)
        monkeypatch.setattr(waiting_departure, "reserve_execution", reserve)
        monkeypatch.setattr(waiting_departure, "release_unstarted_execution", release)
        monkeypatch.setattr(
            waiting_departure,
            "_start_turn",
            lambda admission, _user, candidate: self.started.append((admission, candidate)),
        )

    async def _claim(self, *_args: object, **_kwargs: object) -> bool:
        return self.claims.pop(0) if self.claims else True


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> Harness:
    return Harness(monkeypatch)


async def test_a_claimed_message_starts_the_persons_turn(harness: Harness) -> None:
    candidate = _candidate()
    assert (await waiting_departure.depart(OWNER, candidate)).outcome is Departure.SENT
    [(admission, started)] = harness.started
    assert started == candidate and admission.relayed and admission.cancellable
    assert harness.released == []


async def test_a_busy_account_stops_the_departure_without_claiming(harness: Harness) -> None:
    harness.busy = True
    assert (await waiting_departure.depart(OWNER, _candidate())).outcome is Departure.BUSY
    assert harness.started == [] and harness.released == []


async def test_an_edit_that_won_the_claim_releases_the_slot(harness: Harness) -> None:
    harness.claims = [False]
    assert (await waiting_departure.depart(OWNER, _candidate())).outcome is Departure.CLAIM_LOST
    assert harness.started == [] and len(harness.released) == 1


async def test_an_inactive_account_sends_nothing_and_reserves_nothing(harness: Harness) -> None:
    harness.user = SimpleNamespace(id=OWNER, is_active=False)
    assert (await waiting_departure.depart(OWNER, _candidate())).outcome is Departure.SKIPPED
    assert harness.started == [] and harness.reserved == 0 and harness.released == []


async def test_a_refused_attempt_releases_the_slot_without_a_second_departure(
    harness: Harness,
) -> None:
    harness.claims = [False]
    await waiting_departure.depart(OWNER, _candidate())
    assert harness.announced == [False]


async def test_a_question_seen_after_the_reservation_releases_it(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = iter([None, "question"])

    async def pending(_runtime_id: str) -> str | None:
        return next(answers)

    monkeypatch.setattr(waiting_departure, "pending_run_id", pending)
    assert (await waiting_departure.depart(OWNER, _candidate())).outcome is Departure.SKIPPED
    assert harness.started == [] and len(harness.released) == 1


async def test_a_failed_start_gives_the_slot_back(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_args: object) -> None:
        raise RuntimeError("the producer could not be built")

    monkeypatch.setattr(waiting_departure, "_start_turn", broken)
    with pytest.raises(RuntimeError):
        await waiting_departure.depart(OWNER, _candidate())
    assert len(harness.released) == 1


async def test_the_queue_skips_a_discussion_with_a_question_and_sends_the_next(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked, next_one = _candidate("asked"), _candidate("next")
    monkeypatch.setattr(waiting_departure, "_candidates", AsyncMock(return_value=[asked, next_one]))
    original = waiting_departure._resolve

    async def resolve(owner: UUID, candidate: Candidate) -> tuple[ConversationRef, Any] | None:
        resolved = await original(owner, candidate)
        if resolved is not None and candidate is asked:
            harness.pending.add(resolved[0].runtime_id)
        return resolved

    monkeypatch.setattr(waiting_departure, "_resolve", resolve)
    await waiting_departure.depart_after_release(OWNER, RunEnd.NORMAL)
    assert [candidate.content for _, candidate in harness.started] == ["next"]


async def test_a_lost_claim_reads_the_queue_again_in_its_order(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    edited = _candidate("first", version=1)
    reread = Candidate(edited.id, 2, edited.conversation_id, 0, "first, edited", None)
    reads = AsyncMock(side_effect=[[edited, _candidate("second")], [reread]])
    monkeypatch.setattr(waiting_departure, "_candidates", reads)
    harness.claims = [False]
    await waiting_departure.depart_after_release(OWNER, RunEnd.NORMAL)
    assert [candidate.content for _, candidate in harness.started] == ["first, edited"]


async def test_lost_claims_stop_after_the_declared_rounds(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    reads = AsyncMock(return_value=[_candidate()])
    monkeypatch.setattr(waiting_departure, "_candidates", reads)
    harness.claims = [False] * 10
    await waiting_departure.depart_after_release(OWNER, RunEnd.NORMAL)
    assert reads.await_count == waiting_departure.WAITING_DEPARTURE_ROUNDS
    assert harness.started == []


async def test_a_busy_account_ends_the_queue_until_its_next_release(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    reads = AsyncMock(return_value=[_candidate("a"), _candidate("b")])
    monkeypatch.setattr(waiting_departure, "_candidates", reads)
    harness.busy = True
    await waiting_departure.depart_after_release(OWNER, RunEnd.NORMAL)
    assert reads.await_count == 1 and harness.started == []


def test_the_departure_is_the_installed_release_listener() -> None:
    from src.infrastructure.streaming import release_listener

    assert release_listener._listener is waiting_departure.depart_after_release
