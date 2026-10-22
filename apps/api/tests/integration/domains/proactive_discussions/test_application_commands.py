"""Real exact-HITL controls reuse owner repositories and reject changed approval scope."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.discussion_commands import (
    execute_discussion_action,
    prepare_discussion_action,
)
from src.domains.agents.application.discussion_schemas import (
    DiscussionPreferencesIntent,
    DiscussionPurgeIntent,
    DiscussionPurgeSelection,
    DiscussionRebuildIntent,
    DiscussionUseIntent,
    DiscussionUseSelection,
)
from src.domains.agents.effects.digest import draft_digest
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.domains.proactive_discussions.context_store.models import ContextStateRecord
from src.domains.proactive_discussions.policy_repository import DiscussionPolicyRepository
from src.domains.proactive_discussions.write_schemas import DiscussionPolicyPatch
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


def approval(draft):
    ref = str(draft.command_id)
    return EffectScope(
        run_id=ref,
        idempotency_key=f"draft:{ref}",
        approved=True,
        approval_kind="draft_critique",
        approval_ref=ref,
        draft_digest=draft_digest(draft.model_dump(mode="json")),
    )


async def test_confirmed_settings_use_native_revision_and_preserve_event_notifications(
    async_engine, discussion_owner, monkeypatch
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    request = DiscussionPreferencesIntent(
        discussion_preferences=DiscussionPolicyPatch(enabled=True, daily_max=None)
    )
    async with AsyncSession(async_engine) as db:
        draft = await prepare_discussion_action(
            db, discussion_owner, request, operation="proactive_discussions.update"
        )
        await db.commit()
    async with AsyncSession(async_engine) as db:
        receipt = PreferenceWriteReceipt()
        with effect_scope(approval(draft)):
            await execute_discussion_action(db, discussion_owner, draft, receipt)
        assert receipt.committed
    async with AsyncSession(async_engine) as db:
        policy = await DiscussionPolicyRepository(db).get_policy(discussion_owner)
        assert policy.enabled and policy.daily_max is None and policy.revision == 1


async def test_confirmed_rebuild_kicks_background_context_after_its_commit(
    async_engine, discussion_owner, monkeypatch
):
    import src.domains.agents.application.discussion_commands as commands

    monkeypatch.setattr(settings, "application_tools_enabled", True)
    calls = []
    monkeypatch.setattr(
        commands, "kick_context_rebuild", lambda owner, epoch: calls.append((owner, epoch))
    )
    request = DiscussionRebuildIntent(discussion_context_rebuild=True)
    async with AsyncSession(async_engine) as db:
        draft = await prepare_discussion_action(
            db, discussion_owner, request, operation="discussion_context.rebuild"
        )
        await db.commit()
    async with AsyncSession(async_engine) as db:
        receipt = PreferenceWriteReceipt()
        with effect_scope(approval(draft)):
            await execute_discussion_action(db, discussion_owner, draft, receipt)
        assert receipt.committed
    async with AsyncSession(async_engine) as db:
        state = await db.scalar(
            select(ContextStateRecord).where(ContextStateRecord.user_id == discussion_owner)
        )
        assert state.refresh_requested
    assert calls == [(discussion_owner, 1)]


async def test_concurrent_ui_edit_invalidates_approved_setting_snapshot(
    async_engine, discussion_owner, monkeypatch
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    request = DiscussionPreferencesIntent(
        discussion_preferences=DiscussionPolicyPatch(enabled=True)
    )
    async with AsyncSession(async_engine) as db:
        draft = await prepare_discussion_action(
            db, discussion_owner, request, operation="proactive_discussions.update"
        )
        await db.commit()
    async with AsyncSession(async_engine) as db:
        await DiscussionPolicyRepository(db).update_policy(
            discussion_owner, DiscussionPolicyPatch(daily_max=4), expected_revision=0
        )
        await db.commit()
    async with AsyncSession(async_engine) as db:
        with effect_scope(approval(draft)), pytest.raises(CommandRejected, match="STALE_STATE"):
            await execute_discussion_action(db, discussion_owner, draft, PreferenceWriteReceipt())
        await db.rollback()
        policy = await DiscussionPolicyRepository(db).get_policy(discussion_owner)
        assert not policy.enabled and policy.daily_max == 4


async def test_new_generation_between_preview_and_purge_requires_new_approval(
    async_engine, discussion_owner, monkeypatch
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    async with AsyncSession(async_engine) as db:
        draft = await prepare_discussion_action(
            db,
            discussion_owner,
            DiscussionPurgeIntent(discussion_context_purge=DiscussionPurgeSelection()),
            operation="discussion_context.purge",
        )
        await db.commit()
    async with AsyncSession(async_engine) as db:
        state = await db.scalar(
            select(ContextStateRecord).where(ContextStateRecord.user_id == discussion_owner)
        )
        state.generation += 1
        await db.commit()
    async with AsyncSession(async_engine) as db:
        with effect_scope(approval(draft)), pytest.raises(CommandRejected, match="STALE_STATE"):
            await execute_discussion_action(db, discussion_owner, draft, PreferenceWriteReceipt())


async def test_unknown_context_item_produces_no_confirmation_or_foreign_projection(
    async_engine, discussion_owner, monkeypatch
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    async with AsyncSession(async_engine) as db:
        request = DiscussionUseIntent(
            discussion_context_use=DiscussionUseSelection(item_id=uuid4(), usable=False)
        )
        with pytest.raises(CommandRejected, match="NOT_FOUND_OR_UNAUTHORIZED"):
            await prepare_discussion_action(
                db, discussion_owner, request, operation="discussion_context.use"
            )


async def test_changed_intent_cannot_reuse_the_prior_approval(
    async_engine, discussion_owner, monkeypatch
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    request = DiscussionPreferencesIntent(
        discussion_preferences=DiscussionPolicyPatch(enabled=True)
    )
    async with AsyncSession(async_engine) as db:
        draft = await prepare_discussion_action(
            db, discussion_owner, request, operation="proactive_discussions.update"
        )
        await db.commit()
    changed = draft.model_copy(update={"intent": {"discussion_preferences": {"enabled": False}}})
    async with AsyncSession(async_engine) as db:
        with (
            effect_scope(approval(draft)),
            pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"),
        ):
            await execute_discussion_action(db, discussion_owner, changed, PreferenceWriteReceipt())
