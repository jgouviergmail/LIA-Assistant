"""An approved fleet selection never grows and must retain live step-up authority."""

import json
from datetime import UTC, datetime, timedelta
from importlib import import_module

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.availability import require_application_tools
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention",
    [
        "valid",
        "gone",
        "stale",
        "current_gone",
        "wrong_origin",
        "operator_off",
        "expired",
        "withdrawn_proof",
        "incomplete",
        "inactive",
        "later_origin",
    ],
)
async def test_revoke_other_sessions_spends_only_the_approved_resolved_selection(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    intervention: str,
) -> None:
    module = import_module("src.domains.auth.session_bulk_commands")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor_id = test_user.id
    invalid_session_id = f"invalid-{actor_id}"
    redis = await get_redis_session()
    store = SessionStore(redis)
    current = await store.create_session(str(actor_id))
    first = await store.create_session(str(actor_id))
    second = await store.create_session(str(actor_id))
    origin = bind_browser_session(actor_id, current.session_id)
    assert origin is not None
    later = None
    receipt = PreferenceWriteReceipt()
    try:
        expected = await module.read_owned_other_device_sessions(async_session, test_user, origin)
        assert {item.id for item in expected.sessions} == {first.display_id, second.display_id}
        assert all(item.current is False for item in expected.sessions)
        assert current.session_id not in expected.model_dump_json()
        later = await store.create_session(str(actor_id))
        if intervention == "gone":
            await store.delete_session(first.session_id)
        elif intervention == "stale":
            first.created_at -= timedelta(minutes=1)
            await redis.set(
                f"session:{first.session_id}", json.dumps(first.to_dict()), keepttl=True
            )
        elif intervention == "current_gone":
            await store.delete_session(current.session_id)
        elif intervention == "wrong_origin":
            origin = bind_browser_session(actor_id, first.session_id)
        elif intervention == "later_origin":
            origin = bind_browser_session(actor_id, later.session_id)
        elif intervention == "incomplete":
            await redis.sadd(f"user:{actor_id}:sessions", invalid_session_id)
            await redis.set(f"session:{invalid_session_id}", "bad-json", ex=60)
        deadline = datetime.now(UTC) + timedelta(minutes=5)
        if intervention == "expired":
            deadline = datetime.now(UTC) - timedelta(seconds=1)

        async def check() -> None:
            if intervention == "operator_off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            elif intervention == "inactive":
                test_user.is_active = False
                await async_session.commit()
            elif intervention == "withdrawn_proof":
                current.step_up_at = None
                await redis.set(
                    f"session:{current.session_id}", json.dumps(current.to_dict()), keepttl=True
                )
            await require_application_tools(async_session)

        if intervention in {"valid", "gone"}:
            removed = await module.revoke_owned_other_device_sessions(
                async_session,
                actor_id,
                expected,
                origin,
                receipt,
                check=check,
                approved_until=deadline,
            )
            assert receipt.committed and not receipt.no_op
            assert removed == (1 if intervention == "gone" else 2)
            assert not await redis.exists(f"session:{first.session_id}")
            assert not await redis.exists(f"session:{second.session_id}")
        else:
            with pytest.raises((AuthorizationError, ResourceConflictError)):
                await module.revoke_owned_other_device_sessions(
                    async_session,
                    actor_id,
                    expected,
                    origin,
                    receipt,
                    check=check,
                    approved_until=deadline,
                )
            assert not receipt.committed
            assert await redis.exists(f"session:{first.session_id}")
            assert await redis.exists(f"session:{second.session_id}")
        assert await redis.exists(f"session:{later.session_id}")
        if intervention != "current_gone":
            assert await redis.exists(f"session:{current.session_id}")
    finally:
        for item in (current, first, second, later):
            if item is not None:
                await store.delete_session(item.session_id)
        await redis.delete(f"session:{invalid_session_id}")
        await redis.srem(f"user:{actor_id}:sessions", invalid_session_id)


async def test_an_empty_approved_selection_is_a_noop_even_when_a_later_session_appears(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = import_module("src.domains.auth.session_bulk_commands")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor_id = test_user.id
    redis = await get_redis_session()
    store = SessionStore(redis)
    current = await store.create_session(str(actor_id))
    later = None
    try:
        origin = bind_browser_session(actor_id, current.session_id)
        expected = await module.read_owned_other_device_sessions(async_session, test_user, origin)
        assert expected.sessions == ()
        later = await store.create_session(str(actor_id))
        receipt = PreferenceWriteReceipt()

        async def check() -> None:
            await require_application_tools(async_session)

        assert (
            await module.revoke_owned_other_device_sessions(
                async_session,
                actor_id,
                expected,
                origin,
                receipt,
                check=check,
                approved_until=datetime.now(UTC) + timedelta(minutes=5),
            )
            == 0
        )
        assert receipt.committed and receipt.no_op
        assert await redis.exists(f"session:{current.session_id}")
        assert await redis.exists(f"session:{later.session_id}")
    finally:
        await store.delete_session(current.session_id)
        if later is not None:
            await store.delete_session(later.session_id)
