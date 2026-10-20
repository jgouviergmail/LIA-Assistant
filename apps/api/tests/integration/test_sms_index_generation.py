"""A stale derived index must be detected across algorithm upgrades and restores."""

import pytest
from sqlalchemy import select

from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.models import SmsSearchTerm
from src.domains.sms.read_schemas import SmsQuery
from src.domains.sms.reads import SmsReadService
from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration


async def test_stale_projection_cannot_be_mistaken_for_a_complete_current_index(
    db_session, test_user
):
    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(actor, [message(body="Unique café")])
    index = await db_session.scalar(select(SmsSearchTerm))
    index.term_hashes = []
    index.index_version = 99
    await db_session.commit()
    found = await SmsReadService(db_session).list(
        test_user.id, SmsQuery(query="unique"), assistant=False
    )
    assert found.total == 1
