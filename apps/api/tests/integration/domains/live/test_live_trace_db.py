"""The live trace against REAL PostgreSQL (ADR-299).

Three facts belong to the database and to nothing else, so a unit test over a
stub proves none of them:

- the injection predicate returns the two live rows in order — both roles —
  and never a hidden one, next to the proactive rows it always returned;
- a delegated turn's user row is found by its live stamp, its run id names
  the summary the meter reads, and a voice-only row is NOT a delegated turn;
- the aggregate is the SUM of those summaries and nothing else.

Everything runs inside the ``async_session`` fixture's transaction: nothing
persists.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import LIVE_TURN_MESSAGE_TYPE
from src.core.field_names import FIELD_LIVE_SESSION_ID, FIELD_RUN_ID
from src.domains.chat.models import MessageTokenSummary
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.conversations.repository import ConversationRepository
from src.domains.users.models import User
from src.domains.voice_sessions.summary import (
    aggregate_usage,
    count_voice_turns,
    session_run_ids,
    session_run_ids_by_key,
    session_voice_rows,
)

pytestmark = pytest.mark.integration

SESSION = "c" * 32
T0 = datetime(2026, 9, 18, 9, 0, tzinfo=UTC)
LIVE = {
    "type": LIVE_TURN_MESSAGE_TYPE,
    FIELD_LIVE_SESSION_ID: SESSION,
    FIELD_RUN_ID: "live_session_c",
}


async def _user(db: AsyncSession) -> User:
    user = User(
        email=f"live_{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    db.add(user)
    await db.flush()
    return user


async def _conversation(db: AsyncSession, user: User) -> Conversation:
    conversation = Conversation(user_id=user.id, title="L", message_count=0, total_tokens=0)
    db.add(conversation)
    await db.flush()
    return conversation


async def _row(
    db: AsyncSession,
    conversation: Conversation,
    role: str,
    content: str,
    metadata: dict,
    seconds: int,
    *,
    hidden: bool = False,
) -> ConversationMessage:
    row = ConversationMessage(
        conversation_id=conversation.id,
        role=role,
        content=content,
        message_metadata=metadata,
        hidden=hidden,
        created_at=T0 + timedelta(seconds=seconds),
    )
    db.add(row)
    await db.flush()
    return row


async def test_injection_returns_live_rows_in_order_and_skips_hidden(
    async_session: AsyncSession,
) -> None:
    user = await _user(async_session)
    conversation = await _conversation(async_session, user)
    await _row(async_session, conversation, "user", "hello", LIVE, 0)
    await _row(async_session, conversation, "assistant", "hi", LIVE, 1)
    await _row(async_session, conversation, "assistant", "secret", LIVE, 2, hidden=True)
    await _row(async_session, conversation, "user", "typed", {FIELD_RUN_ID: "r"}, 3)
    await _row(async_session, conversation, "assistant", "news", {"type": "proactive_interest"}, 4)

    rows = await ConversationRepository(async_session).get_proactive_messages_after(
        conversation_id=conversation.id, after_timestamp=T0 - timedelta(minutes=1), limit=10
    )

    assert [(r.role, r.content) for r in rows] == [
        ("user", "hello"),
        ("assistant", "hi"),
        ("assistant", "news"),
    ]


async def test_run_ids_by_stamp_and_their_sum(async_session: AsyncSession) -> None:
    user = await _user(async_session)
    conversation = await _conversation(async_session, user)
    for i, run_id in enumerate(("run_a", "run_b")):
        await _row(
            async_session,
            conversation,
            "user",
            "q",
            {FIELD_RUN_ID: run_id, FIELD_LIVE_SESSION_ID: SESSION},
            i,
        )
        async_session.add(
            MessageTokenSummary(
                user_id=user.id,
                session_id="s",
                run_id=run_id,
                conversation_id=conversation.id,
                total_prompt_tokens=10,
                total_completion_tokens=5,
                total_cached_tokens=1,
                total_cost_eur=Decimal("0.25"),
                google_api_requests=2,
            )
        )
    # A voice-only user row of the SAME session is not a delegated turn.
    await _row(async_session, conversation, "user", "hello", LIVE, 5)
    # Another turn of the conversation, outside the session.
    await _row(async_session, conversation, "user", "other", {FIELD_RUN_ID: "run_x"}, 6)
    await async_session.flush()

    run_ids = await session_run_ids(
        async_session, conversation_id=conversation.id, live_session_id=SESSION
    )
    assert run_ids == ["run_a", "run_b"]

    usage = await aggregate_usage(async_session, run_ids)
    assert usage is not None
    assert (usage.tokens_in, usage.tokens_out, usage.tokens_cache) == (20, 10, 2)
    assert usage.cost_eur == pytest.approx(0.5)
    assert usage.google_api_requests == 4

    voice = await session_voice_rows(
        async_session, conversation_id=conversation.id, live_session_id=SESSION
    )
    assert voice == [("user", "hello")]


async def test_voice_turns_are_counted_by_exchange_not_by_row(async_session: AsyncSession) -> None:
    # The two rows of one exchange share the `started_at` the client measured:
    # three rows, two exchanges — an aggregate, never a claim (ADR-185).
    user = await _user(async_session)
    conversation = await _conversation(async_session, user)
    first = {**LIVE, "started_at": "2026-09-18T09:00:00+00:00"}
    second = {**LIVE, "started_at": "2026-09-18T09:00:10+00:00"}
    await _row(async_session, conversation, "user", "hello", first, 0)
    await _row(async_session, conversation, "assistant", "hi", first, 1)
    await _row(async_session, conversation, "assistant", "still here", second, 2)
    # A delegated turn's row is stamped but is not an exchange.
    await _row(
        async_session,
        conversation,
        "user",
        "q",
        {FIELD_RUN_ID: "r", FIELD_LIVE_SESSION_ID: SESSION},
        3,
    )

    assert (
        await count_voice_turns(
            async_session, conversation_id=conversation.id, live_session_id=SESSION
        )
        == 2
    )
    assert (
        await count_voice_turns(
            async_session, conversation_id=conversation.id, live_session_id="d" * 32
        )
        == 0
    )


async def test_the_runs_of_several_sessions_are_read_together(async_session: AsyncSession) -> None:
    """A page of Live phone calls reads its delegated runs in ONE query (ADR-301)."""
    user = await _user(async_session)
    conversation = await _conversation(async_session, user)
    phone_a, phone_b, phone_c = ("phone_call_" + c * 32 for c in "abc")
    await _row(
        async_session,
        conversation,
        "user",
        "q1",
        {FIELD_RUN_ID: "ra1", FIELD_LIVE_SESSION_ID: phone_a},
        0,
    )
    await _row(
        async_session,
        conversation,
        "user",
        "q2",
        {FIELD_RUN_ID: "ra2", FIELD_LIVE_SESSION_ID: phone_a},
        1,
    )
    await _row(
        async_session,
        conversation,
        "user",
        "q3",
        {FIELD_RUN_ID: "rb1", FIELD_LIVE_SESSION_ID: phone_b},
        2,
    )
    # A voice-only row of session B is not a delegated turn.
    await _row(
        async_session, conversation, "user", "hi", {**LIVE, FIELD_LIVE_SESSION_ID: phone_b}, 3
    )
    # A session outside the page is not read.
    await _row(
        async_session,
        conversation,
        "user",
        "q4",
        {FIELD_RUN_ID: "rz", FIELD_LIVE_SESSION_ID: "phone_call_" + "z" * 32},
        4,
    )
    await async_session.flush()

    grouped = await session_run_ids_by_key(
        async_session, conversation_id=conversation.id, live_session_ids=[phone_a, phone_b, phone_c]
    )
    assert grouped == {phone_a: ["ra1", "ra2"], phone_b: ["rb1"]}
    assert (
        await session_run_ids_by_key(
            async_session, conversation_id=conversation.id, live_session_ids=[]
        )
        == {}
    )


async def test_the_direct_card_is_rewritten_with_the_relay_fate(
    async_session: AsyncSession,
) -> None:
    """ADR-301: the card archived at the closing says « scheduled »; once the
    relayed turn settled it says the fate — content AND nested metadata, on
    the real row (a shallow merge cannot reach ``live_session.relay``)."""
    from src.domains.agents.api.archive_metadata import build_live_session_summary_metadata
    from src.domains.voice_sessions.session import VoiceSession
    from src.domains.voice_sessions.summary import render_summary_markdown
    from src.infrastructure.scheduler.voice_session_closing import _rewrite_card

    user = await _user(async_session)
    conversation = await _conversation(async_session, user)
    session = VoiceSession.browser(
        session_id=SESSION,
        run_id="live_session_c",
        mode="direct",
        user_id=user.id,
        conversation_id=conversation.id,
        language="fr",
        timezone="Europe/Paris",
    )
    metadata = build_live_session_summary_metadata(
        run_id=session.run_id,
        live_session_id=SESSION,
        outcome="ended",
        duration_seconds=75,
        delegations=0,
        voice_turns=0,
        usage={
            "tokens_in": 10,
            "tokens_out": 2,
            "tokens_cache": 0,
            "cost_eur": 0.01,
            "google_api_requests": 0,
        },
        mode="direct",
        relay="scheduled",
    )
    card = await _row(
        async_session,
        conversation,
        "assistant",
        render_summary_markdown(
            language="fr",
            outcome="ended",
            mode="direct",
            duration_seconds=75,
            delegations=0,
            voice_turns=0,
            usage=None,
            extensions=0,
            relay="scheduled",
        ),
        metadata,
        0,
    )

    await _rewrite_card(async_session, session, card.id, "waiting", extensions=0)
    await async_session.flush()

    row = (
        await async_session.execute(
            select(ConversationMessage)
            .where(ConversationMessage.id == card.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert row.message_metadata["live_summary"]["relay"] == "waiting"
    assert row.message_metadata["live_summary"]["mode"] == "direct"
    assert row.message_metadata["live_summary"]["duration_seconds"] == 75
    # The figures are read again at the settle: the relayed turn spent under
    # the session's run id AFTER the card was written (here: nothing).
    assert "cost_eur" not in row.message_metadata
    assert "LIA a une question pour toi" in row.content
    assert "0.0000" in row.content
