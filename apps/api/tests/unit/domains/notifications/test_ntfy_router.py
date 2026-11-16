"""The ntfy settings routes at the door (ADR-391).

A topic is a password and a token a credential: the routes never reflect what was typed in a
refusal, and never let an answer be cached. A test publication is the person's own request on
one subscription: it reaches that subscription — paused or not — after the request's read
ended (ADR-304), within a per-account limit.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.exceptions import BaseAPIException
from src.core.i18n import _
from src.core.security.utils import encrypt_data
from src.core.session_dependencies import get_current_active_session
from src.domains.notifications import ntfy_router
from src.domains.notifications.models import NtfySubscription
from src.domains.notifications.ntfy import NtfyContent, NtfyServerKind
from src.domains.notifications.ntfy_delivery import NtfyBatch
from src.domains.notifications.ntfy_schemas import NtfyOverview
from src.domains.notifications.ntfy_service import NtfySubscriptionService
from src.infrastructure.external.ntfy_client import NtfyOutcome

pytestmark = pytest.mark.unit

TOKEN = "tk_" + "a1B2c3" * 4 + "d4E5f"


async def _handler(_: Any, exc: BaseAPIException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers
    )


class _Session:
    """The request's session: it says whether its read ended."""

    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


def _row(owner: Any, *, active: bool = True, topic: str = "lia_TestTopic") -> NtfySubscription:
    return NtfySubscription(
        id=uuid4(),
        user_id=owner.id,
        server_kind=NtfyServerKind.INSTANCE.value,
        server_url=None,
        topic_encrypted=encrypt_data(topic),
        token_encrypted=None,
        content=NtfyContent.FULL.value,
        is_active=active,
    )


@pytest.fixture
async def http(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[AsyncClient, Any]]:
    monkeypatch.setattr(
        "src.domains.feature_switches.guard.is_capability_enabled", AsyncMock(return_value=True)
    )
    limiter = MagicMock(acquire=AsyncMock(return_value=True))
    monkeypatch.setattr(
        "src.infrastructure.rate_limiting.user_limiter.get_rate_limiter",
        AsyncMock(return_value=limiter),
    )
    session = _Session()
    owner = SimpleNamespace(id=uuid4(), language="fr")
    published: list[Any] = []

    async def deliver(pairs: Any, **_: Any) -> NtfyBatch:
        published.append((list(pairs), session.committed))
        return NtfyBatch(outcomes=(NtfyOutcome.SENT,) * len(pairs))

    monkeypatch.setattr(ntfy_router, "deliver", deliver)
    app = FastAPI()
    app.include_router(ntfy_router.router)
    app.add_exception_handler(BaseAPIException, _handler)  # type: ignore[arg-type]
    app.dependency_overrides[get_current_active_session] = lambda: owner
    app.dependency_overrides[get_db] = lambda: session
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        yield client, SimpleNamespace(
            owner=owner, session=session, limiter=limiter, published=published
        )


