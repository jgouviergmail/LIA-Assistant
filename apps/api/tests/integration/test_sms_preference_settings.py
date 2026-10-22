"""An explicit settings toggle changes one field without an assistant approval draft."""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.session_dependencies import get_current_active_session
from src.domains.ingestion.models import IngestionDelivery
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.management_commands import set_sms_preference
from src.domains.sms.preferences import SmsPreferenceUpdate
from src.domains.users.models import User
from src.main import app
from tests.integration.test_application_memory_independent_transactions import (
    committed_actor as committed_actor,
)
from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration


@pytest.fixture
def sms_session(test_user):
    app.dependency_overrides[get_current_active_session] = lambda: test_user
    yield
    app.dependency_overrides.pop(get_current_active_session, None)


@pytest.mark.parametrize("field", ["ingestion_enabled", "assistant_enabled", "push_enabled"])
async def test_one_settings_toggle_preserves_the_other_fields(
    async_client, db_session, test_user, sms_session, field
):
    before = {"ingestion_enabled": True, "assistant_enabled": False, "push_enabled": False}
    test_user.sms_preferences = before
    await db_session.commit()
    response = await async_client.patch(
        "/api/v1/sms/preferences", json={"field": field, "value": not before[field]}
    )
    assert response.status_code == 200, response.text
    assert response.json() == {**before, field: not before[field]}
    assert response.headers["cache-control"] == "no-store"
    await db_session.refresh(test_user)
    assert test_user.sms_preferences == response.json()


@pytest.mark.parametrize(
    "payload",
    [
        {"field": "assistant_enabled", "value": "true"},
        {"field": "is_superuser", "value": True},
        {"field": "push_enabled", "value": False, "user_id": "other"},
    ],
)
async def test_preference_input_is_strict_and_private(async_client, sms_session, payload):
    response = await async_client.patch("/api/v1/sms/preferences", json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": {"error_code": "INVALID_INPUT"}}


async def test_an_ingestion_credential_cannot_change_preferences(async_client):
    response = await async_client.patch(
        "/api/v1/sms/preferences",
        json={"field": "assistant_enabled", "value": True},
        headers={"Authorization": "Bearer pi_test"},
    )
    assert response.status_code == 401


async def test_settings_keep_delivery_cancellation_and_consent_invalidation(
    async_client, db_session, test_user, sms_session
):
    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(actor, [message()])
    revision = test_user.extraction_revision or 0
    response = await async_client.patch(
        "/api/v1/sms/preferences", json={"field": "push_enabled", "value": False}
    )
    assert response.status_code == 200
    assert (await db_session.scalar(select(IngestionDelivery))).state == "cancelled"
    assert test_user.extraction_revision == revision
    for _ in range(2):
        response = await async_client.patch(
            "/api/v1/sms/preferences", json={"field": "assistant_enabled", "value": True}
        )
        assert response.status_code == 200
        await db_session.refresh(test_user)
        assert test_user.extraction_revision == revision + 1


async def test_inactive_owner_is_rechecked_under_the_write_fence(
    async_client, db_session, test_user, sms_session
):
    test_user.is_active = False
    await db_session.commit()
    response = await async_client.patch(
        "/api/v1/sms/preferences", json={"field": "assistant_enabled", "value": True}
    )
    assert response.status_code == 401


async def test_concurrent_toggles_from_two_sessions_preserve_both_intents(
    async_engine, committed_actor
):
    async with (
        AsyncSession(async_engine) as first,
        AsyncSession(async_engine) as second,
    ):
        await asyncio.gather(
            set_sms_preference(
                first, committed_actor, SmsPreferenceUpdate(field="assistant_enabled", value=True)
            ),
            set_sms_preference(
                second, committed_actor, SmsPreferenceUpdate(field="push_enabled", value=False)
            ),
        )
    async with AsyncSession(async_engine) as read:
        actor = await read.get(User, committed_actor)
        assert actor.sms_preferences == {
            "ingestion_enabled": True,
            "assistant_enabled": True,
            "push_enabled": False,
        }
