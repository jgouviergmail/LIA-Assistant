"""Consolidation lifecycle against PostgreSQL: cooldown stamp, gauges, eligibility.

Covers the ADR-159 review findings that only a real database can pin:

- the cooldown stamp is written on EVERY completed run, including the very
  common one that decides there is nothing to maintain. Skipping it left the
  user permanently eligible and the consolidation LLM re-ran at every scheduler
  tick, forever;
- the portrait-age gauge and the scheduler's eligibility query share ONE
  predicate, so the gauge can never report a staleness the scheduler will not
  act on;
- the effectiveness gauges publish a value for every theme, including the
  absent ones — a theme with no series reads as "no data", a theme at 0 reads
  as "unreachable", and only the second is alertable.

The consolidation LLM is faked: these tests are about persistence and metrics,
not about what the model answers.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.journals import (
    consolidation_lifecycle,
    consolidation_service,
    consolidation_settlement,
    maintenance_actions,
)
from src.domains.journals.models import JournalEntry, JournalTheme
from src.domains.journals.repository import (
    JournalEntryRepository,
    consolidation_eligible_user_conditions,
)
from src.domains.users.models import User

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture(autouse=True)
def _offline_consolidation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep provider work offline while exercising the real SQL settlement."""

    def offline_llm(slot: str) -> SimpleNamespace:
        assert slot == "journal_consolidation"
        config = consolidation_service.get_llm_config_for_agent(
            consolidation_service.settings, slot
        )
        return SimpleNamespace(model_name=config.model)

    monkeypatch.setattr(consolidation_service, "get_llm", offline_llm)
    monkeypatch.setattr(consolidation_service.settings, "journals_enabled", True)
    monkeypatch.setattr(
        consolidation_lifecycle, "is_capability_enabled", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        maintenance_actions, "prepare_embeddings", AsyncMock(return_value=(None, None))
    )