class TestATestPublication:
    @pytest.mark.parametrize("active", [True, False])
    async def test_it_reaches_that_subscription_once_the_read_ended(
        self, http: tuple[AsyncClient, Any], monkeypatch: pytest.MonkeyPatch, active: bool
    ) -> None:
        """A paused subscription is tested all the same: the person asked for this one."""
        client, world = http
        row = _row(world.owner, active=active)
        monkeypatch.setattr(NtfySubscriptionService, "owned", AsyncMock(return_value=row))

        response = await client.post(f"/notifications/ntfy/{row.id}/test")

        assert response.status_code == 200
        assert response.json() == {"outcome": "sent"}
        ((pairs, read_ended),) = world.published
        ((target, notice),) = pairs
        assert read_ended, "the request's transaction ended before the server was asked"
        assert (target.id, target.topic) == (row.id, "lia_TestTopic")
        assert notice.title == _("LIA test notification", "fr")
        assert notice.body == _("ntfy works: LIA can reach you here.", "fr")
        assert notice.language == "fr"

    async def test_a_subscription_whose_secret_no_longer_reads_is_refused_with_a_code(
        self, http: tuple[AsyncClient, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, world = http
        row = _row(world.owner)
        row.topic_encrypted = "no-longer-a-fernet-token"
        monkeypatch.setattr(NtfySubscriptionService, "owned", AsyncMock(return_value=row))

        response = await client.post(f"/notifications/ntfy/{row.id}/test")

        assert response.status_code == 409
        assert response.json()["detail"] == {"code": "ntfy_subscription_unreadable"}
        assert world.published == []

    async def test_it_is_limited_per_account(
        self, http: tuple[AsyncClient, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, world = http
        world.limiter.acquire.return_value = False
        row = _row(world.owner)
        monkeypatch.setattr(NtfySubscriptionService, "owned", AsyncMock(return_value=row))

        response = await client.post(f"/notifications/ntfy/{row.id}/test")

        assert response.status_code == 429
        assert world.published == []
        assert world.limiter.acquire.await_args.kwargs["key"] == (
            f"auth:ntfy_test:user:{world.owner.id}"
        )


class TestSecretsAtTheDoor:
    async def test_a_refused_body_never_reflects_what_was_typed(
        self, http: tuple[AsyncClient, Any]
    ) -> None:
        client, _world = http
        typed = TOKEN + "x" * 100

        response = await client.post(
            "/notifications/ntfy",
            json={"server": "custom", "server_url": "https://ntfy.sh", "token": typed},
        )

        assert response.status_code == 422
        assert typed not in response.text
        assert response.headers["cache-control"] == "no-store"

    async def test_an_answer_carrying_topics_is_never_cached(
        self, http: tuple[AsyncClient, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, _world = http
        monkeypatch.setattr(
            NtfySubscriptionService,
            "overview",
            AsyncMock(
                return_value=NtfyOverview(
                    instance_url=None,
                    custom_servers_enabled=True,
                    max_subscriptions=3,
                    subscriptions=[],
                )
            ),
        )

        response = await client.get("/notifications/ntfy")

        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"


class TestTheQrCode:
    async def test_it_draws_the_link_that_subscribes_the_app(
        self, http: tuple[AsyncClient, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, world = http
        row = _row(world.owner)
        monkeypatch.setattr(NtfySubscriptionService, "owned", AsyncMock(return_value=row))
        monkeypatch.setattr(settings, "ntfy_public_url", "https://ntfy.example.org")
        drawn: list[str] = []

        def draw(text: str) -> str:
            drawn.append(text)
            return "data:image/png;base64,UVI="

        monkeypatch.setattr(ntfy_router, "render_qr_data_uri", draw)

        response = await client.get(f"/notifications/ntfy/{row.id}/qr")

        assert response.status_code == 200
        assert response.json() == {"qr_data_uri": "data:image/png;base64,UVI="}
        assert drawn == ["ntfy://ntfy.example.org/lia_TestTopic?display=LIA"]
        assert response.headers["cache-control"] == "no-store"

    async def test_a_real_code_is_a_png(
        self, http: tuple[AsyncClient, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, world = http
        row = _row(world.owner)
        monkeypatch.setattr(NtfySubscriptionService, "owned", AsyncMock(return_value=row))
        monkeypatch.setattr(settings, "ntfy_public_url", "https://ntfy.example.org")

        response = await client.get(f"/notifications/ntfy/{row.id}/qr")

        encoded = response.json()["qr_data_uri"].removeprefix("data:image/png;base64,")
        assert base64.b64decode(encoded).startswith(b"\x89PNG\r\n\x1a\n")

    async def test_a_subscription_that_no_longer_reads_has_none(
        self, http: tuple[AsyncClient, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, world = http
        row = _row(world.owner)
        row.topic_encrypted = "no-longer-a-fernet-token"
        monkeypatch.setattr(NtfySubscriptionService, "owned", AsyncMock(return_value=row))

        response = await client.get(f"/notifications/ntfy/{row.id}/qr")

        assert response.status_code == 409
        assert response.json()["detail"] == {"code": "ntfy_subscription_unreadable"}
