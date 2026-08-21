"""Google push webhook endpoints (lot H, 2026-08).

Contract: the webhook ALWAYS answers 2xx — an error status would make Google
retry (channels) or Pub/Sub redeliver, and a differentiated status would
reveal what the channel registry knows to whoever found the public URL.
"""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.dependencies import get_db
from src.domains.push_channels.router import router as push_router
from src.domains.push_channels.service import NotificationOutcome

pytestmark = pytest.mark.unit


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(push_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: MagicMock()
    return TestClient(app)


_CHANNEL_HEADERS = {
    "X-Goog-Channel-ID": "chan-1",
    "X-Goog-Channel-Token": "secret",
    "X-Goog-Resource-ID": "res-1",
    "X-Goog-Resource-State": "exists",
    "X-Goog-Message-Number": "3",
}


class TestChannelWebhook:
    def test_valid_notification_returns_200(self, client: TestClient) -> None:
        service = MagicMock()
        service.handle_channel_notification = AsyncMock(return_value=NotificationOutcome.PROCESSED)
        with patch("src.domains.push_channels.router.PushChannelService", return_value=service):
            response = client.post("/api/v1/webhooks/google", headers=_CHANNEL_HEADERS)
        assert response.status_code == 200
        service.handle_channel_notification.assert_awaited_once()

    def test_unknown_channel_still_returns_200(self, client: TestClient) -> None:
        service = MagicMock()
        service.handle_channel_notification = AsyncMock(
            return_value=NotificationOutcome.IGNORED_UNKNOWN
        )
        with patch("src.domains.push_channels.router.PushChannelService", return_value=service):
            response = client.post("/api/v1/webhooks/google", headers=_CHANNEL_HEADERS)
        assert response.status_code == 200

    def test_non_google_request_returns_200_without_processing(self, client: TestClient) -> None:
        service = MagicMock()
        service.handle_channel_notification = AsyncMock()
        with patch("src.domains.push_channels.router.PushChannelService", return_value=service):
            response = client.post("/api/v1/webhooks/google")
        assert response.status_code == 200
        service.handle_channel_notification.assert_not_awaited()


class TestPubSubWebhook:
    @staticmethod
    def _envelope() -> dict:
        data = base64.b64encode(
            json.dumps({"emailAddress": "user@gmail.com", "historyId": 12}).encode()
        ).decode()
        return {"message": {"data": data, "messageId": "m1"}, "subscription": "s"}

    def test_valid_event_passes_the_query_token(self, client: TestClient) -> None:
        service = MagicMock()
        service.handle_gmail_push = AsyncMock(return_value=NotificationOutcome.PROCESSED)
        with patch("src.domains.push_channels.router.PushChannelService", return_value=service):
            response = client.post(
                "/api/v1/webhooks/google/pubsub?token=platform-secret",
                json=self._envelope(),
            )
        assert response.status_code == 200
        _, kwargs = service.handle_gmail_push.await_args
        assert kwargs.get("provided_token") == "platform-secret"

    def test_malformed_body_still_returns_200(self, client: TestClient) -> None:
        service = MagicMock()
        service.handle_gmail_push = AsyncMock()
        with patch("src.domains.push_channels.router.PushChannelService", return_value=service):
            response = client.post(
                "/api/v1/webhooks/google/pubsub",
                content=b"not-json",
                headers={"Content-Type": "application/json"},
            )
        assert response.status_code == 200
        service.handle_gmail_push.assert_not_awaited()
