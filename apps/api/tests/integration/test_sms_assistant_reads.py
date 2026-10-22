"""Assistant reads and saved references cannot outlive live SMS authority."""

import pytest
from sqlalchemy import delete

from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.agents.sms.read_service import SmsToolReader
from src.domains.agents.sms.schemas import SmsGetRequest, SmsListRequest, SmsSearchRequest
from src.domains.agents.sms.snapshots import SmsSnapshotGuard
from src.domains.sms import identity_resolution as facade
from src.domains.sms.identity import IdentityBook
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.models import SmsMessage
from tests.integration.test_sms_ingestion import authority, message

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("sms_identity_session")]


@pytest.fixture(autouse=True)
def no_external_directory(monkeypatch):
    async def empty(owner, *, cache_scope=None):
        return IdentityBook()

    monkeypatch.setattr(facade, "load_identity_book", empty)


async def test_read_tools_share_real_source_search_and_owner_fences(
    db_session, test_user, test_superuser
):
    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(
        actor, [message(body="Café demain"), message(body="Autre rendez-vous")]
    )
    reader = SmsToolReader(db_session)
    with pytest.raises(AuthorizationError):
        await reader.list(test_user.id, SmsListRequest())
    test_user.sms_preferences = {"assistant_enabled": True}
    await db_session.commit()
    first = await reader.list(test_user.id, SmsListRequest(limit=1))
    assert first.total == 2 and len(first.sms_messages) == 1 and first.next_cursor
    second = await reader.list(test_user.id, SmsListRequest(limit=1, cursor=first.next_cursor))
    assert first.sms_messages[0].id != second.sms_messages[0].id
    found = await reader.search(test_user.id, SmsSearchRequest(query="cafe"))
    assert found.total == 1 and found.sms_messages[0].body == "Café demain"
    own = await reader.get(test_user.id, SmsGetRequest(message_id=found.sms_messages[0].id))
    assert own.sms_messages[0].body == "Café demain"
    test_superuser.sms_preferences = {"assistant_enabled": True}
    await db_session.commit()
    with pytest.raises(ResourceNotFoundError):
        await reader.get(test_superuser.id, SmsGetRequest(message_id=found.sms_messages[0].id))


async def test_reference_guard_checks_revision_live_rows_and_consent(db_session, test_user):
    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(actor, [message()])
    test_user.sms_preferences = {"assistant_enabled": True}
    await db_session.commit()
    output = await SmsToolReader(db_session).list(test_user.id, SmsListRequest())
    guard = SmsSnapshotGuard(db_session)
    assert await guard.allows(test_user.id, output.sms_messages)
    test_user.extraction_revision = (test_user.extraction_revision or 0) + 1
    await db_session.commit()
    assert not await guard.allows(test_user.id, output.sms_messages)
    fresh = await SmsToolReader(db_session).list(test_user.id, SmsListRequest())
    await db_session.execute(delete(SmsMessage).where(SmsMessage.user_id == test_user.id))
    await db_session.commit()
    assert not await guard.allows(test_user.id, fresh.sms_messages)
    test_user.sms_preferences = {"assistant_enabled": False}
    await db_session.commit()
    assert not await guard.allows(test_user.id, output.sms_messages)
