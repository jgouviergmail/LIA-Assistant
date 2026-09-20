"""Every image the media proxies serve is counted where Google bills it.

The route map used to be PRE-COUNTED by the tool that built its URL (a fetch
that may never happen, and a re-fetch past the browser cache never counted),
the location map was never counted at all, and neither proxy held a tracker.
Now one helper fetches, counts on the 200 and persists under the accounting
the signed URL names — the four proxies (routes map, location map, Street
View, Places photo) all go through it.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.core.context import current_tracker
from src.core.exceptions import ExternalServiceError
from src.domains.chat.service import TrackingContext
from src.domains.connectors import media_proxy_router as mod
from src.domains.connectors.media_attribution import with_attribution

pytestmark = pytest.mark.unit


@pytest.fixture
def persisted(monkeypatch: pytest.MonkeyPatch) -> list[TrackingContext]:
    """Capture every tracker the helper persists, without a database."""
    seen: list[TrackingContext] = []

    async def _persist(self: TrackingContext) -> None:
        seen.append(self)

    monkeypatch.setattr(TrackingContext, "_persist_to_database", _persist)
    monkeypatch.setattr(
        "src.domains.google_api.pricing_service.GoogleApiPricingService.get_cost_per_request",
        lambda *_a, **_k: (Decimal("0.002"), Decimal("0.0018"), Decimal("0.91")),
    )
    return seen


def _google(status: int, body: bytes = b"png") -> AsyncMock:
    response = httpx.Response(status, content=body, headers={"content-type": "image/png"})
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__.return_value = client
    return client


async def _serve(run: str | None, sig: str | None, user_id: uuid.UUID) -> object:
    return await mod.serve_billed_image(
        "https://maps.googleapis.com/x",
        api_name="static_maps",
        endpoint="/staticmap",
        service="google_routes",
        operation="static_map",
        timeout=5.0,
        default_media_type="image/png",
        user_id=user_id,
        run=run,
        sig=sig,
    )


def _signed_params(run_id: str, user_id: uuid.UUID) -> tuple[str, str]:
    token = current_tracker.set(TrackingContext(run_id, user_id, "s", None))
    try:
        query = with_attribution("/p").split("?", 1)[1]
    finally:
        current_tracker.reset(token)
    params = dict(part.split("=", 1) for part in query.split("&"))
    return params["run"], params["sig"]


async def test_a_served_image_is_counted_on_the_turn_that_asked(persisted: list) -> None:
    user_id = uuid.uuid4()
    run, sig = _signed_params("turn-42", user_id)
    with patch.object(httpx, "AsyncClient", return_value=_google(200)):
        response = await _serve(run, sig, user_id)
    assert response.media_type == "image/png"
    (tracker,) = persisted
    assert tracker.run_id == "turn-42"
    assert tracker.user_id == user_id
    # ``_persist_to_database`` is stubbed, so the records are still held:
    assert tracker.pending_families()["google_api"] == 1
    assert tracker.get_summary()["google_api_cost_eur"] == pytest.approx(0.0018)


async def test_an_unsigned_fetch_is_counted_on_a_fresh_run_of_the_caller(persisted: list) -> None:
    user_id = uuid.uuid4()
    with patch.object(httpx, "AsyncClient", return_value=_google(200)):
        await _serve("turn-42", None, user_id)
    (tracker,) = persisted
    assert tracker.run_id.startswith("media_")
    assert tracker.user_id == user_id
    assert tracker.pending_families()["google_api"] == 1


async def test_a_refused_request_is_not_billed_and_not_counted(persisted: list) -> None:
    user_id = uuid.uuid4()
    with (
        patch.object(httpx, "AsyncClient", return_value=_google(403, b"denied")),
        pytest.raises(ExternalServiceError),
    ):
        await _serve(None, None, user_id)
    assert persisted == []


async def test_the_count_is_persisted_before_the_bytes_are_returned(persisted: list) -> None:
    """The tracker closes inside the helper: nothing is left for a caller to flush."""
    user_id = uuid.uuid4()
    with patch.object(httpx, "AsyncClient", return_value=_google(200)):
        await _serve(None, None, user_id)
    assert len(persisted) == 1
    assert current_tracker.get() is None
