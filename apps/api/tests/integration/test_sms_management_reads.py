"""Personal settings metadata never exposes credentials, indexes or message bodies."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.core.security.utils import encrypt_data
from src.domains.ingestion.models import IngestionDelivery, IngestionToken
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.models import SmsSenderBlock
from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration


async def test_settings_are_personal_and_device_counts_do_not_include_sse(db_session, test_user):
    from src.domains.sms.management_reads import SmsManagementReader

    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(actor, [message(body="Confidential meal plan")])
    root = await db_session.scalar(select(IngestionDelivery))
    root.state = "expanded"
    db_session.add_all(
        [
            IngestionDelivery(
                user_id=test_user.id,
                receipt_id=root.receipt_id,
                destination_key="sse",
                state="sent",
            ),
            IngestionDelivery(
                user_id=test_user.id,
                receipt_id=root.receipt_id,
                destination_key=f"device:{uuid4()}",
                device_id=uuid4(),
                state="unknown",
            ),
        ]
    )
    await db_session.flush()
    data = await SmsManagementReader(db_session).settings(test_user.id)
    assert not data.preferences.assistant_enabled
    assert data.usage.message_count == 1 and data.usage.receipt_count == 1
    assert data.usage.logical_bytes > 0
    assert data.device_deliveries.unknown == 1 and data.device_deliveries.sent == 0
    assert "Confidential meal plan" not in data.model_dump_json()
    assert "ingestion_key" not in data.model_dump_json()


async def test_token_metadata_pages_are_bounded_and_never_include_hash_or_secret(
    db_session, test_user
):
    from src.domains.sms.management_read_schemas import SmsManagementPageQuery
    from src.domains.sms.management_reads import SmsManagementReader

    actor = await authority(db_session, test_user)
    for i in range(3):
        db_session.add(
            IngestionToken(
                user_id=test_user.id,
                source_id=actor.source_id,
                token_hash=f"{i:064x}",
                token_prefix=f"pi_public_{i}",
                scopes=["sms:write"],
            )
        )
    await db_session.flush()
    service = SmsManagementReader(db_session)
    page = await service.tokens(test_user.id, SmsManagementPageQuery(limit=2))
    assert len(page.tokens) == 2 and page.total == 4 and page.next_cursor is not None
    second = await service.tokens(
        test_user.id, SmsManagementPageQuery(limit=2, after_id=page.next_cursor, as_of=page.as_of)
    )
    assert len(second.tokens) == 2 and not {x.id for x in page.tokens} & {
        x.id for x in second.tokens
    }
    assert "token_hash" not in page.model_dump_json() and "pi_test" not in page.model_dump_json()
    assert all(x.resource.value == "sms" for x in page.tokens)


async def test_block_list_does_not_export_sender_hmac(db_session, test_user):
    from src.domains.sms.management_read_schemas import SmsManagementPageQuery
    from src.domains.sms.management_reads import SmsManagementReader

    db_session.add(
        SmsSenderBlock(
            user_id=test_user.id, sender_hash="a" * 64, sender_encrypted=encrypt_data("BANK")
        )
    )
    await db_session.flush()
    page = await SmsManagementReader(db_session).blocks(test_user.id, SmsManagementPageQuery())
    assert page.blocks[0].sender == "BANK" and page.total == 1
    assert "sender_hash" not in page.model_dump_json()


async def test_foreign_or_missing_metadata_cursor_refuses_instead_of_resetting(
    db_session, test_user
):
    from src.core.exceptions import ResourceConflictError
    from src.domains.sms.management_read_schemas import SmsManagementPageQuery
    from src.domains.sms.management_reads import SmsManagementReader

    with pytest.raises(ResourceConflictError):
        await SmsManagementReader(db_session).tokens(
            test_user.id, SmsManagementPageQuery(after_id=uuid4(), as_of=datetime.now(UTC))
        )


async def test_personal_metadata_http_routes_are_uncached_and_session_only(
    async_client, db_session, test_user
):
    from src.core.session_dependencies import get_current_active_session
    from src.main import app

    await authority(db_session, test_user)
    app.dependency_overrides[get_current_active_session] = lambda: test_user
    try:
        for path in ("settings", "tokens", "blocked-senders"):
            response = await async_client.get("/api/v1/sms/" + path)
            assert response.status_code == 200, (path, response.text)
            assert response.headers["cache-control"] == "no-store"
            assert "token_hash" not in response.text and "ingestion_key" not in response.text
    finally:
        app.dependency_overrides.pop(get_current_active_session, None)
    response = await async_client.get(
        "/api/v1/sms/settings", headers={"Authorization": "Bearer pi_test"}
    )
    assert response.status_code == 401


async def test_rehydrated_metadata_query_cannot_bypass_limits(db_session, test_user):
    from pydantic import ValidationError

    from src.domains.sms.management_read_schemas import SmsManagementPageQuery
    from src.domains.sms.management_reads import SmsManagementReader

    query = SmsManagementPageQuery().model_copy(update={"limit": 100000})
    with pytest.raises(ValidationError):
        await SmsManagementReader(db_session).tokens(test_user.id, query)


async def test_metadata_http_pagination_accepts_typed_query_strings(
    async_client, db_session, test_user
):
    from src.core.session_dependencies import get_current_active_session
    from src.main import app

    await authority(db_session, test_user)
    app.dependency_overrides[get_current_active_session] = lambda: test_user
    try:
        response = await async_client.get("/api/v1/sms/tokens?limit=2")
        assert response.status_code == 200, response.text
    finally:
        app.dependency_overrides.pop(get_current_active_session, None)
