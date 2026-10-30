"""The Google weather and environment clients open ONE HTTP client per instance.

Measured on production (spec 2026-10-21 §0ter W1): a weather card made 8
sequential requests (current conditions plus five 24-hour forecast pages),
each on a fresh ``httpx.AsyncClient`` — a new TLS setup every time, about
672 ms each, 5.0 s at the median. These tests pin the pooled form: one client
per instance across every page, released by ``close()``, never reopened after
it (an orphaned forecast page must not open a client nobody closes), and the
read-budget hooks bound to the instance's account as before.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest

from src.domains.connectors.clients import google_environment_client, google_weather_client
from src.domains.connectors.clients.google_environment_client import GoogleEnvironmentClient
from src.domains.connectors.clients.google_weather_client import GoogleWeatherClient

pytestmark = pytest.mark.unit

_REAL_ASYNC_CLIENT = httpx.AsyncClient
_PAGES = 5


def _weather_response(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("currentConditions:lookup"):
        return httpx.Response(200, json={"currentTime": "2026-10-28T10:00:00Z"})
    page = int(request.url.params.get("pageToken") or 0)
    body: dict[str, Any] = {
        "forecastHours": [
            {"interval": {"startTime": f"2026-10-28T{(page * 24 + h) % 24:02d}:00:00Z"}}
            for h in range(24)
        ]
    }
    if page + 1 < _PAGES:
        body["nextPageToken"] = str(page + 1)
    return httpx.Response(200, json=body)


class _Recorder:
    """Counts the ``httpx.AsyncClient`` constructions and the closes."""

    def __init__(self) -> None:
        self.built: list[dict[str, Any]] = []
        self.closed = 0

    def factory(self, handler: Any) -> type[httpx.AsyncClient]:
        recorder = self

        class CountingClient(_REAL_ASYNC_CLIENT):
            def __init__(self, **kwargs: Any) -> None:
                recorder.built.append(kwargs)
                super().__init__(transport=httpx.MockTransport(handler), **kwargs)

            async def aclose(self) -> None:
                recorder.closed += 1
                await super().aclose()

        return CountingClient


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    rec = _Recorder()
    monkeypatch.setattr(httpx, "AsyncClient", rec.factory(_weather_response))
    monkeypatch.setattr(google_weather_client.settings, "google_api_key", "test-key")
    monkeypatch.setattr(google_weather_client, "track_google_api_call", lambda *a, **k: None)
    return rec


async def test_one_http_client_per_instance_across_pages(recorder: _Recorder) -> None:
    client = GoogleWeatherClient(uuid.uuid4(), rate_limit_per_second=1000)

    await client.get_current_weather(lat=48.85, lon=2.35)
    forecast = await client.get_hourly_forecast(lat=48.85, lon=2.35, hours=_PAGES * 24)
    await client.close()

    assert len(forecast["list"]) == _PAGES * 24
    assert len(recorder.built) == 1
    assert recorder.closed == 1


async def test_close_releases_and_refuses_reuse(recorder: _Recorder) -> None:
    client = GoogleWeatherClient(uuid.uuid4(), rate_limit_per_second=1000)
    await client.get_current_weather(lat=1.0, lon=2.0)

    await client.close()
    await client.close()  # idempotent

    assert recorder.closed == 1
    with pytest.raises(RuntimeError):
        await client.get_current_weather(lat=1.0, lon=2.0)
    assert len(recorder.built) == 1


async def test_close_before_any_request_opens_nothing(recorder: _Recorder) -> None:
    await GoogleWeatherClient(uuid.uuid4()).close()
    assert recorder.built == []


async def test_hooks_bound_to_instance_owner(
    recorder: _Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    owners: list[uuid.UUID | None] = []

    def hooks(owner: uuid.UUID | None) -> dict[str, list[Any]]:
        owners.append(owner)
        return {"request": []}

    monkeypatch.setattr(google_weather_client, "source_http_hooks", hooks)
    account = uuid.uuid4()
    client = GoogleWeatherClient(account, rate_limit_per_second=1000)

    await client.get_current_weather(lat=1.0, lon=2.0)
    await client.get_hourly_forecast(lat=1.0, lon=2.0, hours=48)
    await client.close()

    assert owners == [account]
    assert recorder.built[0]["event_hooks"] == {"request": []}


async def test_environment_client_pools_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = _Recorder()
    monkeypatch.setattr(
        httpx, "AsyncClient", rec.factory(lambda _request: httpx.Response(200, json={}))
    )
    monkeypatch.setattr(google_environment_client.settings, "google_api_key", "test-key")
    monkeypatch.setattr(google_environment_client, "track_google_api_call", lambda *a, **k: None)
    client = GoogleEnvironmentClient(uuid.uuid4(), rate_limit_per_second=1000)

    await client.get_air_quality(lat=48.85, lon=2.35, language="fr")
    await client.get_pollen_forecast(lat=48.85, lon=2.35, days=1, language="fr")
    await client.close()

    assert len(rec.built) == 1
    assert rec.closed == 1
    with pytest.raises(RuntimeError):
        await client.get_air_quality(lat=48.85, lon=2.35, language="fr")


async def test_a_refused_weather_request_is_a_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A provider refusal raises its status; the pooled client still closes once."""
    from src.core.exceptions import ConnectorAPIError

    rec = _Recorder()
    monkeypatch.setattr(
        httpx, "AsyncClient", rec.factory(lambda _request: httpx.Response(403, json={}))
    )
    monkeypatch.setattr(google_weather_client.settings, "google_api_key", "test-key")
    monkeypatch.setattr(google_weather_client, "track_google_api_call", lambda *a, **k: None)
    client = GoogleWeatherClient(uuid.uuid4(), rate_limit_per_second=1000)

    with pytest.raises(ConnectorAPIError) as refused:
        await client.get_daily_summaries(48.85, 2.35, lang="fr", days=3)
    await client.close()

    assert refused.value.status_code == 403
    assert rec.closed == 1


async def test_a_refused_environment_request_is_a_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.exceptions import ConnectorAPIError

    rec = _Recorder()
    monkeypatch.setattr(
        httpx, "AsyncClient", rec.factory(lambda _request: httpx.Response(429, json={}))
    )
    monkeypatch.setattr(google_environment_client.settings, "google_api_key", "test-key")
    monkeypatch.setattr(google_environment_client, "track_google_api_call", lambda *a, **k: None)
    client = GoogleEnvironmentClient(uuid.uuid4(), rate_limit_per_second=1000)

    with pytest.raises(ConnectorAPIError) as refused:
        await client.get_air_quality(lat=48.85, lon=2.35, language="fr")
    await client.close()

    assert refused.value.status_code == 429
