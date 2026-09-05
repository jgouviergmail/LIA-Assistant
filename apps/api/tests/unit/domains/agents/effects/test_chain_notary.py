"""The notary's decisions, apart from its SQL (ADR-263, lot 5).

What the database proves lives in ``tests/integration/.../test_chain_notary_db.py``.
What lives here is everything that is a DECISION rather than a query: that a
verification resumes correctly across pages, that a pass counts only what it
committed, that the job is inert while the flag is off, and that a failing pass
is logged rather than raised into the scheduler.

The split matters: a decision proven only against PostgreSQL is a decision
nobody can re-read.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError

from src.domains.agents.effects.chain_link import ChainBreak, ChainLink, link_hash, walk

pytestmark = [pytest.mark.unit]

_WHEN = datetime(2026, 9, 4, 19, 0, tzinfo=UTC)


def _link(seq: int, previous: str | None, *, kind: str = "treatment.recorded") -> ChainLink:
    digest = f"{seq:064d}"
    subject = uuid.uuid5(uuid.NAMESPACE_OID, str(seq))
    return ChainLink(
        seq=seq,
        kind=kind,
        subject_id=subject,
        payload_digest=digest,
        prev_hash=previous,
        entry_hash=link_hash(
            seq=seq,
            kind=kind,
            subject_id=subject,
            payload_digest=digest,
            prev_hash=previous,
        ),
        digest_version=1,
        occurred_at=_WHEN,
    )


def _chain(length: int) -> list[ChainLink]:
    links: list[ChainLink] = []
    previous: str | None = None
    for seq in range(1, length + 1):
        links.append(_link(seq, previous))
        previous = links[-1].entry_hash
    return links


class TestAWalkResumesAcrossPages:
    """A chain has no upper length, so verification reads it in pages.

    Every property below is about the SEAM between two pages — the one place
    a paginated verifier can silently accept a chain it never checked.
    """

    def test_two_pages_verify_exactly_like_one(self) -> None:
        links = _chain(10)

        whole = walk(links)
        first = walk(links[:4])
        second = walk(links[4:], start_seq=5, previous=first.head_hash)

        assert whole.ok and first.ok and second.ok
        assert second.head_hash == whole.head_hash
        assert first.entries_checked + second.entries_checked == whole.entries_checked

    def test_a_page_that_does_not_follow_the_previous_one_is_REFUSED(self) -> None:
        """Otherwise a whole page could be swapped out between two reads."""
        links = _chain(10)

        verdict = walk(links[4:], start_seq=5, previous="f" * 64)

        assert not verdict.ok
        assert verdict.reason is ChainBreak.PREV_HASH
        assert verdict.broken_at_seq == 5

    def test_a_page_starting_at_the_wrong_position_is_REFUSED(self) -> None:
        first = walk(_chain(10)[:4])

        verdict = walk(_chain(10)[4:], start_seq=9, previous=first.head_hash)

        assert not verdict.ok
        assert verdict.reason is ChainBreak.SEQUENCE

    def test_an_empty_last_page_carries_the_head_forward(self) -> None:
        """The loop ends on an empty page: it must not lose the head there."""
        first = walk(_chain(3))

        verdict = walk([], start_seq=4, previous=first.head_hash)

        assert verdict.ok
        assert verdict.head_hash == first.head_hash


class TestAPassCountsOnlyWhatItCommitted:
    async def test_a_rolled_back_account_increments_no_entry_counter(self) -> None:
        """A metric incremented inside the transaction would count links that
        never existed — and this counter is read as evidence."""
        from src.domains.agents.effects import notary as module

        db = AsyncMock()
        with (
            patch.object(
                module.ChainRepository,
                "accounts_with_pending",
                AsyncMock(return_value=[uuid.uuid4()]),
            ),
            patch.object(
                module,
                "notarise_account",
                AsyncMock(side_effect=OperationalError("boom", None, Exception("boom"))),
            ),
            patch.object(module, "ledger_chain_entries_total") as entries,
            patch.object(module, "ledger_chain_pass_failures_total") as failures,
        ):
            report = await module.run_notary_pass(db)

        assert report.failed == 1
        assert report.entries == 0
        entries.labels.assert_not_called()
        failures.inc.assert_called_once()
        db.rollback.assert_awaited_once()

    async def test_a_committed_account_counts_one_link_per_KIND(self) -> None:
        from src.domains.agents.effects import notary as module

        db = AsyncMock()
        done = module.AccountPass(
            entries=3,
            opened=True,
            kinds=("chain.genesis", "effect.claimed", "effect.settled"),
        )
        with (
            patch.object(
                module.ChainRepository,
                "accounts_with_pending",
                AsyncMock(return_value=[uuid.uuid4()]),
            ),
            patch.object(module, "notarise_account", AsyncMock(return_value=done)),
            patch.object(module, "ledger_chain_entries_total") as entries,
        ):
            report = await module.run_notary_pass(db)

        assert (report.accounts, report.entries, report.chains_opened) == (1, 3, 1)
        assert [call.kwargs["kind"] for call in entries.labels.call_args_list] == list(done.kinds)

    @pytest.mark.parametrize(
        "failure",
        [
            OperationalError("boom", None, Exception("boom")),
            # NOT a SQL error: the canonical encoding refuses a column type
            # nobody classified. Catching only SQLAlchemyError would abort the
            # whole pass and every account queued behind it, every tick, for as
            # long as that one row exists.
            TypeError("chain_digest cannot encode <class 'decimal.Decimal'>"),
        ],
        ids=["sql", "not-sql"],
    )
    async def test_ANY_failure_costs_one_account_and_no_other(self, failure: Exception) -> None:
        from src.domains.agents.effects import notary as module

        db = AsyncMock()
        healthy = module.AccountPass(entries=1, opened=False, kinds=("treatment.recorded",))
        doomed, spared = uuid.uuid4(), uuid.uuid4()

        async def _one_bad(_db: object, user_id: uuid.UUID, **_: object) -> object:
            if user_id == doomed:
                raise failure
            return healthy

        with (
            patch.object(
                module.ChainRepository,
                "accounts_with_pending",
                AsyncMock(return_value=[doomed, spared]),
            ),
            patch.object(module, "notarise_account", _one_bad),
        ):
            report = await module.run_notary_pass(db)

        assert report.failed == 1
        assert report.accounts == 1, "the healthy account was not served"
        assert report.entries == 1

    async def test_an_account_with_nothing_pending_is_not_counted_as_served(self) -> None:
        from src.domains.agents.effects import notary as module

        db = AsyncMock()
        empty = module.AccountPass(entries=0, opened=False, kinds=())
        with (
            patch.object(
                module.ChainRepository,
                "accounts_with_pending",
                AsyncMock(return_value=[uuid.uuid4()]),
            ),
            patch.object(module, "notarise_account", AsyncMock(return_value=empty)),
        ):
            report = await module.run_notary_pass(db)

        assert report == module.NotaryReport()


class TestADeletedEntryIsNoticedForFree:
    async def test_a_gap_between_the_head_and_the_count_is_counted_and_logged(self) -> None:
        """The only tampering detection that runs continuously."""
        from src.domains.agents.effects import notary as module

        repository = AsyncMock()
        repository.entry_count = AsyncMock(return_value=41)
        with patch.object(module, "ledger_chain_breaks_total") as breaks:
            await module._check_contiguity(repository, uuid.uuid4(), head_seq=42)

        breaks.labels.assert_called_once_with(reason=ChainBreak.SEQUENCE.value)

    async def test_a_contiguous_chain_raises_nothing(self) -> None:
        from src.domains.agents.effects import notary as module

        repository = AsyncMock()
        repository.entry_count = AsyncMock(return_value=42)
        with patch.object(module, "ledger_chain_breaks_total") as breaks:
            await module._check_contiguity(repository, uuid.uuid4(), head_seq=42)

        breaks.labels.assert_not_called()


class TestTheJobIsInertUntilItIsTurnedOn:
    async def test_the_body_re_checks_the_flag(self) -> None:
        """A schedule left behind by a config change must do nothing."""
        from src.infrastructure.startup import scheduler_ledger as module

        with (
            patch.object(module.settings, "ledger_chain_enabled", False),
            patch("src.domains.agents.effects.notary.run_notary_pass", AsyncMock()) as pass_,
        ):
            await module.run_ledger_notary()

        pass_.assert_not_called()

    def test_nothing_is_registered_while_the_flag_is_off(self) -> None:
        from src.infrastructure.startup import scheduler_ledger as module

        # MagicMock, not AsyncMock: ``add_job`` is synchronous, and an async
        # double would hand production code a coroutine nobody awaits (F028).
        scheduler = MagicMock()
        with patch.object(module.settings, "ledger_chain_enabled", False):
            module.register_ledger_jobs(scheduler)

        scheduler.add_job.assert_not_called()

    def test_the_job_carries_jitter_and_a_single_instance(self) -> None:
        """Six jobs sharing a divisor fire on the same second forever (ADR-254),
        and a second notary behind a slow one would only lose races."""
        from src.core.constants import SCHEDULER_JOB_LEDGER_NOTARY
        from src.infrastructure.startup import scheduler_ledger as module

        scheduler = MagicMock()
        with patch.object(module.settings, "ledger_chain_enabled", True):
            module.register_ledger_jobs(scheduler)

        kwargs: dict[str, Any] = scheduler.add_job.call_args.kwargs
        assert kwargs["id"] == SCHEDULER_JOB_LEDGER_NOTARY
        assert kwargs["jitter"] > 0
        assert kwargs["max_instances"] == 1
        assert kwargs["replace_existing"] is True
        assert kwargs["next_run_time"] is not None, "an interval-only job would starve"

    async def test_a_failing_pass_is_logged_and_never_raised(self) -> None:
        """A scheduler job that raises takes the tick down with it."""
        from src.infrastructure.startup import scheduler_ledger as module

        with (
            patch.object(module.settings, "ledger_chain_enabled", True),
            patch(
                "src.infrastructure.database.session.get_db_context",
                side_effect=RuntimeError("no database"),
            ),
        ):
            await module.run_ledger_notary()