@pytest.fixture
def _redirect_db_context(async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """Route ``get_db_context()`` to the test session.

    The consolidation service opens its OWN sessions, on purpose: it runs
    detached from any request. That makes it invisible to the per-test
    transaction, so a naive test asserts on a row the service never saw.

    Patch both source spellings and the lifecycle/source modules that bind the
    function at import time. Each sequential phase must see the fixture's rows,
    including source gates before the lease's first commit.
    """
    from src.domains.habits import portrait_source as habits_source
    from src.domains.interests import portrait_source as interests_source
    from src.domains.memories import portrait_source as memories_source
    from src.domains.relations.debrief import portrait_source as debriefs_source
    from src.infrastructure import database
    from src.infrastructure.database import session as database_session

    @asynccontextmanager
    async def _fake_ctx() -> AsyncIterator[AsyncSession]:
        yield async_session

    monkeypatch.setattr(database, "get_db_context", _fake_ctx)
    monkeypatch.setattr(database_session, "get_db_context", _fake_ctx)
    for module in (
        consolidation_lifecycle,
        consolidation_settlement,
        habits_source,
        interests_source,
        memories_source,
        debriefs_source,
    ):
        monkeypatch.setattr(module, "get_db_context", _fake_ctx)


async def _make_user(session: AsyncSession, **overrides: Any) -> User:
    """Insert a consolidation-eligible user, overridable field by field."""
    fields: dict[str, Any] = {
        "email": f"conso-{uuid.uuid4().hex[:8]}@example.com",
        "hashed_password": "x",
        "is_active": True,
        "journals_enabled": True,
        "journal_consolidation_enabled": True,
    }
    fields.update(overrides)
    user = User(**fields)
    session.add(user)
    await session.flush()
    return user


def _fake_llm(
    actions: list[dict[str, Any]] | None = None,
    portrait_claims: list[dict[str, Any]] | None = None,
) -> Any:
    """Build a stand-in for ``invoke_with_instrumentation``.

    The payload is serialised with ``json.dumps`` rather than interpolated:
    the consolidation answer is a JSON object whose braces would otherwise
    fight with any templating, and a test that silently produced invalid JSON
    would assert on the parser's empty fallback instead of on the service.
    """
    payload = json.dumps(
        {
            "actions": actions or [],
            "portrait_claims": portrait_claims,
        }
    )

    async def _call(**kwargs: Any) -> AIMessage:
        return AIMessage(content=payload)

    return _call


async def _make_conversation(session: AsyncSession, user: User) -> Conversation:
    """Insert the person's one conversation."""
    conversation = Conversation(user_id=user.id, title="c")
    session.add(conversation)
    await session.flush()
    return conversation


async def _make_message(
    session: AsyncSession,
    conversation: Conversation,
    *,
    role: str,
    content: str,
    at: datetime,
    hidden: bool = False,
) -> ConversationMessage:
    """Insert one row the way the repository writes it: `user` or `assistant`,
    hidden when it belongs to a run LIA ran alone (ADR-276)."""
    row = ConversationMessage(
        conversation_id=conversation.id, role=role, content=content, created_at=at, hidden=hidden
    )
    session.add(row)
    await session.flush()
    return row


async def _make_entry(session: AsyncSession, user: User, theme: str) -> JournalEntry:
    """Insert one active journal entry with the given theme."""
    entry = JournalEntry(
        user_id=user.id,
        theme=theme,
        title=f"t-{theme}",
        content="c",
        mood="reflective",
        status="active",
        source="conversation",
        char_count=1,
        level="L1",
    )
    session.add(entry)
    await session.flush()
    return entry


class TestPortraitSources:
    """The portrait reads nine records, and says which (2026-09-16 part B, ADR-343)."""

    async def test_the_prompt_carries_the_sections_and_the_portrait_its_provenance(
        self,
        async_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        _redirect_db_context: None,
    ) -> None:
        from src.domains.journals.portrait_sources import PortraitSourceBundle

        user = await _make_user(async_session, journal_last_consolidated_at=None)
        await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)
        bundle = PortraitSourceBundle(
            sections={
                "memories": (
                    "## LONG-TERM MEMORIES (2 of 2)\n"
                    "- [personal] [NEUTRE] Prefers comparing options before deciding (2026-09-01)"
                    "\n- [personal] [NEUTRE] Asks for concise responses (2026-09-02)"
                ),
                "interests": "",
                "habits": "## LEARNED HABITS\n- Usual activity: weekdays 08:00-10:00",
                "relation_debriefs": "",
            },
            provenance={
                "version": 1,
                "journal_entries": 1,
                "sources": {
                    "memories": {"status": "used", "used": 2, "total": 2},
                    "interests": {"status": "empty", "used": 0, "total": 0},
                    "habits": {"status": "used", "used": 1, "total": 1},
                    "relation_debriefs": {"status": "disabled", "used": 0, "total": 0},
                },
            },
        )

        async def _sections(*args: Any, **kwargs: Any) -> PortraitSourceBundle:
            return bundle

        monkeypatch.setattr(consolidation_service, "build_portrait_source_sections", _sections)
        prompts: list[str] = []
        claims = [
            {
                "facet": "posture",
                "text": (
                    "Je comprends que tu privilégies une décision éclairée par les alternatives. "
                    "Je dois donc rendre les options faciles à comparer dans nos échanges."
                ),
                "supports": [
                    {
                        "source": "memories",
                        "quote": (
                            "- [personal] [NEUTRE] Prefers comparing options before deciding "
                            "(2026-09-01)"
                        ),
                    }
                ],
                "placement": "brief",
            },
            {
                "facet": "context",
                "text": "Ton activité se concentre généralement en début de matinée les jours travaillés.",
                "supports": [
                    {"source": "habits", "quote": "- Usual activity: weekdays 08:00-10:00"}
                ],
                "placement": "full",
            },
        ]
        fake = _fake_llm(portrait_claims=claims)

        async def _capture(**kwargs: Any) -> AIMessage:
            prompts.append(str(kwargs["messages"]))
            return await fake(**kwargs)

        monkeypatch.setattr(consolidation_service, "invoke_with_instrumentation", _capture)

        await consolidation_service.consolidate_journals_for_user(
            user_id=user.id,
            personality_instruction=None,
            personality_code=None,
            user_language="fr",
        )

        assert len(prompts) == 1  # one generation; no semantic review any more
        assert "## LONG-TERM MEMORIES (2 of 2)" in prompts[0]
        assert "## LEARNED HABITS" in prompts[0]
        assert "## INTERESTS" not in prompts[0] and "## RELATIONSHIP DEBRIEFS" not in prompts[0]
        await async_session.refresh(user)
        # Each format is written from its own claims: the `full` one, the `brief` one.
        assert user.journal_portrait_full == claims[1]["text"]
        assert user.journal_portrait_brief == claims[0]["text"]
        assert "[personal]" not in user.journal_portrait_full
        assert "08:00" not in user.journal_portrait_full
        assert user.journal_portrait_sources is not None
        for key, value in bundle.provenance.items():
            assert user.journal_portrait_sources[key] == value
        assert user.journal_portrait_sources["journal_revision"] == user.journal_revision
        assert user.journal_portrait_sources["claims"] == claims
        from src.domains.journals.source_state import portrait_source_state

        assert user.journal_portrait_sources["source_state"] == await portrait_source_state(
            async_session, user
        )

    async def test_no_portrait_keeps_unverifiable_previous_words_stale(
        self,
        async_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        _redirect_db_context: None,
    ) -> None:
        from src.domains.journals.portrait_sources import PortraitSourceBundle

        previous = {"version": 1, "journal_entries": 3, "sources": {}}
        user = await _make_user(
            async_session,
            journal_last_consolidated_at=None,
            journal_portrait_full="Ancien portrait.",
            journal_portrait_sources=previous,
        )
        await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)

        async def _sections(*args: Any, **kwargs: Any) -> PortraitSourceBundle:
            return PortraitSourceBundle(
                sections=dict.fromkeys(
                    ("memories", "interests", "habits", "relation_debriefs"), ""
                ),
                provenance={"version": 1, "journal_entries": 1, "sources": {}},
            )

        monkeypatch.setattr(consolidation_service, "build_portrait_source_sections", _sections)
        monkeypatch.setattr(consolidation_service, "invoke_with_instrumentation", _fake_llm())

        await consolidation_service.consolidate_journals_for_user(
            user_id=user.id,
            personality_instruction=None,
            personality_code=None,
            user_language="fr",
        )

        await async_session.refresh(user)
        # The unverifiable words STAY (served stale) under their own provenance: it
        # keeps no revision, so they read as stale, and the follow-up is pending.
        from src.domains.journals.lifecycle import portrait_is_current

        assert user.journal_portrait_full == "Ancien portrait."
        assert user.journal_portrait_sources == {**previous, "portrait_pending": True}
        assert await portrait_is_current(async_session, user) is False

    async def test_no_portrait_preserves_already_current_words_and_their_provenance(
        self,
        async_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        _redirect_db_context: None,
    ) -> None:
        from src.domains.journals.source_state import portrait_source_state

        user = await _make_user(async_session)
        entry = await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)
        compiled_at = datetime.now(UTC)
        previous = {
            "version": 1,
            "journal_entries": 1,
            "sources": {},
            "journal_revision": user.journal_revision,
            "source_state": await portrait_source_state(async_session, user),
            "portrait_pending": False,
            "claims": [
                {
                    "facet": "interaction",
                    "text": "Une synthèse déjà approuvée.",
                    "supports": [{"source": f"journal:{entry.id}", "quote": entry.content}],
                    "placement": "brief",
                }
            ],
        }
        user.journal_portrait_full = user.journal_portrait_brief = "Une synthèse déjà approuvée."
        user.journal_portrait_compiled_at = compiled_at
        user.journal_portrait_sources = previous
        await async_session.flush()
        monkeypatch.setattr(consolidation_service, "invoke_with_instrumentation", _fake_llm())

        applied = await consolidation_service.consolidate_journals_for_user(
            user_id=user.id,
            personality_instruction=None,
            personality_code=None,
            user_language="fr",
        )

        assert applied == 0
        await async_session.refresh(user)
        assert user.journal_portrait_full == "Une synthèse déjà approuvée."
        assert user.journal_portrait_brief == "Une synthèse déjà approuvée."
        assert user.journal_portrait_compiled_at == compiled_at
        assert user.journal_portrait_sources == previous


