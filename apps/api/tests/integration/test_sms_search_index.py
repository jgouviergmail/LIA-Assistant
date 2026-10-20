"""A compact native array index keeps lexical AND and owner boundaries."""

import pytest
from sqlalchemy import func, select

from src.core.security.utils import decrypt_data
from src.domains.ingestion.key_material import key_for_owner
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.models import SmsMessage, SmsSearchTerm
from src.domains.sms.search import blind_terms
from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration


async def test_one_opaque_index_projection_per_message(db_session, test_user):
    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(actor, [message(body="Café demain 東京 Bonjour")])
    assert await db_session.scalar(select(func.count()).select_from(SmsSearchTerm)) == 1
    index = await db_session.scalar(select(SmsSearchTerm))
    assert index.term_hashes and all(
        isinstance(term, bytes) and len(term) == 32 for term in index.term_hashes
    )
    assert "café" not in repr(index.__dict__)


async def test_native_array_query_requires_all_terms_and_the_owner(db_session, test_user):
    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(
        actor, [message(body="Café demain 東京"), message(body="Café hier 北京")]
    )
    key = key_for_owner(test_user)
    required = [bytes.fromhex(term) for term in blind_terms(test_user.id, "Café demain", key=key)]
    results = (
        await db_session.scalars(
            select(SmsMessage)
            .join(SmsSearchTerm, SmsSearchTerm.message_id == SmsMessage.id)
            .where(
                SmsMessage.user_id == test_user.id,
                SmsSearchTerm.user_id == test_user.id,
                SmsSearchTerm.term_hashes.contains(required),
            )
        )
    ).all()
    assert len(results) == 1 and decrypt_data(results[0].body_encrypted) == "Café demain 東京"
