"""Real SQL read boundaries, stable cursors and honest lexical search."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.models import SmsMessage
from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration


async def test_snapshot_cursor_ties_late_receipts_and_ownership(
    db_session, test_user, test_superuser
):
    from src.domains.sms.read_schemas import SmsQuery
    from src.domains.sms.reads import SmsReadService

    actor = await authority(db_session, test_user)
    stamp = datetime.now(UTC) - timedelta(days=1)
    await SmsIngestionService(db_session).ingest(
        actor, [message(date=stamp.isoformat(), body=f"Bonjour {i}") for i in range(3)]
    )
    reader = SmsReadService(db_session)
    first = await reader.list(test_user.id, SmsQuery(limit=2), assistant=False)
    assert first.total == 3 and len(first.items) == 2 and first.next_cursor
    await SmsIngestionService(db_session).ingest(
        actor, [message(date=(stamp - timedelta(days=10)).isoformat())]
    )
    second = await reader.list(
        test_user.id, SmsQuery(limit=2, cursor=first.next_cursor), assistant=False
    )
    assert second.total == 3 and len(second.items) == 1
    assert not ({i.id for i in first.items} & {i.id for i in second.items})
    with pytest.raises(ResourceConflictError):
        await reader.list(
            test_user.id,
            SmsQuery(limit=2, cursor=first.next_cursor, query="Bonjour"),
            assistant=False,
        )
    with pytest.raises(ResourceConflictError):
        await reader.list(
            test_superuser.id, SmsQuery(limit=2, cursor=first.next_cursor), assistant=False
        )
    with pytest.raises(ResourceNotFoundError):
        await reader.get(test_superuser.id, first.items[0].id, assistant=False)


async def test_assistant_consent_is_fresh_and_ordinary_archive_stays_readable(
    db_session, test_user
):
    from src.domains.sms.read_schemas import SmsQuery
    from src.domains.sms.reads import SmsReadService

    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(actor, [message()])
    reader = SmsReadService(db_session)
    with pytest.raises(AuthorizationError):
        await reader.list(test_user.id, SmsQuery(), assistant=True)
    test_user.sms_preferences = {"assistant_enabled": True}
    await db_session.commit()
    assert (await reader.list(test_user.id, SmsQuery(), assistant=True)).total == 1
    test_user.sms_preferences = {"assistant_enabled": False}
    await db_session.commit()
    with pytest.raises(AuthorizationError):
        await reader.get(
            test_user.id,
            (await reader.list(test_user.id, SmsQuery(), assistant=False)).items[0].id,
            assistant=True,
        )


async def test_search_and_terms_accents_cjk_incomplete_and_exact_count(db_session, test_user):
    from src.domains.sms.read_schemas import SmsQuery
    from src.domains.sms.reads import SmsReadService

    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(
        actor,
        [
            message(body="Café demain 東京"),
            message(body="Cafe hier 東京"),
            message(body="Demain seulement"),
        ],
    )
    reader = SmsReadService(db_session)
    found = await reader.list(test_user.id, SmsQuery(query="cafe demain", limit=1), assistant=False)
    assert found.total == 1 and found.items[0].body == "Café demain 東京"
    assert (await reader.list(test_user.id, SmsQuery(query="東京"), assistant=False)).total == 2
    # An incomplete projection must participate, then be checked against decrypted text.
    row = await db_session.scalar(select(SmsMessage).where(SmsMessage.id == found.items[0].id))
    row.search_complete = False
    await db_session.commit()
    assert (await reader.list(test_user.id, SmsQuery(query="absent"), assistant=False)).total == 0
    assert (await reader.list(test_user.id, SmsQuery(query="demain"), assistant=False)).total == 2


async def test_sender_groups_have_their_own_pagination(db_session, test_user):
    from src.domains.sms.reads import SmsReadService

    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(
        actor,
        [
            *[message(sender="Alice") for _ in range(25)],
            message(sender="Bob", date="2020-01-01T00:00:00Z"),
        ],
    )
    reader = SmsReadService(db_session)
    first = await reader.senders(test_user.id, limit=1, assistant=False)
    second = await reader.senders(test_user.id, limit=1, cursor=first.next_cursor, assistant=False)
    assert first.total == second.total == 2
    assert {first.items[0].sender, second.items[0].sender} == {"Alice", "Bob"}
    assert sorted([first.items[0].total, second.items[0].total]) == [1, 25]


async def test_broad_search_refuses_instead_of_publishing_a_partial_total(
    db_session, test_user, monkeypatch
):
    from src.core.config import settings
    from src.domains.sms.read_schemas import SmsQuery
    from src.domains.sms.reads import SmsReadService

    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(
        actor, [message(body="Commun demain") for _ in range(3)]
    )
    monkeypatch.setattr(settings, "sms_search_max_candidates", 2)
    with pytest.raises(ResourceConflictError) as failure:
        await SmsReadService(db_session).list(
            test_user.id, SmsQuery(query="commun"), assistant=False
        )
    assert failure.value.detail["error_code"] == "QUERY_TOO_BROAD"


async def test_decrypted_search_budget_never_turns_a_partial_scan_into_zero_results(
    db_session, test_user, monkeypatch
):
    from src.core.config import settings
    from src.domains.sms.read_schemas import SmsQuery
    from src.domains.sms.reads import SmsReadService

    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(actor, [message(body="Commun " + "A" * 200)])
    from src.domains.sms import reads

    monkeypatch.setattr(
        reads, "settings", settings.model_copy(update={"sms_search_max_verified_chars": 100})
    )
    with pytest.raises(ResourceConflictError) as failure:
        await SmsReadService(db_session).list(
            test_user.id, SmsQuery(query="commun"), assistant=False
        )
    assert failure.value.detail["error_code"] == "QUERY_TOO_BROAD"


async def test_missing_derived_index_is_verified_not_reported_as_absence(db_session, test_user):
    from sqlalchemy import delete

    from src.domains.sms.models import SmsSearchTerm
    from src.domains.sms.read_schemas import SmsQuery
    from src.domains.sms.reads import SmsReadService

    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(actor, [message(body="Unique café")])
    await db_session.execute(delete(SmsSearchTerm).where(SmsSearchTerm.user_id == test_user.id))
    await db_session.commit()
    assert (
        await SmsReadService(db_session).list(
            test_user.id, SmsQuery(query="unique"), assistant=False
        )
    ).total == 1


async def test_unreadable_content_has_an_explicit_source_error_not_false_absence(
    db_session, test_user
):
    from src.core.exceptions import ExternalServiceError
    from src.domains.sms.read_schemas import SmsQuery
    from src.domains.sms.reads import SmsReadService

    actor = await authority(db_session, test_user)
    result = await SmsIngestionService(db_session).ingest(actor, [message(body="Café unique")])
    row = await db_session.get(SmsMessage, result.items[0].message_id)
    row.body_encrypted = "invalid-private-cipher"
    await db_session.commit()
    reader = SmsReadService(db_session)
    with pytest.raises(ExternalServiceError):
        await reader.get(test_user.id, row.id, assistant=False)
    with pytest.raises(ExternalServiceError):
        await reader.list(test_user.id, SmsQuery(query="unique"), assistant=False)


async def test_data_read_requires_an_explicit_audience_instead_of_silently_bypassing_assistant_consent(
    db_session, test_user
):
    from src.domains.sms.read_schemas import SmsQuery
    from src.domains.sms.reads import SmsReadService

    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(actor, [message()])
    with pytest.raises(TypeError):
        await SmsReadService(db_session).list(test_user.id, SmsQuery())