class TestPortraitFollowUp:
    """Maintenance nominates one paced synthesis pass without self-citation or churn."""

    async def test_actual_mutation_needs_follow_up_then_stable_portrait_consumes_it(
        self,
        async_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        _redirect_db_context: None,
    ) -> None:
        user = await _make_user(async_session)
        entry = await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)
        corrected = "WHEN deleting email -> DO verify the selected identifiers before deletion."
        monkeypatch.setattr(
            consolidation_service,
            "invoke_with_instrumentation",
            _fake_llm(
                actions=[{"action": "update", "entry_id": str(entry.id), "content": corrected}]
            ),
        )

        arguments = {
            "user_id": user.id,
            "personality_instruction": None,
            "personality_code": None,
            "user_language": "fr",
            "manual": True,
        }
        assert await consolidation_service.consolidate_journals_for_user(**arguments) == 1
        await async_session.refresh(user)
        await async_session.refresh(entry)
        assert entry.content == corrected
        assert user.journal_consolidated_revision == user.journal_revision
        assert user.journal_portrait_sources["portrait_pending"] is True
        assert await consolidation_lifecycle.consolidation_needed(async_session, user) is True

        claims = [
            {
                "facet": "interaction",
                "text": (
                    "Pour les suppressions de courriels, je dois vérifier précisément "
                    "la sélection concernée avant de passer à l’action."
                ),
                "supports": [{"source": f"journal:{entry.id}", "quote": corrected}],
                "placement": "full",
            }
        ]
        monkeypatch.setattr(
            consolidation_service, "invoke_with_instrumentation", _fake_llm(portrait_claims=claims)
        )
        assert await consolidation_service.consolidate_journals_for_user(**arguments) == 0
        await async_session.refresh(user)
        assert user.journal_portrait_full == claims[0]["text"]
        assert user.journal_portrait_sources["portrait_pending"] is False
        assert await consolidation_lifecycle.consolidation_needed(async_session, user) is False

        stable_revision = user.journal_revision
        stable_full, stable_brief = user.journal_portrait_full, user.journal_portrait_brief
        stable_compiled_at = user.journal_portrait_compiled_at
        monkeypatch.setattr(
            consolidation_service,
            "invoke_with_instrumentation",
            _fake_llm(
                actions=[{"action": "update", "entry_id": str(entry.id), "title": entry.title}]
            ),
        )
        assert await consolidation_service.consolidate_journals_for_user(**arguments) == 0
        await async_session.refresh(user)
        assert user.journal_revision == stable_revision
        assert user.journal_portrait_full == stable_full
        assert user.journal_portrait_brief == stable_brief
        assert user.journal_portrait_compiled_at == stable_compiled_at
        assert user.journal_portrait_sources["portrait_pending"] is False
        assert await consolidation_lifecycle.consolidation_needed(async_session, user) is False

    async def test_omitted_portrait_keeps_actual_maintenance_pending(
        self,
        async_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        _redirect_db_context: None,
    ) -> None:
        user = await _make_user(async_session)
        entry = await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)
        arguments = {
            "user_id": user.id,
            "personality_instruction": None,
            "personality_code": None,
            "user_language": "fr",
            "manual": True,
        }
        monkeypatch.setattr(
            consolidation_service,
            "invoke_with_instrumentation",
            _fake_llm(
                actions=[{"action": "update", "entry_id": str(entry.id), "content": "New rule."}]
            ),
        )
        assert await consolidation_service.consolidate_journals_for_user(**arguments) == 1
        await async_session.refresh(user)
        assert user.journal_portrait_sources["portrait_pending"] is True

        monkeypatch.setattr(consolidation_service, "invoke_with_instrumentation", _fake_llm())
        assert await consolidation_service.consolidate_journals_for_user(**arguments) == 0
        await async_session.refresh(user)
        assert user.journal_consolidated_revision == user.journal_revision
        assert user.journal_portrait_sources["portrait_pending"] is True
        assert await consolidation_lifecycle.consolidation_needed(async_session, user) is True

    async def test_old_extractive_policy_is_not_current_and_no_output_cannot_bless_it(
        self,
        async_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        _redirect_db_context: None,
    ) -> None:
        from src.domains.journals.lifecycle import portrait_is_current
        from src.domains.journals.source_state import portrait_source_state

        user = await _make_user(async_session)
        await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)
        old_state = await portrait_source_state(async_session, user)
        old_state["_rendering"]["portrait_policy"] = "extractive-before-natural-review"
        user.journal_portrait_full = "[memories] [personal] A copied fact."
        user.journal_portrait_brief = "[learnings] WHEN deleting email -> DO verify identifiers."
        user.journal_portrait_compiled_at = datetime.now(UTC)
        user.journal_consolidated_revision = user.journal_revision
        user.journal_portrait_sources = {
            "version": 1,
            "journal_entries": 1,
            "sources": {},
            "journal_revision": user.journal_revision,
            "source_state": old_state,
            "portrait_pending": False,
        }
        await async_session.flush()
        assert await portrait_is_current(async_session, user) is False
        assert await consolidation_lifecycle.consolidation_needed(async_session, user) is True

        monkeypatch.setattr(consolidation_service, "invoke_with_instrumentation", _fake_llm())
        assert (
            await consolidation_service.consolidate_journals_for_user(
                user.id,
                personality_instruction=None,
                personality_code=None,
                user_language="fr",
                manual=True,
            )
            == 0
        )
        await async_session.refresh(user)
        # The old-policy words stay under their OLD provenance (a rewritten one would
        # bless them as current), flagged stale by the moved policy, until replaced.
        assert user.journal_portrait_full == "[memories] [personal] A copied fact."
        assert user.journal_portrait_compiled_at is not None
        assert user.journal_portrait_sources["source_state"] == old_state
        assert await portrait_is_current(async_session, user) is False
        assert user.journal_portrait_sources["portrait_pending"] is True
        assert await consolidation_lifecycle.consolidation_needed(async_session, user) is True

        monkeypatch.setattr(
            consolidation_service, "invoke_with_instrumentation", _fake_llm(portrait_claims=[])
        )
        assert (
            await consolidation_service.consolidate_journals_for_user(
                user.id,
                personality_instruction=None,
                personality_code=None,
                user_language="fr",
                manual=True,
            )
            == 0
        )
        await async_session.refresh(user)
        assert user.journal_portrait_sources["portrait_pending"] is False
        assert await consolidation_lifecycle.consolidation_needed(async_session, user) is False


