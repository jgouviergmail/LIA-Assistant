"""SMS notifications point at the protected locale route and contain no SMS text."""

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.i18n import language_scope
from src.infrastructure.scheduler.ingestion_delivery import DeliveryEnvelope
from src.infrastructure.scheduler.ingestion_transport import IngestionTransport

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("language,url_language", [("fr", "fr"), ("en", "en"), ("zh-CN", "zh")])
async def test_sms_sse_destination_is_localized_protected_and_content_free(
    monkeypatch, language, url_language
):
    owner, message, occurrence = uuid4(), uuid4(), uuid4()
    redis = AsyncMock()
    monkeypatch.setattr(
        "src.infrastructure.scheduler.ingestion_transport.get_redis_cache",
        AsyncMock(return_value=redis),
    )
    result = await IngestionTransport().send(
        DeliveryEnvelope(
            user_id=owner,
            message_id=message,
            occurrence=occurrence,
            destination_key="sse",
            device_id=None,
            title="Generic",
            body="Generic",
            language=language,
        )
    )
    data = json.loads(redis.publish.await_args.args[1])
    assert data["url"] == f"/{url_language}/dashboard/sms?message={message}"
    assert data["user_id"] == str(owner) and data["occurrence_id"] == str(occurrence)
    assert set(data) == {"type", "url", "user_id", "occurrence_id", "message_id"}
    assert result.disposition.value == "accepted"


async def test_an_absent_transport_language_uses_the_declared_language(monkeypatch):
    redis = AsyncMock()
    monkeypatch.setattr(
        "src.infrastructure.scheduler.ingestion_transport.get_redis_cache",
        AsyncMock(return_value=redis),
    )
    envelope = DeliveryEnvelope(
        user_id=uuid4(),
        message_id=uuid4(),
        occurrence=uuid4(),
        destination_key="sse",
        device_id=None,
        title="Generic",
        body="Generic",
    )
    with language_scope("de"):
        await IngestionTransport().send(envelope)
    assert json.loads(redis.publish.await_args.args[1])["url"].startswith("/de/dashboard/sms?")
