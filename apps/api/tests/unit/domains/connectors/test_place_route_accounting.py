"""The selected-place correction uses real incremental accounting, never duplicate rows."""

import asyncio
from contextlib import asynccontextmanager, suppress
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest

from src.core.exceptions import BaseAPIException
from src.domains.agents.tools.location_resolution import ResolvedLocation
from src.domains.chat import service as chat_service
from src.domains.connectors import place_route_service as service
from src.domains.connectors.place_route_schemas import PlaceRouteRequest

pytestmark = pytest.mark.unit


def _route(distance):
    return {
        "routes": [
            {"distanceMeters": distance, "duration": "20s", "polyline": {"encodedPolyline": "????"}}
        ]
    }


@pytest.fixture
def accounting(monkeypatch):
    import src.domains.chat.repository as chat_repository
    import src.domains.google_api.repository as google_repository
    from src.domains.usage_limits.instance_budget import InstanceBudgetService

    state = SimpleNamespace(rows=[], gate_commits=[], refuse=False)
    db = MagicMock()
    db.commit = AsyncMock()

    @asynccontextmanager
    async def db_context():
        yield db

    monkeypatch.setattr(chat_service, "get_db_context", db_context)
    chat_repo = MagicMock()
    chat_repo.bulk_create_token_logs = AsyncMock()
    chat_repo.create_or_update_token_summary = AsyncMock()
    monkeypatch.setattr(chat_repository, "ChatRepository", MagicMock(return_value=chat_repo))
    google_repo = MagicMock()
    google_repo.bulk_create_logs = AsyncMock(side_effect=lambda rows: state.rows.extend(rows))
    monkeypatch.setattr(
        google_repository, "GoogleApiUsageRepository", MagicMock(return_value=google_repo)
    )
    # Keep the REAL commit/_do_persist/record-clear path; only repository I/O is simulated.
    monkeypatch.setattr(chat_service.TrackingContext, "_update_user_statistics", AsyncMock())
    budget = AsyncMock()
    monkeypatch.setattr(InstanceBudgetService, "record_run_summary", budget)

    async def guard(_):
        state.gate_commits.append(db.commit.await_count)
        if state.refuse and len(state.gate_commits) > 1:
            raise BaseAPIException(429, {"code": "usage_limit_exceeded"})

    monkeypatch.setattr(service, "check_route_access", AsyncMock(side_effect=guard))
    monkeypatch.setattr(
        service,
        "resolve_implicit_location",
        AsyncMock(return_value=ResolvedLocation(48.85, 2.351, "browser")),
    )
    monkeypatch.setattr(service.settings, "google_api_key", "server-only")

    def price(_, endpoint):
        usd = Decimal("0.015") if endpoint.endswith(":enterprise") else Decimal("0.005")
        return usd, usd * Decimal("0.9"), Decimal("0.9")

    monkeypatch.setattr(service.GoogleApiPricingService, "get_cost_per_request", price)
    transport = SimpleNamespace(
        post=AsyncMock(
            side_effect=[
                httpx.Response(200, json=_route(2001)),
                httpx.Response(200, json=_route(2500)),
            ]
        ),
        is_closed=False,
        aclose=AsyncMock(),
    )
    client = service.GoogleRoutesClient()
    client._client = transport
    monkeypatch.setattr(service, "GoogleRoutesClient", MagicMock(return_value=client))
    return SimpleNamespace(
        state=state, db=db, chat_repo=chat_repo, budget=budget, client=client, transport=transport
    )


