"""The actual BFF session gate protects the Jev administration routes (ADR-325, ADR-374)."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.users.models import AdminAuditLog, User

pytestmark = pytest.mark.integration
ENDPOINT = "/api/v1/admin/llm-config/jev"
THRESHOLDS = f"{ENDPOINT}/thresholds"
EMAIL = "email_classification"
MOVE = {"usage": EMAIL, "values": {"priority": 0.6}}


def _usage(settings: dict[str, Any], usage: str) -> dict[str, Any]:
    return next(item for item in settings["usages"] if item["usage"] == usage)


@pytest.mark.parametrize("method", ["GET", "PATCH"])
async def test_anonymous_cannot_read_or_change_routing(
    async_client: AsyncClient, method: str
) -> None:
    response = await async_client.request(
        method, ENDPOINT, json={"enabled": False} if method == "PATCH" else None
    )
    assert response.status_code == 401


@pytest.mark.parametrize("method", ["GET", "PATCH"])
async def test_regular_session_cannot_administer_routing(
    authenticated_client: tuple[AsyncClient, User], method: str
) -> None:
    client, _ = authenticated_client
    response = await client.request(
        method, ENDPOINT, json={"enabled": False} if method == "PATCH" else None
    )
    assert response.status_code == 403


async def test_admin_reads_default_off_and_schema_rejects_unknown_usage(
    admin_client: tuple[AsyncClient, User],
) -> None:
    client, _ = admin_client
    response = await client.get(ENDPOINT)
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["usages"][0]["effective"] is False
    for body in (
        {"usage": "invented", "enabled": True},
        {"enabled": "false"},
        {"enabled": False, "secret": "x"},
    ):
        invalid = await client.patch(ENDPOINT, json=body)
        assert invalid.status_code == 422
    off = await client.patch(ENDPOINT, json={"enabled": False})
    assert off.status_code == 200 and off.json()["enabled"] is False


async def test_anonymous_cannot_move_a_threshold(
    async_client: AsyncClient,
) -> None:
    assert (await async_client.patch(THRESHOLDS, json=MOVE)).status_code == 401


async def test_regular_session_cannot_move_a_threshold(
    authenticated_client: tuple[AsyncClient, User],
) -> None:
    client, _ = authenticated_client
    assert (await client.patch(THRESHOLDS, json=MOVE)).status_code == 403


async def test_admin_moves_a_threshold_reads_it_back_and_restores_its_default(
    admin_client: tuple[AsyncClient, User], async_session: AsyncSession
) -> None:
    client, admin = admin_client
    moved = await client.patch(THRESHOLDS, json=MOVE)
    assert moved.status_code == 200
    email = _usage(moved.json(), EMAIL)
    priority = next(gate for gate in email["gates"] if gate["key"] == "priority")
    assert (priority["value"], priority["default"]) == (0.6, 0.8)
    assert email["qualified"] is False
    assert _usage((await client.get(ENDPOINT)).json(), EMAIL) == email

    for body in (
        {"usage": EMAIL, "values": {"invented": 0.8}},
        {"usage": EMAIL, "values": {"priority": 0.2}},
        {"usage": EMAIL, "values": {"priority": "0.605"}},
        {"usage": EMAIL, "values": {}},
        {"usage": EMAIL, "values": {"priority": 0.7}, "secret": "x"},
        {"usage": "observe_memory", "values": {"empty": 0.9}},
    ):
        assert (await client.patch(THRESHOLDS, json=body)).status_code == 422, body
    # A refused update writes nothing: the moved value still stands.
    assert _usage((await client.get(ENDPOINT)).json(), EMAIL) == email

    back = await client.patch(THRESHOLDS, json={"usage": EMAIL, "values": {"priority": 0.8}})
    assert back.status_code == 200 and _usage(back.json(), EMAIL)["qualified"] is True
    # Only a value away from its default is stored, and both writes are audited.
    stored = await async_session.scalar(
        select(SystemSetting.value).where(
            SystemSetting.key == SystemSettingKey.JEV_EMAIL_CLASSIFICATION_THRESHOLDS
        )
    )
    assert stored == "{}"
    audited = await async_session.scalar(
        select(func.count())
        .select_from(AdminAuditLog)
        .where(
            AdminAuditLog.admin_user_id == admin.id,
            AdminAuditLog.action == "jev_thresholds_updated",
        )
    )
    assert audited == 2
