"""A reply's guard is lifted only when its extraction fully succeeded (ADR-359).

A person's reply to an opening keeps a transient restriction until memory
extraction has handled it. The receipts are the safe side by construction: they
lift the guard only for a complete store, and a receipt that fails never raises —
the guard stays, which only delays the next opening. Measured 2026-10-23: neither
the unit nor the integration suite executed these decisions (AC-030b); the guard
store itself (``replies.acknowledge_reply``) is the integration suite's.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from structlog.testing import capture_logs

from src.domains.proactive_discussions import reply_receipts

pytestmark = pytest.mark.unit

OWNER = uuid4()


class _Guards:
    """The guard store, in memory: which replies were acknowledged, in which session."""

    def __init__(self) -> None:
        self.acknowledged: list[tuple[UUID, str]] = []
        self.sessions = 0
        self.failure: Exception | None = None

    @asynccontextmanager
    async def session(self) -> AsyncIterator[object]:
        self.sessions += 1
        yield object()

    async def acknowledge(self, db: object, owner: UUID, run_id: str, *, now: datetime) -> None:
        assert now.tzinfo is not None
        if self.failure is not None:
            raise self.failure
        self.acknowledged.append((owner, run_id))


@pytest.fixture
def guards(monkeypatch: pytest.MonkeyPatch) -> _Guards:
    store = _Guards()
    monkeypatch.setattr(reply_receipts, "get_db_context", store.session)
    monkeypatch.setattr(reply_receipts, "acknowledge_reply", store.acknowledge)
    return store


async def test_a_processed_reply_lifts_its_own_guard(guards: _Guards) -> None:
    await reply_receipts.acknowledge_extracted_reply(str(OWNER), "run-1")

    assert guards.acknowledged == [(OWNER, "run-1")]


@pytest.mark.parametrize(
    ("owner", "run_id"),
    [(None, "run-1"), ("", "run-1"), (str(OWNER), None), (str(OWNER), "")],
    # Stable ids: OWNER is drawn at import, so its value would name the case
    # differently in every xdist worker, which then refuses the collection.
    ids=["no-owner", "empty-owner", "no-run", "empty-run"],
)
async def test_without_an_owner_and_a_run_nothing_is_opened(
    guards: _Guards, owner: str | None, run_id: str | None
) -> None:
    await reply_receipts.acknowledge_extracted_reply(owner, run_id)

    assert guards.acknowledged == [] and guards.sessions == 0


@pytest.mark.parametrize(
    "failure", [RuntimeError("guard store unavailable"), ValueError("not an account")]
)
async def test_a_failing_receipt_never_raises_and_keeps_the_guard(
    guards: _Guards, failure: Exception
) -> None:
    guards.failure = failure

    with capture_logs() as logs:
        await reply_receipts.acknowledge_extracted_reply(str(OWNER), "run-1")

    assert guards.acknowledged == []
    assert [entry["error_type"] for entry in logs] == [type(failure).__name__]


async def test_an_owner_that_is_no_account_id_keeps_the_guard(guards: _Guards) -> None:
    with capture_logs() as logs:
        await reply_receipts.acknowledge_extracted_reply("not-an-account", "run-1")

    assert guards.acknowledged == []
    assert [entry["event"] for entry in logs] == ["discussion_reply_receipt_failed"]


@pytest.mark.parametrize(("result", "acknowledged"), [("  []\n", True), ('[{"a": 1}]', False)])
async def test_an_extraction_that_learned_nothing_is_processed_all_the_same(
    guards: _Guards, result: str, acknowledged: bool
) -> None:
    await reply_receipts.acknowledge_empty_reply(str(OWNER), "run-1", result)

    assert guards.acknowledged == ([(OWNER, "run-1")] if acknowledged else [])


@pytest.mark.parametrize(
    ("parsed", "entries", "acknowledged"),
    [
        (2, [{"stored": True}, {"stored": True}], True),
        (1, [{"kind": "fact"}], True),
        (0, [], True),
        (2, [{"stored": True}], False),
        (2, [{"stored": True}, {"stored": False}], False),
    ],
)
async def test_only_a_complete_store_lifts_the_guard(
    guards: _Guards, parsed: int, entries: list[dict[str, object]], acknowledged: bool
) -> None:
    await reply_receipts.acknowledge_completed_reply(str(OWNER), "run-1", parsed, entries)

    assert guards.acknowledged == ([(OWNER, "run-1")] if acknowledged else [])
