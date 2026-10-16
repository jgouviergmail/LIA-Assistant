"""A provider wait cannot restore credentials after account/config revocation."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.exceptions import BaseAPIException
from src.core.oauth import flow_handler as oauth_flow
from src.core.session_dependencies import get_session_store
from src.domains.connectors import service as service_module
from src.domains.connectors.clients.philips_hue_client import PhilipsHueClient
from src.domains.connectors.models import (
    Connector,
    ConnectorGlobalConfig,
    ConnectorStatus,
    ConnectorType,
)
from src.domains.connectors.oauth_bulk import plan_connection
from src.domains.connectors.oauth_bulk_service import BulkOAuthService
from src.domains.connectors.oauth_identity import ProviderIdentity
from src.domains.connectors.router import get_db, rotate_api_key, router
from src.domains.connectors.schemas import (
    APIKeyActivationRequest,
    ConnectorGlobalConfigUpdate,
    ConnectorUpdate,
)
from src.domains.connectors.service import ConnectorService
from src.domains.users.models import User
from src.infrastructure.cache.session_store import UserSession
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("revocation", ["inactive", "deleted", "missing"])
async def test_grouped_oauth_uses_the_same_active_owner_boundary(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    revocation: str,
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    async with maker() as setup:
        user = UserFactory.create()
        setup.add(user)
        await setup.flush()
        committed_user_ids.append(user.id)
        await setup.commit()
        user_id = user.id
    async with maker() as admin:
        if revocation == "missing":
            await admin.execute(delete(User).where(User.id == user_id))
        else:
            values = (
                {"is_active": False}
                if revocation == "inactive"
                else {"deleted_at": datetime.now(UTC)}
            )
            await admin.execute(update(User).where(User.id == user_id).values(**values))
        await admin.commit()
    async with maker() as request:
        plan = plan_connection("google", [], [ConnectorType.GOOGLE_GMAIL])
        with pytest.raises(BaseAPIException) as refused:
            await BulkOAuthService(request)._lock_account_and_connectors(
                user_id,
                "google",
                plan,
                ProviderIdentity("proof-subject", "proof@example.com"),
                "proof-client",
                "connect",
            )
        assert refused.value.status_code == 403


@pytest.mark.parametrize("path", ["api-key", "hue-local", "oauth", "hue-remote", "hue-remote-wait"])
@pytest.mark.parametrize("revocation", ["inactive", "deleted", "missing"])
async def test_each_native_activation_refuses_a_revoked_owner_before_persisting(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    revocation: str,
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    async with maker() as setup:
        user = UserFactory.create()
        setup.add(user)
        await setup.flush()
        committed_user_ids.append(user.id)
        await setup.commit()
        user_id = user.id

    async def revoke(*args: object) -> None:
        async with maker() as admin:
            if revocation == "missing":
                await admin.execute(delete(User).where(User.id == user_id))
            else:
                values = (
                    {"is_active": False}
                    if revocation == "inactive"
                    else {"deleted_at": datetime.now(UTC)}
                )
                await admin.execute(update(User).where(User.id == user_id).values(**values))
            await admin.commit()

    if path == "api-key":
        await revoke()
    elif path == "hue-local":
        monkeypatch.setattr(PhilipsHueClient, "test_connection", AsyncMock(side_effect=revoke))
    else:

        async def callback(*args: object) -> tuple[oauth_flow.OAuthTokenResponse, dict[str, str]]:
            if path != "hue-remote-wait":
                await revoke()
            return (
                oauth_flow.OAuthTokenResponse(
                    access_token="proof-access",
                    refresh_token="proof-refresh",
                    token_type="Bearer",
                    scope="https://www.googleapis.com/auth/gmail.modify",
                ),
                {"user_id": str(user_id), "connector_type": ConnectorType.GOOGLE_GMAIL.value},
            )

        handler = MagicMock(handle_callback=AsyncMock(side_effect=callback))
        monkeypatch.setattr("src.core.oauth.OAuthFlowHandler", lambda *args: handler)
        monkeypatch.setattr(
            service_module, "get_redis_session", AsyncMock(return_value=MagicMock())
        )
    remote_client = MagicMock(put=AsyncMock(), post=AsyncMock())
    remote_context = MagicMock(
        __aenter__=AsyncMock(return_value=remote_client),
        __aexit__=AsyncMock(return_value=False),
    )
    remote_factory = MagicMock(return_value=remote_context)
    if path.startswith("hue-remote"):
        monkeypatch.setattr(service_module.httpx, "AsyncClient", remote_factory)
    async with maker() as request:

        async def remote_ack(*args: object, **kwargs: object) -> MagicMock:
            assert not request.in_transaction(), "provider wait must not retain SQL"
            if path == "hue-remote-wait":
                await revoke()
            return MagicMock(json=lambda: [{"success": {"username": "proof-remote-user"}}])

        remote_client.post.side_effect = remote_ack
        service = ConnectorService(request)
        monkeypatch.setattr(service, "_invalidate_user_connectors_cache", AsyncMock())
        with pytest.raises(BaseAPIException) as refused:
            if path == "api-key":
                await service.activate_api_key_connector(
                    user_id, ConnectorType.BRAVE_SEARCH, "proof-key-not-real"
                )
            elif path == "hue-local":
                await service.activate_hue_local(user_id, "192.168.1.2", "proof-key-not-real")
            elif path.startswith("hue-remote"):
                await service.handle_hue_oauth_callback("proof-code", "proof-state")
            else:
                await service._handle_oauth_connector_callback(
                    user_id,
                    "proof-code",
                    "proof-state",
                    ConnectorType.GOOGLE_GMAIL,
                    lambda config: MagicMock(),
                )
        assert refused.value.status_code == 403
        if path == "hue-remote":
            remote_factory.assert_not_called()
        elif path == "hue-remote-wait":
            remote_client.post.assert_awaited_once()
        await request.rollback()
    async with maker() as verification:
        assert (
            list(
                (
                    await verification.scalars(
                        select(Connector.id).where(Connector.user_id == user_id)
                    )
                ).all()
            )
            == []
        )


@pytest.mark.parametrize("same_type", [False, True])
async def test_key_rotation_targets_the_owned_type_without_holding_sql_during_verification(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
    same_type: bool,
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    async with maker() as setup:
        user = UserFactory.create()
        setup.add(user)
        await setup.flush()
        committed_user_ids.append(user.id)
        connector = Connector(
            user_id=user.id,
            connector_type=ConnectorType.BRAVE_SEARCH,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
            credentials_encrypted="proof-original-credentials",
        )
        setup.add(connector)
        await setup.commit()
        connector_id = connector.id
    async with maker() as request:

        async def validate(*args: object) -> tuple[bool, str]:
            if same_type:
                assert (
                    not request.in_transaction()
                ), "rotation holds SQL during provider verification"
            return True, "proof verified"

        verifier = AsyncMock(side_effect=validate)
        monkeypatch.setattr(ConnectorService, "validate_api_key", verifier)
        monkeypatch.setattr(ConnectorService, "_invalidate_user_connectors_cache", AsyncMock())
        payload = APIKeyActivationRequest(
            connector_type=ConnectorType.BRAVE_SEARCH if same_type else ConnectorType.PERPLEXITY,
            api_key="proof-new-key-not-real",
        )
        if same_type:
            response = await rotate_api_key(connector_id, payload, user, request)
            assert response.id == connector_id
            verifier.assert_awaited_once()
        else:
            with pytest.raises(BaseAPIException) as refused:
                await rotate_api_key(connector_id, payload, user, request)
            assert refused.value.status_code == 400
            verifier.assert_not_awaited()
    async with maker() as verification:
        rows = list(
            (
                await verification.scalars(select(Connector).where(Connector.user_id == user.id))
            ).all()
        )
        assert len(rows) == 1 and rows[0].id == connector_id
        if not same_type:
            assert rows[0].credentials_encrypted == "proof-original-credentials"


async def test_status_update_cannot_reactivate_a_globally_disabled_connector(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    async with maker() as setup:
        user = UserFactory.create()
        setup.add(user)
        await setup.flush()
        committed_user_ids.append(user.id)
        connector = Connector(
            user_id=user.id,
            connector_type=ConnectorType.BRAVE_SEARCH,
            status=ConnectorStatus.REVOKED,
            scopes=[],
            credentials_encrypted="proof-unused-credentials",
        )
        config = ConnectorGlobalConfig(
            connector_type=ConnectorType.BRAVE_SEARCH,
            is_enabled=False,
            disabled_reason="Proof global disable",
        )
        setup.add_all([connector, config])
        await setup.commit()
        user_id, connector_id, config_id = user.id, connector.id, config.id
    try:
        async with maker() as request:
            service = ConnectorService(request)
            monkeypatch.setattr(service, "_invalidate_user_connectors_cache", AsyncMock())
            with pytest.raises(BaseAPIException) as refused:
                await service.update_connector(
                    user_id, connector_id, ConnectorUpdate(status=ConnectorStatus.ACTIVE)
                )
            assert refused.value.status_code == 403
        async with maker() as verification:
            connector = await verification.get(Connector, connector_id)
            assert connector is not None and connector.status == ConnectorStatus.REVOKED
    finally:
        async with maker() as cleanup:
            await cleanup.execute(
                delete(ConnectorGlobalConfig).where(ConnectorGlobalConfig.id == config_id)
            )
            await cleanup.commit()


@pytest.mark.parametrize("revocation", ["inactive", "deleted", "missing"])
async def test_apple_activation_rechecks_the_account_after_the_provider_wait(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
    revocation: str,
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    async with maker() as setup:
        user = UserFactory.create()
        setup.add(user)
        await setup.flush()
        committed_user_ids.append(user.id)
        await setup.commit()
        user_id = user.id

    async def accepted(*args: object) -> tuple[bool, str]:
        async with maker() as admin:
            if revocation == "missing":
                await admin.execute(delete(User).where(User.id == user_id))
            else:
                values = (
                    {"is_active": False}
                    if revocation == "inactive"
                    else {"deleted_at": datetime.now(UTC)}
                )
                await admin.execute(update(User).where(User.id == user_id).values(**values))
            await admin.commit()
        return True, "Accepted by the simulated provider"

    async with maker() as request:
        service = ConnectorService(request)
        monkeypatch.setattr(service, "test_apple_connection", accepted)
        monkeypatch.setattr(service, "_invalidate_user_connectors_cache", AsyncMock())
        with pytest.raises(BaseAPIException) as refused:
            await service.activate_apple_connectors(
                user_id, "proof@example.test", "proof-password", [ConnectorType.APPLE_EMAIL]
            )
        assert refused.value.status_code == 403
        await request.rollback()
    async with maker() as verification:
        assert (
            list(
                (
                    await verification.scalars(
                        select(Connector.id).where(Connector.user_id == user_id)
                    )
                ).all()
            )
            == []
        )


async def test_apple_activation_rechecks_configuration_and_holds_no_sql_during_probe(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    async with maker() as setup:
        user = UserFactory.create()
        config = ConnectorGlobalConfig(connector_type=ConnectorType.APPLE_EMAIL, is_enabled=True)
        setup.add_all([user, config])
        await setup.flush()
        committed_user_ids.append(user.id)
        await setup.commit()
        user_id, config_id = user.id, config.id

    try:
        async with maker() as request:
            service = ConnectorService(request)

            async def accepted(*args: object) -> tuple[bool, str]:
                assert (
                    not request.in_transaction()
                ), "provider wait pins the request's SQL transaction"
                async with maker() as admin:
                    await admin.execute(
                        update(ConnectorGlobalConfig)
                        .where(ConnectorGlobalConfig.id == config_id)
                        .values(is_enabled=False)
                    )
                    await admin.commit()
                return True, "Accepted by the simulated provider"

            monkeypatch.setattr(service, "test_apple_connection", accepted)
            monkeypatch.setattr(service, "_invalidate_user_connectors_cache", AsyncMock())
            with pytest.raises(BaseAPIException) as refused:
                await service.activate_apple_connectors(
                    user_id, "proof@example.test", "proof-password", [ConnectorType.APPLE_EMAIL]
                )
            assert refused.value.status_code == 403
            await request.rollback()
        async with maker() as verification:
            assert (
                list(
                    (
                        await verification.scalars(
                            select(Connector.id).where(Connector.user_id == user_id)
                        )
                    ).all()
                )
                == []
            )
    finally:
        async with maker() as cleanup:
            await cleanup.execute(
                delete(ConnectorGlobalConfig).where(ConnectorGlobalConfig.id == config_id)
            )
            await cleanup.commit()


@pytest.mark.parametrize("operation", ["validate", "activate"])
async def test_the_authenticated_route_releases_sql_before_vendor_io(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    async with maker() as setup:
        user = UserFactory.create()
        setup.add(user)
        await setup.flush()
        committed_user_ids.append(user.id)
        await setup.commit()
        user_id = user.id

    sessions: list[AsyncSession] = []

    async def request_db() -> AsyncIterator[AsyncSession]:
        async with maker() as db:
            sessions.append(db)
            yield db

    async def accepted(*args: object) -> tuple[bool, str]:
        assert all(
            not db.in_transaction() for db in sessions
        ), "authentication holds SQL across vendor IO"
        return True, "Accepted by the simulated provider"

    probe = AsyncMock(side_effect=accepted)
    monkeypatch.setattr(ConnectorService, "test_apple_connection", probe)
    monkeypatch.setattr(ConnectorService, "_invalidate_user_connectors_cache", AsyncMock())
    store = MagicMock(
        get_session=AsyncMock(return_value=UserSession("proof-session", str(user_id))),
        touch_last_seen=AsyncMock(),
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = request_db
    app.dependency_overrides[get_session_store] = lambda: store
    body: dict[str, object] = {
        "apple_id": "proof@icloud.com",
        "app_password": "aaaa-bbbb-cccc-dddd",
    }
    if operation == "activate":
        body["services"] = [ConnectorType.APPLE_EMAIL.value]
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://proof.example",
        cookies={"lia_session": "proof-session"},
    ) as client:
        response = await client.post(f"/connectors/apple/{operation}", json=body)
    assert response.status_code == 200, response.text
    probe.assert_awaited_once()


@pytest.mark.parametrize(
    "existing_configuration", [False, True], ids=["default-without-row", "existing-row"]
)
async def test_global_disabling_cannot_miss_an_activation_between_check_and_commit(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
    existing_configuration: bool,
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    async with maker() as setup:
        user, admin = UserFactory.create(), UserFactory.create(is_superuser=True)
        setup.add_all([user, admin])
        if existing_configuration:
            setup.add(
                ConnectorGlobalConfig(connector_type=ConnectorType.APPLE_EMAIL, is_enabled=True)
            )
        await setup.flush()
        committed_user_ids.extend([user.id, admin.id])
        await setup.commit()
        user_id, admin_id = user.id, admin.id

    checked, release = asyncio.Event(), asyncio.Event()
    tasks: list[asyncio.Task[object]] = []
    notification = AsyncMock(return_value=True)
    monkeypatch.setattr(
        service_module,
        "get_email_service",
        lambda: MagicMock(send_connector_disabled_notification=notification),
    )
    try:
        async with maker() as activation_db, maker() as admin_db:
            activator = ConnectorService(activation_db)
            checker = activator._check_connector_enabled

            async def pause_after_check(*args: object, **kwargs: object) -> None:
                await checker(*args, **kwargs)
                checked.set()
                await release.wait()

            monkeypatch.setattr(activator, "_check_connector_enabled", pause_after_check)
            monkeypatch.setattr(
                activator, "test_apple_connection", AsyncMock(return_value=(True, "Accepted"))
            )
            monkeypatch.setattr(activator, "_invalidate_user_connectors_cache", AsyncMock())
            activation = asyncio.create_task(
                activator.activate_apple_connectors(
                    user_id, "proof@icloud.com", "proof-password", [ConnectorType.APPLE_EMAIL]
                )
            )
            tasks.append(activation)
            await asyncio.wait_for(checked.wait(), timeout=5)
            admin_pid = await admin_db.scalar(text("SELECT pg_backend_pid()"))
            disabling = asyncio.create_task(
                ConnectorService(admin_db).update_global_config(
                    ConnectorType.APPLE_EMAIL,
                    ConnectorGlobalConfigUpdate(
                        is_enabled=False, disabled_reason="Proof global disable"
                    ),
                    admin_id,
                )
            )
            tasks.append(disabling)
            blocked = False
            async with asyncio.timeout(5):
                while not disabling.done():
                    async with maker() as observer:
                        blocked = bool(
                            await observer.scalar(
                                text(
                                    "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE pid = :pid AND NOT granted)"
                                ),
                                {"pid": admin_pid},
                            )
                        )
                    if blocked:
                        break
                    await asyncio.sleep(0.01)
            assert (
                blocked
            ), "global disable passed the activation's checked configuration before its commit"
            release.set()
            await asyncio.gather(activation, disabling)
        async with maker() as verification:
            row = await verification.scalar(
                select(Connector).where(
                    Connector.user_id == user_id,
                    Connector.connector_type == ConnectorType.APPLE_EMAIL,
                )
            )
            assert row is not None
            assert row.status is ConnectorStatus.REVOKED
            config = await verification.scalar(
                select(ConnectorGlobalConfig).where(
                    ConnectorGlobalConfig.connector_type == ConnectorType.APPLE_EMAIL
                )
            )
            assert config is not None and config.is_enabled is False
        notification.assert_awaited_once()
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        # Join both owned tasks even when the assertion fails; their primary
        # assertion/exception remains the test's reported failure.
        await asyncio.gather(*tasks, return_exceptions=True)
        async with maker() as cleanup:
            await cleanup.execute(
                delete(ConnectorGlobalConfig).where(
                    ConnectorGlobalConfig.connector_type == ConnectorType.APPLE_EMAIL
                )
            )
            await cleanup.commit()
