"""Journal provenance mirrors the source UI and never reconstitutes deleted source text."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.journal_provenance_schemas import JournalProvenanceRequest
from src.domains.agents.tools.application_journal_tools import get_lia_journal_provenance_tool
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.journals.models import JournalEntry
from src.domains.journals.router import get_entry_provenance
from src.domains.shared.provenance import ProvenanceOutcome, ProvenanceReference
from src.domains.shared.provenance_repository import ProvenanceRepository
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "live",
        "deleted",
        "archived",
        "foreign",
        "unknown",
        "disabled",
        "late_disabled",
        "source_disabled",
        "foreign_source",
    ],
)
async def test_journal_provenance_matches_source_ui_with_fresh_authority_and_no_injection(
    async_session: AsyncSession,
    test_user: User,
    test_superuser: User,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    owner, identity = test_user.id, uuid4()
    monkeypatch.setattr(settings, "journals_enabled", True)
    test_user.journals_enabled = False
    conversation = Conversation(
        user_id=test_superuser.id if scenario == "foreign_source" else owner,
        title="Own source",
        message_count=0,
        total_tokens=0,
        deleted_at=datetime.now(UTC) if scenario == "deleted" else None,
    )
    async_session.add(conversation)
    await async_session.flush()
    message = ConversationMessage(
        conversation_id=conversation.id,
        role="user",
        content="<script>Saved signal is untrusted data</script>",
    )
    entry = JournalEntry(
        id=identity,
        user_id=test_superuser.id if scenario == "foreign" else owner,
        content="Saved fact",
        theme="learnings",
        title="Saved observation",
        char_count=10,
        status="archived" if scenario == "archived" else "active",
    )
    async_session.add_all([message, entry])
    await async_session.flush()
    async_session.add(
        ProvenanceReference(
            user_id=owner,
            journal_entry_id=identity,
            conversation_id=conversation.id,
            message_id=message.id,
            outcome=ProvenanceOutcome.ORIGIN.value,
        )
    )
    await async_session.commit()
    if scenario == "unknown":
        identity = uuid4()
    if scenario == "disabled":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    if scenario == "source_disabled":
        monkeypatch.setattr(settings, "journals_enabled", False)
    source_resolve = ProvenanceRepository.resolve_for

    async def withdraw_after_read(repository: ProvenanceRepository, **kwargs):
        result = await source_resolve(repository, **kwargs)
        monkeypatch.setattr(settings, "application_tools_enabled", False)
        return result

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    with (
        installed_runtime_context(user_id=owner, language="fr"),
        patch("src.domains.agents.tools.application_journal_tools.get_db_context", session),
    ):
        if scenario == "late_disabled":
            monkeypatch.setattr(ProvenanceRepository, "resolve_for", withdraw_after_read)
        output = await get_lia_journal_provenance_tool.coroutine(
            selection=JournalProvenanceRequest(entry_id=identity),
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        success = scenario in {"live", "deleted", "archived", "foreign_source"}
        assert output.success is success
        if success:
            expected = await get_entry_provenance(
                entry_id=identity, user=test_user, db=async_session
            )
            assert output.structured_data == expected.model_dump(mode="json")
            assert expected.references[0].is_tombstone is (
                scenario in {"deleted", "foreign_source"}
            )
            assert (
                expected.references[0].excerpt is None
                if scenario in {"deleted", "foreign_source"}
                else expected.references[0].excerpt == message.content
            )
        else:
            assert output.error_code == (
                "CAPABILITY_DISABLED"
                if scenario in {"disabled", "late_disabled", "source_disabled"}
                else "NOT_FOUND"
            )
            assert "Saved signal" not in str(output)
        await async_session.refresh(entry)
        await async_session.refresh(test_user)
        assert entry.injection_count == 0 and test_user.journals_enabled is False
