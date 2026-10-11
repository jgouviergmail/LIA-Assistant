"""A pending handoff grants one fenced continuation, never a fresh action approval."""

from datetime import UTC, datetime, timedelta
from importlib import import_module
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_interaction import PendingApplicationInteraction
from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.command_repository import (
    claim_command,
    close_command,
    get_command,
    save_command,
)
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.preparation import prepare_preference_content
from src.domains.agents.application.schemas import PreferencePatch
from src.domains.users.models import User
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention", ["none", "wrong_session", "stale_step_up", "expired", "operator_off"]
)
async def test_waiting_continuation_requires_original_live_session_and_can_only_be_claimed_once(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    intervention: str,
) -> None:
    module = import_module("src.domains.agents.application.interaction_claim")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    store = SessionStore(await get_redis_session())
    session = await store.create_session(str(test_user.id))
    other = await store.create_session(str(test_user.id))
    origin = bind_browser_session(test_user.id, session.session_id)
    assert origin is not None
    try:
        draft = await prepare_preference_content(
            async_session, test_user.id, PreferencePatch(font_size=17)
        )
        await save_command(async_session, draft, f"draft-{uuid4()}", origin=origin)
        await async_session.commit()
        original_token = await claim_command(async_session, draft.command_id, test_user.id)
        assert original_token is not None
        waiting = ApplicationExecutionOutcome(
            success=False,
            phase=ApplicationPhase.WAITING,
            interaction=PendingApplicationInteraction(
                interaction_id=draft.command_id, kind="secure", expires_at=draft.expires_at
            ),
        )
        assert await close_command(
            async_session, draft.command_id, test_user.id, original_token, waiting
        )
        if intervention == "wrong_session":
            origin = bind_browser_session(test_user.id, other.session_id)
        elif intervention == "stale_step_up":

            async def stale_read():
                from src.core.application_origin import ApplicationSessionFacts

                return ApplicationSessionFacts(
                    user_id=test_user.id,
                    binding_id=origin.binding_id,
                    display_id="display",
                    step_up_at=datetime.now(UTC) - timedelta(days=1),
                )

            from src.core.application_origin import ApplicationOrigin

            origin = ApplicationOrigin(test_user.id, origin.binding_id, stale_read)
        elif intervention == "expired":
            row = await get_command(async_session, draft.command_id, test_user.id)
            row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await async_session.commit()
        elif intervention == "operator_off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        if intervention != "none":
            with pytest.raises(AuthorizationError):
                await module.claim_waiting_interaction(
                    async_session, test_user.id, draft.command_id, origin
                )
            return
        claimed = await module.claim_waiting_interaction(
            async_session, test_user.id, draft.command_id, origin
        )
        assert claimed is not None and claimed.token != original_token
        assert claimed.previous_outcome == waiting and claimed.draft == draft
        assert (
            await module.claim_waiting_interaction(
                async_session, test_user.id, draft.command_id, origin
            )
            is None
        )
        row = await get_command(async_session, draft.command_id, test_user.id)
        assert row.phase.value == "resuming" and row.claim_token == claimed.token
        wrong_origin = bind_browser_session(test_user.id, other.session_id)
        with pytest.raises(AuthorizationError):
            await module.claim_waiting_interaction(
                async_session, test_user.id, draft.command_id, wrong_origin
            )
        assert not await close_command(
            async_session,
            draft.command_id,
            test_user.id,
            original_token,
            ApplicationExecutionOutcome(
                success=True, phase=ApplicationPhase.COMMITTED, committed=True
            ),
        )
        assert await close_command(
            async_session,
            draft.command_id,
            test_user.id,
            claimed.token,
            ApplicationExecutionOutcome(
                success=True, phase=ApplicationPhase.COMMITTED, committed=True
            ),
        )
    finally:
        await store.delete_session(session.session_id)
        await store.delete_session(other.session_id)
