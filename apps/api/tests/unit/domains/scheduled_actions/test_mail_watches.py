"""« Tell me when Marie replies » should not wait two hours (ADR-281, lot 5).

A CONDITION routine is evaluated at its own cron tick, capped at twelve a day
(ADR-268) — so a watch on an awaited e-mail answers up to two hours late, while
the push wake sweep already holds the fresh Gmail delta, to the minute, and does
nothing with it. ``TriggerKind`` calls the real event-driven path « a documented
phase 2 »; this is it.

Four rules the design turns on, each pinned below:

- **the wake does not RUN the routine.** It pulls ``next_trigger_at`` forward
  and stops; the executor, the only thing that knows how to run one, takes it
  at its next tick. A second runner would be a second authority on what runs
  for somebody's account.
- **no second deduplication.** The executor's fingerprint already decides
  whether a fact is new, so arming twice costs nothing and a second ledger
  here would be the drift ADR-255 names.
- **a trigger is pulled FORWARD, never resurrected.** ``next_trigger_at`` NULL
  means the series is over (the model says so); arming it would restart
  something that ended.
- **the arming clears the read it depends on.** The executor re-evaluates
  through ``fetch_mails``, whose Gmail search is cached for
  ``emails_cache_search_ttl_seconds``; a cache filled before the mail arrived
  would answer « not met », and that verdict CONSUMES the arming — the routine
  moves to its next cron slot and the wake is lost. Arming past the published
  TTL makes the evaluation live by construction.

The wake's own pre-filter has NO say here: it answers « is this worth waking
the heartbeat », a watch answers « is this the thing I am waiting for ». A mail
the pre-filter calls unimportant is exactly what a watch may be for.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.scheduled_actions.mail_watches import arm_mail_watches, mail_matches
from src.domains.scheduled_actions.models import ScheduledActionStatus, TriggerKind

pytestmark = pytest.mark.unit

_MODULE = "src.domains.scheduled_actions.mail_watches"

# Anchored on the REAL clock: the module reads its own, so a frozen literal
# would pass until the day it names and then redden for ever.
_FAR_AHEAD = timedelta(hours=6)


def _message(
    *,
    subject: str = "Re: devis",
    sender: str = "Marie <marie@x.fr>",
) -> dict[str, Any]:
    """A Gmail ``format=metadata`` resource, the shape the pre-filter reads."""
    return {
        "id": "m-1",
        "labelIds": ["INBOX", "UNREAD"],
        "payload": {
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": sender},
            ]
        },
    }


def _watch(query: str = "Marie", **overrides: Any) -> Any:
    fields: dict[str, Any] = {
        "id": uuid4(),
        "title": "Watch",
        "trigger_kind": TriggerKind.CONDITION.value,
        "status": ScheduledActionStatus.ACTIVE.value,
        "condition_config": {"type": "mail_match", "query": query},
        "next_trigger_at": datetime.now(UTC) + _FAR_AHEAD,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _db_ctx(watches: list[Any]) -> tuple[Any, Any]:
    """A session whose one statement answers ``watches``."""
    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = watches
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    @asynccontextmanager
    async def _ctx() -> Any:
        yield session

    return _ctx, session


class TestTheMatchingPredicate:
    """One reading of « does this mail match what they await »."""

    def test_a_subject_match(self) -> None:
        assert mail_matches(_message(subject="Re: le devis"), "devis") is True

    def test_a_sender_match(self) -> None:
        assert mail_matches(_message(sender="Marie Dupont <m@x.fr>"), "Dupont") is True

    def test_an_address_match(self) -> None:
        assert mail_matches(_message(sender="M <marie@acme.fr>"), "acme.fr") is True

    def test_case_and_accents_of_the_query_do_not_matter(self) -> None:
        assert mail_matches(_message(subject="Le DEVIS"), "devis") is True

    def test_something_else_entirely(self) -> None:
        assert mail_matches(_message(subject="Newsletter"), "devis") is False

    def test_an_empty_query_matches_nothing(self) -> None:
        """A needle matching everything would fire on every mail that arrives."""
        assert mail_matches(_message(), "") is False
        assert mail_matches(_message(), "   ") is False

    def test_a_message_with_no_headers(self) -> None:
        assert mail_matches({"id": "m-1"}, "devis") is False

    def test_the_body_is_never_read(self) -> None:
        """Metadata format carries no body; a match there would be invented."""
        message = _message(subject="Newsletter")
        message["snippet"] = "le devis est joint"
        assert mail_matches(message, "devis") is False


class TestArmingAWatch:
    async def test_a_matching_delta_arms_the_watch(self) -> None:
        watch = _watch("devis")
        before = watch.next_trigger_at
        ctx, session = _db_ctx([watch])

        with patch(f"{_MODULE}.get_db_context", new=ctx):
            armed = await arm_mail_watches(uuid4(), [_message(subject="Re: devis")])

        assert armed == 1
        assert watch.next_trigger_at < before
        session.commit.assert_awaited()

    async def test_it_arms_past_the_published_search_cache(self) -> None:
        """A cache filled before the mail would answer « not met » and eat it."""
        watch = _watch("devis")
        ctx, _ = _db_ctx([watch])

        with patch(f"{_MODULE}.get_db_context", new=ctx):
            await arm_mail_watches(uuid4(), [_message(subject="Re: devis")])

        waited = watch.next_trigger_at - datetime.now(UTC)
        assert waited >= timedelta(seconds=settings.emails_cache_search_ttl_seconds - 5)

    async def test_a_delta_that_matches_nothing_arms_nothing(self) -> None:
        watch = _watch("devis")
        before = watch.next_trigger_at
        ctx, _ = _db_ctx([watch])

        with patch(f"{_MODULE}.get_db_context", new=ctx):
            armed = await arm_mail_watches(uuid4(), [_message(subject="Newsletter")])

        assert armed == 0
        assert watch.next_trigger_at == before

    async def test_one_matching_mail_in_a_batch_is_enough(self) -> None:
        watch = _watch("devis")
        ctx, _ = _db_ctx([watch])

        with patch(f"{_MODULE}.get_db_context", new=ctx):
            armed = await arm_mail_watches(
                uuid4(),
                [_message(subject="Newsletter"), _message(subject="Re: devis")],
            )

        assert armed == 1

    async def test_an_empty_delta_costs_no_query_at_all(self) -> None:
        ctx, session = _db_ctx([])

        with patch(f"{_MODULE}.get_db_context", new=ctx):
            armed = await arm_mail_watches(uuid4(), [])

        assert armed == 0
        session.execute.assert_not_awaited()

    async def test_an_account_with_no_watch_commits_nothing_of_its_own(self) -> None:
        """`get_db_context` commits on exit anyway, so the claim is narrow:
        this module issues no commit of its own when it armed nothing."""
        ctx, session = _db_ctx([])

        with patch(f"{_MODULE}.get_db_context", new=ctx):
            assert await arm_mail_watches(uuid4(), [_message()]) == 0

        session.commit.assert_not_awaited()


class TestWhatIsNeverArmed:
    async def test_an_exhausted_series_is_never_resurrected(self) -> None:
        """NULL means nothing follows — the model says so."""
        watch = _watch("devis", next_trigger_at=None)
        ctx, _ = _db_ctx([watch])

        with patch(f"{_MODULE}.get_db_context", new=ctx):
            armed = await arm_mail_watches(uuid4(), [_message(subject="Re: devis")])

        assert armed == 0
        assert watch.next_trigger_at is None

    async def test_a_watch_already_due_is_left_alone(self) -> None:
        """The executor takes it at its next tick; pulling it says nothing new."""
        already = datetime.now(UTC) - timedelta(minutes=5)
        watch = _watch("devis", next_trigger_at=already)
        ctx, _ = _db_ctx([watch])

        with patch(f"{_MODULE}.get_db_context", new=ctx):
            armed = await arm_mail_watches(uuid4(), [_message(subject="Re: devis")])

        assert armed == 0
        assert watch.next_trigger_at == already

    async def test_a_trigger_sooner_than_the_arming_is_left_alone(self) -> None:
        """Arming may only ever bring a run FORWARD, never push it back."""
        soon = datetime.now(UTC) + timedelta(seconds=5)
        watch = _watch("devis", next_trigger_at=soon)
        ctx, _ = _db_ctx([watch])

        with patch(f"{_MODULE}.get_db_context", new=ctx):
            armed = await arm_mail_watches(uuid4(), [_message(subject="Re: devis")])

        assert armed == 0
        assert watch.next_trigger_at == soon

    async def test_it_never_runs_the_routine_itself(self) -> None:
        """It moves the trigger and stops: the executor owns running."""
        watch = _watch("devis")
        ctx, _ = _db_ctx([watch])

        with patch(f"{_MODULE}.get_db_context", new=ctx):
            await arm_mail_watches(uuid4(), [_message(subject="Re: devis")])

        assert watch.status == ScheduledActionStatus.ACTIVE.value
        assert not hasattr(watch, "last_executed_at")
        assert not hasattr(watch, "condition_state")


class TestTheStatementItReads:
    """The query NARROWS; the decider above is what actually arms."""

    async def test_it_asks_only_for_this_account(self) -> None:
        ctx, session = _db_ctx([])

        with patch(f"{_MODULE}.get_db_context", new=ctx):
            user_id = uuid4()
            await arm_mail_watches(user_id, [_message()])

        statement = session.execute.await_args.args[0]
        # Asserting on the compiled SQL is a trap: `select(Model)` names every
        # column, so any word appears. The WHERE clause is the real oracle.
        rendered = str(statement.whereclause)
        assert "user_id" in rendered
        assert "is_enabled" in rendered
        assert "trigger_kind" in rendered
        # A finished series carries a NULL trigger, which is also how a watch
        # past its `SeriesEnd` date is excluded — no second column to read.
        assert "next_trigger_at" in rendered

    async def test_it_never_reads_more_than_an_account_can_hold(self) -> None:
        from src.core.constants import SCHEDULED_ACTIONS_MAX_PER_USER

        ctx, session = _db_ctx([])

        with patch(f"{_MODULE}.get_db_context", new=ctx):
            await arm_mail_watches(uuid4(), [_message()])

        statement = session.execute.await_args.args[0]
        assert statement._limit == SCHEDULED_ACTIONS_MAX_PER_USER


class TestItNeverCostsTheWake:
    async def test_a_database_failure_is_swallowed(self) -> None:
        @asynccontextmanager
        async def _broken() -> Any:
            raise RuntimeError("database gone")
            yield  # pragma: no cover

        with patch(f"{_MODULE}.get_db_context", new=_broken):
            assert await arm_mail_watches(uuid4(), [_message()]) == 0

    async def test_a_malformed_condition_is_stepped_over(self) -> None:
        """One unreadable row must not cost the others their arming."""
        broken = _watch(condition_config=None)
        good = _watch("devis")
        ctx, _ = _db_ctx([broken, good])

        with patch(f"{_MODULE}.get_db_context", new=ctx):
            armed = await arm_mail_watches(uuid4(), [_message(subject="Re: devis")])

        assert armed == 1

    async def test_a_condition_with_no_query_is_stepped_over(self) -> None:
        ctx, _ = _db_ctx([_watch(query="")])

        with patch(f"{_MODULE}.get_db_context", new=ctx):
            assert await arm_mail_watches(uuid4(), [_message()]) == 0

    async def test_it_steps_over_a_row_the_executor_is_holding(self) -> None:
        """A claimed row will have its trigger rewritten when the run ends.

        Arming it would be a write nobody ever reads. SKIP rather than wait:
        a wake answers an event and must not queue behind a transaction.
        """
        ctx, session = _db_ctx([])

        with patch(f"{_MODULE}.get_db_context", new=ctx):
            await arm_mail_watches(uuid4(), [_message()])

        statement = session.execute.await_args.args[0]
        assert statement._for_update_arg is not None
        assert statement._for_update_arg.skip_locked is True
