"""Owned archive selection, current provider and request-local composition scope."""

import asyncio
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from src.core.card_composition import (
    CardCompositionRequest,
    CardCompositionUnavailable,
    card_composition_ctx,
    ensure_composition_account,
    ensure_composition_provider,
)
from src.domains.agents.services.card_composition_prompt import build_card_composition_block
from src.domains.agents.services.card_composition_service import (
    composition_scope,
    resolve_composition,
)

pytestmark = pytest.mark.unit
USER = UUID("00000000-0000-0000-0000-000000000001")
THREAD = UUID("00000000-0000-0000-0000-000000000002")
MESSAGE = "00000000-0000-0000-0000-000000000003"


def request():
    return CardCompositionRequest(
        version=1, message_id=MESSAGE, run_id="source-run", registry_id="email_a", action="reply"
    )


def metadata():
    return {
        "run_id": "source-run",
        "lia_card_actions": {
            "version": 1,
            "run_id": "source-run",
            "items": [
                {
                    "registry_id": "email_a",
                    "kind": "EMAIL",
                    "target_id": "canonical123",
                    "provider": "google_gmail",
                    "account_binding": "00000000-0000-0000-0000-000000000004",
                    "label": "External subject",
                    "actions": ["reply", "forward"],
                }
            ],
        },
    }


@pytest.mark.asyncio
async def test_owned_query_and_context_never_take_a_client_target():
    db = AsyncMock()
    db.scalar.return_value = metadata()
    resolved = await resolve_composition(db, USER, THREAD, request())
    assert resolved.target_id == "canonical123"
    assert resolved.user_id == USER
    statement = db.scalar.call_args.args[0]
    sql = str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    for expected in (
        "JOIN conversations",
        "conversations.user_id",
        "conversation_messages.conversation_id",
        "conversation_messages.role",
        "conversations.deleted_at IS NULL",
        "conversation_messages.hidden IS false",
        MESSAGE,
    ):
        assert expected in sql
    assert "assistant" in sql


@pytest.mark.parametrize(
    "change", ["missing", "run", "version", "no_version", "item", "action", "duplicate", "extra"]
)
@pytest.mark.asyncio
async def test_invalid_archived_selection_fails_closed(change):
    value = metadata()
    projection = value["lia_card_actions"]
    if change == "run":
        value["run_id"] = "another"
    if change == "version":
        projection["version"] = True
    if change == "no_version":
        del projection["version"]
    if change == "item":
        projection["items"][0]["registry_id"] = "other"
    if change == "action":
        projection["items"][0]["actions"] = ["forward"]
    if change == "duplicate":
        projection["items"] *= 2
    if change == "extra":
        projection["target_id"] = "forged"
    db = AsyncMock()
    db.scalar.return_value = None if change == "missing" else value
    with pytest.raises(CardCompositionUnavailable):
        await resolve_composition(db, USER, THREAD, request())


@pytest.mark.asyncio
async def test_scope_provider_check_prompt_and_reset(monkeypatch):
    db = AsyncMock()
    db.scalar.return_value = metadata()
    deps = AsyncMock()
    deps.get_connector_service.return_value.get_connector_credentials.return_value.account_binding = (
        "00000000-0000-0000-0000-000000000004"
    )
    resolver = AsyncMock(return_value="google_gmail")
    monkeypatch.setattr(
        "src.domains.agents.services.card_composition_service.resolve_active_connector", resolver
    )
    assert build_card_composition_block() == ""
    async with composition_scope(db, USER, THREAD, request(), deps):
        ensure_composition_provider(USER, "email", "google_gmail")
        ensure_composition_account(USER, "google_gmail", "00000000-0000-0000-0000-000000000004")
        with pytest.raises(CardCompositionUnavailable):
            ensure_composition_account(USER, "google_gmail", "00000000-0000-0000-0000-000000000005")
        ensure_composition_provider(USER, "contacts", "microsoft_contacts")
        with pytest.raises(CardCompositionUnavailable):
            ensure_composition_provider(USER, "email", "microsoft_outlook")
        with pytest.raises(CardCompositionUnavailable):
            ensure_composition_provider(UUID(int=99), "email", "google_gmail")
        block = build_card_composition_block()
        assert "canonical123" in block and "reply" in block
        assert "External subject" not in block and "HITL" in block
    assert card_composition_ctx.get() is None
    assert build_card_composition_block() == ""


@pytest.mark.asyncio
async def test_provider_switch_rejected_before_context_is_bound(monkeypatch):
    db = AsyncMock()
    db.scalar.return_value = metadata()
    monkeypatch.setattr(
        "src.domains.agents.services.card_composition_service.resolve_active_connector",
        AsyncMock(return_value="microsoft_outlook"),
    )
    with pytest.raises(CardCompositionUnavailable):
        async with composition_scope(db, USER, THREAD, request(), AsyncMock()):
            pytest.fail("Must not enter the turn")
    assert card_composition_ctx.get() is None


@pytest.mark.asyncio
async def test_concurrent_scopes_and_cancel_restore_prior_context(monkeypatch):
    monkeypatch.setattr(
        "src.domains.agents.services.card_composition_service.resolve_active_connector",
        AsyncMock(return_value="google_gmail"),
    )

    async def turn(target):
        value = metadata()
        value["lia_card_actions"]["items"][0]["target_id"] = target
        db = AsyncMock()
        db.scalar.return_value = value
        deps = AsyncMock()
        deps.get_connector_service.return_value.get_connector_credentials.return_value.account_binding = (
            "00000000-0000-0000-0000-000000000004"
        )
        with pytest.raises(asyncio.CancelledError):
            async with composition_scope(db, USER, THREAD, request(), deps):
                await asyncio.sleep(0)
                assert card_composition_ctx.get().target_id == target
                raise asyncio.CancelledError
        assert card_composition_ctx.get() is None

    await asyncio.gather(turn("one"), turn("two"))


def test_request_extra_target_and_malformed_ids_rejected():
    from pydantic import ValidationError

    for update in (
        {"target_id": "forged"},
        {"message_id": "latest"},
        {"version": True},
        {"action": "send"},
    ):
        with pytest.raises(ValidationError):
            CardCompositionRequest.model_validate({**request().model_dump(), **update})
