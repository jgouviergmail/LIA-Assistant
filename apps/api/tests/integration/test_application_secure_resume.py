"""A resumed secure action requires original HITL, fresh proof and one actual completion."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib import import_module
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from redis.exceptions import RedisError
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.application_interaction import PendingApplicationInteraction
from src.core.config import settings
from src.core.dependencies import get_db
from src.core.exceptions import AuthorizationError
from src.core.session_dependencies import get_current_active_session
from src.domains.agents.application.command_repository import (
    claim_command,
    close_command,
    get_command,
    save_command,
)
from src.domains.agents.application.command_status import ApplicationCommandStatus
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.application.session_bulk_operations import (
    SESSION_FLEET_OPERATION,
    prepare_other_sessions_revocation,
)
from src.domains.agents.effects.digest import args_digest, draft_digest
from src.domains.agents.effects.models import AgentEffect, EffectStatus
from src.domains.agents.effects.repository import EffectLedgerRepository
from src.domains.agents.effects.schemas import ClaimRequest
from src.domains.users.models import User
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore

pytestmark = pytest.mark.integration


@pytest.fixture
async def secure_request(
    async_engine: AsyncEngine,
) -> AsyncIterator[tuple[AsyncSession, User]]:
    """Real commits are required: a second connection cannot see a test SAVEPOINT."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    actor_id = uuid4()
    try:
        async with maker() as request:
            actor = User(id=actor_id, email=f"secure-{actor_id}@example.test", is_active=True)
            request.add(actor)
            await request.commit()
            yield request, actor
    finally:
        async with maker() as cleanup:
            await cleanup.execute(delete(User).where(User.id == actor_id))
            await cleanup.commit()


