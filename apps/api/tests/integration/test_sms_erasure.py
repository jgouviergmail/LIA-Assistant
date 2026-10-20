"""Erasure fences derived artefacts while retaining only retry tombstones."""

import pytest
from sqlalchemy import func, select

from src.core.exceptions import ResourceConflictError
from src.domains.account_export.models import AccountExportJob
from src.domains.ingestion.models import IngestionDelivery, IngestionReceipt
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.models import SmsMessage, SmsSearchTerm
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration


async def check():
    return None


async def test_erased_message_retry_cannot_resurrect_and_exports_are_revoked(db_session, test_user):
    from src.domains.sms.management_commands import erase_sms, prepare_sms_erasure
    from src.domains.sms.management_schemas import SmsEraseRequest

    actor = await authority(db_session, test_user)
    payload = message()
    await SmsIngestionService(db_session).ingest(actor, [payload])
    db_session.add(
        AccountExportJob(user_id=test_user.id, status="done", file_path="/fictional.zip")
    )
    await db_session.commit()
    revision = test_user.extraction_revision or 0
    selection = await prepare_sms_erasure(
        db_session, test_user.id, SmsEraseRequest(all_messages=True)
    )
    receipt = PreferenceWriteReceipt()
    await erase_sms(db_session, test_user.id, selection, receipt, check)
    assert receipt.committed
    for model in (SmsMessage, SmsSearchTerm):
        assert await db_session.scalar(select(func.count()).select_from(model)) == 0
    assert (await db_session.scalar(select(IngestionReceipt))).verdict == "deleted"
    assert (await db_session.scalar(select(IngestionDelivery))).state == "cancelled"
    assert (await db_session.scalar(select(AccountExportJob))).status == "expired"
    assert test_user.extraction_revision == revision + 1
    assert (await SmsIngestionService(db_session).ingest(actor, [payload])).duplicate == 1
    assert await db_session.scalar(select(func.count()).select_from(SmsMessage)) == 0


async def test_erasure_closes_the_reviewed_snapshot_not_a_later_arrival(db_session, test_user):
    from src.domains.sms.management_commands import erase_sms, prepare_sms_erasure
    from src.domains.sms.management_schemas import SmsEraseRequest

    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(actor, [message()])
    selection = await prepare_sms_erasure(
        db_session, test_user.id, SmsEraseRequest(all_messages=True)
    )
    await SmsIngestionService(db_session).ingest(actor, [message(sender="Later")])
    await erase_sms(db_session, test_user.id, selection, PreferenceWriteReceipt(), check)
    assert await db_session.scalar(select(func.count()).select_from(SmsMessage)) == 1
    with pytest.raises(ResourceConflictError):
        await erase_sms(db_session, test_user.id, selection, PreferenceWriteReceipt(), check)


async def test_withdrawal_fences_extraction_and_pending_push_without_erasing_archive(
    db_session, test_user
):
    from src.domains.sms.management_commands import update_sms_preferences
    from src.domains.sms.preferences import SmsPreferences

    test_user.sms_preferences = {"assistant_enabled": True}
    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(actor, [message()])
    expected = SmsPreferences.from_stored(test_user.sms_preferences)
    changed = expected.model_copy(update={"assistant_enabled": False, "push_enabled": False})
    revision = test_user.extraction_revision or 0
    await update_sms_preferences(
        db_session, test_user.id, expected, changed, PreferenceWriteReceipt(), check
    )
    assert (await db_session.scalar(select(IngestionDelivery))).state == "cancelled"
    assert await db_session.scalar(select(func.count()).select_from(SmsMessage)) == 1
    assert test_user.extraction_revision == revision + 1
    with pytest.raises(ResourceConflictError):
        await update_sms_preferences(
            db_session, test_user.id, expected, changed, PreferenceWriteReceipt(), check
        )


async def test_erasure_refuses_a_message_changed_since_confirmation(db_session, test_user):
    from src.core.security.utils import encrypt_data
    from src.domains.sms.management_commands import erase_sms, prepare_sms_erasure
    from src.domains.sms.management_schemas import SmsEraseRequest

    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(actor, [message()])
    selection = await prepare_sms_erasure(
        db_session, test_user.id, SmsEraseRequest(all_messages=True)
    )
    row = await db_session.scalar(select(SmsMessage))
    row.body_encrypted = encrypt_data("Changed after review")
    await db_session.commit()
    with pytest.raises(ResourceConflictError):
        await erase_sms(db_session, test_user.id, selection, PreferenceWriteReceipt(), check)


async def test_push_switch_is_independent_of_assistant_data_consent_and_extraction_revision(
    db_session, test_user
):
    from src.domains.sms.management_commands import update_sms_preferences
    from src.domains.sms.preferences import SmsPreferences

    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(actor, [message()])
    before = SmsPreferences.from_stored(test_user.sms_preferences)
    revision = test_user.extraction_revision or 0
    await update_sms_preferences(
        db_session,
        test_user.id,
        before,
        before.model_copy(update={"push_enabled": False}),
        PreferenceWriteReceipt(),
        check,
    )
    assert test_user.extraction_revision == revision
    assert (await db_session.scalar(select(IngestionDelivery))).state == "cancelled"


async def test_empty_reviewed_erasure_has_no_effect_on_existing_exports_or_revision(
    db_session, test_user
):
    from src.domains.sms.management_commands import erase_sms, prepare_sms_erasure
    from src.domains.sms.management_schemas import SmsEraseRequest

    job = AccountExportJob(user_id=test_user.id, status="done", file_path="/fictional.zip")
    db_session.add(job)
    await db_session.commit()
    selected = await prepare_sms_erasure(
        db_session, test_user.id, SmsEraseRequest(all_messages=True)
    )
    before = test_user.extraction_revision or 0
    receipt = PreferenceWriteReceipt()
    await erase_sms(db_session, test_user.id, selected, receipt, check)
    await db_session.refresh(job)
    assert receipt.no_op and job.status == "done" and test_user.extraction_revision == before
