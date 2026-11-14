"""The batch door: every document a source queued embeds under its source's lease.

``process_queued`` is the one place a source's documents embed in bulk (full
Drive and Gmail syncs, push windows, history passes). It names its source, so
no caller can embed for minutes while its lease runs out behind it — the
2026-11-09 double sync.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.domains.rag_spaces import drive_ingest
from src.domains.rag_spaces.drive_ingest import process_queued
from src.domains.rag_spaces.jobs_repository import DRIVE_SOURCE_TABLE, MAIL_SOURCE_TABLE
from src.infrastructure.llm.embedding_patience import embeddings_may_wait

pytestmark = pytest.mark.unit


class _Lease:
    """Stands for the keeper: records when the lease is held and for whom."""

    def __init__(self) -> None:
        self.events: list[tuple[Any, ...]] = []

    @asynccontextmanager
    async def kept(self, source_id: uuid.UUID, *, table: str) -> AsyncIterator[None]:
        self.events.append(("held", source_id, table))
        try:
            yield
        finally:
            self.events.append(("released",))


@pytest.fixture
def lease(monkeypatch: pytest.MonkeyPatch) -> _Lease:
    spy = _Lease()
    monkeypatch.setattr(drive_ingest, "source_lease_kept", spy.kept)
    return spy


def _counter() -> MagicMock:
    return MagicMock()


async def test_every_document_embeds_while_the_source_lease_is_held(lease: _Lease) -> None:
    source_id = uuid.uuid4()
    documents = [{"document_id": uuid.uuid4()} for _ in range(3)]

    async def processor(**kwargs: Any) -> bool:
        lease.events.append(("embedded", kwargs["document_id"]))
        return True

    synced, failed = await process_queued(
        documents,
        source_id=source_id,
        source_table=MAIL_SOURCE_TABLE,
        counter=_counter(),
        processor=processor,
    )

    assert (synced, failed) == (3, 0)
    assert lease.events[0] == ("held", source_id, MAIL_SOURCE_TABLE)
    assert lease.events[-1] == ("released",)
    embedded = {event[1] for event in lease.events[1:-1]}
    assert embedded == {doc["document_id"] for doc in documents}


async def test_the_lease_kept_is_the_callers_source_and_table(lease: _Lease) -> None:
    source_id = uuid.uuid4()

    async def processor(**_kwargs: Any) -> bool:
        return True

    await process_queued(
        [{"document_id": uuid.uuid4()}],
        source_id=source_id,
        source_table=DRIVE_SOURCE_TABLE,
        counter=_counter(),
        processor=processor,
    )

    assert lease.events[0] == ("held", source_id, DRIVE_SOURCE_TABLE)


async def test_nothing_queued_holds_no_lease_and_counts_nothing(lease: _Lease) -> None:
    counter = _counter()

    async def processor(**_kwargs: Any) -> bool:
        raise AssertionError("nothing was queued")

    result = await process_queued(
        [],
        source_id=uuid.uuid4(),
        source_table=MAIL_SOURCE_TABLE,
        counter=counter,
        processor=processor,
    )

    assert result == (0, 0)
    assert lease.events == []
    counter.labels.assert_not_called()


async def test_a_document_that_fails_or_raises_is_counted_and_the_lease_is_still_released(
    lease: _Lease,
) -> None:
    documents = [{"document_id": uuid.uuid4()} for _ in range(3)]
    outcomes = iter([True, False, RuntimeError("provider refused")])

    async def processor(**_kwargs: Any) -> bool:
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    counter = _counter()
    synced, failed = await process_queued(
        documents,
        source_id=uuid.uuid4(),
        source_table=MAIL_SOURCE_TABLE,
        counter=counter,
        processor=processor,
    )

    assert (synced, failed) == (1, 2)
    assert lease.events[-1] == ("released",)
    results = [call.kwargs["result"] for call in counter.labels.call_args_list]
    assert sorted(results) == ["failed", "failed", "synced"]


async def test_the_batch_may_wait_for_the_embedding_provider_and_nothing_after_it_may(
    lease: _Lease,
) -> None:
    """A source's queue is bulk work: it serves the delay a quota refusal names
    instead of failing its documents one second later (2026-11-09: 253 of them).
    The declaration ends with the batch — the caller goes on to other work."""
    patience: list[bool] = []

    async def processor(**_kwargs: Any) -> bool:
        patience.append(embeddings_may_wait())
        return True

    assert embeddings_may_wait() is False
    await process_queued(
        [{"document_id": uuid.uuid4()} for _ in range(3)],
        source_id=uuid.uuid4(),
        source_table=MAIL_SOURCE_TABLE,
        counter=_counter(),
        processor=processor,
    )

    assert patience == [True, True, True]
    assert embeddings_may_wait() is False
