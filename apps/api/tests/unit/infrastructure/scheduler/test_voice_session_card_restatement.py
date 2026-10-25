"""A closing card states the bill the session ran up — including what it spent after (ADR-185).

The card is archived with the bill known at the closing. A delegated session
then hands its voice-only exchanges to the learning, which spends under the
session's own run id AFTER the card was drawn (measured on production on
2026-10-24: a card frozen before its learning). Once the learning persisted
its spend, the card is restated: only when the bill GREW, never lowered, the
figures the closing settled kept as they were.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.field_names import FIELD_LIVE_SUMMARY
from src.domains.agents.api.archive_metadata import build_live_session_summary_metadata
from src.domains.voice_sessions.session import VoiceSession
from src.domains.voice_sessions.summary import VoiceSessionUsage
from src.infrastructure.scheduler.voice_session_closing import (
    close_voice_session,
    restate_card_bill,
)

pytestmark = pytest.mark.unit

MODULE = "src.infrastructure.scheduler.voice_session_closing"
CARD_ID = uuid.uuid4()
AT_CLOSING = VoiceSessionUsage(
    tokens_in=100, tokens_out=20, tokens_cache=0, cost_eur=0.01, google_api_requests=0
)
AFTER_LEARNING = VoiceSessionUsage(
    tokens_in=160, tokens_out=30, tokens_cache=10, cost_eur=0.014, google_api_requests=0
)


def _session() -> VoiceSession:
    return VoiceSession.browser(
        session_id="d" * 32,
        run_id="live_session_" + "d" * 32,
        mode="delegated",
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        language="fr",
        timezone="UTC",
    )


def _card(session: VoiceSession, usage: VoiceSessionUsage | None) -> SimpleNamespace:
    return SimpleNamespace(
        id=CARD_ID,
        message_metadata=build_live_session_summary_metadata(
            run_id=session.run_id,
            live_session_id=session.key,
            outcome="ended",
            duration_seconds=95,
            delegations=2,
            voice_turns=3,
            usage=usage.model_dump() if usage else None,
            extensions=1,
            mode=session.mode,
        ),
    )


class _Db:
    def __init__(self) -> None:
        self.commit = AsyncMock()


def _restating(card: SimpleNamespace | None, fresh: VoiceSessionUsage | None) -> dict[str, Any]:
    """Patch the restatement's reads; return its recorders."""
    db = _Db()

    @asynccontextmanager
    async def _context() -> Any:
        yield db

    recorders: dict[str, Any] = {
        "db": db,
        "rewrite": AsyncMock(return_value=True),
        "aggregate": AsyncMock(return_value=fresh),
        "run_ids": AsyncMock(return_value=["turn_1", "turn_2"]),
    }
    recorders["patches"] = [
        patch(f"{MODULE}.get_db_context", _context),
        patch(f"{MODULE}.session_card", AsyncMock(return_value=card)),
        patch(f"{MODULE}.session_run_ids", recorders["run_ids"]),
        patch(f"{MODULE}.aggregate_usage", recorders["aggregate"]),
        patch(f"{MODULE}.rewrite_session_card", recorders["rewrite"]),
    ]
    return recorders


async def _restate(card: SimpleNamespace | None, fresh: VoiceSessionUsage | None) -> dict[str, Any]:
    session = _session()
    recorders = _restating(card, fresh)
    for item in recorders["patches"]:
        item.start()
    try:
        await restate_card_bill(session, CARD_ID)
    finally:
        for item in recorders["patches"]:
            item.stop()
    recorders["session"] = session
    return recorders


async def test_a_bill_that_grew_is_restated_and_the_settled_figures_kept() -> None:
    session = _session()
    recorders = await _restate(_card(session, AT_CLOSING), AFTER_LEARNING)

    recorders["rewrite"].assert_awaited_once()
    metadata = recorders["rewrite"].call_args.kwargs["metadata"]
    assert metadata["cost_eur"] == AFTER_LEARNING.cost_eur
    assert metadata["tokens_in"] == AFTER_LEARNING.tokens_in
    figures = metadata[FIELD_LIVE_SUMMARY]
    assert (figures["delegations"], figures["voice_turns"], figures["extensions"]) == (2, 3, 1)
    assert figures["duration_seconds"] == 95 and "relay" not in figures
    # The bill is read over the delegated turns AND the session's own run.
    assert recorders["aggregate"].call_args.args[1] == [
        "turn_1",
        "turn_2",
        recorders["session"].run_id,
    ]
    recorders["db"].commit.assert_awaited_once()


