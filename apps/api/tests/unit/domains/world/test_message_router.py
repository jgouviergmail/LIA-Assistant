"""HTTP privacy envelope, native exception taxonomy and immediate dispatch."""

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import SQLAlchemyError

from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.users.models import User
from src.domains.world import message_router
from src.domains.world.message_attempts import AttemptBusy, AttemptConflict
from src.domains.world.messaging import AcceptedSend, MessageAccepted
from src.domains.world.store import WorldUnavailable

pytestmark = pytest.mark.unit


@pytest.fixture
async def http_messages() -> AsyncIterator[tuple[httpx.AsyncClient, AsyncMock]]:
    app = FastAPI()
    app.include_router(message_router.router)
    service = AsyncMock()
    user = User(id=uuid4(), email="inert@example.com", is_active=True)

    async def allow() -> None:
        return None

    async def identity() -> User:
        return user

    async def messaging() -> AsyncMock:
        return service

    for dependency in message_router.router.dependencies:
        app.dependency_overrides[dependency.dependency] = allow
    app.dependency_overrides[get_current_active_session_for_stream] = identity
    app.dependency_overrides[message_router.get_messaging] = messaging
    app.dependency_overrides[message_router.write_limit] = allow
    app.dependency_overrides[message_router.read_limit] = allow
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://inert.test"
    ) as client:
        yield client, service


@pytest.mark.parametrize("path", ["send", "read", "status", "translate"])
async def test_invalid_private_input_is_never_reflected_and_cannot_be_cached(
    http_messages: tuple[httpx.AsyncClient, AsyncMock], path: str
) -> None:
    client, service = http_messages
    response = await client.post(
        "/messages/" + path,
        json={"PRIVATE_FIELD": "PRIVATE_BODY", "text": "PRIVATE_TEXT"},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": {"error_code": "INVALID_INPUT"}}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    service.send.assert_not_called()
    service.read.assert_not_called()
    service.retranslate.assert_not_called()


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (ValueError("PRIVATE_POLICY"), 403),
        (WorldUnavailable("PRIVATE_CACHE"), 503),
        (RedisConnectionError("PRIVATE_REDIS"), 503),
        (SQLAlchemyError("PRIVATE_SQL"), 500),
        (AttemptBusy(), 429),
        (AttemptConflict(), 409),
    ],
)
async def test_closed_service_errors_use_native_status_without_private_details(
    http_messages: tuple[httpx.AsyncClient, AsyncMock], error: Exception, status: int
) -> None:
    client, service = http_messages
    client.cookies.set("lia_session", "inert-cookie")
    service.read.side_effect = error
    response = await client.post(
        "/messages/read", json={"epoch": str(uuid4()), "controller": "c" * 43}
    )
    assert response.status_code == status
    assert "PRIVATE_" not in response.text
    assert response.headers["cache-control"] == "no-store"


async def test_missing_cookie_cannot_dispatch_even_with_a_cached_identity(
    http_messages: tuple[httpx.AsyncClient, AsyncMock],
) -> None:
    client, service = http_messages
    response = await client.post(
        "/messages/read", json={"epoch": str(uuid4()), "controller": "c" * 43}
    )
    assert response.status_code == 401
    service.read.assert_not_called()


async def test_accepted_translation_starts_immediately_and_is_never_in_the_response(
    http_messages: tuple[httpx.AsyncClient, AsyncMock],
) -> None:
    client, service = http_messages
    started = asyncio.Event()

    async def job() -> None:
        started.set()

    identifier = str(uuid4())
    service.send.return_value = AcceptedSend(
        MessageAccepted(id=identifier, status="pending"), job()
    )
    client.cookies.set("lia_session", "inert-cookie")
    response = await client.post(
        "/messages/send",
        json={
            "epoch": str(uuid4()),
            "controller": "c" * 43,
            "id": identifier,
            "recipient": str(uuid4()),
            "text": "PRIVATE_LITERAL",
            "created_at": 1000.0,
            "translation_consent": True,
        },
    )
    assert response.status_code == 202
    assert response.json() == {"id": identifier, "status": "pending"}
    await asyncio.wait_for(started.wait(), 1)
    service.send.assert_awaited_once()
