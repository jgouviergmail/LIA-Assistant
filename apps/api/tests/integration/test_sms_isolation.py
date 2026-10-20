"""Storage itself enforces ownership; key maintenance preserves idempotency."""

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.core.security import utils as security_utils
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.account_export.builder import _fetch_user_profile
from src.domains.ingestion.models import IngestionReceipt, IngestionSource, IngestionToken
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.models import SmsMessage
from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration


async def test_composite_foreign_key_rejects_a_token_using_another_owners_source(
    db_session, test_user, test_superuser
):
    actor = await authority(db_session, test_user)
    await db_session.commit()
    with pytest.raises(IntegrityError) as failure:
        async with db_session.begin_nested():
            db_session.add(
                IngestionToken(
                    user_id=test_superuser.id,
                    source_id=actor.source_id,
                    token_hash="b" * 64,
                    token_prefix="pi_cross",
                    scopes=["sms:write"],
                )
            )
            await db_session.flush()
    assert getattr(failure.value.orig, "sqlstate", None) == "23503"


async def test_composite_foreign_key_rejects_message_using_another_owners_receipt(
    db_session, test_user, test_superuser
):
    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(actor, [message(body="OTP: 123456")])
    receipt = await db_session.scalar(
        select(IngestionReceipt).where(IngestionReceipt.user_id == test_user.id)
    )
    with pytest.raises(IntegrityError) as failure:
        async with db_session.begin_nested():
            db_session.add(
                SmsMessage(
                    user_id=test_superuser.id,
                    receipt_id=receipt.id,
                    sender_encrypted=encrypt_data("other"),
                    sender_hash="c" * 64,
                    body_encrypted=encrypt_data("body"),
                    origin="iphone",
                    received_at=receipt.created_at,
                    date_kind="unknown",
                    logical_bytes=4,
                )
            )
            await db_session.flush()
    assert getattr(failure.value.orig, "sqlstate", None) == "23503"


async def test_rewrapping_tenant_key_preserves_existing_receipt_identity(db_session, test_user):
    actor = await authority(db_session, test_user)
    payload = message()
    service = SmsIngestionService(db_session)
    assert (await service.ingest(actor, [payload])).inserted == 1
    plain_key = decrypt_data(test_user.ingestion_key_encrypted)
    row = await db_session.scalar(select(SmsMessage).where(SmsMessage.user_id == test_user.id))
    source = await db_session.get(IngestionSource, actor.source_id)
    body, sender, label = (
        decrypt_data(row.body_encrypted),
        decrypt_data(row.sender_encrypted),
        decrypt_data(source.label_encrypted),
    )
    with patch.object(security_utils, "cipher_suite", Fernet(Fernet.generate_key())):
        test_user.ingestion_key_encrypted = encrypt_data(plain_key)
        row.body_encrypted, row.sender_encrypted = encrypt_data(body), encrypt_data(sender)
        source.label_encrypted = encrypt_data(label)
        await db_session.commit()
        retried = await service.ingest(actor, [payload])
        assert retried.duplicate == 1 and retried.inserted == 0
        assert decrypt_data(row.body_encrypted) == payload["body"]


async def test_personal_export_excludes_wrapped_hmac_material(db_session, test_user):
    await authority(db_session, test_user)
    await db_session.commit()

    @asynccontextmanager
    async def session():
        yield db_session

    with patch("src.domains.account_export.builder.get_db_context", session):
        exported = await _fetch_user_profile(test_user.id)
    assert "ingestion_key_encrypted" not in exported
    assert test_user.ingestion_key_encrypted not in str(exported)


async def test_missing_established_key_fails_closed_instead_of_resetting_identity(
    db_session, test_user
):
    from uuid import uuid4

    from src.core.exceptions import ExternalServiceError
    from src.domains.ingestion.token_commands import create_managed_token
    from src.domains.users.preference_cas import PreferenceWriteReceipt

    actor = await authority(db_session, test_user)
    await db_session.commit()
    test_user.ingestion_key_encrypted = None
    await db_session.commit()
    with pytest.raises(ExternalServiceError):
        await SmsIngestionService(db_session).ingest(actor, [message()])
    await db_session.rollback()

    async def check():
        return None

    with pytest.raises(ExternalServiceError):
        await create_managed_token(
            db_session, actor.user_id, uuid4(), "Another", None, PreferenceWriteReceipt(), check
        )
    await db_session.rollback()
