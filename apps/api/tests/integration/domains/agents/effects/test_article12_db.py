"""The whole extraction, against the real database (ADR-263, lot 9).

The composition has its own unit suite. What only PostgreSQL can prove is that
the five reads actually reach five different tables, that the period filters all
five the same way — they have five differently named timestamp columns — and
that the file a regulator would receive holds no raw identifier. The last one no
mock can vouch for: the pseudonymisation key and the real column values are both
involved.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.article12_export import (
    RECORD_KEY,
    article12_filters,
    extract_of,
    known_sources,
    render_article12,
)
from src.domains.agents.effects.decision_repository import DecisionRepository
from src.domains.agents.effects.decisions import TurnDecision
from src.domains.agents.effects.integrity import IntegrityKind
from src.domains.agents.effects.integrity_repository import IntegrityRepository
from src.domains.agents.effects.models import EffectSource, TreatmentOutcome
from src.domains.agents.effects.technical_reads import TechnicalQuery, read_register
from src.domains.users.models import User

pytestmark = pytest.mark.integration

_START = datetime(2026, 9, 5, 9, 0, tzinfo=UTC)
_CAP = 500


@pytest.fixture
async def user(async_session: AsyncSession) -> User:
    """The account the extraction covers."""
    row = User(
        email=f"a12-{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Article 12 Owner",
    )
    async_session.add(row)
    await async_session.flush()
    return row


async def _populate(session: AsyncSession, user: User, *, at: datetime) -> None:
    """One row in each of the five records, at the same instant."""
    from src.domains.agents.effects.models import AgentTreatment
    from src.domains.agents.effects.repository import EffectLedgerRepository
    from src.domains.agents.effects.schemas import ClaimRequest
    from src.domains.chat.models import TokenUsageLog

    tag = f"run-{at.hour}{at.minute}"
    await DecisionRepository(session).record(
        TurnDecision(
            run_id=tag,
            user_id=user.id,
            thread_id="thread-A",
            execution_mode="pipeline",
            started_at=at,
        ),
        ended_at=at + timedelta(seconds=1),
    )
    await EffectLedgerRepository(session).claim(
        ClaimRequest(
            user_id=user.id,
            thread_id="thread-A",
            run_id=tag,
            source="user",
            execution_mode="pipeline",
            tool_name="send_email_tool",
            mutation_policy="draft",
            idempotency_key=f"call-{tag}",
            args_digest="a" * 64,
        )
    )
    session.add(
        AgentTreatment(
            user_id=user.id,
            thread_id="thread-A",
            run_id=tag,
            source=EffectSource.USER,
            execution_mode="pipeline",
            tool_name="get_emails_tool",
            mutation_policy="read",
            outcome=TreatmentOutcome.OK,
            duration_ms=11,
            occurred_at=at,
        )
    )
    session.add(
        TokenUsageLog(
            user_id=user.id,
            run_id=tag,
            node_name="response",
            model_name="gpt-4.1-mini",
            prompt_tokens=10,
            completion_tokens=5,
            cached_tokens=0,
            provider="openai",
            temperature=0.3,
            params_digest="d" * 64,
            created_at=at,
        )
    )
    await IntegrityRepository(session).record(
        kind=IntegrityKind.EFFECT_UNRECORDED,
        user_id=user.id,
        run_id=tag,
        detail="no_claim:draft",
    )
    await session.flush()

    # Two of the five stamp their own instant (the ledger claims at ``now()``,
    # the integrity repository observes at ``now()``), which is right in
    # production and useless for a period test. Backdate them so all five
    # actually sit at ``at`` — otherwise this file would assert that a filter
    # works while three sources were simply empty.
    from sqlalchemy import update as sql_update

    from src.domains.agents.effects.models import AgentEffect, AgentIntegrityEvent

    await session.execute(
        sql_update(AgentEffect).where(AgentEffect.run_id == tag).values(claimed_at=at)
    )
    await session.execute(
        sql_update(AgentIntegrityEvent)
        .where(AgentIntegrityEvent.run_id == tag)
        .values(occurred_at=at)
    )
    await session.flush()


async def _extraction(
    session: AsyncSession,
    *,
    user_ids: list[uuid.UUID] | None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict[str, Any]]:
    """Run the extraction exactly as the route does, and parse it back."""
    extracts = []
    for spec in known_sources():
        rows = await read_register(
            session,
            TechnicalQuery(
                register=spec.slug,
                since=since,
                until=until,
                user_ids=user_ids,
                tool_name=None,
                mutation_policy=None,
                status=None,
                source=None,
                execution_mode=None,
            ),
            _CAP,
        )
        extracts.append(extract_of(spec, rows, cap=_CAP))
    content = render_article12(
        extracts,
        cap=_CAP,
        filters=article12_filters(since=since, until=until, user_ids=user_ids),
    )
    return [json.loads(line) for line in content.strip().splitlines()]


class TestTheFiveReadsReachFiveTables:
    async def test_every_record_contributes_its_own_line(
        self, async_session: AsyncSession, user: User
    ) -> None:
        await _populate(async_session, user, at=_START)

        lines = await _extraction(async_session, user_ids=[user.id])

        assert {line[RECORD_KEY] for line in lines[1:]} == {
            "lia.decisions",
            "lia.actions",
            "lia.consultations",
            "lia.inference",
            "lia.integrity",
        }

    async def test_the_header_counts_each_of_them(
        self, async_session: AsyncSession, user: User
    ) -> None:
        await _populate(async_session, user, at=_START)

        header = (await _extraction(async_session, user_ids=[user.id]))[0]

        assert all(source["lines"] == 1 for source in header["sources"].values())
        assert header["complete"] is True

    async def test_the_inference_line_carries_what_was_SENT(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """Lot 7, read back through lot 9: the parameters survive the whole
        path — callback vocabulary, column, contract, extraction."""
        await _populate(async_session, user, at=_START)

        lines = await _extraction(async_session, user_ids=[user.id])
        inference = next(line for line in lines[1:] if line[RECORD_KEY] == "lia.inference")

        assert inference["provider"] == "openai"
        assert inference["temperature"] == 0.3
        assert inference["params_digest"] == "d" * 64


class TestThePeriodFiltersAllFiveTheSameWay:
    async def test_a_window_excludes_what_falls_outside_it(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """Five tables, five differently named timestamp columns. A period that
        filtered four of them would produce a file whose sources describe
        different windows — and nothing in it would say so."""
        await _populate(async_session, user, at=_START)
        await _populate(async_session, user, at=_START + timedelta(hours=1))

        header = (
            await _extraction(
                async_session, user_ids=[user.id], since=_START + timedelta(minutes=30)
            )
        )[0]

        assert all(
            source["lines"] == 1 for source in header["sources"].values()
        ), f"a source ignored the period: {header['sources']}"


class TestNothingIdentifyingLeavesTheInstance:
    async def test_no_raw_account_id_anywhere_in_the_file(
        self, async_session: AsyncSession, user: User
    ) -> None:
        await _populate(async_session, user, at=_START)

        lines = await _extraction(async_session, user_ids=[user.id])

        assert str(user.id) not in json.dumps(lines)

    async def test_the_action_wording_never_leaves(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """``label`` is the one column that names people."""
        await _populate(async_session, user, at=_START)

        lines = await _extraction(async_session, user_ids=[user.id])

        for line in lines[1:]:
            assert "label" not in line

    async def test_the_correlation_SURVIVES_the_pseudonymisation(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """Identity must not survive; correlation must — otherwise the file
        cannot show which effects belong to which turn."""
        await _populate(async_session, user, at=_START)

        lines = await _extraction(async_session, user_ids=[user.id])
        runs = {line["run_id"] for line in lines[1:] if line.get("run_id")}

        assert len(runs) == 1, "one turn read as several"
        assert "run-90" not in runs, "a raw correlation id left in the clear"
