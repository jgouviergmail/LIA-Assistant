"""SMS management prepares exact native commands without writing source state."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.core.application_origin import ApplicationOrigin, ApplicationSessionFacts
from src.domains.ingestion.models import IngestionToken
from src.domains.ingestion.token_commands import (
    IngestionTokenCompletionUnknown,
    create_managed_token,
)
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.models import SmsMessage, SmsSenderBlock
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration


def origin_for(owner):
    async def current():
        return ApplicationSessionFacts(owner, "a" * 64, "browser", None)

    return ApplicationOrigin(owner, "a" * 64, current)


@pytest.mark.parametrize(
    "operation,payload",
    [
        ("sms_token.create", {"label": "iPhone"}),
        (
            "sms_preferences.update",
            {"ingestion_enabled": True, "assistant_enabled": True, "push_enabled": False},
        ),
        ("sms_sender_block.update", {"sender": "BANK", "blocked": True}),
        ("sms_messages.delete", {"all_messages": True}),
    ],
)
async def test_prepare_is_exact_and_never_writes_source(db_session, test_user, operation, payload):
    from src.domains.agents.application.sms_actions import canonical_sms_action, prepare_sms_action

    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(actor, [message()])
    draft = await prepare_sms_action(
        db_session, test_user.id, operation, payload, origin=origin_for(test_user.id)
    )
    assert draft.operation_id == operation and draft.actor_id == test_user.id
    assert canonical_sms_action(draft)
    assert await db_session.scalar(select(func.count()).select_from(IngestionToken)) == 1
    assert await db_session.scalar(select(func.count()).select_from(SmsMessage)) == 1
    assert await db_session.scalar(select(func.count()).select_from(SmsSenderBlock)) == 0
    assert not (test_user.sms_preferences or {}).get("assistant_enabled", False)


async def test_prepare_token_revocation_names_only_public_metadata(db_session, test_user):
    from src.domains.agents.application.sms_actions import prepare_sms_action

    actor = await authority(db_session, test_user)
    draft = await prepare_sms_action(
        db_session,
        test_user.id,
        "sms_token.revoke",
        {"token_id": str(actor.token_id)},
        origin=origin_for(test_user.id),
    )
    assert "token_hash" not in str(draft.before) + str(draft.after)
    assert draft.after["ingestion_token_to_revoke"]["revoked"] is True


@pytest.mark.parametrize(
    "failure", [OSError("synthetic lost ack"), TimeoutError("synthetic lost ack")]
)
async def test_token_commit_socket_failures_are_explicitly_unknown(
    db_session, test_user, monkeypatch, failure
):
    async def check():
        pass

    monkeypatch.setattr(db_session, "commit", AsyncMock(side_effect=failure))
    with pytest.raises(IngestionTokenCompletionUnknown):
        await create_managed_token(
            db_session, test_user.id, uuid4(), "iPhone", None, PreferenceWriteReceipt(), check
        )


async def test_unapproved_execution_never_changes_preferences(db_session, test_user):
    from src.domains.agents.application.command_service import CommandRejected
    from src.domains.agents.application.sms_actions import prepare_sms_action
    from src.domains.agents.application.sms_execution import execute_sms_action

    draft = await prepare_sms_action(
        db_session,
        test_user.id,
        "sms_preferences.update",
        {"ingestion_enabled": True, "assistant_enabled": True, "push_enabled": False},
    )
    with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
        await execute_sms_action(db_session, test_user.id, draft, PreferenceWriteReceipt())
    assert not (test_user.sms_preferences or {}).get("assistant_enabled", False)


async def test_exact_approved_execution_and_expiry_are_enforced(db_session, test_user):
    from src.domains.agents.application.command_service import CommandRejected
    from src.domains.agents.application.sms_actions import prepare_sms_action
    from src.domains.agents.application.sms_execution import execute_sms_action
    from src.domains.agents.effects.digest import draft_digest
    from src.domains.agents.effects.scope import EffectScope, effect_scope

    draft = await prepare_sms_action(
        db_session,
        test_user.id,
        "sms_preferences.update",
        {"ingestion_enabled": True, "assistant_enabled": True, "push_enabled": False},
    )

    def approved(content):
        return effect_scope(
            EffectScope(
                run_id="sms-test",
                idempotency_key="draft:test",
                approved=True,
                approval_kind="draft_critique",
                approval_ref="test",
                draft_digest=draft_digest(content.model_dump(mode="json")),
            )
        )

    receipt = PreferenceWriteReceipt()
    with approved(draft):
        await execute_sms_action(db_session, test_user.id, draft, receipt)
    assert receipt.committed and test_user.sms_preferences["assistant_enabled"]
    expired = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    with approved(expired), pytest.raises(CommandRejected, match="EXPIRED"):
        await execute_sms_action(db_session, test_user.id, expired, PreferenceWriteReceipt())