class TestExecutionPreferences:
    """Stale caller arguments cannot reopen an opted-out history or old limits."""

    async def test_current_account_preferences_override_stale_caller_arguments(
        self,
        async_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        _redirect_db_context: None,
    ) -> None:
        user = await _make_user(
            async_session,
            language="en",
            journal_consolidation_with_history=False,
            journal_max_total_chars=4000,
            journal_max_entry_chars=200,
        )
        await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)
        history = AsyncMock(side_effect=AssertionError("Opted-out history must not be read"))
        conversation = AsyncMock(wraps=consolidation_service._conversation_section)
        monkeypatch.setattr(consolidation_service, "_load_conversation_history", history)
        monkeypatch.setattr(consolidation_service, "_conversation_section", conversation)
        prompts: list[str] = []
        fake = _fake_llm()

        async def capture(**kwargs: Any) -> AIMessage:
            prompts.append(str(kwargs["messages"]))
            return await fake(**kwargs)

        monkeypatch.setattr(consolidation_service, "invoke_with_instrumentation", capture)
        assert (
            await consolidation_service.consolidate_journals_for_user(
                user.id,
                personality_instruction=None,
                personality_code=None,
                user_language="fr",
                consolidation_with_history=True,
                max_total_chars=5000,
                max_entry_chars=500,
                last_consolidated_at=datetime.now(UTC) - timedelta(days=200),
                manual=True,
            )
            == 0
        )
        history.assert_not_awaited()
        conversation.assert_awaited_once_with(user.id, None, enabled=False)
        assert len(prompts) == 1
        assert "Write in English." in prompts[0]
        assert "Write in French." not in prompts[0]
        assert "max 200 chars" in prompts[0] and "max 500 chars" not in prompts[0]
        assert "/ 4000 characters used." in prompts[0]


