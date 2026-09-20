"""A DIRECT session's words become the person's own turn, OFF the request path (ADR-301).

The closing answers at once — the card says « scheduled » — and everything
that spends or waits (the relay synthesis, the relayed turn, the card's
rewrite, the notice) runs in a task the closing owns. Three rules, each a
test: no model is called inside ``POST /end`` (the person pressed stop, the
claim must be released now, and a slow provider must not hang the banner);
the settle NEVER leaves the card at « scheduled » — whatever raised, the
fate known at that instant is written; and an authenticated browser session
is the account holder's by construction — the synthesis's own owner flag,
a model output, must not turn it into « someone else was speaking ».
"""

from __future__ import annotations

import uuid
from contextlib import ExitStack, asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions_domains import UsageLimitExceededError
from src.domains.telephony.schemas import SelfCallRelay
from src.domains.voice_sessions.session import VoiceSession
from src.domains.voice_sessions.transcript import VoiceTranscript
from src.infrastructure.scheduler.voice_relay import RelayOutcome
from src.infrastructure.scheduler.voice_session_closing import (
    RELAY_SCHEDULED,
    _settle_direct_relay,
    close_voice_session,
)

pytestmark = pytest.mark.unit

MODULE = "src.infrastructure.scheduler.voice_session_closing"
CARD_ID = uuid.uuid4()


def _session() -> VoiceSession:
    return VoiceSession.browser(
        session_id="s" * 32,
        run_id="live_session_" + "s" * 32,
        mode="direct",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        language="fr",
        timezone="Europe/Paris",
    )


def _transcript() -> VoiceTranscript:
    return VoiceTranscript.from_rows(
        [("user", "remind me to call the bank"), ("assistant", "noted")]
    )


def _relay(owner_confirmed: bool = True) -> SelfCallRelay:
    return SelfCallRelay(
        owner_confirmed=owner_confirmed, relay_message="Remind me to call the bank.", summary="s"
    )


def _closing_patches(*, archive: AsyncMock) -> list[Any]:
    return [
        patch(f"{MODULE}.session_run_ids", AsyncMock(return_value=[])),
        patch(f"{MODULE}.session_voice_rows", AsyncMock(return_value=[])),
        patch(f"{MODULE}.count_voice_turns", AsyncMock(return_value=0)),
        patch(f"{MODULE}.aggregate_usage", AsyncMock(return_value=None)),
        patch(f"{MODULE}.record_decision", AsyncMock()),
        patch(f"{MODULE}.archive_row", archive),
    ]


# -- the closing: instant, no model ----------------------------------------------


async def test_the_closing_calls_no_model_and_schedules_the_relay() -> None:
    archive = AsyncMock(return_value=SimpleNamespace(id=CARD_ID))
    db = MagicMock()
    db.commit = AsyncMock()
    synth, scheduled = AsyncMock(), MagicMock()
    with ExitStack() as stack:
        for seam in _closing_patches(archive=archive):
            stack.enter_context(seam)
        stack.enter_context(patch(f"{MODULE}.synthesize_relay", synth))
        stack.enter_context(patch(f"{MODULE}.safe_fire_and_forget", scheduled))
        closed = await close_voice_session(
            db,
            session=_session(),
            memory_enabled=True,
            outcome="ended",
            duration_seconds=90,
            transcript=_transcript(),
        )
    synth.assert_not_awaited()
    assert closed.relay == RELAY_SCHEDULED
    assert archive.call_args.kwargs["metadata"]["live_summary"]["relay"] == RELAY_SCHEDULED
    # The task the closing owns carries the transcript and the card to rewrite.
    scheduled.assert_called_once()
    coroutine = scheduled.call_args.args[0]
    assert coroutine.cr_code.co_name == "_settle_direct_relay"
    coroutine.close()


async def test_a_session_with_nothing_said_relays_nothing_and_schedules_nothing() -> None:
    archive = AsyncMock(return_value=SimpleNamespace(id=CARD_ID))
    db = MagicMock()
    db.commit = AsyncMock()
    synth, scheduled = AsyncMock(), MagicMock()
    with ExitStack() as stack:
        for seam in _closing_patches(archive=archive):
            stack.enter_context(seam)
        stack.enter_context(patch(f"{MODULE}.synthesize_relay", synth))
        stack.enter_context(patch(f"{MODULE}.safe_fire_and_forget", scheduled))
        closed = await close_voice_session(
            db,
            session=_session(),
            memory_enabled=True,
            outcome="ended",
            duration_seconds=3,
            transcript=VoiceTranscript.from_rows([]),
        )
    synth.assert_not_awaited()
    scheduled.assert_not_called()
    assert closed.relay == RelayOutcome.EMPTY.value


# -- the settle: the fate is always written ----------------------------------------


class _Rig:
    """The settle's doors: one fake db context, every seam an AsyncMock."""

    def __init__(self, *, relay: SelfCallRelay | None = None, synth_error: Exception | None = None):
        self.db = MagicMock()
        self.db.commit = AsyncMock()
        self.db.get = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))
        self.contexts = 0
        rig = self

        @asynccontextmanager
        async def _db_context():  # noqa: ANN202
            rig.contexts += 1
            rig.open += 1
            try:
                yield rig.db
            finally:
                rig.open -= 1

        self.db_context = _db_context
        if synth_error is not None:
            self.synth = AsyncMock(side_effect=synth_error)
        else:
            self.synth = AsyncMock(return_value=(relay or _relay(), None))
        self.tracked = AsyncMock()
        self.open = 0
        self.open_during_relay: int | None = None

        async def _relay_run(_request):  # noqa: ANN001
            # The turn runs with NO session of the settle's open.
            rig.open_during_relay = rig.open
            return rig.relay_outcome

        self.relay_outcome = RelayOutcome.ANSWERED
        self.relay_run = AsyncMock(side_effect=_relay_run)
        self.rewrite = AsyncMock()
        self.notify = AsyncMock()
        self.counter = MagicMock()

    def patches(self) -> list[Any]:
        return [
            patch(f"{MODULE}.get_db_context", self.db_context),
            patch(f"{MODULE}.synthesize_relay", self.synth),
            patch(f"{MODULE}.track_voice_synthesis_usage", self.tracked),
            patch(f"{MODULE}.run_voice_relay", self.relay_run),
            patch(f"{MODULE}._rewrite_card", self.rewrite),
            patch(f"{MODULE}._notify_relay", self.notify),
            patch(f"{MODULE}.live_direct_relay_total", self.counter),
        ]