@pytest.mark.parametrize("transport", ["service", "http", "independent_http"])
@pytest.mark.parametrize(
    "intervention",
    [
        "valid",
        "gone",
        "stale_proof",
        "operator_off",
        "other_origin",
        "missing_approval",
        "lost_ack",
        "cancelled",
    ],
)
async def test_secure_resume_only_revokes_the_previously_approved_other_sessions(
    secure_request: tuple[AsyncSession, User],
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    intervention: str,
    transport: str,
) -> None:
    async_session, test_user = secure_request
    module = import_module("src.domains.agents.application.secure_continuation")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor_id = test_user.id
    redis = await get_redis_session()
    store = SessionStore(redis)
    current = await store.create_session(str(actor_id))
    target = await store.create_session(str(actor_id))
    later = None
    origin = bind_browser_session(actor_id, current.session_id)

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        if transport == "independent_http":
            maker = async_sessionmaker(async_engine, expire_on_commit=False)
            async with maker() as writer:
                assert writer is not async_session
                await writer.execute(text("SET LOCAL lock_timeout = '500ms'"))
                yield writer
                await writer.commit()
            return
        yield async_session
        await async_session.commit()

    monkeypatch.setattr(module, "get_db_context", session, raising=False)

    async def attempt() -> ApplicationCommandStatus:
        if transport == "service":
            return await module.resume_secure_application_command(
                async_session, actor_id, draft.command_id, origin
            )
        routes = import_module("src.domains.agents.application.command_router")
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_db] = lambda: async_session
        app.dependency_overrides[get_current_active_session] = lambda: User(
            id=actor_id, is_active=True
        )
        app.dependency_overrides[routes.rate_limit_command_resume] = lambda: None
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            cookies={
                settings.session_cookie_name: (
                    later.session_id
                    if intervention == "other_origin" and later is not None
                    else current.session_id
                )
            },
        ) as client:
            response = await client.post(f"/application-commands/{draft.command_id}/resume")
        assert "private provider-secret" not in response.text
        assert response.headers["cache-control"] == "no-store"
        if response.status_code != 200:
            assert response.status_code == 403
            if intervention == "stale_proof":
                assert response.json()["detail"]["error"] == "step_up_required"
            raise AuthorizationError()
        return ApplicationCommandStatus.model_validate(response.json())

    try:
        with patch.dict(
            APPLICATION_OPERATIONS._operations,
            {SESSION_FLEET_OPERATION.operation_id: SESSION_FLEET_OPERATION},
        ):
            draft = await prepare_other_sessions_revocation(async_session, actor_id, origin=origin)
            draft_id = f"secure-{uuid4()}"
            await save_command(async_session, draft, draft_id, origin=origin)
            await async_session.commit()
            token = await claim_command(async_session, draft.command_id, actor_id)
            assert token is not None
            waiting = ApplicationExecutionOutcome(
                success=False,
                phase=ApplicationPhase.WAITING,
                interaction=PendingApplicationInteraction(
                    interaction_id=draft.command_id,
                    kind="secure",
                    expires_at=draft.expires_at,
                ),
            )
            assert await close_command(async_session, draft.command_id, actor_id, token, waiting)
            repository = EffectLedgerRepository(async_session)
            original_id = None
            if intervention != "missing_approval":
                content = draft.model_dump(mode="json")
                original = await repository.claim(
                    ClaimRequest(
                        user_id=actor_id,
                        thread_id=f"thread-{uuid4()}",
                        run_id="original-run",
                        source="user",
                        execution_mode="react",
                        tool_name="draft:application_action",
                        mutation_policy="draft",
                        idempotency_key=f"draft:{draft_id}",
                        args_digest=args_digest("draft:application_action", {"draft": content}),
                        approval_kind="draft_critique",
                        approval_ref=draft_id,
                        draft_digest=draft_digest(content),
                    )
                )
                assert original.claim_token is not None
                original_id = original.effect.id
                assert await repository.close_waiting(
                    original_id,
                    original.claim_token,
                    result_payload=waiting.model_dump(mode="json"),
                )
                await async_session.commit()
            later = await store.create_session(str(actor_id))
            if intervention == "gone":
                await store.delete_session(target.session_id)
            elif intervention == "stale_proof":
                current.step_up_at = None
                await redis.set(
                    f"session:{current.session_id}", json.dumps(current.to_dict()), keepttl=True
                )
            elif intervention == "operator_off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            elif intervention == "other_origin":
                origin = bind_browser_session(actor_id, later.session_id)
            elif intervention in {"lost_ack", "cancelled"}:
                source = import_module("src.domains.auth.session_bulk_commands")
                actual = source.revoke_selected_sessions

                async def lose_ack(*args, **kwargs):
                    await actual(*args, **kwargs)
                    if intervention == "cancelled":
                        raise asyncio.CancelledError()
                    raise RedisError("private provider-secret")

                monkeypatch.setattr(source, "revoke_selected_sessions", lose_ack)
            refused = intervention in {
                "stale_proof",
                "operator_off",
                "other_origin",
                "missing_approval",
            }
            if refused:
                with pytest.raises(AuthorizationError):
                    await attempt()
                assert await redis.exists(f"session:{target.session_id}")
            elif intervention == "cancelled":
                with pytest.raises(asyncio.CancelledError):
                    await attempt()
                assert not await redis.exists(f"session:{target.session_id}")
                row = await get_command(async_session, draft.command_id, actor_id)
                assert row is not None and row.phase == ApplicationPhase.FAILED
            else:
                result = await attempt()
                assert result.outcome is not None
                assert result.outcome.success is (intervention != "lost_ack")
                if intervention == "lost_ack":
                    assert result.outcome.error_code == "COMPLETION_UNKNOWN"
                    assert "provider-secret" not in result.model_dump_json()
                else:
                    assert result.outcome.no_op is (intervention == "gone")
                    assert result.outcome.values["revoked_sessions"] == int(intervention == "valid")
                assert not await redis.exists(f"session:{target.session_id}")
                again = await attempt()
                assert again == result
            await async_session.rollback()
            effects = (
                await async_session.scalars(
                    select(AgentEffect).where(AgentEffect.user_id == actor_id)
                )
            ).all()
            assert len(effects) == (0 if original_id is None else (1 if refused else 2))
            if original_id is not None:
                original_effect = await async_session.get(AgentEffect, original_id)
                assert (
                    original_effect is not None and original_effect.status == EffectStatus.WAITING
                )
            if intervention == "cancelled":
                completed = next(effect for effect in effects if effect.id != original_id)
                assert completed.status == EffectStatus.FAILED
                assert completed.error_code == "COMPLETION_UNKNOWN"
            assert await redis.exists(f"session:{current.session_id}")
            assert await redis.exists(f"session:{later.session_id}")
    finally:
        for item in (current, target, later):
            if item is not None:
                await store.delete_session(item.session_id)
