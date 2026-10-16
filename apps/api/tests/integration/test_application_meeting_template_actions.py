"""Native template drafts execute once through original PostgreSQL owners."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_meeting_template_tools import (
    create_lia_meeting_template_tool,
    delete_lia_meeting_template_tool,
    update_lia_meeting_template_tool,
)
from src.domains.meetings.preference_commands import replace_meeting_preferences
from src.domains.meetings.repository import MeetingPreferenceRepository, MeetingTemplateRepository
from src.domains.meetings.schemas import (
    MeetingPreferencesUpdate,
    MeetingTemplateCreate,
    MeetingTemplateUpdate,
    TemplateSection,
)
from src.domains.meetings.template_gateway import SavedMeetingTemplates
from src.domains.meetings.template_service import MeetingTemplateService
from src.domains.users.models import User
from src.infrastructure.meeting_templates import configure_meeting_templates
from tests.helpers.draft_refusals import draft_refusal_code
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def template_owner():
    previous = configure_meeting_templates(SavedMeetingTemplates())
    try:
        yield
    finally:
        configure_meeting_templates(previous)


@pytest.mark.parametrize(
    "action,intervention",
    [
        (action, intervention)
        for action in ("create", "update", "delete")
        for intervention in ("none", "changed", "disabled")
    ]
    + [
        ("update", "no_op"),
        ("delete", "default_changed"),
        ("create", "lost_ack"),
        ("delete", "legacy_default"),
    ],
)
async def test_native_template_mutations_are_confirmed_owned_and_fresh(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    intervention: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "meetings_enabled", True)
    monkeypatch.setattr(settings, "meetings_max_user_templates", 10)
    section = TemplateSection(
        key="summary", label="Summary", instruction="Preserve literal instruction", kind="paragraph"
    )
    service = MeetingTemplateService(async_session)
    original = await service.create(
        test_user.id,
        MeetingTemplateCreate(
            name="Original",
            description="Preserve description",
            category="business",
            sections=[section],
        ),
        "fr",
    )
    actor_id, original_id, original_ref = test_user.id, original.id, original.ref
    assert original_id is not None
    await replace_meeting_preferences(
        async_session,
        actor_id,
        MeetingPreferencesUpdate(
            stt_engine="auto",
            language="auto",
            auto_email=False,
            keep_audio_hours=0,
            default_template_ref=original_ref,
        ),
        "fr",
    )
    if intervention == "legacy_default":
        preference = await MeetingPreferenceRepository(async_session).get_for_user(actor_id)
        assert preference is not None
        preference.default_template_ref = "user:" + str(original_id).upper()
        await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    tool = {
        "create": create_lia_meeting_template_tool,
        "update": update_lia_meeting_template_tool,
        "delete": delete_lia_meeting_template_tool,
    }[action]
    requested = {
        "create": {"duplicate_of": original_ref},
        "update": {"ref": original_ref, "changes": {"name": "Updated"}},
        "delete": {"ref": original_ref},
    }[action]
    if intervention == "no_op":
        requested = {"ref": original_ref, "changes": {"name": "Original"}}
    if intervention == "lost_ack":
        real_commit = async_session.commit

        async def lost_commit() -> None:
            await real_commit()
            raise OperationalError("COMMIT", {}, Exception("lost acknowledgment"))

        class LostAcknowledgment(SavedMeetingTemplates):
            async def create(self, db, actor_id, request, language, confirmation):
                with patch.object(db, "commit", lost_commit):
                    await super().create(db, actor_id, request, language, confirmation)

        configure_meeting_templates(LostAcknowledgment())
    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    queue: asyncio.Queue[ChatStreamChunk] = asyncio.Queue()
    with (
        installed_runtime_context(
            user_id=actor_id, language="fr", deps=object(), side_channel_queue=queue
        ),
        patch(
            "src.domains.agents.tools.application_meeting_template_tools.get_db_context", session
        ),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
    ):
        proposal = await tool.coroutine(
            request=requested, runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore())
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        assert await MeetingTemplateRepository(async_session).count_for_user(actor_id) == 1
        if intervention == "changed":
            if action == "create":
                await service.create(
                    actor_id, MeetingTemplateCreate(name="Other", sections=[section]), "fr"
                )
            else:
                await service.update(
                    actor_id,
                    original_ref,
                    MeetingTemplateUpdate(
                        name="Changed",
                        description="Preserve description",
                        category="business",
                        sections=[section],
                    ),
                )
        if intervention == "disabled":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        if intervention == "default_changed":
            await replace_meeting_preferences(
                async_session,
                actor_id,
                MeetingPreferencesUpdate(
                    stt_engine="auto",
                    language="auto",
                    auto_email=False,
                    keep_audio_hours=0,
                    default_template_ref=None,
                ),
                "fr",
            )
        draft_executor.register_executor("application_action", execute_application_action_draft)
        outcome = await draft_executor._execute_confirmed_draft(
            {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": item.payload["content"],
            },
            {"configurable": {"thread_id": "template-confirmation"}},
            "template-confirmation",
            "fr",
        )
        if intervention in {"none", "no_op", "lost_ack"}:
            replay = await draft_executor._execute_confirmed_draft(
                {
                    "draft_id": item.id,
                    "draft_type": "application_action",
                    "draft_content": item.payload["content"],
                },
                {"configurable": {"thread_id": "template-confirmation"}},
                "template-confirmation",
                "fr",
            )
            assert replay.success is False
    assert outcome.success is (intervention in {"none", "no_op", "legacy_default"})
    rows = await MeetingTemplateRepository(async_session).list_for_user(actor_id)
    if intervention in {"none", "no_op", "lost_ack", "legacy_default"}:
        if action == "create":
            assert len(rows) == 2
            assert {row.name for row in rows} == {"Original", "Original (2)"}
        if action == "update":
            assert len(rows) == 1 and rows[0].name == (
                "Original" if intervention == "no_op" else "Updated"
            )
            assert rows[0].description == "Preserve description" and rows[0].category == "business"
            assert rows[0].sections[0]["instruction"] == "Preserve literal instruction"
        if action == "delete":
            assert rows == []
            preference = await MeetingPreferenceRepository(async_session).get_for_user(actor_id)
            assert preference is not None and preference.default_template_ref is None
    else:
        assert any(row.id == original_id for row in rows)
        assert draft_refusal_code(outcome) == (
            "STALE_STATE"
            if intervention in {"changed", "default_changed"}
            else "CAPABILITY_DISABLED"
        )
    if intervention == "lost_ack":
        assert draft_refusal_code(outcome) == "COMPLETION_UNKNOWN"
    hints = [queue.get_nowait() for _ in range(queue.qsize())]
    hints = [event for event in hints if event.type == "application_state_changed"]
    assert len(hints) == int(intervention in {"none", "legacy_default"})
    if hints:
        expected = (
            ["meeting_templates", "meeting_preferences"]
            if action == "delete"
            else ["meeting_templates"]
        )
        assert hints[0].metadata["change"]["resources"] == expected
        assert "instruction" not in str(hints[0].metadata)