class TestSourceFreshness:
    """A change in a portrait source makes the account eligible again (part B)."""

    @pytest.fixture(autouse=True)
    def _sources_installed(self) -> None:
        """The boot installs the four probes; a test process must do the same.

        Without them the query falls back to journal-only work — never MORE
        eligible than before part B, which is the safe side — so the probes
        must be present for this class to test anything.
        """
        import src.domains.habits.portrait_source  # noqa: F401
        import src.domains.interests.portrait_source  # noqa: F401
        import src.domains.memories.portrait_source  # noqa: F401
        import src.domains.relations.debrief.portrait_source  # noqa: F401

    async def _eligible(self, session: AsyncSession) -> list[uuid.UUID]:
        from src.domains.journals.repository import build_consolidation_eligible_users_query

        query = build_consolidation_eligible_users_query(
            cooldown_threshold=datetime.now(UTC) + timedelta(seconds=1), min_entries=1
        )
        return [row.id for row in (await session.execute(query)).scalars().all()]

    async def test_a_memory_written_after_the_stamp_reopens_the_account(
        self, async_session: AsyncSession
    ) -> None:
        from src.domains.memories.models import Memory

        stamp = datetime.now(UTC) - timedelta(hours=10)
        user = await _make_user(async_session, journal_last_consolidated_at=stamp)
        entry = await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)
        # The entry predates the stamp: no work from the journal itself.
        entry.updated_at = stamp - timedelta(hours=1)
        await async_session.flush()
        assert user.id not in await self._eligible(async_session)

        async_session.add(
            Memory(user_id=user.id, content="I moved to Lyon", category="personal", char_count=15)
        )
        await async_session.flush()

        assert user.id in await self._eligible(async_session)

    async def test_an_account_with_no_entry_but_a_fresh_interest_is_eligible(
        self, async_session: AsyncSession
    ) -> None:
        from src.domains.interests.models import UserInterest

        stamp = datetime.now(UTC) - timedelta(hours=10)
        user = await _make_user(async_session, journal_last_consolidated_at=stamp)
        assert user.id not in await self._eligible(async_session)
        async_session.add(
            UserInterest(
                user_id=user.id,
                topic="Rust embarqué",
                category="technology",
                last_mentioned_at=datetime.now(UTC),
            )
        )
        await async_session.flush()

        assert user.id in await self._eligible(async_session)

    async def test_a_consolidation_s_own_run_never_retriggers_itself(
        self, async_session: AsyncSession
    ) -> None:
        """The stamp is written after the run; a source untouched since stays quiet."""
        from src.domains.memories.models import Memory

        user = await _make_user(async_session, journal_last_consolidated_at=None)
        async_session.add(
            Memory(user_id=user.id, content="I moved to Lyon", category="personal", char_count=15)
        )
        await async_session.flush()
        assert user.id in await self._eligible(async_session)
        user.journal_last_consolidated_at = datetime.now(UTC) + timedelta(seconds=5)
        await async_session.flush()
        assert user.id not in await self._eligible(async_session)


