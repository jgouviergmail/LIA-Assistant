"""Real SQL persistence and independent sessions; contact providers stay simulated."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.core.security.utils import encrypt_data
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType, OAuthGrant
from src.domains.sms import identity_resolution as resolution
from src.domains.sms.identity import ContactIdentity, IdentityBook, SenderIdentity
from src.domains.sms.identity_models import SmsSenderIdentity
from src.domains.sms.identity_store import publish_resolutions, read_resolutions, reset_resolutions
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def sms_owner(async_engine, committed_user_ids):
    owner = uuid4()
    async with AsyncSession(async_engine) as db:
        db.add(
            User(
                id=owner,
                email=f"sms-registry-{owner}@example.test",
                full_name="SMS registry",
                is_active=True,
                is_verified=True,
                is_superuser=False,
                ingestion_key_encrypted=encrypt_data("v1:" + "34" * 32),
                sms_preferences={"assistant_enabled": True},
            )
        )
        await db.flush()
        committed_user_ids.append(owner)
        await db.commit()
    return owner


@pytest.mark.parametrize("known", [True, False])
async def test_persisted_resolution_shared_by_fresh_readers_and_explicitly_reset(
    async_engine, sms_owner, monkeypatch, known
):
    book = IdentityBook(
        contacts=(ContactIdentity("Alice", numbers=("+33612345678",)),) if known else (),
        complete=True,
    )
    load = AsyncMock(return_value=book)
    monkeypatch.setattr(resolution, "load_identity_book", load)
    for _ in range(6):
        result = await resolution.resolve_senders(
            sms_owner, ["+33612345678"], revision=0, assistant=False
        )
        assert result.identities["+33612345678"].display_name == (
            "Alice" if known else "+33612345678"
        )
    load.assert_awaited_once()
    async with AsyncSession(async_engine) as db:
        row = await db.scalar(
            select(SmsSenderIdentity).where(SmsSenderIdentity.user_id == sms_owner)
        )
        assert row is not None and "Alice" not in row.identity_encrypted
        await db.commit()
        await reset_resolutions(db, sms_owner)
    load.return_value = IdentityBook(
        contacts=(ContactIdentity("Bob", numbers=("+33612345678",)),), complete=True
    )
    updated = await resolution.resolve_senders(
        sms_owner, ["+33612345678"], revision=0, assistant=False
    )
    assert updated.identities["+33612345678"].display_name == "Bob"
    assert load.await_count == 2


async def test_reset_fences_a_contact_lookup_without_holding_a_sql_lock(
    async_engine, sms_owner, monkeypatch
):
    async def contact_lookup(owner, *, cache_scope=None):
        async with AsyncSession(async_engine) as db:
            await db.execute(text("SET LOCAL lock_timeout='150ms'"))
            await reset_resolutions(db, owner)
        return IdentityBook(complete=True)

    monkeypatch.setattr(resolution, "load_identity_book", contact_lookup)
    with pytest.raises(ResourceConflictError):
        await resolution.resolve_senders(sms_owner, ["12345"], revision=0, assistant=False)
    async with AsyncSession(async_engine) as db:
        assert (
            await db.scalar(
                select(SmsSenderIdentity.id).where(SmsSenderIdentity.user_id == sms_owner)
            )
            is None
        )


async def test_cached_names_still_obey_consent_and_retry_only_after_failure_cooldown(
    async_engine, sms_owner, monkeypatch
):
    load = AsyncMock(return_value=IdentityBook())
    monkeypatch.setattr(resolution, "load_identity_book", load)
    for _ in range(3):
        await resolution.resolve_senders(sms_owner, ["12345"], revision=0, assistant=True)
    load.assert_awaited_once()
    async with AsyncSession(async_engine) as db:
        row = await db.scalar(
            select(SmsSenderIdentity).where(SmsSenderIdentity.user_id == sms_owner)
        )
        row.retry_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    await resolution.resolve_senders(sms_owner, ["12345"], revision=0, assistant=True)
    assert load.await_count == 2
    async with AsyncSession(async_engine) as db:
        user = await db.get(User, sms_owner)
        user.sms_preferences = {"assistant_enabled": False}
        await db.commit()
    with pytest.raises(AuthorizationError):
        await resolution.resolve_senders(sms_owner, ["12345"], revision=0, assistant=True)
    assert load.await_count == 2
    # Withdrawing model access does not revoke the personal archive.
    await resolution.resolve_senders(sms_owner, ["12345"], revision=0, assistant=False)
    async with AsyncSession(async_engine) as db:
        user = await db.get(User, sms_owner)
        user.is_active = False
        await db.commit()
    with pytest.raises(AuthorizationError):
        await resolution.resolve_senders(sms_owner, ["12345"], revision=0, assistant=False)
    assert load.await_count == 2


async def test_registry_is_owner_scoped_and_keeps_each_raw_sender_spelling(
    async_engine, sms_owner, committed_user_ids
):
    scope, _ = await read_resolutions(sms_owner, ("+33 6 12 34 56 78",), 0, False)
    await publish_resolutions(
        scope,
        {"+33 6 12 34 56 78": SenderIdentity("+33 6 12 34 56 78", "raw", "unresolved")},
        assistant=False,
    )
    _, cached = await read_resolutions(sms_owner, ("+33612345678", "+33 6 12 34 56 78"), 0, False)
    assert cached["+33612345678"].display_name == "+33612345678"
    assert cached["+33 6 12 34 56 78"].display_name == "+33 6 12 34 56 78"
    other = uuid4()
    async with AsyncSession(async_engine) as db:
        db.add(
            User(
                id=other,
                email=f"sms-other-{other}@example.test",
                full_name="Other",
                is_active=True,
                ingestion_key_encrypted=encrypt_data("v1:" + "56" * 32),
            )
        )
        await db.flush()
        committed_user_ids.append(other)
        await db.commit()
    _, foreign = await read_resolutions(other, ("+33612345678",), 0, False)
    assert not foreign


async def test_concurrent_readers_share_one_resolution(sms_owner, monkeypatch):
    async def slow(owner, *, cache_scope=None):
        await asyncio.sleep(0.1)
        return IdentityBook(contacts=(ContactIdentity("Alice", numbers=("12345",)),), complete=True)

    load = AsyncMock(side_effect=slow)
    monkeypatch.setattr(resolution, "load_identity_book", load)
    results = await asyncio.gather(
        *(
            resolution.resolve_senders(sms_owner, ["12345"], revision=0, assistant=False)
            for _ in range(4)
        )
    )
    assert all(result.identities["12345"].display_name == "Alice" for result in results)
    load.assert_awaited_once()


async def test_account_switch_invalidates_names_but_token_refresh_does_not(
    async_engine, sms_owner, monkeypatch
):
    async with AsyncSession(async_engine) as db:
        first = OAuthGrant(
            user_id=sms_owner,
            provider="google",
            client_id="test",
            subject="account-a",
            scopes=[],
            credentials_encrypted="initial",
        )
        second = OAuthGrant(
            user_id=sms_owner,
            provider="google",
            client_id="test",
            subject="account-b",
            scopes=[],
            credentials_encrypted="other",
        )
        db.add_all([first, second])
        await db.flush()
        connector = Connector(
            user_id=sms_owner,
            connector_type=ConnectorType.GOOGLE_CONTACTS,
            status=ConnectorStatus.ACTIVE,
            credentials_encrypted="unused",
            oauth_grant_id=first.id,
        )
        db.add(connector)
        await db.flush()
        first_id, second_id, connector_id = first.id, second.id, connector.id
        await db.commit()
    load = AsyncMock(
        return_value=IdentityBook(
            contacts=(ContactIdentity("Alice", numbers=("12345",)),), complete=True
        )
    )
    monkeypatch.setattr(resolution, "load_identity_book", load)
    await resolution.resolve_senders(sms_owner, ["12345"], revision=0, assistant=False)
    async with AsyncSession(async_engine) as db:
        grant = await db.get(OAuthGrant, first_id)
        grant.credentials_encrypted = "rotated-token"
        await db.commit()
    await resolution.resolve_senders(sms_owner, ["12345"], revision=0, assistant=False)
    load.assert_awaited_once()
    async with AsyncSession(async_engine) as db:
        connector = await db.get(Connector, connector_id)
        connector.oauth_grant_id = second_id
        await db.commit()
    load.return_value = IdentityBook(
        contacts=(ContactIdentity("Bob", numbers=("12345",)),), complete=True
    )
    updated = await resolution.resolve_senders(sms_owner, ["12345"], revision=0, assistant=False)
    assert updated.identities["12345"].display_name == "Bob"
    assert load.await_count == 2
    async with AsyncSession(async_engine) as db:
        connector = await db.get(Connector, connector_id)
        connector.status = ConnectorStatus.REVOKED
        await db.commit()
    load.return_value = IdentityBook(complete=True)
    disconnected = await resolution.resolve_senders(
        sms_owner, ["12345"], revision=0, assistant=False
    )
    assert disconnected.identities["12345"].state == "unresolved"
    assert load.await_count == 3