async def test_an_unchanged_bill_writes_nothing() -> None:
    session = _session()
    recorders = await _restate(_card(session, AT_CLOSING), AT_CLOSING)

    recorders["rewrite"].assert_not_awaited()
    recorders["db"].commit.assert_not_awaited()


async def test_a_figure_already_shown_is_never_lowered() -> None:
    session = _session()
    lower = AT_CLOSING.model_copy(update={"cost_eur": 0.005})
    recorders = await _restate(_card(session, AT_CLOSING), lower)

    recorders["rewrite"].assert_not_awaited()


async def test_a_card_drawn_with_no_bill_takes_the_first_one() -> None:
    session = _session()
    recorders = await _restate(_card(session, None), AFTER_LEARNING)

    assert recorders["rewrite"].call_args.kwargs["metadata"]["cost_eur"] == 0.014


async def test_a_missing_card_is_left_alone() -> None:
    recorders = await _restate(None, AFTER_LEARNING)

    recorders["rewrite"].assert_not_awaited()


async def test_a_failure_never_raises() -> None:
    session = _session()
    recorders = _restating(_card(session, AT_CLOSING), AFTER_LEARNING)
    recorders["aggregate"].side_effect = RuntimeError("database gone")
    for item in recorders["patches"]:
        item.start()
    try:
        await restate_card_bill(session, CARD_ID)  # must not raise
    finally:
        for item in recorders["patches"]:
            item.stop()
    recorders["rewrite"].assert_not_awaited()


async def test_a_delegated_closing_restates_its_card_once_the_learning_spent() -> None:
    """End to end through the closing: the card ends up with the learning's spend."""
    session = _session()
    card = _card(session, AT_CLOSING)
    archive = AsyncMock(return_value=card)
    rewrite = AsyncMock(return_value=True)
    restating_db = _Db()

    @asynccontextmanager
    async def _context() -> Any:
        yield restating_db

    tracking = MagicMock()
    tracking.return_value.__aenter__ = AsyncMock(return_value=None)
    tracking.return_value.__aexit__ = AsyncMock(return_value=False)
    with (
        patch(f"{MODULE}.session_run_ids", AsyncMock(return_value=["turn_1"])),
        patch(f"{MODULE}.count_voice_turns", AsyncMock(return_value=3)),
        patch(f"{MODULE}.session_voice_rows", AsyncMock(return_value=[("user", "hi")])),
        patch(f"{MODULE}.aggregate_usage", AsyncMock(side_effect=[AT_CLOSING, AFTER_LEARNING])),
        patch(f"{MODULE}.record_decision", AsyncMock()),
        patch(f"{MODULE}.archive_row", archive),
        patch(f"{MODULE}.extract_memories_background", AsyncMock(return_value=1)),
        patch(f"{MODULE}.extract_interests_background", AsyncMock(return_value=0)),
        patch(f"{MODULE}.TrackingContext", tracking),
        patch(f"{MODULE}.get_db_context", _context),
        patch(f"{MODULE}.session_card", AsyncMock(return_value=card)),
        patch(f"{MODULE}.rewrite_session_card", rewrite),
    ):
        closed = await close_voice_session(
            AsyncMock(),
            session=session,
            memory_enabled=True,
            outcome="ended",
            duration_seconds=95,
            learn_inline=True,
        )

    assert closed.usage == AT_CLOSING  # what the closing reported
    rewrite.assert_awaited_once()  # then the card followed the learning
    assert rewrite.call_args.args[1] == CARD_ID
    assert rewrite.call_args.kwargs["metadata"]["cost_eur"] == AFTER_LEARNING.cost_eur
    restating_db.commit.assert_awaited_once()
