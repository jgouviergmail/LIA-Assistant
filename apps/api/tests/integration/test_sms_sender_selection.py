"""Sender selection is an indexed owner-scoped predicate, separate from body search."""

import pytest

from src.core.exceptions import ResourceConflictError
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.read_schemas import SmsQuery
from src.domains.sms.reads import SmsReadService
from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration


async def test_literal_sender_filter_is_normalized_owned_and_cursor_bound(
    db_session, test_user, test_superuser
):
    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(
        actor,
        [
            message(sender="+33612345678", body="Déjeuner demain"),
            message(sender="+33612345678", body="Dîner ce soir"),
            message(sender="Autre", body="Déjeuner ailleurs"),
        ],
    )
    test_user.sms_preferences = {"assistant_enabled": True}
    await db_session.commit()
    reader = SmsReadService(db_session)
    query = SmsQuery(sender="+33 6 12 34 56 78", limit=1)
    first = await reader.list(test_user.id, query, assistant=True)
    assert first.total == 2 and len(first.items) == 1 and first.next_cursor
    second = await reader.list(
        test_user.id, query.model_copy(update={"cursor": first.next_cursor}), assistant=True
    )
    assert second.total == 2 and second.items[0].id != first.items[0].id
    narrowed = await reader.list(
        test_user.id, SmsQuery(sender="+33 6 12 34 56 78", query="dejeuner"), assistant=True
    )
    assert narrowed.total == 1 and narrowed.items[0].body == "Déjeuner demain"
    with pytest.raises(ResourceConflictError):
        await reader.list(
            test_user.id,
            SmsQuery(sender="Autre", limit=1, cursor=first.next_cursor),
            assistant=True,
        )
    assert (
        await reader.list(test_superuser.id, SmsQuery(sender="+33612345678"), assistant=False)
    ).total == 0


async def test_empty_search_needs_no_key_but_existing_archive_with_lost_key_refuses(
    db_session, test_user
):
    from src.core.exceptions import ExternalServiceError

    reader = SmsReadService(db_session)
    assert test_user.ingestion_key_encrypted is None
    assert (await reader.list(test_user.id, SmsQuery(query="bonjour"), assistant=False)).total == 0
    assert (await reader.list(test_user.id, SmsQuery(sender="Alice"), assistant=False)).total == 0
    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(actor, [message(sender="Alice", body="Bonjour")])
    test_user.ingestion_key_encrypted = None
    await db_session.commit()
    with pytest.raises(ExternalServiceError):
        await reader.list(test_user.id, SmsQuery(sender="Alice"), assistant=False)
    with pytest.raises(ExternalServiceError):
        await reader.list(test_user.id, SmsQuery(query="bonjour"), assistant=False)
