"""External Shortcuts endpoint: wire status, no echoed content, no session authority."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import ConnectionError

from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration


async def test_shortcut_object_and_retry_status(async_client, db_session, test_user):
    await authority(db_session, test_user)
    await db_session.commit()
    payload = message()
    first = await async_client.post(
        "/api/v1/ingest/message", json=payload, headers={"Authorization": "Bearer pi_test"}
    )
    assert first.status_code == 201
    assert first.json()["inserted"] == 1
    retry = await async_client.post(
        "/api/v1/ingest/message", json=payload, headers={"Authorization": "pi_test"}
    )
    assert retry.status_code == 200 and retry.json()["duplicate"] == 1
    conflict = await async_client.post(
        "/api/v1/ingest/message",
        json={**payload, "body": "different"},
        headers={"Authorization": "pi_test"},
    )
    assert conflict.status_code == 409


@pytest.mark.parametrize("token", ["", "hm_test", "pi_unknown"])
async def test_session_or_health_token_does_not_grant_sms_ingestion(async_client, token):
    response = await async_client.post(
        "/api/v1/ingest/message", json=message(), headers={"Authorization": token}
    )
    assert response.status_code == 401


async def test_ndjson_accounts_for_invalid_elements(async_client, db_session, test_user):
    await authority(db_session, test_user)
    await db_session.commit()
    body = json.dumps(message()) + "\nnull\n" + json.dumps(message(body="OTP: 123456"))
    response = await async_client.post(
        "/api/v1/ingest/message", content=body, headers={"Authorization": "pi_test"}
    )
    assert response.status_code == 200
    data = response.json()
    assert (data["received"], data["inserted"], data["rejected"], data["ignored"]) == (3, 1, 1, 1)
    assert "123456" not in response.text


async def test_invalid_object_is_422_without_pydantic_input(async_client, db_session, test_user):
    await authority(db_session, test_user)
    await db_session.commit()
    response = await async_client.post(
        "/api/v1/ingest/message",
        json=message(date="private-invalid-date"),
        headers={"Authorization": "pi_test"},
    )
    assert response.status_code == 422
    assert "private-invalid-date" not in response.text and "input" not in response.text


async def test_required_redis_failure_is_retryable_503(async_client, db_session, test_user):
    await authority(db_session, test_user)
    await db_session.commit()
    with patch(
        "src.domains.ingestion.limits.get_rate_limiter",
        AsyncMock(side_effect=ConnectionError("unavailable")),
    ):
        response = await async_client.post(
            "/api/v1/ingest/message", json=message(), headers={"Authorization": "pi_test"}
        )
    assert response.status_code == 503


async def test_business_byte_ceiling_is_enforced(async_client, db_session, test_user):
    await authority(db_session, test_user)
    await db_session.commit()
    response = await async_client.post(
        "/api/v1/ingest/message", content=b"x" * 262145, headers={"Authorization": "pi_test"}
    )
    assert response.status_code == 413


@pytest.mark.parametrize(
    "committed", [False, True], ids=["rollback-before-commit", "ack-lost-after-commit"]
)
async def test_uncertain_commit_is_resolved_by_same_event_retry(
    async_client, db_session, test_user, committed
):
    from sqlalchemy import func, select
    from sqlalchemy.exc import SQLAlchemyError

    from src.domains.sms.models import SmsMessage

    await authority(db_session, test_user)
    await db_session.commit()
    payload = message()
    original = db_session.commit

    async def uncertain():
        if committed:
            await original()
        raise SQLAlchemyError("simulated transport loss")

    with patch.object(db_session, "commit", uncertain):
        response = await async_client.post(
            "/api/v1/ingest/message", json=payload, headers={"Authorization": "pi_test"}
        )
    assert response.status_code == 503
    retried = await async_client.post(
        "/api/v1/ingest/message", json=payload, headers={"Authorization": "pi_test"}
    )
    assert retried.status_code == (200 if committed else 201)
    assert await db_session.scalar(select(func.count()).select_from(SmsMessage)) == 1


async def test_real_health_and_sms_credentials_cannot_cross_resources(
    async_client, db_session, test_user
):
    from uuid import uuid4

    from src.domains.health_metrics.service import HealthMetricsService
    from src.domains.ingestion.token_commands import create_managed_token
    from src.domains.users.preference_cas import PreferenceWriteReceipt
    from tests.integration.test_health_metrics import _steps_payload

    async def check():
        return None

    health = await HealthMetricsService(db_session).create_token(test_user.id, label="Health")
    await db_session.commit()
    sms = await create_managed_token(
        db_session, test_user.id, uuid4(), "SMS", None, PreferenceWriteReceipt(), check
    )
    wrong_sms = await async_client.post(
        "/api/v1/ingest/message", json=message(), headers={"Authorization": health.token}
    )
    wrong_health = await async_client.post(
        "/api/v1/ingest/health/steps", json=_steps_payload(12), headers={"Authorization": sms.token}
    )
    assert wrong_sms.status_code == wrong_health.status_code == 401
    health_ok = await async_client.post(
        "/api/v1/ingest/health/steps",
        json=_steps_payload(12),
        headers={"Authorization": health.token},
    )
    assert health_ok.status_code == 200


@pytest.mark.parametrize("failure", ["sql", "socket", "timeout"])
async def test_storage_unavailable_during_authentication_is_retryable(async_client, failure):
    from sqlalchemy.exc import SQLAlchemyError

    errors = {
        "sql": SQLAlchemyError("storage down"),
        "socket": OSError("storage down"),
        "timeout": TimeoutError("storage down"),
    }
    with patch(
        "src.domains.sms.ingest_router.SmsIngestionService.authenticate",
        AsyncMock(side_effect=errors[failure]),
    ):
        response = await async_client.post(
            "/api/v1/ingest/message", json=message(), headers={"Authorization": "pi_test"}
        )
    assert response.status_code == 503 and response.headers["retry-after"] == "60"
    assert "storage down" not in response.text
