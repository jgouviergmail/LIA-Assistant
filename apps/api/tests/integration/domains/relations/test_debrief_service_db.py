"""The debrief's freshness contract, end to end against real PostgreSQL.

The rules under test are the ones that cost money when they are wrong: how
often an LLM call happens, whose day decides "today", and what survives a
failure. Each is asserted on the CALL COUNT as well as the stored row —
a rule that produces the right row while paying twice is not the rule.

Only two seams are stubbed: the evidence assembly (it would reach connectors)
and the model itself. Everything between them is real, including the claim.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.core.llm_usage import LLMUsage
from src.domains.relations.debrief import service as service_module
from src.domains.relations.debrief.models import DebriefState
from src.domains.relations.debrief.repository import RelationDebriefRepository
from src.domains.relations.debrief.schemas import DebriefBody, DebriefStatus
from src.domains.relations.debrief.service import RelationDebriefService
from src.domains.relations.schemas import IdentityConfidence, RelationDetail

pytestmark = pytest.mark.integration

PERSON = "Gérard Dupont"
KEY = "gerard dupont"

USAGE = LLMUsage(
    tokens_in=1234, tokens_out=567, tokens_cache=0, cost_eur=0.0021, model_name="gpt-4.1-mini"
)

BODY = DebriefBody(
    headline="Vous lui devez une réponse.",
    where_we_stand="Deux échanges cette semaine.",
    open_points=["Répondre au devis"],
    suggested_next_step=None,
    notable_facts=[],
)


def _detail() -> RelationDetail:
    return RelationDetail(
        display_name=PERSON,
        identity_confidence=IdentityConfidence.EXACT,
        open_loops=[],
        open_loops_total=0,
        recent_calls=[],
        recent_calls_total=0,
        memories=[],
        memories_total=0,
        peer_messages=[],
        peer_messages_total=0,
        peer_link=None,
        is_favorite=False,
        is_peer=False,
    )


def _evidence(blocks: dict | None = None) -> SimpleNamespace:
    """A stand-in for OverviewEvidence — only three attributes are read."""
    return SimpleNamespace(
        detail=_detail(),
        blocks=blocks if blocks is not None else {"open_commitments": [{"subject": "devis"}]},
        unavailable=["emails"],
    )


@pytest.fixture
async def maker(async_engine):
    """Sessions of our own.

    The service claims through ``get_db_context()`` — its OWN connection, on
    purpose, because the claim must be committed before the LLM call. The
    suite's shared ``async_session`` runs inside a transaction it rolls back,
    so a user created there is invisible to that connection and the row it
    writes is invisible here. This test therefore owns its data end to end.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(async_engine, expire_on_commit=False)


@pytest.fixture
async def reader(maker):
    """One active user with a timezone, owning the debriefs under test."""
    from sqlalchemy import delete

    from src.domains.users.models import User

    user = User(
        email=f"debrief-{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Debrief Reader",
        language="fr",
        timezone="Europe/Paris",
    )
    async with maker() as session:
        session.add(user)
        await session.commit()
    yield user
    async with maker() as session:
        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()


async def _save(maker, user) -> None:
    """Persist a change to the reader on the connection the service reads."""
    async with maker() as session:
        await session.merge(user)
        await session.commit()


async def _stored(maker, user_id):
    """Read the debrief row back on the same connection the service wrote it."""
    async with maker() as session:
        return await RelationDebriefRepository(session).get(user_id, KEY)


def _stubs(*, evidence=None, body=BODY, write_error: Exception | None = None):
    """Patch the two seams: the evidence assembly and the model."""
    ev = evidence if evidence is not None else _evidence()
    # A real ``LLMUsage``, never a stand-in: the service stores it, so a fake
    # that merely carries the same attribute names would pass here and fail on
    # the one call that matters.
    write = AsyncMock(
        return_value=(body, USAGE),
        side_effect=write_error,
    )
    return (
        patch.object(
            service_module,
            "build_overview_evidence",
            AsyncMock(
                return_value=ev,
                side_effect=ev if isinstance(ev, BaseException) else None,
            ),
        ),
        patch.object(service_module, "write_debrief", write),
        patch.object(service_module, "overview_payload", lambda e: {"person": PERSON, **e.blocks}),
        write,
    )


class TestOnceADay:
    """The rule the whole feature rests on, asserted on the CALL COUNT."""

    async def test_the_second_build_of_the_day_calls_no_model(self, maker, reader) -> None:
        service = RelationDebriefService(reader.id)
        p_ev, p_write, p_payload, write = _stubs()
        with p_ev, p_write, p_payload:
            first = await service.build(PERSON)
            second = await service.build(PERSON)

        assert first.status is DebriefStatus.READY
        assert second.status is DebriefStatus.READY
        assert write.await_count == 1

    async def test_a_read_never_builds(self, maker, reader) -> None:
        service = RelationDebriefService(reader.id)
        p_ev, p_write, p_payload, write = _stubs()
        with p_ev, p_write, p_payload:
            absent = await service.read(PERSON)
        assert absent.status is DebriefStatus.ABSENT
        assert write.await_count == 0


