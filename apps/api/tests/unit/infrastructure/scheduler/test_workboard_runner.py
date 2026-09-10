"""The sweep that lets LIA run a ticket alone (ADR-276, lot 2).

Two families of assertion, because the module has two kinds of decision:

- **the settle branch table**, which is PURE (:func:`plan_settle`) and is
  therefore enumerated rather than sampled. It is the whole feature's honesty:
  what a run says happened must be what happened.
- **the gates around the claim**, which are I/O and are checked on the SHAPE
  they leave behind — a refusal must RELEASE the claim (never settle it as a
  failure), and a permanent refusal must settle it (never leave it to be
  offered again every minute).

The claim's own race, the settle's conditional write and the retention DELETE
are proved on a real server in
``tests/integration/domains/workboard/test_run_lifecycle_db.py``: they are
properties of PostgreSQL, and a mock would only repeat what this code asked
for.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.constants import WORKBOARD_RUN_ERROR_MAX_CHARS
from src.domains.workboard.constants import RunError, RunOutcome, TicketStatus
from src.domains.workboard.notifications import WorkboardEvent
from src.infrastructure.scheduler import workboard_runner
from src.infrastructure.scheduler.out_of_turn_run import RunOutcome as StreamOutcome
from src.infrastructure.scheduler.out_of_turn_run import RunResult, TurnInterrupt
from src.infrastructure.scheduler.workboard_runner import plan_settle, sweep_workboard_runs

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
MODULE = "src.infrastructure.scheduler.workboard_runner"


class TestWhatAFinishedRunWrites:
    """Every branch of the settle, from what the turn actually produced."""

    def test_an_answer_moves_the_ticket_to_validation(self) -> None:
        plan = plan_settle(
            RunResult(outcome=StreamOutcome.SUCCESS, text="The venue is booked."),
            language="fr",
            timezone="Europe/Paris",
        )

        assert plan.status == TicketStatus.VALIDATING.value
        assert plan.outcome == RunOutcome.SUCCESS.value
        assert plan.comment == "The venue is booked."
        assert plan.error is None

    def test_an_answer_with_no_text_is_not_an_answer(self) -> None:
        """A run that streamed nothing would otherwise file an empty comment
        and tell the person something was done (ADR-275's doctrine)."""
        plan = plan_settle(
            RunResult(outcome=StreamOutcome.SUCCESS, text="   "),
            language="fr",
            timezone="Europe/Paris",
        )

        assert plan.status == TicketStatus.IN_PROGRESS.value
        assert plan.outcome == RunOutcome.FAILED.value
        assert plan.comment is None
        assert plan.error == RunError.EMPTY_ANSWER.value

    def test_a_refused_capability_stops_the_ticket_and_names_it(self) -> None:
        plan = plan_settle(
            RunResult(
                outcome=StreamOutcome.WAITING,
                text="",
                refusals=[("send_email_tool", "confirmation_impossible_unattended")],
            ),
            language="fr",
            timezone="Europe/Paris",
        )

        assert plan.status == TicketStatus.WAITING.value
        assert plan.outcome == RunOutcome.WAITING.value
        assert plan.comment is not None
        assert "send email" in plan.comment, "the capability is named as a person reads it"
        assert plan.error is None

    def test_a_stop_with_nothing_to_name_still_says_so(self) -> None:
        """The D5 safety net: a clarification interrupt carries no refusal, and
        a comment saying « something » beats no comment at all."""
        plan = plan_settle(
            RunResult(outcome=StreamOutcome.WAITING), language="fr", timezone="Europe/Paris"
        )

        assert plan.status == TicketStatus.WAITING.value
        assert plan.comment
        assert "{" not in plan.comment, "no placeholder may reach a person"

    def test_the_work_done_before_stopping_is_kept(self) -> None:
        """The person reads ONE comment about this run: dropping the work to
        keep the question would hide what was already done."""
        plan = plan_settle(
            RunResult(
                outcome=StreamOutcome.WAITING,
                text="I found three rooms.",
                refusals=[("send_email_tool", "confirmation_impossible_unattended")],
            ),
            language="fr",
            timezone="Europe/Paris",
        )

        assert plan.comment is not None
        assert plan.comment.startswith("I found three rooms.")
        assert "send email" in plan.comment

    def test_a_stopped_run_speaks_the_holders_language(self) -> None:
        french = plan_settle(
            RunResult(outcome=StreamOutcome.WAITING), language="fr", timezone="Europe/Paris"
        )
        chinese = plan_settle(
            RunResult(outcome=StreamOutcome.WAITING), language="zh-CN", timezone="Europe/Paris"
        )

        assert french.comment != chinese.comment

    def test_a_failure_leaves_the_ticket_where_it_was_and_says_why(self) -> None:
        """No comment: a failure is not something LIA has to say on a ticket,
        and the code is what the board renders."""
        plan = plan_settle(
            RunResult(outcome=StreamOutcome.FAILED, error="TimeoutError: 600s"),
            language="fr",
            timezone="Europe/Paris",
        )

        assert plan.status == TicketStatus.IN_PROGRESS.value
        assert plan.outcome == RunOutcome.FAILED.value
        assert plan.comment is None
        assert plan.error is not None
        assert plan.error.startswith(RunError.RUN_FAILED.value)
        assert "TimeoutError: 600s" in plan.error

    def test_a_failure_with_no_message_still_carries_its_code(self) -> None:
        plan = plan_settle(
            RunResult(outcome=StreamOutcome.FAILED), language="fr", timezone="Europe/Paris"
        )

        assert plan.error == RunError.RUN_FAILED.value

    def test_the_stored_message_is_bounded(self) -> None:
        """`last_run_error` is read by a person on a card; a provider that
        returns a page of HTML must not become a page of HTML in the database."""
        plan = plan_settle(
            RunResult(outcome=StreamOutcome.FAILED, error="x" * 5000),
            language="fr",
            timezone="Europe/Paris",
        )

        assert plan.error is not None
        assert len(plan.error) == WORKBOARD_RUN_ERROR_MAX_CHARS


def _usage() -> Any:
    """What a run spent, in the five figures the chat already shows."""
    from src.domains.workboard.repository import RunUsage

    return RunUsage(
        tokens_in=1200,
        tokens_out=340,
        tokens_cache=512,
        google_requests=2,
        cost_eur=Decimal("0.0042"),
    )


def _repository(ticket: Any | None) -> Any:
    """A repository whose scan offers ``ticket`` and whose claim takes it."""
    repository = MagicMock()
    repository.db = AsyncMock()
    repository.reap_stale_claims = AsyncMock(return_value=0)
    repository.purge_hidden_rows = AsyncMock(return_value=0)
    repository.claimable_stmt = MagicMock(return_value="<stmt>")
    repository.claim_ticket = AsyncMock(return_value=ticket)
    repository.settle_run = AsyncMock(return_value=True)
    repository.release_claim = AsyncMock(return_value=True)
    repository.add_comment = AsyncMock()
    repository.add_event = AsyncMock()
    repository.run_usage = AsyncMock(return_value=_usage())
    repository.hidden_volume = AsyncMock(return_value=(4, 9600))
    repository.db.execute = AsyncMock(
        return_value=MagicMock(scalars=lambda: MagicMock(first=lambda: ticket))
    )
    return repository


def _ticket() -> Any:
    ticket = MagicMock()
    ticket.id = uuid.uuid4()
    ticket.owner_user_id = uuid.uuid4()
    ticket.effective_assignee_id = ticket.owner_user_id
    ticket.title = "Book the venue"
    ticket.description = "Twelve people, the 20th."
    ticket.parent_id = None
    ticket.pending_action = None
    ticket.execution_mode = "react"
    return ticket


def _context() -> Any:
    return MagicMock(
        language="fr", timezone="Europe/Paris", display_name="Jean", display_mode="cards"
    )


@asynccontextmanager
async def _session(db: Any) -> Any:
    yield db


class _Env:
    """Every collaborator of one tick, patched and observable."""

    def __init__(self, repository: Any) -> None:
        self.repository = repository
        self.stream = AsyncMock(return_value=RunResult(outcome=StreamOutcome.SUCCESS, text="Done."))
        self.blocked = AsyncMock(return_value=False)
        self.pending = AsyncMock(return_value=(False, uuid.uuid4()))
        self.context = AsyncMock(return_value=_context())
        self.lease_acquired = True
        # The dispatch itself is tested on its own; here it only has to be
        # OBSERVED, so a tick never opens Redis or a notification channel.
        self.notify = AsyncMock()

    @asynccontextmanager
    async def _lease(self, *args: Any, **kwargs: Any) -> Any:
        yield self.lease_acquired


@asynccontextmanager
async def _running(env: _Env) -> Any:
    """Run one tick with every boundary replaced."""
    db = AsyncMock()
    # The scan runs on the SESSION, not on the repository: the statement is the
    # repository's, the execution is the caller's.
    db.execute = env.repository.db.execute
    with (
        patch(f"{MODULE}.get_db_context", lambda: _session(db)),
        patch(f"{MODULE}.WorkboardRepository", return_value=env.repository),
        patch(f"{MODULE}.resolve_run_context", env.context),
        patch(f"{MODULE}.conversation_has_pending_hitl", env.pending),
        patch(f"{MODULE}.build_ticket_brief", AsyncMock(return_value="Do the thing.")),
        patch(f"{MODULE}.stream_instruction", env.stream),
        patch(f"{MODULE}.active_run_lease", env._lease),
        patch(
            "src.domains.usage_limits.service.UsageLimitService.is_user_blocked_for_llm",
            env.blocked,
        ),
        patch("src.infrastructure.cache.redis.get_redis_cache", AsyncMock()),
        patch(f"{MODULE}._clear_pending_question", AsyncMock()),
        patch(f"{MODULE}._notify", env.notify),
    ):
        yield env


class TestTheTick:
    async def test_housekeeping_runs_even_when_nothing_is_claimable(self) -> None:
        """The reaper and the retention are not a reward for having work."""
        env = _Env(_repository(None))
        async with _running(env):
            await sweep_workboard_runs()

        env.repository.reap_stale_claims.assert_awaited_once()
        env.repository.purge_hidden_rows.assert_awaited_once()
        env.stream.assert_not_awaited()

    async def test_a_ticket_nobody_else_took_is_run_and_settled(self) -> None:
        env = _Env(_repository(_ticket()))
        async with _running(env):
            await sweep_workboard_runs()

        env.stream.assert_awaited_once()
        env.repository.settle_run.assert_awaited_once()
        settle = env.repository.settle_run.await_args.kwargs
        assert settle["status"] == TicketStatus.VALIDATING.value
        assert settle["outcome"] == RunOutcome.SUCCESS.value
        assert settle["usage"].tokens_in == 1200
        assert settle["usage"].cost_eur == Decimal("0.0042")
        env.repository.add_comment.assert_awaited_once()
        assert env.repository.add_comment.await_args.kwargs["body"] == "Done."

    async def test_the_run_and_the_ticket_share_one_id(self) -> None:
        """The registers, the token logs, the hidden rows and the ticket must
        all name the SAME run, or the cost aggregate finds nothing."""
        env = _Env(_repository(_ticket()))
        async with _running(env):
            await sweep_workboard_runs()

        claimed_id = env.repository.claim_ticket.await_args.kwargs["run_id"]
        request = env.stream.await_args.args[0]
        assert request.run_id == claimed_id
        assert request.origin is not None
        assert request.origin.run_id == claimed_id
        assert env.repository.run_usage.await_args.args[0] == claimed_id

    async def test_the_turn_is_stamped_as_a_workboard_run(self) -> None:
        """Without the origin the two archived rows would be visible in the
        chat, and the gate would refuse nothing."""
        env = _Env(_repository(_ticket()))
        async with _running(env):
            await sweep_workboard_runs()

        origin = env.stream.await_args.args[0].origin
        assert origin.kind == "workboard"
        assert origin.ticket_id

    async def test_a_started_and_a_finished_event_frame_the_run(self) -> None:
        """And a THIRD says the ticket came back.

        The default run here delivers a result, so it lands in « en validation »
        and the ball is the person's: the ticket is handed back in the same
        statement that settles it, and the history has to say so — otherwise a
        reader sees a ticket that changed hands with nothing explaining it.
        """
        env = _Env(_repository(_ticket()))
        async with _running(env):
            await sweep_workboard_runs()

        calls = env.repository.add_event.await_args_list
        kinds = [call.kwargs["kind"] for call in calls]
        assert kinds == ["run_started", "run_finished", "assigned"]
        assert calls[-1].kwargs["payload"]["reason"] == "handed_back"

    async def test_a_run_that_stops_on_a_question_hands_the_ticket_back(self) -> None:
        """A question nobody holds is a question nobody answers."""
        env = _Env(_repository(_ticket()))
        async with _running(env):
            await sweep_workboard_runs()

        assert env.repository.settle_run.await_args is not None
        assert env.repository.settle_run.await_args.kwargs["hand_back"] is True

    async def test_a_lost_claim_stops_the_tick(self) -> None:
        """The scan offered it, another worker took it: nothing to undo, and
        nothing to run."""
        repository = _repository(_ticket())
        repository.claim_ticket = AsyncMock(return_value=None)
        env = _Env(repository)
        async with _running(env):
            await sweep_workboard_runs()

        env.stream.assert_not_awaited()
        repository.settle_run.assert_not_awaited()
        repository.release_claim.assert_not_awaited()


class TestTheGates:
    async def test_an_inactive_account_settles_and_never_retries(self) -> None:
        """Permanent: offering the ticket again every minute would burn its
        whole lifetime budget on an account that is gone."""
        env = _Env(_repository(_ticket()))
        env.context = AsyncMock(return_value=None)
        async with _running(env):
            await sweep_workboard_runs()

        env.stream.assert_not_awaited()
        env.repository.release_claim.assert_not_awaited()
        settle = env.repository.settle_run.await_args.kwargs
        assert settle["outcome"] == RunOutcome.FAILED.value
        assert settle["error"] == RunError.ASSIGNEE_INACTIVE.value
        assert settle["status"] == TicketStatus.IN_PROGRESS.value

    async def test_a_quota_ceiling_releases_with_a_back_off(self) -> None:
        """A quota refusal is not a generation failure (ADR-272): the ticket
        goes back to `todo`, keeps its run, and waits."""
        env = _Env(_repository(_ticket()))
        env.blocked = AsyncMock(return_value=True)
        async with _running(env):
            await sweep_workboard_runs()

        env.stream.assert_not_awaited()
        env.repository.settle_run.assert_not_awaited()
        release = env.repository.release_claim.await_args.kwargs
        assert release["outcome"] == RunOutcome.SKIPPED_QUOTA.value
        assert release["retry_after"] is not None

    async def test_the_quota_question_is_asked_for_the_holder(self) -> None:
        ticket = _ticket()
        holder = uuid.uuid4()
        ticket.effective_assignee_id = holder
        env = _Env(_repository(ticket))
        env.blocked = AsyncMock(return_value=True)
        async with _running(env):
            await sweep_workboard_runs()

        assert env.blocked.await_args.args[0] == holder
        assert env.blocked.await_args.kwargs["layer"] == "workboard_runner"

    async def test_a_pending_question_on_the_thread_releases_without_a_back_off(self) -> None:
        """Busy now, free in a minute: a back-off would be a punishment."""
        env = _Env(_repository(_ticket()))
        env.pending = AsyncMock(return_value=(True, uuid.uuid4()))
        async with _running(env):
            await sweep_workboard_runs()

        env.stream.assert_not_awaited()
        release = env.repository.release_claim.await_args.kwargs
        assert release["outcome"] == RunOutcome.SKIPPED_BUSY.value
        assert release["retry_after"] is None

    async def test_a_live_conversation_keeps_its_thread(self) -> None:
        """The person typing owns the conversation; the ticket can wait."""
        env = _Env(_repository(_ticket()))
        env.lease_acquired = False
        async with _running(env):
            await sweep_workboard_runs()

        env.stream.assert_not_awaited()
        env.repository.settle_run.assert_not_awaited()
        assert (
            env.repository.release_claim.await_args.kwargs["outcome"]
            == RunOutcome.SKIPPED_BUSY.value
        )

    async def test_an_unresolvable_conversation_still_runs(self) -> None:
        """The probe FAILS OPEN by contract: « I could not ask » must not
        become « I will not run » for the whole board."""
        env = _Env(_repository(_ticket()))
        env.pending = AsyncMock(return_value=(False, None))
        async with _running(env):
            await sweep_workboard_runs()

        env.stream.assert_awaited_once()
        env.repository.settle_run.assert_awaited_once()


class TestTheSettleIsConditional:
    async def test_a_lost_settle_writes_no_comment(self) -> None:
        """A person who moved the ticket mid-run wins: a comment about work on
        a column they closed would be the settle sneaking back in."""
        repository = _repository(_ticket())
        repository.settle_run = AsyncMock(return_value=False)
        env = _Env(repository)
        async with _running(env):
            await sweep_workboard_runs()

        repository.add_comment.assert_not_awaited()
        kinds = [call.kwargs["kind"] for call in repository.add_event.await_args_list]
        assert kinds == ["run_started"], "no run_finished on a settle nobody accepted"

    async def test_a_crash_around_the_turn_settles_rather_than_stranding(self) -> None:
        """Everything inside the turn is settled by the engine; reaching here
        means the plumbing broke, and the reaper is ten minutes away."""
        env = _Env(_repository(_ticket()))
        env.stream = AsyncMock(side_effect=RuntimeError("redis is gone"))
        async with _running(env):
            await sweep_workboard_runs()

        settle = env.repository.settle_run.await_args.kwargs
        assert settle["outcome"] == RunOutcome.FAILED.value
        assert "redis is gone" in settle["error"]

    async def test_the_comment_is_cut_to_the_column_bound(self) -> None:
        env = _Env(_repository(_ticket()))
        env.stream = AsyncMock(
            return_value=RunResult(outcome=StreamOutcome.SUCCESS, text="x" * 99_999)
        )
        async with _running(env):
            await sweep_workboard_runs()

        from src.core.config import settings

        body = env.repository.add_comment.await_args.kwargs["body"]
        assert len(body) == settings.workboard_comment_max_chars


class TestAStoppedRunClearsItsQuestion:
    async def test_the_pending_interrupt_is_dropped_on_a_waiting_settle(self) -> None:
        """Left behind, the person's next ordinary chat message would be read
        as the answer to a question they never saw."""
        env = _Env(_repository(_ticket()))
        env.stream = AsyncMock(return_value=RunResult(outcome=StreamOutcome.WAITING))
        cleared = AsyncMock()
        async with _running(env):
            with patch(f"{MODULE}._clear_pending_question", cleared):
                await sweep_workboard_runs()

        cleared.assert_awaited_once()

    async def test_a_successful_run_leaves_the_thread_alone(self) -> None:
        env = _Env(_repository(_ticket()))
        cleared = AsyncMock()
        async with _running(env):
            with patch(f"{MODULE}._clear_pending_question", cleared):
                await sweep_workboard_runs()

        cleared.assert_not_awaited()


class TestItNeverRaises:
    async def test_a_housekeeping_failure_does_not_stop_the_run(self) -> None:
        repository = _repository(_ticket())
        repository.reap_stale_claims = AsyncMock(side_effect=RuntimeError("no database"))
        env = _Env(repository)
        async with _running(env):
            await sweep_workboard_runs()

        env.stream.assert_awaited_once()

    async def test_a_claim_failure_ends_the_tick_quietly(self) -> None:
        repository = _repository(_ticket())
        repository.claim_ticket = AsyncMock(side_effect=RuntimeError("no database"))
        env = _Env(repository)
        async with _running(env):
            await sweep_workboard_runs()

        env.stream.assert_not_awaited()

    async def test_a_settle_that_cannot_be_written_does_not_raise(self) -> None:
        """« Never raises » must hold for the LAST phase too.

        The claim was committed and the turn has run; a database that goes away
        between the two leaves the tick with nothing to do but say so. Left to
        propagate, the operator reads a stack trace from the scheduler for a
        state the reaper already covers — and the tick that raises never
        reaches the notification either.
        """
        repository = _repository(_ticket())
        repository.settle_run = AsyncMock(side_effect=RuntimeError("no database"))
        env = _Env(repository)
        async with _running(env):
            await sweep_workboard_runs()

        env.stream.assert_awaited_once()
        # « LIA a commencé » went out when the run really started; nothing else
        # can be said, because nothing was written.
        events = [call.args[2] for call in env.notify.await_args_list]
        assert events == [WorkboardEvent.RUN_STARTED]

    async def test_a_notification_phase_that_breaks_does_not_raise(self) -> None:
        """The ticket already carries the answer: the durable half is written,
        and a channel that is down must not turn a settled run into a crash."""
        env = _Env(_repository(_ticket()))
        env.notify = AsyncMock(side_effect=RuntimeError("no channel"))
        async with _running(env):
            await sweep_workboard_runs()

        env.repository.settle_run.assert_awaited()


class TestTheReaperNeverFreesALiveRun:
    """The arithmetic trap: the engine bounds ONE ATTEMPT, not one run."""

    def test_the_worst_case_covers_every_attempt_and_every_pause(self) -> None:
        from src.domains.workboard.constants import worst_case_run_seconds

        assert worst_case_run_seconds(600, 3, 30) == 600 * 3 + 30 * 2

    def test_a_single_attempt_needs_no_pause(self) -> None:
        from src.domains.workboard.constants import worst_case_run_seconds

        assert worst_case_run_seconds(600, 1, 30) == 600

    def test_the_reaper_waits_longer_than_one_attempt(self) -> None:
        """Reaping at the attempt timeout would hand a ticket a live worker is
        still running to a second one: two runs, spending twice and possibly
        acting twice."""
        from src.core.config import settings
        from src.infrastructure.scheduler.workboard_runner import _worst_case_seconds

        assert _worst_case_seconds() >= settings.workboard_run_timeout_seconds
        if settings.workboard_run_max_attempts > 1:
            assert _worst_case_seconds() > settings.workboard_run_timeout_seconds

    async def test_the_tick_reaps_on_the_worst_case(self) -> None:
        """The reaper's cut-off is the worst case BEFORE the sweep's own instant.

        Measured against the REAL clock, not against the module's frozen ``NOW``:
        the sweep reads ``datetime.now(UTC)`` itself, so comparing its answer to
        a literal made this assertion true only while the wall clock sat before
        that literal — it passed for months and failed the moment the day it
        names went past noon. A test about a DURATION must bound the duration,
        never the instant.
        """
        from src.infrastructure.scheduler.workboard_runner import _worst_case_seconds

        env = _Env(_repository(None))
        before = datetime.now(UTC)
        async with _running(env):
            await sweep_workboard_runs()
        after = datetime.now(UTC)

        older_than = env.repository.reap_stale_claims.await_args.kwargs["older_than"]
        worst_case = timedelta(seconds=_worst_case_seconds())
        # The sweep read its own instant BETWEEN these two, so the cut-off it
        # computed sits exactly one worst case behind it — bounded on both
        # sides rather than compared to a literal.
        assert after - older_than >= worst_case
        assert before - older_than <= worst_case
        # And it is that window, not an arbitrarily older one: a stranded claim
        # must not be left held for an extra pass.
        assert after - older_than <= worst_case + timedelta(seconds=5)


class TestTheAnswerLandsBeforeTheNotification:
    async def test_a_run_is_announced_when_it_starts_and_when_it_ends(self) -> None:
        """The ticket carries the answer whatever happens to the notification,
        and the dispatcher commits its own archived row rather than deciding
        when ours lands."""
        env = _Env(_repository(_ticket()))
        async with _running(env):
            await sweep_workboard_runs()

        env.repository.settle_run.assert_awaited_once()
        events = [call.args[2].value for call in env.notify.await_args_list]
        assert events == ["run_started", "run_finished"]

    async def test_the_start_is_announced_only_once_the_lease_is_held(self) -> None:
        """A claim released for a busy thread ran nothing; a person following
        the ticket must not be told about work that did not happen."""
        env = _Env(_repository(_ticket()))
        env.lease_acquired = False
        async with _running(env):
            await sweep_workboard_runs()

        env.notify.assert_not_awaited()

    async def test_a_lost_settle_announces_no_ending(self) -> None:
        """The run started — that was true and was said — but the person who
        moved the ticket mid-run gets no « finished » about a column they left."""
        repository = _repository(_ticket())
        repository.settle_run = AsyncMock(return_value=False)
        env = _Env(repository)
        async with _running(env):
            await sweep_workboard_runs()

        events = [call.args[2].value for call in env.notify.await_args_list]
        assert events == ["run_started"]

    async def test_a_released_claim_tells_nobody(self) -> None:
        """Nothing ran; there is nothing to report."""
        env = _Env(_repository(_ticket()))
        env.lease_acquired = False
        async with _running(env):
            await sweep_workboard_runs()

        env.notify.assert_not_awaited()


class TestWhoIsToldAboutTheRun:
    """The dispatch itself: claimed before it leaves, settled from its result."""

    @staticmethod
    def _plan(outcome: str) -> Any:
        from src.infrastructure.scheduler.workboard_runner import SettlePlan

        return SettlePlan(status="x", outcome=outcome, comment="The room is booked.", error=None)

    @pytest.mark.parametrize(
        ("outcome", "event"),
        [
            (RunOutcome.SUCCESS.value, "run_finished"),
            (RunOutcome.WAITING.value, "waiting"),
            (RunOutcome.CONFIRMING.value, "confirming"),
            (RunOutcome.FAILED.value, "run_failed"),
        ],
    )
    def test_each_settled_run_maps_to_one_event(self, outcome: str, event: str) -> None:
        from src.infrastructure.scheduler.workboard_runner import _event_of

        assert _event_of(self._plan(outcome)).value == event

    async def test_a_ticket_nobody_follows_sends_nothing(self) -> None:
        from src.infrastructure.scheduler.workboard_runner import _notify

        db = AsyncMock()
        db.get = AsyncMock(return_value=_followed_ticket(follow_owner=False))
        sender = AsyncMock()
        with patch(f"{MODULE}._notify_one", sender):
            await _notify(db, _prepared(), WorkboardEvent.RUN_FINISHED, "Done.")

        sender.assert_not_awaited()

    async def test_a_followed_ticket_reaches_its_owner(self) -> None:
        from src.infrastructure.scheduler.workboard_runner import _notify

        db = AsyncMock()
        db.get = AsyncMock(return_value=_followed_ticket(follow_owner=True))
        sender = AsyncMock()
        with patch(f"{MODULE}._notify_one", sender):
            await _notify(db, _prepared(), WorkboardEvent.RUN_FINISHED, "Done.")

        sender.assert_awaited_once()
        assert sender.await_args.kwargs["event"].value == "run_finished"

    async def test_a_stopped_run_reaches_a_holder_who_follows_the_ticket(self) -> None:
        from src.infrastructure.scheduler.workboard_runner import _notify

        db = AsyncMock()
        db.get = AsyncMock(return_value=_followed_ticket(follow_owner=True))
        sender = AsyncMock()
        with patch(f"{MODULE}._notify_one", sender):
            await _notify(db, _prepared(), WorkboardEvent.WAITING, None)

        sender.assert_awaited_once()
        assert sender.await_args.kwargs["event"].value == "waiting"

    async def test_a_stopped_run_says_nothing_on_an_unfollowed_ticket(self) -> None:
        """D59: « LIA travaille en silence » holds even when she is blocked —
        the board, the hub badge and the heartbeat carry the question instead."""
        from src.infrastructure.scheduler.workboard_runner import _notify

        db = AsyncMock()
        db.get = AsyncMock(return_value=_followed_ticket(follow_owner=False))
        sender = AsyncMock()
        with patch(f"{MODULE}._notify_one", sender):
            await _notify(db, _prepared(), WorkboardEvent.WAITING, None)

        sender.assert_not_awaited()

    async def test_a_ticket_deleted_mid_run_notifies_nobody(self) -> None:
        from src.infrastructure.scheduler.workboard_runner import _notify

        db = AsyncMock()
        db.get = AsyncMock(return_value=None)
        sender = AsyncMock()
        with patch(f"{MODULE}._notify_one", sender):
            await _notify(db, _prepared(), WorkboardEvent.RUN_FINISHED, "Done.")

        sender.assert_not_awaited()

    async def test_what_the_seam_reports_is_what_is_counted(self) -> None:
        """The claim, the dispatch and the settle belong to the seam's adapter
        now; what stays here is the recipient, the sentence and the counter."""
        from src.infrastructure.scheduler.workboard_runner import _notify_one

        db = AsyncMock()
        db.get = AsyncMock(return_value=MagicMock(language="fr"))
        sent = AsyncMock(return_value=False)

        with patch("src.domains.shared.proactive_sink.send_proactive_notification", sent):
            await _notify_one(
                db,
                user_id=uuid.uuid4(),
                ticket=_followed_ticket(follow_owner=True),
                event=WorkboardEvent.RUN_FINISHED,
                run_id="r-1",
                comment="Done.",
            )

        sent.assert_awaited_once()
        call = sent.await_args.kwargs
        assert call["task_type"] == "workboard"
        assert "Book the venue" in call["content"]
        assert call["metadata"]["event"] == "run_finished"
        assert call["run_id"] == "r-1"
        # Started, finished, waiting: three acts under one run, three claims.
        assert call["occurrence"] == "run_finished"

    async def test_a_stopped_run_carries_the_link_that_finishes_it(self) -> None:
        from src.infrastructure.scheduler.workboard_runner import _notify_one

        db = AsyncMock()
        db.get = AsyncMock(return_value=MagicMock(language="fr"))
        sent = AsyncMock(return_value=True)

        with patch("src.domains.shared.proactive_sink.send_proactive_notification", sent):
            await _notify_one(
                db,
                user_id=uuid.uuid4(),
                ticket=_followed_ticket(follow_owner=False),
                event=WorkboardEvent.WAITING,
                run_id="r-1",
                comment=None,
            )

        assert "intent" in sent.await_args.kwargs["metadata"]

    async def test_a_failed_dispatch_never_costs_a_settled_run(self) -> None:
        from src.infrastructure.scheduler.workboard_runner import _notify_one

        db = AsyncMock()
        db.get = AsyncMock(side_effect=RuntimeError("redis is gone"))

        # Must not raise: the ticket already carries the answer, which is the
        # durable half of what this run owed the person.
        await _notify_one(
            db,
            user_id=uuid.uuid4(),
            ticket=_followed_ticket(follow_owner=True),
            event=WorkboardEvent.RUN_FINISHED,
            run_id="r-1",
            comment="Done.",
        )


def _followed_ticket(*, follow_owner: bool) -> Any:
    from src.domains.workboard.constants import AssigneeKind

    ticket = MagicMock()
    ticket.id = uuid.uuid4()
    ticket.title = "Book the venue"
    ticket.owner_user_id = uuid.uuid4()
    ticket.effective_assignee_id = ticket.owner_user_id
    ticket.assignee_kind = AssigneeKind.LIA.value
    ticket.assignee_user_id = None
    ticket.follow_owner = follow_owner
    ticket.follow_assignee = False
    return ticket


def _prepared() -> Any:
    from src.infrastructure.scheduler.workboard_runner import ClaimedRun

    return ClaimedRun(
        ticket_id=uuid.uuid4(),
        holder_id=uuid.uuid4(),
        run_id="r-1",
        language="fr",
        timezone="Europe/Paris",
        display_name="Jean",
        display_mode="cards",
        conversation_id=uuid.uuid4(),
        brief="Do the thing.",
        claimed_at=NOW,
        execution_mode="react",
    )


#: Settings the sweep may read that are not its own. Each one belongs to a
#: mechanism it borrows rather than to the workboard, and each is named here so
#: the list stays a decision instead of an accident.
_FOREIGN_SETTINGS: frozenset[str] = frozenset(
    {
        # Clearing a stopped turn's pending question uses the HITL store's own
        # retention — a second number here would drift from it.
        "hitl_pending_data_ttl_seconds",
        # A notification carries links into the web app; the deployment's own
        # origin belongs to the deployment, not to this feature.
        "frontend_url",
        # An account with no stored language still has to be written to.
        "default_language",
    }
)


def test_every_bound_the_sweep_applies_is_a_workboard_setting() -> None:
    """An operator who changes a workboard setting must change what the sweep
    does — and nothing else may quietly decide for it.

    Read from the AST, not from the prose: a constant hard-coded in a branch is
    exactly what this refuses, and a docstring saying otherwise would not.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(workboard_runner))
    read = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "settings"
    }

    assert read, "the sweep reads its bounds from settings, not from literals"
    assert (
        read - _FOREIGN_SETTINGS
        == {name for name in read if name.startswith("workboard_")} - _FOREIGN_SETTINGS
    )
    assert all(name.startswith("workboard_") or name in _FOREIGN_SETTINGS for name in read), sorted(
        read
    )


def _draft_interrupt(**draft_overrides: Any) -> TurnInterrupt:
    """The interrupt a run stops on when a tool asked for a confirmation."""
    draft: dict[str, Any] = {
        "draft_id": "draft_1",
        "draft_type": "tool_call",
        "draft_content": {
            "tool_name": "mcp_x_delete",
            "tool_label": "x: delete",
            "tool_args": {"target": "the archive"},
        },
        "tool_name": "mcp_x_delete",
    }
    draft.update(draft_overrides)
    return TurnInterrupt(
        kind="draft_critique", question="Je supprime « the archive » ?", draft=draft
    )


class TestAConfirmationLandsOnTheTicket:
    """Lot 7: a run that built a draft it may not run alone asks ON THE TICKET."""

    def test_the_ticket_goes_to_confirming_and_carries_the_draft(self) -> None:
        plan = plan_settle(
            RunResult(outcome=StreamOutcome.WAITING, interrupt=_draft_interrupt()),
            language="fr",
            timezone="Europe/Paris",
        )

        assert plan.status == TicketStatus.CONFIRMING.value
        assert plan.outcome == RunOutcome.CONFIRMING.value
        assert plan.error is None
        assert plan.pending_action == {
            "draft_id": "draft_1",
            "draft_type": "tool_call",
            "draft_content": {
                "tool_name": "mcp_x_delete",
                "tool_label": "x: delete",
                "tool_args": {"target": "the archive"},
            },
            "tool_name": "mcp_x_delete",
            "question": "Je supprime « the archive » ?",
            "approved": False,
        }

    def test_the_comment_is_the_question_and_how_to_answer(self) -> None:
        """Exactly what the chat showed — the card travels INSIDE the question
        since lot 14 — then the gesture that resumes. Nothing twice: appending
        the renderer's preview here is how the e-mail came to be read twice on
        the ticket (capture 2, 2026-09-09)."""
        question = (
            "🛠️ **x: delete**\n\n- **Outil** : x: delete\n- **Détails** : target: the archive"
            "\n\n---\n\nJe supprime « the archive » ?"
        )
        plan = plan_settle(
            RunResult(
                outcome=StreamOutcome.WAITING,
                interrupt=TurnInterrupt(
                    kind="draft_critique", question=question, draft=_draft_interrupt().draft
                ),
            ),
            language="fr",
            timezone="Europe/Paris",
        )

        assert plan.comment is not None
        assert plan.comment.startswith(question)
        assert plan.comment.count("the archive") == 2  # the card's row, the question
        assert "je m'en occupe" in plan.comment  # how to answer, in the holder's language
        assert "<br/>" not in plan.comment

    def test_the_draft_wins_over_a_refusal_collected_earlier(self) -> None:
        """The ask IS the refusal's continuation: the gate records the missing
        confirmation, then builds the draft. One comment, about the draft."""
        plan = plan_settle(
            RunResult(
                outcome=StreamOutcome.WAITING,
                refusals=[("mcp_x_delete", "confirmation_missing")],
                interrupt=_draft_interrupt(),
            ),
            language="fr",
            timezone="Europe/Paris",
        )
        assert plan.status == TicketStatus.CONFIRMING.value
        assert "Je me suis arrêtée" not in (plan.comment or "")

    def test_a_question_that_is_not_a_draft_stays_waiting_and_quotes_it(self) -> None:
        """A clarification cannot be answered by « oui »: the ticket waits, and
        the comment carries LIA's own question so the person knows what."""
        plan = plan_settle(
            RunResult(
                outcome=StreamOutcome.WAITING,
                interrupt=TurnInterrupt(kind="clarification", question="Quel jour, exactement ?"),
            ),
            language="fr",
            timezone="Europe/Paris",
        )

        assert plan.status == TicketStatus.WAITING.value
        assert plan.pending_action is None
        assert plan.comment is not None
        assert plan.comment.endswith("Quel jour, exactement ?")
        assert "Je me suis arrêtée" in plan.comment

    def test_an_unreadable_draft_still_asks(self) -> None:
        """A draft type nobody can render is still carried and still asked about."""
        plan = plan_settle(
            RunResult(
                outcome=StreamOutcome.WAITING,
                interrupt=_draft_interrupt(draft_type="no_such_type"),
            ),
            language="fr",
            timezone="Europe/Paris",
        )

        assert plan.status == TicketStatus.CONFIRMING.value
        assert plan.pending_action is not None
        assert plan.pending_action["draft_type"] == "no_such_type"
        assert plan.comment is not None
        assert plan.comment.startswith("Je supprime « the archive » ?")

    def test_the_holder_reads_it_in_their_language(self) -> None:
        chinese = plan_settle(
            RunResult(outcome=StreamOutcome.WAITING, interrupt=_draft_interrupt()),
            language="zh-CN",
            timezone="Asia/Shanghai",
        )
        assert chinese.comment is not None
        assert "剩下的交给我" in chinese.comment

    def test_a_confirmation_hands_the_ticket_back(self) -> None:
        assert TicketStatus.CONFIRMING.value in workboard_runner.HANDED_BACK_STATUSES

    async def test_the_settle_stores_the_draft_and_drops_the_threads_question(self) -> None:
        env = _Env(_repository(_ticket()))
        env.stream = AsyncMock(
            return_value=RunResult(outcome=StreamOutcome.WAITING, interrupt=_draft_interrupt())
        )
        cleared = AsyncMock()
        async with _running(env):
            with patch(f"{MODULE}._clear_pending_question", cleared):
                await sweep_workboard_runs()

        kwargs = env.repository.settle_run.await_args.kwargs
        assert kwargs["status"] == TicketStatus.CONFIRMING.value
        assert kwargs["hand_back"] is True
        assert kwargs["pending_action"]["draft_id"] == "draft_1"
        assert kwargs["pending_action"]["approved"] is False
        cleared.assert_awaited_once()
        assert env.notify.await_args.args[2] is WorkboardEvent.CONFIRMING

    async def test_a_finished_run_clears_what_it_replayed(self) -> None:
        """An approval is spent by the run that replayed it."""
        env = _Env(_repository(_ticket()))
        async with _running(env):
            await sweep_workboard_runs()
        assert env.repository.settle_run.await_args.kwargs["pending_action"] is None

    async def test_a_failed_run_keeps_the_approval_for_a_retry(self) -> None:
        """« Lancer maintenant » after a timeout must still replay what the
        person approved, not ask them again."""
        from src.domains.workboard.repository import KEEP_PENDING_ACTION

        env = _Env(_repository(_ticket()))
        env.stream = AsyncMock(return_value=RunResult(outcome=StreamOutcome.FAILED, error="boom"))
        async with _running(env):
            await sweep_workboard_runs()
        assert env.repository.settle_run.await_args.kwargs["pending_action"] is KEEP_PENDING_ACTION


class TestTheRunCarriesTheApproval:
    """The replay is let through on the IDENTITY of what was shown (ADR-092)."""

    async def test_an_approved_draft_travels_by_type_and_digest(self) -> None:
        from src.domains.agents.api.run_origin import ApprovedDraft
        from src.domains.agents.effects.digest import drafts_digest

        content = {"tool_name": "mcp_x_delete", "tool_label": "x: delete", "tool_args": {"t": 1}}
        ticket = _ticket()
        ticket.pending_action = {
            "draft_type": "tool_call",
            "draft_content": content,
            "approved": True,
        }
        env = _Env(_repository(ticket))
        async with _running(env):
            await sweep_workboard_runs()

        origin = env.stream.await_args.args[0].origin
        assert origin.can_carry_draft is True
        assert origin.approved_draft == ApprovedDraft(
            draft_type="tool_call", digest=drafts_digest([content])
        )

    async def test_a_draft_the_person_has_not_approved_travels_nowhere(self) -> None:
        ticket = _ticket()
        ticket.pending_action = {"draft_type": "tool_call", "draft_content": {}, "approved": False}
        env = _Env(_repository(ticket))
        async with _running(env):
            await sweep_workboard_runs()
        assert env.stream.await_args.args[0].origin.approved_draft is None

    async def test_every_ticket_run_can_carry_a_draft(self) -> None:
        """The gate reads this flag: without it a ticket run is a routine."""
        env = _Env(_repository(_ticket()))
        async with _running(env):
            await sweep_workboard_runs()
        assert env.stream.await_args.args[0].origin.can_carry_draft is True


class TestABatchIsOneConfirmation:
    """Lot 7: a FOR_EACH batch is shown whole and approved whole."""

    @staticmethod
    def _batch_interrupt() -> TurnInterrupt:
        first = {"tool_name": "mcp_x_delete", "tool_label": "x: delete", "tool_args": {"t": "one"}}
        second = {"tool_name": "mcp_x_delete", "tool_label": "x: delete", "tool_args": {"t": "two"}}
        return _draft_interrupt(
            draft_content=first,
            batch=[
                {"draft_id": "draft_1", "draft_type": "tool_call", "draft_content": first},
                {"draft_id": "draft_2", "draft_type": "tool_call", "draft_content": second},
            ],
        )

    def test_the_batch_question_is_kept_whole_and_nothing_is_added(self) -> None:
        """The stream's batch question already lists every item; the settle
        does not list them again."""
        interrupt = self._batch_interrupt()
        interrupt = TurnInterrupt(
            kind=interrupt.kind,
            question="⚠️ **Confirmation**\n\n- x: delete : one\n- x: delete : two\n\nOk ?",
            draft=interrupt.draft,
        )
        plan = plan_settle(
            RunResult(outcome=StreamOutcome.WAITING, interrupt=interrupt),
            language="fr",
            timezone="Europe/Paris",
        )
        assert plan.comment is not None
        assert plan.comment.count("one") == 1 and plan.comment.count("two") == 1
        assert plan.comment.index("one") < plan.comment.index("two")

    def test_the_batch_is_stored_on_the_row(self) -> None:
        plan = plan_settle(
            RunResult(outcome=StreamOutcome.WAITING, interrupt=self._batch_interrupt()),
            language="fr",
            timezone="Europe/Paris",
        )
        assert plan.pending_action is not None
        assert [item["draft_id"] for item in plan.pending_action["batch"]] == ["draft_1", "draft_2"]

    def test_a_lone_draft_stores_no_batch(self) -> None:
        plan = plan_settle(
            RunResult(outcome=StreamOutcome.WAITING, interrupt=_draft_interrupt()),
            language="fr",
            timezone="Europe/Paris",
        )
        assert plan.pending_action is not None
        assert "batch" not in plan.pending_action

    async def test_the_approval_covers_the_whole_batch(self) -> None:
        from src.domains.agents.effects.digest import drafts_digest

        first = {"tool_name": "mcp_x_delete", "tool_args": {"t": "one"}}
        second = {"tool_name": "mcp_x_delete", "tool_args": {"t": "two"}}
        ticket = _ticket()
        ticket.pending_action = {
            "draft_type": "tool_call",
            "draft_content": first,
            "batch": [
                {"draft_id": "draft_1", "draft_type": "tool_call", "draft_content": first},
                {"draft_id": "draft_2", "draft_type": "tool_call", "draft_content": second},
            ],
            "approved": True,
        }
        env = _Env(_repository(ticket))
        async with _running(env):
            await sweep_workboard_runs()

        approved = env.stream.await_args.args[0].origin.approved_draft
        assert approved is not None
        assert approved.digest == drafts_digest([first, second])
        assert approved.digest != drafts_digest([first])


class TestTheCommentFitsItsColumn:
    """The settle cuts a comment from the END, where the instruction lives."""

    def test_a_long_question_is_shortened_and_the_instruction_survives(self) -> None:
        from src.core.config import settings

        long_card = "📧 **s**\n\n" + "x" * (settings.workboard_comment_max_chars * 3)
        interrupt = TurnInterrupt(
            kind="draft_critique",
            question=long_card + "\n\n---\n\nJe l'envoie ?",
            draft=_draft_interrupt(draft_type="email").draft,
        )
        plan = plan_settle(
            RunResult(outcome=StreamOutcome.WAITING, interrupt=interrupt),
            language="fr",
            timezone="Europe/Paris",
        )

        assert plan.comment is not None
        assert len(plan.comment) <= settings.workboard_comment_max_chars
        assert plan.comment.startswith("📧 **s**")
        assert plan.comment.rstrip().endswith("ou dis-moi ce qu'il faut changer.")
        assert "…" in plan.comment