async def _settle(rig: _Rig) -> None:
    with ExitStack() as stack:
        for seam in rig.patches():
            stack.enter_context(seam)
        await _settle_direct_relay(_session(), _transcript(), CARD_ID, extensions=1)


def _fate(rig: _Rig) -> str:
    return str(rig.rewrite.call_args.args[3])


def _recap(rig: _Rig) -> str | None:
    return rig.rewrite.call_args.kwargs.get("relay_summary")


async def test_the_settle_synthesises_relays_rewrites_and_tells() -> None:
    rig = _Rig()
    await _settle(rig)
    # The synthesis read the transcript for the session's owner, in their language.
    kwargs = rig.synth.call_args.kwargs
    assert kwargs["transcript"].lines() == ["user: remind me to call the bank", "agent: noted"]
    assert kwargs["user_language"] == "fr" and kwargs["collected"].owner_confirmed is True
    # Its spend is filed under the session's OWN run id, on the live surface.
    assert rig.tracked.call_args.kwargs["run_id"] == "live_session_" + "s" * 32
    assert rig.tracked.call_args.kwargs["task_type"] == "live_session"
    # The relayed turn ran, the card says so, the person's screen was told.
    assert rig.relay_run.await_count == 1
    # The settle's session is opened AFTER the turn, never held across it
    # (measured 8.9 s of idle-in-transaction before, review 2026-09-20).
    assert rig.open_during_relay == 0
    assert rig.contexts == 1
    assert _fate(rig) == RelayOutcome.ANSWERED.value
    assert rig.notify.call_args.args[3] == RelayOutcome.ANSWERED.value
    rig.db.commit.assert_awaited()
    rig.counter.labels.assert_called_with(outcome=RelayOutcome.ANSWERED.value)


async def test_a_relay_that_ran_carries_no_recap_one_that_did_not_keeps_it() -> None:
    # The phone's fallback push carries the recap when the turn did not run
    # (busy, a pending question, a ceiling, a failure); the browser's card
    # does the same, so the person's words are never lost in silence.
    ran = _Rig()
    await _settle(ran)
    assert _recap(ran) is None
    busy = _Rig()
    busy.relay_outcome = RelayOutcome.BUSY
    await _settle(busy)
    assert _fate(busy) == RelayOutcome.BUSY.value
    assert _recap(busy) == "s"


async def test_an_authenticated_session_is_the_account_holder_whatever_the_model_says() -> None:
    rig = _Rig(relay=_relay(owner_confirmed=False))
    await _settle(rig)
    request = rig.relay_run.call_args.args[0]
    assert request.relay.owner_confirmed is True
    assert _fate(rig) == RelayOutcome.ANSWERED.value


async def test_a_synthesis_the_ceiling_refused_writes_quota_blocked() -> None:
    rig = _Rig(synth_error=UsageLimitExceededError("limit", limit_type="daily"))
    await _settle(rig)
    rig.relay_run.assert_not_awaited()
    assert _fate(rig) == RelayOutcome.QUOTA_BLOCKED.value
    rig.counter.labels.assert_called_with(outcome=RelayOutcome.QUOTA_BLOCKED.value)


async def test_a_synthesis_that_broke_writes_failed() -> None:
    rig = _Rig(synth_error=RuntimeError("provider down"))
    await _settle(rig)
    rig.relay_run.assert_not_awaited()
    assert _fate(rig) == RelayOutcome.FAILED.value


async def test_a_synthesis_with_nothing_to_relay_writes_empty() -> None:
    rig = _Rig(relay=SelfCallRelay(owner_confirmed=True, relay_message="  ", summary="s"))
    await _settle(rig)
    rig.relay_run.assert_not_awaited()
    assert _fate(rig) == RelayOutcome.EMPTY.value


async def test_a_relay_that_raised_never_leaves_the_card_at_scheduled() -> None:
    rig = _Rig()
    rig.relay_run = AsyncMock(side_effect=ConnectionError("redis"))
    await _settle(rig)
    # The relay ran with no session of the settle's open, so the net opens the
    # ONE session the rewrite needs (a rewrite that raises is what earns the
    # fresh second session, below).
    assert rig.contexts == 1
    assert _fate(rig) == RelayOutcome.FAILED.value
    rig.counter.labels.assert_called_with(outcome=RelayOutcome.FAILED.value)


async def test_a_rewrite_that_raised_is_retried_with_the_true_fate() -> None:
    rig = _Rig()
    rig.rewrite = AsyncMock(side_effect=[RuntimeError("db"), None])
    await _settle(rig)
    assert rig.rewrite.await_count == 2
    # The turn DID run: the retry writes « answered », never a false « failed ».
    assert _fate(rig) == RelayOutcome.ANSWERED.value
    rig.counter.labels.assert_called_with(outcome=RelayOutcome.ANSWERED.value)
