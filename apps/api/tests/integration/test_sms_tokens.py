"""Scoped credentials issue secrets once, rotate sources and compare revocation snapshots."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from src.domains.ingestion.models import IngestionToken
from src.domains.ingestion.token_auth import hash_token
from src.domains.ingestion.token_commands import (
    create_managed_token,
    read_owned_token,
    revoke_managed_token,
)
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_sms_ingestion import message

pytestmark = pytest.mark.integration


async def fresh_check():
    return None


async def test_secret_is_not_persisted_and_rotation_preserves_idempotency(db_session, test_user):
    receipt = PreferenceWriteReceipt()
    first = await create_managed_token(
        db_session, test_user.id, uuid4(), "iPhone", None, receipt, fresh_check
    )
    assert receipt.committed
    stored = await db_session.get(IngestionToken, first.id)
    assert stored.token_hash == hash_token(first.token)
    assert first.token not in str(receipt.values)
    assert first.token not in repr(stored.__dict__)
    service = SmsIngestionService(db_session)
    payload = message()
    assert (await service.ingest(await service.authenticate(first.token), [payload])).inserted == 1
    rotated = await create_managed_token(
        db_session,
        test_user.id,
        uuid4(),
        "iPhone",
        first.source_id,
        PreferenceWriteReceipt(),
        fresh_check,
    )
    assert rotated.source_id == first.source_id
    assert (
        await service.ingest(await service.authenticate(rotated.token), [payload])
    ).duplicate == 1


async def test_revocation_is_owned_and_observed_before_acknowledgement(db_session, test_user):
    from src.core.exceptions import AuthenticationError

    secret = await create_managed_token(
        db_session, test_user.id, uuid4(), "Phone", None, PreferenceWriteReceipt(), fresh_check
    )
    selected = await read_owned_token(db_session, test_user.id, secret.id)
    receipt = PreferenceWriteReceipt()
    await revoke_managed_token(db_session, test_user.id, selected, receipt, fresh_check)
    assert receipt.committed
    observed = await db_session.scalar(select(IngestionToken).where(IngestionToken.id == secret.id))
    assert observed.revoked_at is not None
    with pytest.raises(AuthenticationError):
        await SmsIngestionService(db_session).authenticate(secret.token)
