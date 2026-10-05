"""A card selection survives editing and is revalidated when HITL sends later."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from src.core.card_composition import (
    CARD_COMPOSITION_DRAFT_KEY,
    CardComposition,
    CardCompositionRequest,
    CardCompositionUnavailable,
    bind_composition_draft,
    card_composition_ctx,
)
from src.domains.agents.drafts.models import Draft, DraftType
from src.domains.agents.tools.emails_tools import execute_email_reply_draft

pytestmark = pytest.mark.unit
USER = UUID(int=1)
REQUEST = CardCompositionRequest(
    version=1,
    message_id=str(UUID(int=3)),
    run_id="run-source",
    registry_id="email_a",
    action="reply",
)


def test_binding_cannot_be_replaced_or_dropped_during_draft_edit():
    token = card_composition_ctx.set(
        CardComposition(USER, "EMAIL", "target", "reply", "google_gmail", str(UUID(int=4)), REQUEST)
    )
    try:
        content = bind_composition_draft({"message_id": "target", "body": "Draft"}, "email_reply")
        with pytest.raises(CardCompositionUnavailable):
            bind_composition_draft({"message_id": "another", "body": "Draft"}, "email_reply")
    finally:
        card_composition_ctx.reset(token)
    draft = Draft(type=DraftType.EMAIL_REPLY, content=content)
    edited = draft.mark_modified(
        {
            "message_id": "target",
            "body": "Edited",
            CARD_COMPOSITION_DRAFT_KEY: {"message_id": "forged"},
        }
    )
    assert edited.content[CARD_COMPOSITION_DRAFT_KEY] == REQUEST.model_dump(mode="json")
    edited.content[CARD_COMPOSITION_DRAFT_KEY]["run_id"] = "accidental-mutation"
    assert draft.content[CARD_COMPOSITION_DRAFT_KEY]["run_id"] == REQUEST.run_id
    edited.content[CARD_COMPOSITION_DRAFT_KEY]["run_id"] = REQUEST.run_id
    serializer = JsonPlusSerializer()
    restored = serializer.loads_typed(serializer.dumps_typed(edited.model_dump(mode="json")))
    assert Draft.model_validate(restored).content[CARD_COMPOSITION_DRAFT_KEY] == REQUEST.model_dump(
        mode="json"
    )
    plain = Draft(type=DraftType.EMAIL_REPLY, content={"message_id": "target"})
    assert (
        CARD_COMPOSITION_DRAFT_KEY
        not in plain.mark_modified(
            {CARD_COMPOSITION_DRAFT_KEY: REQUEST.model_dump(mode="json")}
        ).content
    )


def test_reminder_selection_cannot_create_a_draft_for_another_reminder():
    request = REQUEST.model_copy(update={"action": "cancel_reminder"})
    target = str(UUID(int=8))
    token = card_composition_ctx.set(
        CardComposition(USER, "REMINDER", target, "cancel_reminder", None, source=request)
    )
    try:
        content = bind_composition_draft({"reminder_id": target}, "reminder_delete")
        assert content[CARD_COMPOSITION_DRAFT_KEY] == request.model_dump(mode="json")
        with pytest.raises(CardCompositionUnavailable):
            bind_composition_draft({"reminder_id": str(UUID(int=9))}, "reminder_delete")
    finally:
        card_composition_ctx.reset(token)


@pytest.mark.asyncio
async def test_card_deletion_prepares_a_bound_confirmation_without_mutation():
    from src.domains.agents.tools.emails_tools import DeleteEmailDraftTool

    request = REQUEST.model_copy(update={"action": "delete_email"})
    token = card_composition_ctx.set(
        CardComposition(
            USER, "EMAIL", "target", "delete_email", "google_gmail", str(UUID(int=4)), request
        )
    )
    client = AsyncMock()
    client.get_message.return_value = {
        "payload": {"headers": [{"name": "Subject", "value": "Selected email"}]}
    }
    try:
        tool = DeleteEmailDraftTool()
        prepared = await tool.execute_api_call(client, USER, message_id="target")
        output = tool.format_registry_response(prepared)
        assert output.metadata["requires_confirmation"] is True
        draft = next(iter(output.registry_updates.values())).payload
        assert draft["draft_type"] == "email_delete"
        assert draft["content"]["message_id"] == "target"
        assert draft["content"][CARD_COMPOSITION_DRAFT_KEY] == request.model_dump(mode="json")
        with pytest.raises(CardCompositionUnavailable):
            tool.format_registry_response({**prepared, "message_id": "another"})
        client.trash_email.assert_not_awaited()
    finally:
        card_composition_ctx.reset(token)


def test_hitl_display_content_does_not_expose_host_selection_to_the_model():
    from src.domains.agents.services.hitl.interactions.draft_critique import (
        DraftCritiqueInteraction,
    )

    content = {"body": "Visible draft", CARD_COMPOSITION_DRAFT_KEY: REQUEST.model_dump(mode="json")}
    display = DraftCritiqueInteraction._preconvert_dates_for_display(content, "UTC", "en")
    assert display == {"body": "Visible draft"}
    assert CARD_COMPOSITION_DRAFT_KEY in content


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["target", "forged"])
async def test_later_confirmation_revalidates_source_before_any_send(monkeypatch, target):
    from src.domains.agents.services import card_composition_service

    calls = []

    @asynccontextmanager
    async def scope(db, user, thread, request, deps):
        calls.append((user, request))
        token = card_composition_ctx.set(
            CardComposition(
                USER, "EMAIL", "target", "reply", "google_gmail", str(UUID(int=4)), REQUEST
            )
        )
        try:
            yield
        finally:
            card_composition_ctx.reset(token)

    monkeypatch.setattr(card_composition_service, "composition_scope", scope)

    @asynccontextmanager
    async def db_scope():
        yield AsyncMock()

    monkeypatch.setattr(card_composition_service, "get_db_context", db_scope)
    client = AsyncMock()
    client.reply_email.return_value = {"id": "sent"}
    resolver = AsyncMock(return_value=(client, "google_gmail"))
    monkeypatch.setattr(
        "src.domains.connectors.provider_resolver.resolve_client_for_category", resolver
    )
    content = {
        "message_id": target,
        "body": "Draft",
        CARD_COMPOSITION_DRAFT_KEY: REQUEST.model_dump(mode="json"),
    }
    if target == "forged":
        with pytest.raises(CardCompositionUnavailable):
            await execute_email_reply_draft(content, USER, AsyncMock())
        client.reply_email.assert_not_awaited()
    else:
        await execute_email_reply_draft(content, USER, AsyncMock())
        client.reply_email.assert_awaited_once()
    assert calls == [(USER, REQUEST)]
    assert card_composition_ctx.get() is None