class TestWhoseDayDecides:
    """ "Once a day" is a promise about the READER's day, never about UTC."""

    async def test_the_local_date_is_stored_not_the_utc_one(self, maker, reader) -> None:
        # 23:30 UTC on the 7th is already the 8th in Auckland: a UTC boundary
        # would file this debrief under the wrong day for that reader.
        reader.timezone = "Pacific/Auckland"
        await _save(maker, reader)

        moment = datetime(2026, 9, 7, 23, 30, tzinfo=UTC)
        service = RelationDebriefService(reader.id)
        p_ev, p_write, p_payload, _ = _stubs()
        with p_ev, p_write, p_payload, patch.object(service_module, "datetime") as clock:
            clock.now.side_effect = lambda tz=None: moment.astimezone(tz) if tz else moment
            await service.build(PERSON)

        stored = await _stored(maker, reader.id)
        assert stored is not None
        assert stored.generated_for.isoformat() == "2026-09-08"


class TestWhatMakesARebuildLegitimate:
    """A stored text contradicting the reader's own settings must not survive."""

    async def test_a_language_change_writes_a_new_debrief(self, maker, reader) -> None:
        service = RelationDebriefService(reader.id)
        p_ev, p_write, p_payload, write = _stubs()
        with p_ev, p_write, p_payload:
            await service.build(PERSON)
            reader.language = "en"
            await _save(maker, reader)
            await service.build(PERSON)

        assert write.await_count == 2

    async def test_a_scope_change_writes_a_new_debrief(self, maker, reader) -> None:
        service = RelationDebriefService(reader.id)
        p_ev, p_write, p_payload, write = _stubs()
        with p_ev, p_write, p_payload:
            await service.build(PERSON)
            reader.relation_overview_scope = {"sections": ["calls"], "max_items": 3}
            await _save(maker, reader)
            await service.build(PERSON)

        assert write.await_count == 2


class TestAVerifiedNoChangeCostsNothing:
    """The digest earns its keep exactly once: with the evidence in hand."""

    async def test_a_forced_rebuild_over_identical_evidence_calls_no_model(
        self, maker, reader
    ) -> None:
        service = RelationDebriefService(reader.id)
        p_ev, p_write, p_payload, write = _stubs()
        with p_ev, p_write, p_payload:
            first = await service.build(PERSON)
            again = await service.build(PERSON, force=True)

        assert write.await_count == 1
        # The words keep the date they were written on: a rebuild that wrote
        # nothing must not claim a freshness nothing earned.
        assert again.generated_at == first.generated_at
        assert again.body is not None and again.body.headline == BODY.headline

    async def test_a_forced_rebuild_over_changed_evidence_does_call_the_model(
        self, maker, reader
    ) -> None:
        service = RelationDebriefService(reader.id)
        p_ev, p_write, p_payload, write = _stubs()
        with p_ev, p_write, p_payload:
            await service.build(PERSON)
        p_ev2, p_write2, p_payload2, write2 = _stubs(
            evidence=_evidence({"open_commitments": [{"subject": "autre chose"}]})
        )
        with p_ev2, p_write2, p_payload2:
            await service.build(PERSON, force=True)

        assert write.await_count == 1
        assert write2.await_count == 1


class TestNothingIsEverInvented:
    """No evidence is an ANSWER — and it costs no call."""

    async def test_an_empty_relationship_settles_empty_without_a_model(self, maker, reader) -> None:
        service = RelationDebriefService(reader.id)
        p_ev, p_write, p_payload, write = _stubs(evidence=_evidence({}))
        with p_ev, p_write, p_payload:
            result = await service.build(PERSON)

        assert result.status is DebriefStatus.EMPTY
        assert result.body is None
        assert write.await_count == 0

    async def test_a_model_failure_settles_failed_and_never_a_half_body(
        self, maker, reader
    ) -> None:
        service = RelationDebriefService(reader.id)
        p_ev, p_write, p_payload, _ = _stubs(write_error=ValueError("schema refused"))
        with p_ev, p_write, p_payload:
            result = await service.build(PERSON)

        assert result.status is DebriefStatus.FAILED
        assert result.body is None
        stored = await _stored(maker, reader.id)
        assert stored is not None and stored.state is DebriefState.FAILED

    async def test_an_unreadable_relationship_settles_failed(self, maker, reader) -> None:
        from src.domains.relations.overview import OverviewEvidenceUnavailable

        service = RelationDebriefService(reader.id)
        p_ev, p_write, p_payload, write = _stubs(evidence=OverviewEvidenceUnavailable(PERSON))
        with p_ev, p_write, p_payload:
            result = await service.build(PERSON)

        assert result.status is DebriefStatus.FAILED
        assert write.await_count == 0


