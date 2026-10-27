"""The personal archive needs a session; an ingestion credential never reads it."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.core.session_dependencies import get_current_active_session
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.preferences import SmsPreferences
from src.domains.users.models import User
from src.main import app
from tests.helpers.committed_users import commit_owner
from tests.integration.test_sms_ingestion import authority, message

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("sms_identity_session")]


@pytest.mark.usefixtures("committed_user_ids")
async def test_personal_search_and_detail_are_readable_without_assistant_consent(
    async_client, db_session, async_engine, committed_user_ids, caplog
):
    # Release owner/key locks before independent identity and recorder connections.
    owner = await commit_owner(async_engine, committed_user_ids)
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    async with maker() as setup:
        setup_user = await setup.get(User, owner)
        assert setup_user is not None
        actor = await authority(setup, setup_user)
        await SmsIngestionService(setup).ingest(actor, [message(body="Café demain")])
        await setup.commit()
    test_user = await db_session.get(User, owner)
    assert test_user is not None
    assert SmsPreferences.from_stored(test_user.sms_preferences).assistant_enabled is False
    app.dependency_overrides[get_current_active_session] = lambda: test_user
    try:
        response = await async_client.post("/api/v1/sms/search", json={"query": "cafe"})
        assert response.status_code == 200
        page = response.json()
        assert page["total"] == 1 and page["items"][0]["body"] == "Café demain"
        assert response.headers["cache-control"] == "no-store"
        detail = await async_client.get("/api/v1/sms/" + page["items"][0]["id"])
        assert detail.status_code == 200
        groups = await async_client.get("/api/v1/sms/senders")
        assert groups.status_code == 200 and groups.json()["total"] == 1
        assert "sms_contact_identity_unavailable" not in caplog.text
        assert "treatment_flush_failed" not in caplog.text
    finally:
        app.dependency_overrides.pop(get_current_active_session, None)


async def test_ingestion_token_cannot_read_personal_archive(async_client):
    response = await async_client.post(
        "/api/v1/sms/search", json={}, headers={"Authorization": "Bearer pi_test"}
    )
    assert response.status_code == 401


async def test_explicit_name_refresh_is_session_only_and_requires_no_assistant_consent(
    async_client, db_session, test_user, monkeypatch
):
    from src.domains.sms.identity_store import read_resolutions

    await authority(db_session, test_user)
    await db_session.commit()
    before, _ = await read_resolutions(test_user.id, ("12345",), 0, False)
    invalidate = AsyncMock()
    monkeypatch.setattr("src.domains.sms.identity_resolution.invalidate_contacts_cache", invalidate)
    app.dependency_overrides[get_current_active_session] = lambda: test_user
    try:
        response = await async_client.post("/api/v1/sms/identities/refresh")
        assert response.status_code == 204 and response.headers["cache-control"] == "no-store"
        after, _ = await read_resolutions(test_user.id, ("12345",), 0, False)
        assert after.generation != before.generation
        invalidate.assert_awaited_once_with(test_user.id)
    finally:
        app.dependency_overrides.pop(get_current_active_session, None)
    denied = await async_client.post(
        "/api/v1/sms/identities/refresh", headers={"Authorization": "Bearer pi_test"}
    )
    assert denied.status_code == 401


@pytest.mark.parametrize("provider", ["google_contacts", "apple_contacts", "microsoft_contacts"])
async def test_provider_directory_is_projected_once_with_literal_identifiers(
    db_session, test_user, monkeypatch, provider
):
    from src.domains.connectors.active_client import ActiveClient
    from src.domains.connectors.clients.contact_directory import ContactDirectory
    from src.domains.connectors.models import ConnectorType
    from src.domains.sms import identity_directory

    client = SimpleNamespace(
        list_email_directory=AsyncMock(
            return_value=ContactDirectory(
                persons=[
                    {
                        "names": [{"displayName": "Alice"}],
                        "phoneNumbers": [{"value": "+33612345678"}],
                    }
                ],
                truncated=False,
                from_cache=True,
            )
        )
    )

    @asynccontextmanager
    async def opened(*args, **kwargs):
        yield ActiveClient(
            client=client, connector_type=ConnectorType(provider), preferred_name=None
        )

    @asynccontextmanager
    async def session():
        yield db_session

    monkeypatch.setattr(identity_directory, "open_active_client", opened)
    monkeypatch.setattr(identity_directory, "get_db_context", session)
    book = await identity_directory.load_identity_book(test_user.id)
    assert book.resolve("06 12 34 56 78").display_name == "Alice"
    assert book.resolve("ACME12345").source == "raw"
    assert client.list_email_directory.await_count == 1
