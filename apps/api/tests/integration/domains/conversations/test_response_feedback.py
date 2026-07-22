"""Integration tests for response feedback on assistant messages (QW-5, ADR-138).

Locks the module contract against the real database:
- verdict persisted atomically in ``message_metadata`` (owner-scoped jsonb_set);
- FIRST verdict feeds the injected journal entries' evidence/contradiction
  counters; a verdict CHANGE never re-feeds them (no decrement path);
- a 👎 comment lands as an L0 ``user_correction`` entry, no consolidation;
- ownership: foreign or non-assistant rows resolve to None (router → 404);
- journals disabled ⇒ metadata persists, counters untouched.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.field_names import FIELD_INJECTED_JOURNAL_IDS, FIELD_RESPONSE_FEEDBACK
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.conversations.response_feedback import (
    apply_verdict_to_journals,
    get_assistant_message_for_user,
    persist_verdict,
    record_comment_as_correction,
)
from src.domains.journals.models import JournalEntry

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _register_journal_hooks() -> None:
    """Wire the real journals implementation into the port (startup mirror)."""
    from src.domains.conversations.response_feedback import register_journal_feedback_hooks
    from src.domains.journals.feedback_hooks import JournalResponseFeedbackHooks

    register_journal_feedback_hooks(JournalResponseFeedbackHooks())


async def _make_user(async_session: AsyncSession, email: str):
    from src.domains.users.models import User

    user = User(email=email, hashed_password="x", is_active=True, is_superuser=False)
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


async def _make_journal_entry(async_session: AsyncSession, user_id: UUID) -> JournalEntry:
    entry = JournalEntry(
        user_id=user_id,
        theme="self_reflection",
        title="Observed preference",
        content="The user prefers concise answers.",
        mood="reflective",
        source="introspection",
        level="L1",
        confidence="medium",
    )
    async_session.add(entry)
    await async_session.commit()
    await async_session.refresh(entry)
    return entry


@pytest.fixture
async def feedback_setup(async_session: AsyncSession):
    """User + conversation + assistant message carrying one injected entry id."""
    user = await _make_user(async_session, "feedback_user@test.local")
    entry = await _make_journal_entry(async_session, user.id)

    conversation = Conversation(
        id=user.id, user_id=user.id, title="F", message_count=0, total_tokens=0
    )
    async_session.add(conversation)
    await async_session.commit()

    message = ConversationMessage(
        conversation_id=conversation.id,
        role="assistant",
        content="Voici ma réponse.",
        message_metadata={FIELD_INJECTED_JOURNAL_IDS: [str(entry.id)]},
    )
    async_session.add(message)
    await async_session.commit()
    await async_session.refresh(message)

    return user, message, entry


async def _submit(
    db: AsyncSession, user_id: UUID, message_id: UUID, verdict, comment: str | None = None
) -> None:
    """Replicate the router flow (read → first-verdict gate → persist)."""
    row = await get_assistant_message_for_user(db, user_id, message_id)
    assert row is not None
    metadata = dict(row.message_metadata or {})
    first_verdict = not isinstance(metadata.get(FIELD_RESPONSE_FEEDBACK), dict)
    await persist_verdict(db, user_id, message_id, verdict, comment)
    if first_verdict:
        await apply_verdict_to_journals(db, user_id, metadata, verdict)
    if comment and verdict == "thumbs_down":
        await record_comment_as_correction(db, user_id, comment)
    await db.commit()


class TestResponseFeedback:
    async def test_thumbs_up_persists_verdict_and_feeds_evidence(
        self, async_session: AsyncSession, feedback_setup, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "journals_enabled", True)
        user, message, entry = feedback_setup

        await _submit(async_session, user.id, message.id, "thumbs_up")

        await async_session.refresh(message)
        assert message.message_metadata[FIELD_RESPONSE_FEEDBACK] == {"verdict": "thumbs_up"}
        await async_session.refresh(entry)
        assert entry.evidence_count == 1
        assert entry.contradiction_count == 0

    async def test_verdict_change_updates_metadata_but_never_refeeds_counters(
        self, async_session: AsyncSession, feedback_setup, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "journals_enabled", True)
        user, message, entry = feedback_setup

        await _submit(async_session, user.id, message.id, "thumbs_up")
        await _submit(async_session, user.id, message.id, "thumbs_down")

        await async_session.refresh(message)
        assert message.message_metadata[FIELD_RESPONSE_FEEDBACK]["verdict"] == "thumbs_down"
        await async_session.refresh(entry)
        # First verdict fed evidence once; the change fed NOTHING further.
        assert entry.evidence_count == 1
        assert entry.contradiction_count == 0

    async def test_thumbs_down_comment_lands_as_l0_correction(
        self, async_session: AsyncSession, feedback_setup, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "journals_enabled", True)
        user, message, entry = feedback_setup

        await _submit(
            async_session, user.id, message.id, "thumbs_down", comment="La date était fausse."
        )

        await async_session.refresh(message)
        stored = message.message_metadata[FIELD_RESPONSE_FEEDBACK]
        assert stored == {"verdict": "thumbs_down", "comment": "La date était fausse."}
        await async_session.refresh(entry)
        assert entry.contradiction_count == 1

        corrections = (
            (
                await async_session.execute(
                    select(JournalEntry).where(
                        JournalEntry.user_id == user.id,
                        JournalEntry.source == "user_correction",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(corrections) == 1
        assert corrections[0].level == "L0"
        assert "La date était fausse." in corrections[0].content

    async def test_journals_disabled_persists_verdict_without_counters(
        self, async_session: AsyncSession, feedback_setup, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "journals_enabled", False)
        user, message, entry = feedback_setup

        await _submit(async_session, user.id, message.id, "thumbs_up")

        await async_session.refresh(message)
        assert message.message_metadata[FIELD_RESPONSE_FEEDBACK]["verdict"] == "thumbs_up"
        await async_session.refresh(entry)
        assert entry.evidence_count == 0

    async def test_foreign_and_non_assistant_rows_resolve_to_none(
        self, async_session: AsyncSession, feedback_setup
    ) -> None:
        user, message, _ = feedback_setup
        stranger = await _make_user(async_session, "stranger@test.local")

        assert await get_assistant_message_for_user(async_session, stranger.id, message.id) is None
        assert await get_assistant_message_for_user(async_session, user.id, uuid4()) is None

        user_row = ConversationMessage(
            conversation_id=message.conversation_id, role="user", content="question"
        )
        async_session.add(user_row)
        await async_session.commit()
        await async_session.refresh(user_row)
        assert await get_assistant_message_for_user(async_session, user.id, user_row.id) is None

    async def test_vanished_or_foreign_injected_ids_are_skipped(
        self, async_session: AsyncSession, feedback_setup, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "journals_enabled", True)
        user, _, entry = feedback_setup
        stranger = await _make_user(async_session, "stranger2@test.local")
        foreign_entry = await _make_journal_entry(async_session, stranger.id)

        updated = await apply_verdict_to_journals(
            async_session,
            user.id,
            {
                FIELD_INJECTED_JOURNAL_IDS: [
                    str(entry.id),
                    str(uuid4()),  # vanished
                    str(foreign_entry.id),  # not this user's
                    "not-a-uuid",
                ]
            },
            "thumbs_up",
        )
        await async_session.commit()

        assert updated == 1
        await async_session.refresh(foreign_entry)
        assert foreign_entry.evidence_count == 0