class TestAFailedRebuildKeepsWhatStood:
    """The end-to-end version of the repository guarantee."""

    async def test_the_previous_debrief_survives_a_failed_refresh(self, maker, reader) -> None:
        service = RelationDebriefService(reader.id)
        p_ev, p_write, p_payload, _ = _stubs()
        with p_ev, p_write, p_payload:
            first = await service.build(PERSON)

        p_ev2, p_write2, p_payload2, _ = _stubs(
            evidence=_evidence({"open_commitments": [{"subject": "neuf"}]}),
            write_error=RuntimeError("provider down"),
        )
        with p_ev2, p_write2, p_payload2:
            after = await service.build(PERSON, force=True)

        assert after.status is DebriefStatus.FAILED
        assert after.body is not None
        assert after.body.headline == BODY.headline
        assert after.generated_at == first.generated_at


class TestTheAccountsOwnSwitch:
    """A feature the reader turned off is working as asked, never an error."""

    async def test_the_toggle_off_builds_nothing_and_says_so(self, maker, reader) -> None:
        reader.relation_debrief_enabled = False
        await _save(maker, reader)

        service = RelationDebriefService(reader.id)
        p_ev, p_write, p_payload, write = _stubs()
        with p_ev, p_write, p_payload:
            built = await service.build(PERSON)
            read = await service.read(PERSON)

        assert built.status is DebriefStatus.DISABLED
        assert read.status is DebriefStatus.DISABLED
        assert write.await_count == 0
        assert await _stored(maker, reader.id) is None

    async def test_the_instance_switch_off_builds_nothing(self, maker, reader) -> None:
        from src.core.config import settings

        service = RelationDebriefService(reader.id)
        p_ev, p_write, p_payload, write = _stubs()
        with p_ev, p_write, p_payload, patch.object(settings, "relation_debrief_enabled", False):
            built = await service.build(PERSON)

        assert built.status is DebriefStatus.DISABLED
        assert write.await_count == 0


class TestTheCostTravelsWithTheWords:
    """A reader who is charged for a synthesis may see what it cost.

    Stored beside the body so the two can never describe different builds — and
    it is a DISPLAY summary: ``token_usage_logs`` remains the account, and one
    of the five sources the Article-12 extraction composes.
    """

    async def test_a_written_debrief_carries_what_it_cost(self, maker, reader) -> None:
        service = RelationDebriefService(reader.id)
        p_ev, p_write, p_payload, _ = _stubs()
        with p_ev, p_write, p_payload:
            result = await service.build(PERSON)

        assert result.usage is not None
        assert (result.usage.tokens_in, result.usage.tokens_out) == (1234, 567)
        assert result.usage.cost_eur == 0.0021
        assert result.usage.model_name == "gpt-4.1-mini"

    async def test_an_unchanged_rebuild_keeps_the_cost_of_the_words(self, maker, reader) -> None:
        """No model ran, so the figure must stay the one that paid for the text."""
        service = RelationDebriefService(reader.id)
        p_ev, p_write, p_payload, write = _stubs()
        with p_ev, p_write, p_payload:
            first = await service.build(PERSON)
            again = await service.build(PERSON, force=True)

        assert write.await_count == 1
        assert again.usage == first.usage

    async def test_a_failed_refresh_keeps_the_previous_cost(self, maker, reader) -> None:
        service = RelationDebriefService(reader.id)
        p_ev, p_write, p_payload, _ = _stubs()
        with p_ev, p_write, p_payload:
            first = await service.build(PERSON)

        p_ev2, p_write2, p_payload2, _ = _stubs(
            evidence=_evidence({"open_commitments": [{"subject": "neuf"}]}),
            write_error=RuntimeError("provider down"),
        )
        with p_ev2, p_write2, p_payload2:
            after = await service.build(PERSON, force=True)

        assert after.usage == first.usage

    async def test_an_emptied_relationship_clears_the_cost_with_the_words(
        self, maker, reader
    ) -> None:
        """The old figure paid for text that no longer describes anything."""
        service = RelationDebriefService(reader.id)
        p_ev, p_write, p_payload, _ = _stubs()
        with p_ev, p_write, p_payload:
            await service.build(PERSON)

        p_ev2, p_write2, p_payload2, _ = _stubs(evidence=_evidence({}))
        with p_ev2, p_write2, p_payload2:
            emptied = await service.build(PERSON, force=True)

        assert emptied.status is DebriefStatus.EMPTY
        assert emptied.usage is None
        assert emptied.body is None