class TestCooldownStamp:
    """`journal_last_consolidated_at` gates the scheduler — it must always move."""

    async def test_stamp_helper_writes_the_timestamp(
        self, async_session: AsyncSession, _redirect_db_context: None
    ) -> None:
        """The helper persists a fresh UTC timestamp on the user row."""
        user = await _make_user(async_session, journal_last_consolidated_at=None)

        await consolidation_service._stamp_last_consolidated(user.id)

        await async_session.refresh(user)
        assert user.journal_last_consolidated_at is not None
        assert user.journal_last_consolidated_at.tzinfo is not None
        age = datetime.now(UTC) - user.journal_last_consolidated_at
        assert age < timedelta(minutes=5)

    async def test_stamp_helper_is_a_noop_on_an_unknown_user(
        self, _redirect_db_context: None
    ) -> None:
        """A user deleted between the run and the stamp must not raise.

        The stamp runs after the LLM call, in its own session; the row can be
        gone by then, and a raise there would be logged as a whole-run failure.
        """
        await consolidation_service._stamp_last_consolidated(uuid.uuid4())

    async def test_run_with_no_actions_still_consumes_the_cooldown(
        self,
        async_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        _redirect_db_context: None,
    ) -> None:
        """The regression this whole finding is about.

        A consolidation whose LLM answer contains no maintenance action is the
        NORMAL outcome — the prompt explicitly says so. Before the fix it
        returned before stamping, so the scheduler's cooldown gate never closed
        and the run repeated at every tick.
        """
        user = await _make_user(async_session, journal_last_consolidated_at=None)
        await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)

        monkeypatch.setattr(consolidation_service, "invoke_with_instrumentation", _fake_llm())

        applied = await consolidation_service.consolidate_journals_for_user(
            user_id=user.id,
            personality_instruction=None,
            personality_code=None,
            user_language="fr",
        )

        assert applied == 0
        await async_session.refresh(user)
        assert user.journal_last_consolidated_at is not None, (
            "a no-action run must still consume the cooldown, otherwise the "
            "scheduler re-runs the consolidation LLM at every tick forever"
        )

    async def test_stamped_user_is_no_longer_eligible_within_the_cooldown(
        self, async_session: AsyncSession
    ) -> None:
        """The stamp actually closes the scheduler's gate.

        Pins the link between the column and the eligibility predicate: a test
        that only asserted "the column moved" would pass even if the scheduler
        read a different one.
        """
        cooldown_threshold = datetime.now(UTC) - timedelta(hours=6)
        fresh = await _make_user(async_session, journal_last_consolidated_at=datetime.now(UTC))
        stale = await _make_user(
            async_session, journal_last_consolidated_at=datetime.now(UTC) - timedelta(hours=12)
        )
        await async_session.flush()

        eligible = (
            (
                await async_session.execute(
                    select(User.id).where(
                        and_(
                            *consolidation_eligible_user_conditions(),
                            (
                                User.journal_last_consolidated_at.is_(None)
                                | (User.journal_last_consolidated_at < cooldown_threshold)
                            ),
                        )
                    )
                )
            )
            .scalars()
            .all()
        )

        assert stale.id in eligible
        assert fresh.id not in eligible


class TestTheConsolidationIsOneActOfLia:
    """One run, one row in the decision register (ADR-263 amendment 2026-09-27).

    Measured on dev over twelve days: 84 consolidations billed their model call
    under a run of their own and every embedding it wrote under yet another —
    82 ``embed_*`` runs — and not one of them reached the decision register.
    """

    async def test_it_is_filed_once_as_lias_own_initiative_under_its_run(
        self,
        async_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        _redirect_db_context: None,
    ) -> None:
        from src.domains.agents.effects.models import AgentDecision, DecisionOutcome, EffectSource

        user = await _make_user(async_session, journal_last_consolidated_at=None)
        entry = await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)
        billed: list[str | None] = []
        embedded: list[str | None] = []

        async def persist(**kwargs: Any) -> None:
            billed.append(kwargs.get("parent_run_id"))

        def embedding_context(**kwargs: Any) -> None:
            embedded.append(kwargs.get("run_id"))

        monkeypatch.setattr(consolidation_service, "_persist_journal_tokens", persist)
        monkeypatch.setattr(
            "src.infrastructure.llm.embedding_context.set_embedding_context", embedding_context
        )
        monkeypatch.setattr(
            consolidation_service,
            "invoke_with_instrumentation",
            _fake_llm(actions=[{"action": "delete", "entry_id": str(entry.id)}]),
        )

        await consolidation_service.consolidate_journals_for_user(
            user_id=user.id,
            personality_instruction=None,
            personality_code=None,
            user_language="fr",
        )

        decision = (
            await async_session.execute(
                select(AgentDecision).where(AgentDecision.user_id == user.id)
            )
        ).scalar_one()
        assert decision.route == "journal_consolidation"
        assert decision.source is EffectSource.PROACTIVE
        assert decision.outcome is DecisionOutcome.ANSWERED
        assert decision.execution_mode == "direct"
        assert billed == [decision.run_id], "the model call billed apart from the act"
        assert embedded == [decision.run_id], "the embeddings billed apart from the act"

    async def test_a_consolidation_that_broke_after_its_model_call_is_filed_failed(
        self,
        async_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        _redirect_db_context: None,
    ) -> None:
        from src.domains.agents.effects.models import AgentDecision, DecisionOutcome

        user = await _make_user(async_session, journal_last_consolidated_at=None)
        await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)
        billed: list[str | None] = []

        async def persist(**kwargs: Any) -> None:
            billed.append(kwargs.get("parent_run_id"))
            raise RuntimeError("the ledger went away")

        monkeypatch.setattr(consolidation_service, "_persist_journal_tokens", persist)
        monkeypatch.setattr(consolidation_service, "invoke_with_instrumentation", _fake_llm())

        applied = await consolidation_service.consolidate_journals_for_user(
            user_id=user.id,
            personality_instruction=None,
            personality_code=None,
            user_language="fr",
        )

        assert applied == 0
        decision = (
            await async_session.execute(
                select(AgentDecision).where(AgentDecision.user_id == user.id)
            )
        ).scalar_one()
        assert decision.outcome is DecisionOutcome.FAILED
        assert decision.route == "journal_consolidation"
        assert billed == [decision.run_id], "failed billing still belongs to the recorded act"

    async def test_a_model_call_that_never_answered_files_nothing(
        self,
        async_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        _redirect_db_context: None,
    ) -> None:
        """No answer, no known spend: no turn (the register's own rule)."""
        from src.domains.agents.effects.models import AgentDecision

        user = await _make_user(async_session, journal_last_consolidated_at=None)
        await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)

        async def refuse(**_kwargs: Any) -> AIMessage:
            raise RuntimeError("provider down")

        monkeypatch.setattr(consolidation_service, "invoke_with_instrumentation", refuse)

        await consolidation_service.consolidate_journals_for_user(
            user_id=user.id,
            personality_instruction=None,
            personality_code=None,
            user_language="fr",
        )

        rows = (
            await async_session.execute(
                select(AgentDecision).where(AgentDecision.user_id == user.id)
            )
        ).all()
        assert rows == []


