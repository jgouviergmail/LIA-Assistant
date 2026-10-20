"""Atomic receipt/content/outbox behavior against disposable PostgreSQL."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.ingestion.key_material import initialize_owner_key, key_for_owner
from src.domains.ingestion.models import (
    IngestionDelivery,
    IngestionReceipt,
    IngestionSource,
    IngestionToken,
)
from src.domains.ingestion.principal import IngestionPrincipal
from src.domains.ingestion.token_auth import hash_token
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.models import SmsMessage, SmsSearchTerm, SmsSenderBlock
from src.domains.sms.search import blind_digest
from src.domains.sms.sender_policy import normalize_sender

pytestmark = pytest.mark.integration


async def authority(db, user):
    await initialize_owner_key(db, user)
    source = IngestionSource(
        user_id=user.id, resource="sms", label_encrypted=encrypt_data("iPhone")
    )
    db.add(source)
    await db.flush()
    token = IngestionToken(
        user_id=user.id,
        source_id=source.id,
        token_hash=hash_token("pi_test"),
        token_prefix="pi_public",
        scopes=["sms:write"],
    )
    db.add(token)
    await db.flush()
    return IngestionPrincipal(
        user_id=user.id, token_id=token.id, source_id=source.id, scopes=frozenset({"sms:write"})
    )


def message(**overrides):
    return {
        "sender": "+33612345678",
        "date": datetime.now(UTC).isoformat(),
        "body": "Bonjour, déjeuner demain ?",
        "o": "iphone",
        "event_id": str(uuid4()),
        **overrides,
    }


async def test_atomic_archive_and_duplicate_lost_ack(db_session, test_user):
    actor = await authority(db_session, test_user)
    payload = message()
    service = SmsIngestionService(db_session)
    first = await service.ingest(actor, [payload])
    retry = await service.ingest(actor, [payload])
    assert (first.inserted, retry.duplicate) == (1, 1)
    for model in (SmsMessage, IngestionReceipt, IngestionDelivery):
        assert await db_session.scalar(select(func.count()).select_from(model)) == 1
    row = await db_session.scalar(select(SmsMessage))
    assert decrypt_data(row.body_encrypted) == payload["body"]
    assert payload["body"] not in row.body_encrypted
    assert await db_session.scalar(select(func.count()).select_from(SmsSearchTerm)) > 0


async def test_ignored_secret_never_reaches_content_index_or_outbox(db_session, test_user):
    actor = await authority(db_session, test_user)
    result = await SmsIngestionService(db_session).ingest(
        actor, [message(body="Votre code de connexion est 123456")]
    )
    assert result.ignored == 1
    for model in (SmsMessage, SmsSearchTerm, IngestionDelivery):
        assert await db_session.scalar(select(func.count()).select_from(model)) == 0
    receipt = await db_session.scalar(select(IngestionReceipt))
    assert receipt.verdict == "ignored_sensitive"
    assert "123456" not in repr(receipt.__dict__)
    assert "123456" not in result.model_dump_json()


async def test_invalid_item_does_not_disappear_from_acknowledgement(db_session, test_user):
    actor = await authority(db_session, test_user)
    result = await SmsIngestionService(db_session).ingest(
        actor, [message(), None, 42, message(body="OTP: 839201")]
    )
    assert (result.received, result.inserted, result.rejected, result.ignored) == (4, 1, 2, 1)
    assert [item.index for item in result.items] == [0, 1, 2, 3]


async def test_event_identity_conflict_cannot_replace_original(db_session, test_user):
    actor = await authority(db_session, test_user)
    payload = message()
    service = SmsIngestionService(db_session)
    await service.ingest(actor, [payload])
    result = await service.ingest(actor, [{**payload, "body": "Replacement"}])
    assert result.conflict == 1 and result.inserted == 0
    row = await db_session.scalar(select(SmsMessage))
    assert decrypt_data(row.body_encrypted) == payload["body"]


async def test_blocked_sender_leaves_only_an_opaque_receipt(db_session, test_user):
    actor = await authority(db_session, test_user)
    sender = "+33612345678"
    db_session.add(
        SmsSenderBlock(
            user_id=test_user.id,
            sender_hash=blind_digest(
                test_user.id, "sender", normalize_sender(sender), key=key_for_owner(test_user)
            ),
            sender_encrypted=encrypt_data(sender),
        )
    )
    await db_session.flush()
    result = await SmsIngestionService(db_session).ingest(actor, [message(sender=sender)])
    assert result.ignored == 1
    assert await db_session.scalar(select(func.count()).select_from(SmsMessage)) == 0


async def test_soft_account_purge_keeps_user_row_and_other_account_archive(
    db_session, test_user, test_superuser
):
    from src.domains.users.account_deletion_service import (
        AccountDeletionService,
        build_purge_statements,
    )
    from src.domains.users.models import User

    a = await authority(db_session, test_user)
    # Unique token digests are credential identities, even across owners.
    await initialize_owner_key(db_session, test_superuser)
    bsource = IngestionSource(
        user_id=test_superuser.id, resource="sms", label_encrypted=encrypt_data("other")
    )
    db_session.add(bsource)
    await db_session.flush()
    btoken = IngestionToken(
        user_id=test_superuser.id,
        source_id=bsource.id,
        token_hash=hash_token("pi_other"),
        token_prefix="pi_other",
        scopes=["sms:write"],
    )
    db_session.add(btoken)
    await db_session.flush()
    b = IngestionPrincipal(
        user_id=test_superuser.id,
        token_id=btoken.id,
        source_id=bsource.id,
        scopes=frozenset({"sms:write"}),
    )
    service = SmsIngestionService(db_session)
    await service.ingest(a, [message()])
    await service.ingest(b, [message()])
    test_user.is_active = False
    await db_session.flush()
    for _, statement in build_purge_statements(test_user.id):
        await db_session.execute(statement)
    await AccountDeletionService(db_session)._mark_user_deleted(test_user, None)
    await db_session.commit()
    assert test_user.ingestion_key_encrypted is None and test_user.sms_preferences is None
    assert await db_session.get(User, test_user.id) is not None
    for model in (
        IngestionSource,
        IngestionToken,
        IngestionReceipt,
        IngestionDelivery,
        SmsMessage,
        SmsSearchTerm,
        SmsSenderBlock,
    ):
        assert (
            await db_session.scalar(
                select(func.count()).select_from(model).where(model.user_id == test_user.id)
            )
            == 0
        )
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(SmsMessage)
            .where(SmsMessage.user_id == test_superuser.id)
        )
        == 1
    )


async def test_stale_principal_cannot_cross_saved_revocation(db_session, test_user):
    from src.core.exceptions import AuthenticationError

    actor = await authority(db_session, test_user)
    token = await db_session.get(IngestionToken, actor.token_id)
    token.revoked_at = datetime.now(UTC)
    await db_session.commit()
    with pytest.raises(AuthenticationError):
        await SmsIngestionService(db_session).ingest(actor, [message()])
    assert await db_session.scalar(select(func.count()).select_from(SmsMessage)) == 0


async def test_logical_storage_exhaustion_does_not_evict_or_consume_identity(db_session, test_user):
    from unittest.mock import patch

    from src.core.config import settings

    actor = await authority(db_session, test_user)
    payload = message()
    service = SmsIngestionService(db_session)
    with patch.object(settings, "sms_archive_max_logical_bytes", 1):
        refused = await service.ingest(actor, [payload])
    assert refused.rejected == 1 and refused.items[0].verdict == "storage_full"
    assert await db_session.scalar(select(func.count()).select_from(IngestionReceipt)) == 0
    assert (await service.ingest(actor, [payload])).inserted == 1


async def test_valid_credential_without_sms_scope_is_forbidden(db_session, test_user):
    from src.core.exceptions import AuthorizationError

    actor = await authority(db_session, test_user)
    token = await db_session.get(IngestionToken, actor.token_id)
    token.scopes = ["health:write"]
    await db_session.commit()
    with pytest.raises(AuthorizationError):
        await SmsIngestionService(db_session).authenticate("pi_test")


async def test_opaque_receipts_also_have_a_non_evicting_storage_budget(db_session, test_user):
    from unittest.mock import patch

    from src.core.config import settings

    actor = await authority(db_session, test_user)
    service = SmsIngestionService(db_session)
    first = message(body="OTP: 123456")
    with patch.object(settings, "ingestion_max_receipts_per_user", 1):
        assert (await service.ingest(actor, [first])).ignored == 1
        assert (await service.ingest(actor, [first])).duplicate == 1
        refused = await service.ingest(actor, [message()])
    assert refused.rejected == 1 and refused.items[0].verdict == "storage_full"
    assert await db_session.scalar(select(func.count()).select_from(IngestionReceipt)) == 1


async def test_ingestion_refuses_fresh_operator_withdrawal(db_session, test_user):
    from src.core.exceptions import AuthorizationError
    from src.domains.system_settings.models import SystemSetting, SystemSettingKey

    actor = await authority(db_session, test_user)
    db_session.add(SystemSetting(key=SystemSettingKey.CAPABILITY_SMS_ENABLED, value="false"))
    await db_session.commit()
    with pytest.raises(AuthorizationError):
        await SmsIngestionService(db_session).ingest(actor, [message()])
    assert await db_session.scalar(select(func.count()).select_from(SmsMessage)) == 0
