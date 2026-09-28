"""Integration: what a listener's radio spent over the rolling day, on PostgreSQL (ADR-324 decision 37).

What only a server proves: the run prefix is matched LITERALLY (``LIKE``'s
underscore escaped — ``radiox…`` is not a radio run), every family of a run's
row is summed, a run counts while its LAST write is in the window, and neither
another listener's runs nor the listener's chat turns ever count.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.chat.models import MessageTokenSummary
from src.domains.radio import budget as module
from src.domains.radio.budget import RadioSpend, listener_budget, radio_spends
from src.domains.users.models import User

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 27, 18, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def one_session(async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    @contextlib.asynccontextmanager
    async def _ctx() -> AsyncIterator[AsyncSession]:
        yield async_session

    monkeypatch.setattr(module, "get_db_context", _ctx)


async def listener(session: AsyncSession, name: str) -> User:
    user = User(email=f"radio_budget_{name}@test.local", hashed_password="x", is_active=True)
    session.add(user)
    await session.flush()
    return user


def run(
    user: User,
    run_id: str,
    *,
    last_spend: datetime,
    began: datetime | None = None,
    model: str = "0",
    speech: str = "0",
    maps: str = "0",
    images: str = "0",
) -> MessageTokenSummary:
    return MessageTokenSummary(
        user_id=user.id,
        session_id=run_id,
        run_id=run_id,
        conversation_id=None,
        total_prompt_tokens=0,
        total_completion_tokens=0,
        total_cached_tokens=0,
        total_cost_eur=Decimal(model),
        google_api_cost_eur=Decimal(maps),
        image_generation_cost_eur=Decimal(images),
        tts_cost_eur=Decimal(speech),
        created_at=began or last_spend - timedelta(hours=1),
        updated_at=last_spend,
    )


def radio_run() -> str:
    return f"radio_{uuid.uuid4().hex}"


async def seed(session: AsyncSession) -> User:
    """One listener's day, and everything around it that must not count."""
    alice, bob = await listener(session, "alice"), await listener(session, "bob")
    session.add_all(
        [
            # Counted: every family of a session's row, and an article's translation.
            run(alice, radio_run(), last_spend=NOW - timedelta(hours=2), model="0.3", speech="0.5"),
            run(
                alice,
                f"radio_article_{uuid.uuid4().hex}",
                last_spend=NOW - timedelta(hours=1),
                model="0.02",
            ),
            # Counted: begun before the window, its last spend inside it.
            run(
                alice,
                radio_run(),
                began=NOW - timedelta(hours=26),
                last_spend=NOW - timedelta(hours=20),
                maps="0.1",
                images="0.3",
            ),
            # Not counted: its last spend left the window.
            run(alice, radio_run(), last_spend=NOW - timedelta(hours=30), model="1.0"),
            # Not counted: a chat turn, and a lookalike the underscore must not match.
            run(alice, str(uuid.uuid4()), last_spend=NOW - timedelta(hours=1), model="5.0"),
            run(
                alice, f"radiox{uuid.uuid4().hex}", last_spend=NOW - timedelta(hours=1), model="3.0"
            ),
            # Not counted: another listener's radio.
            run(bob, radio_run(), last_spend=NOW - timedelta(hours=1), model="9.0"),
        ]
    )
    await session.flush()
    return alice


async def test_the_listener_s_radio_runs_whose_last_spend_is_in_the_window(
    async_session: AsyncSession,
) -> None:
    alice = await seed(async_session)

    spends = await radio_spends(alice.id, since=NOW - timedelta(hours=24))

    # The ledger's six decimals are summed exactly by the server.
    assert sorted(spends, key=lambda spend: spend.at) == [
        RadioSpend(at=NOW - timedelta(hours=20), eur=0.4),
        RadioSpend(at=NOW - timedelta(hours=2), eur=0.8),
        RadioSpend(at=NOW - timedelta(hours=1), eur=0.02),
    ]


async def test_the_budget_reads_the_day_and_says_when_it_lifts(
    async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    alice = await seed(async_session)
    monkeypatch.setattr(settings, "radio_budget_24h_eur", 1.0)

    budget = await listener_budget(alice.id, now=NOW)

    assert budget.reached and budget.spent_eur == pytest.approx(1.22)
    # The run begun before the window leaves it first: 0.82 € remain, under the bound.
    assert budget.lifts_at == NOW + timedelta(hours=4)