class TestConsolidationDeletesCounter:
    """The pruning counter must actually count — it feeds a live Grafana panel."""

    async def test_applied_deletes_increment_the_counter(
        self,
        async_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        _redirect_db_context: None,
    ) -> None:
        """A delete applied by the consolidation shows up in the metric.

        ``journal_consolidation_deletes_total`` replaced a counter that was
        declared, dashboarded and never incremented — its panel had read
        "No data" since it shipped. Wiring it without an oracle would have
        reproduced exactly that defect, one name later.
        """
        from src.infrastructure.observability.metrics_journals import (
            journal_consolidation_deletes_total,
        )

        user = await _make_user(async_session)
        doomed = await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)
        keeper = await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)
        entry_id = str(doomed.id)

        monkeypatch.setattr(
            consolidation_service,
            "invoke_with_instrumentation",
            _fake_llm(actions=[{"action": "delete", "entry_id": entry_id}]),
        )

        before = journal_consolidation_deletes_total._value.get()
        applied = await consolidation_service.consolidate_journals_for_user(
            user_id=user.id,
            personality_instruction=None,
            personality_code=None,
            user_language="fr",
        )
        after = journal_consolidation_deletes_total._value.get()

        assert applied == 1
        assert after - before == 1.0, (
            "the consolidation deleted an entry but the counter did not move — "
            "the Grafana panel would read 'No data' exactly like its predecessor"
        )

        remaining = (
            (
                await async_session.execute(
                    select(JournalEntry.id).where(JournalEntry.user_id == user.id)
                )
            )
            .scalars()
            .all()
        )
        assert remaining == [keeper.id]

    async def test_a_run_without_deletes_leaves_the_counter_alone(
        self,
        async_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        _redirect_db_context: None,
    ) -> None:
        """Only real deletions count — otherwise the pruning signal is noise."""
        from src.infrastructure.observability.metrics_journals import (
            journal_consolidation_deletes_total,
        )

        user = await _make_user(async_session)
        entry = await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)
        entry_id = str(entry.id)

        monkeypatch.setattr(
            consolidation_service,
            "invoke_with_instrumentation",
            _fake_llm(actions=[{"action": "update", "entry_id": entry_id, "title": "reworded"}]),
        )

        before = journal_consolidation_deletes_total._value.get()
        applied = await consolidation_service.consolidate_journals_for_user(
            user_id=user.id,
            personality_instruction=None,
            personality_code=None,
            user_language="fr",
        )

        assert applied == 1
        assert journal_consolidation_deletes_total._value.get() == before


class TestEligibilityPredicate:
    """One predicate, shared by the scheduler and the portrait-age gauge."""

    @pytest.mark.parametrize(
        "field,value",
        [
            ("journals_enabled", False),
            ("journal_consolidation_enabled", False),
            ("is_active", False),
        ],
    )
    async def test_opted_out_user_is_excluded(
        self, async_session: AsyncSession, field: str, value: bool
    ) -> None:
        """A user who cannot be consolidated is not eligible."""
        user = await _make_user(async_session, **{field: value})
        await async_session.flush()

        eligible = (
            (
                await async_session.execute(
                    select(User.id).where(and_(*consolidation_eligible_user_conditions()))
                )
            )
            .scalars()
            .all()
        )
        assert user.id not in eligible

    async def test_soft_deleted_user_is_excluded(self, async_session: AsyncSession) -> None:
        """A soft-deleted user keeps their rows but must never be processed."""
        user = await _make_user(async_session, deleted_at=datetime.now(UTC))
        await async_session.flush()

        eligible = (
            (
                await async_session.execute(
                    select(User.id).where(and_(*consolidation_eligible_user_conditions()))
                )
            )
            .scalars()
            .all()
        )
        assert user.id not in eligible


