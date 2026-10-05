"""Resumed HITL execution re-reads the archive and the account before mutation."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src.core.card_composition import (
    CARD_COMPOSITION_DRAFT_KEY,
    CardCompositionUnavailable,
    card_composition_ctx,
)
from src.domains.agents.services import card_composition_service
from src.domains.agents.tools.emails_tools import (
    execute_email_delete_draft,
    execute_email_reply_draft,
)
from src.domains.agents.tools.reminder_tools import execute_reminder_delete_draft

pytestmark = pytest.mark.unit
USER = UUID(int=1)


def selection(action):
    return {
        "version": 1,
        "message_id": str(UUID(int=3)),
        "run_id": "source",
        "registry_id": "chosen",
        "action": action,
    }


def archived(kind, target, action):
    return {
        "run_id": "source",
        "lia_card_actions": {
            "version": 1,
            "run_id": "source",
            "items": [
                {
                    "registry_id": "chosen",
                    "kind": kind,
                    "target_id": target,
                    "label": "Received item",
                    "provider": "google_gmail" if kind == "EMAIL" else None,
                    "account_binding": str(UUID(int=4)) if kind == "EMAIL" else None,
                    "actions": (
                        ["reply", "forward", "delete_email"] if kind == "EMAIL" else [action]
                    ),
                }
            ],
        },
    }


def install_database(monkeypatch, metadata):
    db = AsyncMock()
    db.scalar.return_value = metadata

    @asynccontextmanager
    async def database():
        yield db

    monkeypatch.setattr(card_composition_service, "get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    return db


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["changed_account", "revoked", "deleted_source"])
@pytest.mark.parametrize(
    "action,execute",
    [("reply", execute_email_reply_draft), ("delete_email", execute_email_delete_draft)],
)
async def test_later_reply_refuses_changed_or_revoked_account_and_deleted_source(
    monkeypatch, condition, action, execute
):
    metadata = None if condition == "deleted_source" else archived("EMAIL", "target", action)
    install_database(monkeypatch, metadata)
    deps = AsyncMock()
    credentials = None if condition == "revoked" else AsyncMock(account_binding=str(UUID(int=5)))
    deps.get_connector_service.return_value.get_connector_credentials.return_value = credentials
    monkeypatch.setattr(
        card_composition_service, "resolve_active_connector", AsyncMock(return_value="google_gmail")
    )
    resolver = AsyncMock()
    monkeypatch.setattr(
        "src.domains.connectors.provider_resolver.resolve_client_for_category", resolver
    )
    content = {
        "message_id": "target",
        "body": "Edited",
        CARD_COMPOSITION_DRAFT_KEY: selection(action),
    }
    with pytest.raises(CardCompositionUnavailable):
        await execute(content, USER, deps)
    resolver.assert_not_awaited()
    assert card_composition_ctx.get() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [False, True])
async def test_confirmed_deletion_revalidates_archived_email_before_trashing(monkeypatch, changed):
    db = install_database(monkeypatch, archived("EMAIL", "target", "delete_email"))
    deps = AsyncMock()
    deps.get_connector_service.return_value.get_connector_credentials.return_value.account_binding = str(
        UUID(int=4)
    )
    monkeypatch.setattr(
        card_composition_service, "resolve_active_connector", AsyncMock(return_value="google_gmail")
    )
    client = AsyncMock()
    resolver = AsyncMock(return_value=(client, "google_gmail"))
    monkeypatch.setattr(
        "src.domains.connectors.provider_resolver.resolve_client_for_category", resolver
    )
    content = {
        "message_id": "another" if changed else "target",
        CARD_COMPOSITION_DRAFT_KEY: selection("delete_email"),
    }
    if changed:
        with pytest.raises(CardCompositionUnavailable):
            await execute_email_delete_draft(content, USER, deps)
        client.trash_email.assert_not_awaited()
        resolver.assert_not_awaited()
    else:
        await execute_email_delete_draft(content, USER, deps)
        client.trash_email.assert_awaited_once_with("target")
        db.commit.assert_awaited_once()
    assert card_composition_ctx.get() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [False, True])
async def test_later_reminder_confirmation_cannot_retarget_the_selected_item(monkeypatch, changed):
    target = str(UUID(int=8))
    db = install_database(monkeypatch, archived("REMINDER", target, "cancel_reminder"))
    service = AsyncMock()
    monkeypatch.setattr("src.domains.reminders.service.ReminderService", lambda session: service)
    content = {
        "reminder_id": str(UUID(int=9)) if changed else target,
        "content": "Reminder",
        CARD_COMPOSITION_DRAFT_KEY: selection("cancel_reminder"),
    }
    if changed:
        with pytest.raises(CardCompositionUnavailable):
            await execute_reminder_delete_draft(content, USER, AsyncMock())
        service.cancel_reminder.assert_not_awaited()
    else:
        await execute_reminder_delete_draft(content, USER, AsyncMock())
        service.cancel_reminder.assert_awaited_once_with(user_id=USER, reminder_id=UUID(target))
        assert db.commit.await_count == 2
    assert card_composition_ctx.get() is None
