"""The settings adapter cannot lend its authority to native drafts or lock upgrades."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application import sms_execution
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.sms_actions import SmsManagementAudience, prepare_sms_action
from src.domains.agents.effects.digest import draft_digest
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_application_memory_independent_transactions import (
    committed_actor as committed_actor,
)
from tests.integration.test_application_sms_actions import origin_for

pytestmark = pytest.mark.integration


def approved(draft):
    return effect_scope(
        EffectScope(
            run_id=str(uuid4()),
            idempotency_key="draft:native",
            approved=True,
            approval_kind="draft_critique",
            approval_ref="native",
            draft_digest=draft_digest(draft.model_dump(mode="json")),
        )
    )


async def test_settings_audience_cannot_execute_an_approved_native_draft(
    db_session, test_user, monkeypatch
):
    draft = await prepare_sms_action(
        db_session,
        test_user.id,
        "sms_preferences.update",
        {"ingestion_enabled": True, "assistant_enabled": True, "push_enabled": False},
    )
    monkeypatch.setattr(settings, "application_tools_enabled", False)
    with approved(draft), pytest.raises(CommandRejected, match="BROWSER_APPROVAL_REQUIRED"):
        await sms_execution.execute_sms_action(
            db_session,
            test_user.id,
            draft,
            PreferenceWriteReceipt(),
            origin=origin_for(test_user.id),
            audience=SmsManagementAudience.SETTINGS,
        )
    assert not (test_user.sms_preferences or {}).get("assistant_enabled", False)


async def test_settings_preparation_always_requires_a_live_browser_origin(db_session, test_user):
    with pytest.raises(AuthorizationError):
        await prepare_sms_action(
            db_session,
            test_user.id,
            "sms_preferences.update",
            {"ingestion_enabled": True, "assistant_enabled": True, "push_enabled": False},
            audience=SmsManagementAudience.SETTINGS,
        )


async def test_mutation_authorization_already_holds_exclusive_owner_fence(
    async_engine, committed_actor, monkeypatch
):
    owner = committed_actor
    origin = origin_for(owner)
    async with AsyncSession(async_engine, expire_on_commit=False) as preparation:
        draft = await prepare_sms_action(preparation, owner, "sms_token.create", {}, origin=origin)
        await preparation.commit()
    observations = []
    original = sms_execution.authorize_sms_management

    async def observe(*args, **kwargs):
        await original(*args, **kwargs)
        async with AsyncSession(async_engine) as other:
            try:
                await other.scalar(
                    select(User.id).where(User.id == owner).with_for_update(read=True, nowait=True)
                )
            except DBAPIError as error:
                assert getattr(error.orig, "sqlstate", None) == "55P03"
                observations.append(True)
            else:
                observations.append(False)

    monkeypatch.setattr(sms_execution, "authorize_sms_management", observe)
    async with AsyncSession(async_engine, expire_on_commit=False) as execution:
        with approved(draft):
            await sms_execution.execute_sms_action(
                execution, owner, draft, PreferenceWriteReceipt(), origin=origin
            )
    assert (
        observations and observations[0] is True
    ), "A shared-before-exclusive upgrade can deadlock concurrent commands"