class TestPortraitAgeGauge:
    """The staleness gauge must only measure what the scheduler still owns."""

    async def test_ignores_users_without_a_compiled_portrait(
        self, async_session: AsyncSession
    ) -> None:
        """Never compiled is not stale — it is a different, separate signal."""
        await _make_user(async_session, journal_portrait_compiled_at=None)
        await async_session.flush()

        age = await JournalEntryRepository(async_session).compute_max_portrait_age_hours()
        assert age == 0.0

    async def test_reports_the_oldest_eligible_portrait(self, async_session: AsyncSession) -> None:
        """The gauge is a max over eligible users."""
        await _make_user(
            async_session,
            journal_portrait_compiled_at=datetime.now(UTC) - timedelta(hours=3),
        )
        await _make_user(
            async_session,
            journal_portrait_compiled_at=datetime.now(UTC) - timedelta(hours=30),
        )
        await async_session.flush()

        age = await JournalEntryRepository(async_session).compute_max_portrait_age_hours()
        assert 29.0 < age < 31.0

    async def test_ignores_an_ineligible_user_however_stale(
        self, async_session: AsyncSession
    ) -> None:
        """A user the scheduler will never pick up must not pin the gauge.

        Without this filter a single soft-deleted account froze the gauge at an
        ever-growing value, so the staleness alert could never clear and became
        unactionable — the exact opposite of the gauge's purpose.
        """
        await _make_user(
            async_session,
            journal_portrait_compiled_at=datetime.now(UTC) - timedelta(hours=2),
        )
        await _make_user(
            async_session,
            deleted_at=datetime.now(UTC),
            journal_portrait_compiled_at=datetime.now(UTC) - timedelta(days=400),
        )
        await async_session.flush()

        age = await JournalEntryRepository(async_session).compute_max_portrait_age_hours()
        assert age < 24.0, "a soft-deleted user must not pin the staleness gauge"


class TestThemeDistribution:
    """The gauge that would have caught the ADR-159 defect on day one."""

    async def test_counts_active_entries_per_theme(self, async_session: AsyncSession) -> None:
        """Themes present in the corpus are counted."""
        user = await _make_user(async_session)
        await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)
        await _make_entry(async_session, user, JournalTheme.LEARNINGS.value)
        await _make_entry(async_session, user, JournalTheme.SELF_REFLECTION.value)
        await async_session.flush()

        counts = await JournalEntryRepository(async_session).count_by_theme_global()
        assert counts[JournalTheme.LEARNINGS.value] >= 2
        assert counts[JournalTheme.SELF_REFLECTION.value] >= 1

    async def test_archived_entries_are_excluded(self, async_session: AsyncSession) -> None:
        """Only ACTIVE entries shape the corpus."""
        user = await _make_user(async_session)
        entry = await _make_entry(async_session, user, JournalTheme.IDEAS_ANALYSES.value)
        entry.status = "archived"
        await async_session.flush()

        counts = await JournalEntryRepository(async_session).count_by_theme_global()
        assert counts.get(JournalTheme.IDEAS_ANALYSES.value, 0) == 0


class TestTheConversationReadsSpeakTheRepositorysVocabulary:
    """Both enrichment reads filtered `human`/`ai` while the repository writes
    `user`/`assistant` — dead since v1.7.0, invisible to unit tests that stub
    the session — read the UTC hour as the person's, and read a run's hidden
    rows as the person's words. Proven on PostgreSQL."""

    @pytest.mark.usefixtures("_redirect_db_context")
    async def test_the_history_is_the_persons_visible_exchange(
        self, async_session: AsyncSession
    ) -> None:
        user = await _make_user(async_session)
        conversation = await _make_conversation(async_session, user)
        now = datetime.now(UTC)
        await _make_message(
            async_session,
            conversation,
            role="user",
            content="Bonjour",
            at=now - timedelta(minutes=3),
        )
        await _make_message(
            async_session,
            conversation,
            role="assistant",
            content="Salut",
            at=now - timedelta(minutes=2),
        )
        await _make_message(
            async_session,
            conversation,
            role="user",
            content="the brief of a run",
            at=now - timedelta(minutes=1),
            hidden=True,
        )

        history = await consolidation_service._load_conversation_history(
            user.id, since=None, max_messages=10, max_days=7
        )

        assert history == "USER: Bonjour\nASSISTANT: Salut"

    @pytest.mark.usefixtures("_redirect_db_context")
    async def test_usage_patterns_count_the_persons_messages_in_their_own_hours(
        self, async_session: AsyncSession
    ) -> None:
        """Kiritimati is UTC+14: 20:30 UTC is 10:30 the next morning there. Read
        as the UTC hour, the same message was an « evening » one."""
        user = await _make_user(async_session, timezone="Pacific/Kiritimati")
        conversation = await _make_conversation(async_session, user)
        at = (datetime.now(UTC) - timedelta(days=1)).replace(
            hour=20, minute=30, second=0, microsecond=0
        )
        await _make_message(async_session, conversation, role="user", content="q", at=at)
        # Not the person speaking, and not the person either: a run's brief.
        await _make_message(async_session, conversation, role="assistant", content="a", at=at)
        await _make_message(
            async_session, conversation, role="user", content="run", at=at, hidden=True
        )

        section = await consolidation_service._build_usage_patterns_section(user.id)

        assert "User messages: 1." in section
        assert "morning 1" in section
        assert "evening" not in section
