"""Blocking is tenant-keyed, exact, confirmed and separate from historical erasure."""

import pytest
from sqlalchemy import func, select

from src.core.exceptions import ResourceConflictError
from src.domains.ingestion.models import IngestionDelivery
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.models import SmsMessage, SmsSenderBlock
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration


async def check():
    return None


async def test_blocking_prevents_future_storage_and_pending_push_but_preserves_history(
    db_session, test_user
):
    from src.domains.sms.sender_commands import prepare_sender_block, update_sender_block

    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(actor, [message(sender="+33612345678")])
    expected = await prepare_sender_block(
        db_session, test_user.id, "+33 6 12 34 56 78", blocked=True
    )
    receipt = PreferenceWriteReceipt()
    await update_sender_block(db_session, test_user.id, expected, receipt, check)
    assert receipt.committed
    assert (await db_session.scalar(select(IngestionDelivery))).state == "cancelled"
    result = await SmsIngestionService(db_session).ingest(actor, [message(sender="+33612345678")])
    assert result.items[0].verdict == "ignored_sender"
    assert await db_session.scalar(select(func.count()).select_from(SmsMessage)) == 1
    stored = await db_session.scalar(select(SmsSenderBlock))
    assert "33612345678" not in stored.sender_hash + stored.sender_encrypted
    with pytest.raises(ResourceConflictError):
        await update_sender_block(
            db_session, test_user.id, expected, PreferenceWriteReceipt(), check
        )


async def test_missing_key_with_only_block_state_is_not_silently_reinitialized(
    db_session, test_user
):
    from src.core.exceptions import ExternalServiceError
    from src.domains.ingestion.key_material import initialize_owner_key
    from src.domains.sms.sender_commands import prepare_sender_block, update_sender_block

    expected = await prepare_sender_block(db_session, test_user.id, "ACME", blocked=True)
    await update_sender_block(db_session, test_user.id, expected, PreferenceWriteReceipt(), check)
    test_user.ingestion_key_encrypted = None
    await db_session.commit()
    with pytest.raises(ExternalServiceError):
        await initialize_owner_key(db_session, test_user)