@pytest.mark.parametrize(
    "outcome", ["success", "empty", "refused", "unpriced", "timeout", "cancelled"]
)
async def test_two_km_correction_files_each_legitimate_call_once(accounting, monkeypatch, outcome):
    state = accounting.state
    if outcome == "empty":
        accounting.transport.post.side_effect = [
            httpx.Response(200, json=_route(2001)),
            httpx.Response(200, json={"routes": []}),
        ]
    if outcome == "refused":
        state.refuse = True
    if outcome == "unpriced":
        price = service.GoogleApiPricingService.get_cost_per_request
        monkeypatch.setattr(
            service.GoogleApiPricingService,
            "get_cost_per_request",
            lambda api, endpoint: (
                (0, 0, 1) if endpoint.endswith(":enterprise") else price(api, endpoint)
            ),
        )
    if outcome == "timeout":

        async def delayed_post(*_, **__):
            if accounting.transport.post.await_count == 1:
                return httpx.Response(200, json=_route(2001))
            await asyncio.sleep(1)
            return httpx.Response(200, json=_route(2500))

        monkeypatch.setattr(service.settings, "http_timeout_routes_api", 0.05)
        accounting.transport.post.side_effect = delayed_post
    if outcome == "cancelled":
        compute = accounting.client.compute_route

        async def cancel_after_paid_response(**kwargs):
            result = await compute(**kwargs)
            if kwargs["travel_mode"] is service.TravelMode.DRIVE:
                raise asyncio.CancelledError()
            return result

        accounting.client.compute_route = cancel_after_paid_response
    owner = uuid4()
    body = PlaceRouteRequest.model_validate({"destination": {"lat": 48.85, "lng": 2.35}})
    if outcome == "success":
        result = await service.compute_place_route(body, owner)
        assert result.travel_mode == "DRIVE" and result.distance_meters == 2500
    else:
        with pytest.raises(asyncio.CancelledError if outcome == "cancelled" else BaseAPIException):
            await service.compute_place_route(body, owner)
    expected = ["/directions/v2:computeRoutes"]
    first_only = outcome in ("refused", "unpriced", "timeout")
    if not first_only:
        expected.append("/directions/v2:computeRoutes:enterprise")
    assert [row["endpoint"] for row in state.rows] == expected
    assert all(row["user_id"] == owner for row in state.rows)
    assert len({row["run_id"] for row in state.rows}) == 1
    assert state.gate_commits == [0, 1]
    assert accounting.db.commit.await_count == len(expected)
    assert accounting.budget.await_count == len(expected)
    assert accounting.transport.post.await_count == (1 if outcome in ("refused", "unpriced") else 2)
    summaries = [
        call.kwargs["summary_data"]
        for call in accounting.chat_repo.create_or_update_token_summary.call_args_list
    ]
    assert [summary["google_api_requests"] for summary in summaries] == [1] * len(expected)
    assert sum(summary["google_api_cost_eur"] for summary in summaries) == pytest.approx(
        0.0045 if first_only else 0.018
    )
    accounting.transport.aclose.assert_awaited_once()


async def test_walk_two_thousand_meters_is_kept_without_a_second_paid_call(accounting):
    accounting.transport.post.side_effect = [httpx.Response(200, json=_route(2000))]
    body = PlaceRouteRequest.model_validate({"destination": {"lat": 48.85, "lng": 2.35}})
    result = await service.compute_place_route(body, uuid4())
    assert result.travel_mode == "WALK" and result.distance_meters == 2000
    assert len(accounting.state.rows) == accounting.transport.post.await_count == 1
    accounting.transport.aclose.assert_awaited_once()


async def test_repeated_cancellation_during_intermediate_commit_does_not_refile_walk(accounting):
    started, release = asyncio.Event(), asyncio.Event()

    async def commit():
        started.set()
        await release.wait()

    accounting.db.commit.side_effect = commit
    body = PlaceRouteRequest.model_validate({"destination": {"lat": 48.85, "lng": 2.35}})
    task = asyncio.create_task(service.compute_place_route(body, uuid4()))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        for _ in range(5):
            task.cancel()
            await asyncio.sleep(0)
        waited_for_paid_write = not task.done()
    finally:
        release.set()
        with suppress(asyncio.CancelledError):
            await task
        await asyncio.sleep(0)
    assert waited_for_paid_write
    assert len(accounting.state.rows) == accounting.db.commit.await_count == 1
    assert accounting.transport.post.await_count == 1
    accounting.transport.aclose.assert_awaited_once()
