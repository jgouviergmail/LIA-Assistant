"""The actual BFF session gate protects both Jev administration routes."""

import pytest
from httpx import AsyncClient

from src.domains.users.models import User

pytestmark = pytest.mark.integration
ENDPOINT = "/api/v1/admin/llm-config/jev"


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
