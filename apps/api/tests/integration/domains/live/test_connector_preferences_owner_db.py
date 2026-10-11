"""Real SQL Live settings share authority, exact state comparison and commit receipts."""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.exceptions import ResourceConflictError
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.live.connector_preference_commands import (
    connector_preference_snapshot,
    update_live_connector_settings,
)
from src.domains.live.preferences import LivePreferences
from src.domains.live.schemas import LiveConnectorSettings
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("intervention", ["none", "credentials", "provider", "metadata"])
async def test_current_sql_snapshot_preserves_reflexes_and_fences_changed_saved_state(
    async_session: AsyncSession,
    test_user: User,
    intervention: str,
) -> None:
    test_user.live_preferences = LivePreferences(
        interruptions=False, provider="gemini"
    ).model_dump()
    connector = Connector(
        id=uuid4(),
        user_id=test_user.id,
        connector_type=ConnectorType.GEMINI_LIVE,
        status=ConnectorStatus.ACTIVE,
        credentials_encrypted="old-private-key",
        scopes=[],
        connector_metadata={},
    )
    async_session.add(connector)
    await async_session.commit()
    expected = connector_preference_snapshot(test_user, connector, "gemini")
    if intervention == "credentials":
        connector.credentials_encrypted = "rotated-private-key"
    if intervention == "provider":
        test_user.live_preferences = LivePreferences(
            interruptions=False, provider="openai"
        ).model_dump()
    if intervention == "metadata":
        connector.connector_metadata = {"model": "other"}
    await async_session.commit()
    validate = AsyncMock()
    receipt = PreferenceWriteReceipt()
    desired = LiveConnectorSettings(
        model="chosen",
        voice="Kore",
        idle_timeout_seconds=120,
        session_max_minutes=0,
        session_budget_eur=2.5,
    )

    async def write():
        return await update_live_connector_settings(
            async_session,
            test_user.id,
            "gemini",
            desired,
            locate=AsyncMock(return_value=connector),
            validate=validate,
            expected=expected,
            receipt=receipt,
        )

    if intervention == "none":
        await write()
        assert receipt.committed and not receipt.no_op
        validate.assert_awaited_once()
        await async_session.refresh(connector)
        assert connector.connector_metadata["models"]["chosen"]["idle_timeout_seconds"] == 120
        assert connector.connector_metadata["session_budget_eur"] == 2.5
    else:
        with pytest.raises(ResourceConflictError):
            await write()
        assert not receipt.committed
        validate.assert_not_awaited()
    await async_session.refresh(test_user)
    assert test_user.live_preferences["interruptions"] is False


async def test_a_concurrent_reflex_writer_waits_and_preserves_the_live_provider_choice(
    async_engine: AsyncEngine,
) -> None:
    from src.domains.live.preference_commands import update_live_preferences

    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    actor = User(
        id=uuid4(),
        email=f"live-owner-{uuid4()}@example.test",
        is_active=True,
        live_preferences=LivePreferences(provider="gemini").model_dump(),
    )
    connector = Connector(
        id=uuid4(),
        user_id=actor.id,
        connector_type=ConnectorType.GEMINI_LIVE,
        status=ConnectorStatus.ACTIVE,
        scopes=[],
        credentials_encrypted="key",
        connector_metadata={},
    )
    async with maker() as setup:
        setup.add_all([actor, connector])
        await setup.commit()
    actor_id, connector_id = actor.id, connector.id
    probing = asyncio.Event()
    release = asyncio.Event()
    contender_started = asyncio.Event()

    async def validate(
        _actor: User, _connector: Connector, _settings: LiveConnectorSettings
    ) -> None:
        probing.set()
        await release.wait()

    async def configure() -> None:
        async with maker() as db:

            async def locate(_actor: User, _provider: str) -> Connector:
                row = await db.scalar(select(Connector).where(Connector.id == connector_id))
                assert row is not None
                return row

            await update_live_connector_settings(
                db,
                actor_id,
                "gemini",
                LiveConnectorSettings(
                    model="chosen",
                    voice="Kore",
                    idle_timeout_seconds=60,
                    session_max_minutes=10,
                ),
                locate=locate,
                validate=validate,
            )

    async def change_reflex() -> None:
        async with maker() as db:
            contender_started.set()
            await update_live_preferences(db, actor_id, LivePreferences(end_of_speech="calm"))

    configuring = asyncio.create_task(configure())
    changing = None
    try:
        await asyncio.wait_for(probing.wait(), timeout=5)
        changing = asyncio.create_task(change_reflex())
        await asyncio.wait_for(contender_started.wait(), timeout=5)
        await asyncio.sleep(0.05)
        assert not changing.done()
        release.set()
        await asyncio.wait_for(asyncio.gather(configuring, changing), timeout=5)
        async with maker() as verify:
            current = await verify.get(User, actor_id)
            assert current is not None
            assert current.live_preferences["provider"] == "gemini"
            assert current.live_preferences["end_of_speech"] == "calm"
    finally:
        release.set()
        await asyncio.gather(
            configuring, *([changing] if changing is not None else []), return_exceptions=True
        )
        async with maker() as cleanup:
            await cleanup.execute(delete(User).where(User.id == actor_id))
            await cleanup.commit()
