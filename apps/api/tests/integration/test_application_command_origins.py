"""Real command origin persistence, revision fencing and Redis session revocation."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.core.security.utils import decrypt_data
from src.domains.agents.application.command_origin_binding import require_command_origin
from src.domains.agents.application.command_repository import (
    get_command,
    replace_pending_command,
    save_command,
)
from src.domains.agents.application.command_status import read_command_status
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome, ApplicationPhase
from src.domains.agents.application.preparation import prepare_preference_content
from src.domains.agents.application.schemas import PreferencePatch
from src.domains.users.models import User
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore

pytestmark = pytest.mark.integration


async def test_additive_origin_migration_preserves_legacy_unbound_commands(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import Connection, text

    monkeypatch.setattr(settings, "application_tools_enabled", True)
    draft = await prepare_preference_content(
        async_session, test_user.id, PreferencePatch(font_size=17)
    )
    await save_command(async_session, draft, f"draft-{uuid4()}")
    await async_session.commit()
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/2026_10_07_1330-d38fa76219bc_application_command_origin.py"
    )
    spec = importlib.util.spec_from_file_location("origin_additive_legacy_test", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def replay(connection: Connection) -> None:
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.downgrade()
        original = connection.execute(
            text("SELECT content_encrypted, phase FROM application_commands WHERE id=:id"),
            {"id": draft.command_id},
        ).one()
        migration.upgrade()
        upgraded = connection.execute(
            text(
                "SELECT content_encrypted, phase, origin_binding_encrypted FROM application_commands WHERE id=:id"
            ),
            {"id": draft.command_id},
        ).one()
        assert upgraded[:2] == original[:2] and upgraded[2] is None

    await (await async_session.connection()).run_sync(replay)


async def test_real_command_binding_is_encrypted_and_revoked_session_cannot_authorize_it(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    store = SessionStore(await get_redis_session())
    session = await store.create_session(str(test_user.id))
    origin = bind_browser_session(test_user.id, session.session_id)
    assert origin is not None
    try:
        draft = await prepare_preference_content(
            async_session, test_user.id, PreferencePatch(font_size=17)
        )
        await save_command(async_session, draft, f"draft-{uuid4()}", origin=origin)
        await async_session.commit()
        row = await get_command(async_session, draft.command_id, test_user.id)
        assert row is not None and row.origin_binding_encrypted is not None
        assert origin.binding_id not in row.origin_binding_encrypted
        assert session.session_id not in decrypt_data(row.origin_binding_encrypted)
        assert "step_up" not in decrypt_data(row.origin_binding_encrypted)
        await require_command_origin(row, origin)
        status = await read_command_status(async_session, test_user.id, draft.command_id, origin)
        assert status.phase.value == "pending"
        assert "origin_binding" not in status.model_dump_json()
        await store.delete_session(session.session_id)
        with pytest.raises(AuthorizationError):
            await require_command_origin(row, origin)
        with pytest.raises(AuthorizationError):
            await read_command_status(async_session, test_user.id, draft.command_id, origin)
    finally:
        await store.delete_session(session.session_id)


@pytest.mark.parametrize("addressed", [False, True])
async def test_bound_revision_cannot_drop_or_replace_its_original_transport(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    addressed: bool,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    store = SessionStore(await get_redis_session())
    first = await store.create_session(str(test_user.id))
    second = await store.create_session(str(test_user.id))
    original_origin = bind_browser_session(
        test_user.id, first.session_id, device_id=str(uuid4()) if addressed else None
    )
    other_origin = bind_browser_session(test_user.id, second.session_id)
    try:
        draft = await prepare_preference_content(
            async_session, test_user.id, PreferencePatch(font_size=17)
        )
        await save_command(
            async_session,
            draft,
            f"draft-{uuid4()}",
            origin=original_origin,
            bind_device=addressed,
        )
        await async_session.commit()
        revised = await prepare_preference_content(
            async_session, test_user.id, PreferencePatch(font_size=18), command_id=draft.command_id
        )
        for invalid_origin in [None, other_origin]:
            with pytest.raises(AuthorizationError):
                await replace_pending_command(async_session, draft, revised, origin=invalid_origin)
        if addressed:
            wrong_tab = bind_browser_session(test_user.id, first.session_id, device_id=str(uuid4()))
            with pytest.raises(AuthorizationError):
                await replace_pending_command(async_session, draft, revised, origin=wrong_tab)
        assert await replace_pending_command(async_session, draft, revised, origin=original_origin)
        row = await get_command(async_session, draft.command_id, test_user.id)
        assert row is not None
        await require_command_origin(row, original_origin, require_device=addressed)
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await async_session.commit()
        with pytest.raises(AuthorizationError):
            await require_command_origin(row, original_origin)
    finally:
        await store.delete_session(first.session_id)
        await store.delete_session(second.session_id)


@pytest.mark.parametrize("withdrawal", ["inactive", "admin_downgrade", "operator"])
async def test_status_withholds_result_after_authority_changes_during_live_origin_read(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    withdrawal: str,
) -> None:
    from dataclasses import replace

    from sqlalchemy import update

    from src.domains.agents.application import command_status
    from src.domains.agents.application.operation_spec import OperationRegistry

    monkeypatch.setattr(settings, "application_tools_enabled", True)
    test_user.is_superuser = True
    await async_session.commit()
    store = SessionStore(await get_redis_session())
    session = await store.create_session(str(test_user.id))
    origin = bind_browser_session(test_user.id, session.session_id)
    assert origin is not None
    try:
        draft = await prepare_preference_content(
            async_session, test_user.id, PreferencePatch(font_size=17)
        )
        await save_command(async_session, draft, f"draft-{uuid4()}", origin=origin)
        await async_session.commit()
        row = await get_command(async_session, draft.command_id, test_user.id)
        assert row is not None
        row.phase = ApplicationPhase.COMMITTED
        from src.core.security.utils import encrypt_data

        row.result_encrypted = encrypt_data(
            ApplicationExecutionOutcome(
                success=True,
                phase=ApplicationPhase.COMMITTED,
                committed=True,
                values={"font_size": 17},
            ).model_dump_json()
        )
        await async_session.commit()
        if withdrawal == "admin_downgrade":
            operations = OperationRegistry()
            operations.register(
                replace(
                    command_status.APPLICATION_OPERATIONS.get(draft.operation_id),
                    administrative=True,
                )
            )
            monkeypatch.setattr(command_status, "APPLICATION_OPERATIONS", operations)

        async def withdrawing_read():
            facts = await origin.read_current()
            if withdrawal == "operator":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            else:
                await async_session.execute(
                    update(User)
                    .where(User.id == test_user.id)
                    .values(
                        **(
                            {"is_active": False}
                            if withdrawal == "inactive"
                            else {"is_superuser": False}
                        )
                    )
                )
                await async_session.commit()
            return facts

        live = ApplicationOrigin(test_user.id, origin.binding_id, withdrawing_read)
        with pytest.raises(AuthorizationError):
            await read_command_status(async_session, test_user.id, draft.command_id, live)
    finally:
        await store.delete_session(session.session_id)
