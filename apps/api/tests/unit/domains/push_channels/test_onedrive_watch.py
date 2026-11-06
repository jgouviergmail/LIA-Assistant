"""OneDrive's change subscription (ADR-369, lot 11).

Graph, unlike Google, calls the endpoint before it answers, carries the secret in a JSON body, and
holds one subscription per resource: renewing moves its end, and a new one is only for one Graph
has lost. The feed's token survives all of it, or the changes in between would be lost.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.constants import GRAPH_DRIVE_SUBSCRIPTION_MAX_SECONDS
from src.core.dependencies import get_db
from src.core.exceptions import ConnectorAPIError
from src.domains.push_channels.models import PushChannelProvider
from src.domains.push_channels.notifications import GraphNotification, parse_graph_body
from src.domains.push_channels.router import router as push_router
from src.domains.push_channels.service import (
    DRIVE_WATCH_TARGET,
    NotificationOutcome,
    PushChannelService,
    graph_webhook_url,
)

pytestmark = pytest.mark.unit

ONEDRIVE = PushChannelProvider.MICROSOFT_ONEDRIVE.value
USER = uuid4()
GOOGLE_HOOK = "https://api.example.test/api/v1/webhooks/google"
GRAPH_HOOK = "https://api.example.test/api/v1/webhooks/microsoft"
FAR = datetime(2030, 1, 1, tzinfo=UTC)


def _client(**overrides: Any) -> MagicMock:
    client = MagicMock()
    client.get_changes_start_page_token = AsyncMock(return_value="baseline")
    client.create_subscription = AsyncMock(
        return_value={"id": "sub-1", "expirationDateTime": "2026-11-12T08:00:00Z"}
    )
    client.renew_subscription = AsyncMock(
        return_value={"id": "sub-1", "expirationDateTime": "2026-11-19T08:00:00Z"}
    )
    for name, value in overrides.items():
        setattr(client, name, value)
    return client


def _service(existing: Any = None) -> PushChannelService:
    repo = MagicMock()
    repo.get_for_user = AsyncMock(return_value=existing)
    repo.get_by_resource = AsyncMock(return_value=existing)
    db = MagicMock(commit=AsyncMock())
    return PushChannelService(db, repository=repo)


def _channel(**overrides: Any) -> MagicMock:
    values: dict[str, Any] = {
        "id": uuid4(),
        "user_id": USER,
        "provider": ONEDRIVE,
        "channel_id": "chan-1",
        "token": "secret",
        "resource_id": "sub-1",
        "expiration": datetime.now(UTC) + timedelta(minutes=1),
        "page_token": "kept-token",
    }
    channel = MagicMock()
    for name, value in {**values, **overrides}.items():
        setattr(channel, name, value)
    return channel


def _settings(**overrides: Any) -> Any:
    return patch.multiple(
        "src.domains.push_channels.service.settings",
        push_webhook_url=overrides.get("push_webhook_url", GOOGLE_HOOK),
        push_watch_ttl_seconds=overrides.get("push_watch_ttl_seconds", 7 * 86400),
        push_renewal_margin_seconds=3600,
    )


class TestItsAddress:
    def test_it_sits_beside_the_google_endpoint(self) -> None:
        with _settings():
            assert graph_webhook_url() == GRAPH_HOOK

    def test_a_trailing_slash_does_not_move_it(self) -> None:
        with _settings(push_webhook_url="https://api.example.test/api/v1/webhooks/google/"):
            assert graph_webhook_url() == GRAPH_HOOK

    def test_no_public_address_means_none(self) -> None:
        with _settings(push_webhook_url=None):
            assert graph_webhook_url() is None


class TestAFirstWatch:
    async def test_it_is_opened_with_a_secret_of_its_own_on_today_s_baseline(self) -> None:
        service = _service()
        service.db.add = MagicMock()
        client = _client()

        with _settings():
            channel = await service.ensure_onedrive_watch(USER, client)

        address, secret, _ = client.create_subscription.await_args.args
        assert address == GRAPH_HOOK
        assert channel.token == secret
        assert len(secret) >= 32
        assert channel.resource_id == "sub-1"
        assert channel.page_token == "baseline"
        assert channel.provider == ONEDRIVE
        assert channel.watch_target == DRIVE_WATCH_TARGET
        assert channel.expiration == datetime(2026, 11, 12, 8, tzinfo=UTC)
        service.db.add.assert_called_once_with(channel)

    async def test_the_baseline_is_read_first_so_nothing_falls_between(self) -> None:
        order: list[str] = []
        client = _client(
            get_changes_start_page_token=AsyncMock(
                side_effect=lambda: order.append("baseline") or "t"
            ),
            create_subscription=AsyncMock(
                side_effect=lambda *_: order.append("subscribe") or {"id": "s"}
            ),
        )
        service = _service()
        service.db.add = MagicMock()

        with _settings():
            await service.ensure_onedrive_watch(USER, client)

        assert order == ["baseline", "subscribe"]

    async def test_no_public_address_opens_nothing(self) -> None:
        client = _client()

        with _settings(push_webhook_url=None):
            assert await _service().ensure_onedrive_watch(USER, client) is None

        client.create_subscription.assert_not_awaited()

    async def test_its_end_stays_within_what_graph_allows_a_drive(self) -> None:
        service = _service()
        service.db.add = MagicMock()
        client = _client()

        with _settings(push_watch_ttl_seconds=GRAPH_DRIVE_SUBSCRIPTION_MAX_SECONDS * 2):
            await service.ensure_onedrive_watch(USER, client)

        expires_at = client.create_subscription.await_args.args[2]
        ceiling = datetime.now(UTC) + timedelta(seconds=GRAPH_DRIVE_SUBSCRIPTION_MAX_SECONDS)
        assert expires_at <= ceiling


class TestAWatchThatRuns:
    async def test_one_far_from_its_end_is_left_alone(self) -> None:
        channel = _channel(expiration=FAR)
        client = _client()

        with _settings():
            assert await _service(channel).ensure_onedrive_watch(USER, client) is channel

        client.renew_subscription.assert_not_awaited()
        client.create_subscription.assert_not_awaited()

    async def test_one_near_it_is_renewed_in_place_its_feed_untouched(self) -> None:
        channel = _channel()
        client = _client()

        with _settings():
            await _service(channel).ensure_onedrive_watch(USER, client)

        assert client.renew_subscription.await_args.args[0] == "sub-1"
        client.create_subscription.assert_not_awaited()
        assert channel.expiration == datetime(2026, 11, 19, 8, tzinfo=UTC)
        assert channel.page_token == "kept-token"

    async def test_one_graph_lost_is_opened_again_from_where_the_feed_stood(self) -> None:
        channel = _channel()
        client = _client(
            renew_subscription=AsyncMock(
                side_effect=ConnectorAPIError("microsoft_onedrive", 404, "gone")
            )
        )

        with _settings():
            await _service(channel).ensure_onedrive_watch(USER, client)

        client.create_subscription.assert_awaited_once()
        client.get_changes_start_page_token.assert_not_awaited()
        assert channel.resource_id == "sub-1"
        assert channel.page_token == "kept-token"
        assert channel.token == client.create_subscription.await_args.args[1]

    async def test_any_other_refusal_of_a_renewal_stays_what_it_is(self) -> None:
        client = _client(
            renew_subscription=AsyncMock(
                side_effect=ConnectorAPIError("microsoft_onedrive", 403, "denied")
            )
        )

        with _settings(), pytest.raises(ConnectorAPIError):
            await _service(_channel()).ensure_onedrive_watch(USER, client)

        client.create_subscription.assert_not_awaited()


class TestANotification:
    @staticmethod
    def _notified(state: str = "secret") -> GraphNotification:
        return GraphNotification(subscription_id="sub-1", client_state=state)

    async def test_an_unknown_subscription_is_ignored(self) -> None:
        outcome = await _service(None).handle_graph_notification(self._notified())

        assert outcome is NotificationOutcome.IGNORED_UNKNOWN

    async def test_a_wrong_secret_is_ignored(self) -> None:
        service = _service(_channel())

        outcome = await service.handle_graph_notification(self._notified("forged"))

        assert outcome is NotificationOutcome.IGNORED_BAD_TOKEN
        service.db.commit.assert_not_awaited()

    async def test_a_true_one_wakes_the_account_on_its_drive(self) -> None:
        channel = _channel()
        service = _service(channel)
        service._enqueue_wake = AsyncMock()  # type: ignore[method-assign]
        service._try_acquire_debounce = AsyncMock(return_value=True)  # type: ignore[method-assign]

        with patch(
            "src.domains.push_channels.service.invalidate_for_provider", AsyncMock()
        ) as invalidate:
            outcome = await service.handle_graph_notification(self._notified())

        assert outcome is NotificationOutcome.PROCESSED
        invalidate.assert_awaited_once_with(ONEDRIVE, USER)
        service._enqueue_wake.assert_awaited_once_with(USER, ONEDRIVE)

    async def test_it_is_looked_up_among_the_drive_s_own_subscriptions(self) -> None:
        service = _service(None)

        await service.handle_graph_notification(self._notified())

        service.repo.get_by_resource.assert_awaited_once_with(ONEDRIVE, "sub-1")

    async def test_a_storm_is_debounced_by_channel(self) -> None:
        service = _service(_channel())
        service._try_acquire_debounce = AsyncMock(return_value=False)  # type: ignore[method-assign]

        outcome = await service.handle_graph_notification(self._notified())

        assert outcome is NotificationOutcome.DEBOUNCED


class TestItsBody:
    def test_each_entry_names_its_subscription_and_its_secret(self) -> None:
        parsed = parse_graph_body(
            {"value": [{"subscriptionId": "s1", "clientState": "c1", "resource": "x"}]}
        )

        assert parsed == [GraphNotification(subscription_id="s1", client_state="c1")]

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"value": "nope"},
            {"value": [{"subscriptionId": "s1"}]},
            {"value": [{"clientState": "c1"}]},
            {"value": ["nope"]},
            {"value": [{"subscriptionId": 1, "clientState": 2}]},
        ],
    )
    def test_what_is_no_such_entry_is_dropped(self, body: dict[str, Any]) -> None:
        assert parse_graph_body(body) == []

    def test_a_delivery_is_bounded(self) -> None:
        entry = {"subscriptionId": "s", "clientState": "c"}

        assert len(parse_graph_body({"value": [entry] * 5000})) < 5000


@pytest.fixture
def web() -> TestClient:
    app = FastAPI()
    app.include_router(push_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: MagicMock()
    return TestClient(app)


class TestTheEndpoint:
    def test_it_answers_graph_s_handshake_in_plain_text(self, web: TestClient) -> None:
        response = web.post("/api/v1/webhooks/microsoft", params={"validationToken": "a b<c>"})

        assert response.status_code == 200
        assert response.text == "a b<c>"
        assert response.headers["content-type"].startswith("text/plain")

    def test_a_token_longer_than_graph_s_is_not_echoed(self, web: TestClient) -> None:
        response = web.post("/api/v1/webhooks/microsoft", params={"validationToken": "x" * 5000})

        assert response.status_code == 200
        assert len(response.text) < 5000

    def test_a_delivery_is_accepted_and_each_entry_handled(self, web: TestClient) -> None:
        service = MagicMock(
            handle_graph_notification=AsyncMock(return_value=NotificationOutcome.PROCESSED)
        )
        body = {"value": [{"subscriptionId": "s1", "clientState": "c1"}] * 2}

        with patch("src.domains.push_channels.router.PushChannelService", return_value=service):
            response = web.post("/api/v1/webhooks/microsoft", json=body)

        assert response.status_code == 202
        assert service.handle_graph_notification.await_count == 2

    def test_a_body_nobody_can_read_is_accepted_and_dropped(self, web: TestClient) -> None:
        service = MagicMock(handle_graph_notification=AsyncMock())

        with patch("src.domains.push_channels.router.PushChannelService", return_value=service):
            response = web.post(
                "/api/v1/webhooks/microsoft",
                content=b"not json",
                headers={"Content-Type": "application/json"},
            )

        assert response.status_code == 202
        service.handle_graph_notification.assert_not_awaited()
