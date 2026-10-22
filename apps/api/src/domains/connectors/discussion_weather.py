"""Bounded weather signals at a separately consented location, without hidden enrichment."""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domains.connectors.clients.google_weather_client import GoogleWeatherClient
from src.domains.connectors.service import ConnectorService
from src.domains.connectors.weather_provider import resolve_weather_client
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    SourceKey,
    SourceReadRequest,
    SourceSnapshot,
    closed_source,
    semantic_version,
    source_snapshot,
)
from src.domains.users.discussion_location import read_location_focus
from src.infrastructure.database.session import get_db_context

#: The object id of the current conditions at one place, whatever instant stamps them.
_CURRENT = "current"
#: The precision a discussion reads the weather at — whole degrees, humidity by five
#: points, a precipitation chance by tenths: what a sentence about the weather would
#: say. Measured 2026-10-21, the provider refreshed its current conditions within
#: four minutes on a felt-temperature drift; versioned on every decimal, the same
#: weather was interpreted, and paid for, again at every run, and a run whose
#: re-read fell after a refresh stopped on a changed fact.
_DEGREES = 1.0
_HUMIDITY_POINTS = 5.0
_CHANCE = 0.1


class WeatherMain(BaseModel):
    """A weather point's temperature, felt temperature and humidity."""

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    temp: float | None = None
    feels_like: float | None = None
    humidity: float | None = None


class WeatherCondition(BaseModel):
    """A weather point's condition and its description."""

    model_config = ConfigDict(extra="ignore")
    main: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=300)


class WeatherPoint(BaseModel):
    """One weather observation or forecast instant, as the providers' shape gives it."""

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    dt: int
    main: WeatherMain = Field(default_factory=WeatherMain)
    weather: list[WeatherCondition] = Field(default_factory=list, max_length=5)
    pop: float | None = Field(default=None, ge=0, le=1)


class ForecastPage(BaseModel):
    """A forecast's points, filed by the provider under ``list``."""

    model_config = ConfigDict(extra="ignore")
    points: list[WeatherPoint] = Field(default_factory=list, alias="list", max_length=100)


@runtime_checkable
class WeatherReader(Protocol):
    """The read contract every weather client of the person's connector implements."""

    async def get_current_weather(
        self,
        lat: float | None = None,
        lon: float | None = None,
        city: str | None = None,
        country: str | None = None,
        units: str = "metric",
        lang: str | None = None,
    ) -> object:
        """Return the current conditions at a place, as the provider answers them."""

    async def get_forecast(
        self,
        lat: float | None = None,
        lon: float | None = None,
        city: str | None = None,
        country: str | None = None,
        units: str = "metric",
        lang: str | None = None,
        cnt: int = 40,
    ) -> object:
        """Return up to ``cnt`` forecast points at a place, as the provider answers them."""

    async def close(self) -> None:
        """Release the client's transport."""


@asynccontextmanager
async def open_discussion_weather(owner: UUID) -> AsyncIterator[WeatherReader | None]:
    """Open the person's active weather client for one read, and close it after.

    Args:
        owner: The account.

    Yields:
        The client, or None when no weather connector is active.

    Raises:
        ValueError: The client does not implement the read contract.
    """
    async with get_db_context() as db:
        client = await resolve_weather_client(owner, ConnectorService(db), fresh=True)
    if client is None:
        yield None
        return
    try:
        if not isinstance(client, WeatherReader):
            raise ValueError("weather client does not implement the native read contract")
        yield client
    finally:
        await client.close()


class WeatherDiscussionSource:
    """The weather at the person's current place, through their active weather client.

    A billed provider is read only after ``authorize_paid`` reserved its cost.
    """

    def __init__(self, *, authorize_paid: Callable[[], Awaitable[None]] | None = None) -> None:
        self.authorize_paid = authorize_paid

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read the current conditions or the forecast at the person's current place.

        Points outside the window, or more than ninety minutes old, are dropped; each
        point expires after thirty minutes and needs the location's consent too. The
        current conditions are ONE object per provider and place, observed: a
        provider may stamp them with the instant it answered, so a new read is the
        same object, at a new version only when what it says changed at the precision
        a discussion reads it (``_meaning``). A forecast point is planned, and is
        identified by the instant it forecasts.

        Args:
            request: The bounded read.

        Returns:
            The page; empty without a known place, closed when weather or location is
            not consented, no connector is active, or a billed one has no allowance.

        Raises:
            ValueError: The request is for another source.
        """
        if request.request.source != SourceKey.WEATHER:
            raise ValueError("weather source mismatch")
        if not {SourceKey.WEATHER, SourceKey.LOCATION} <= set(request.allowed_sources):
            return closed_source(request, disabled=True, reason="consent")
        focus = await read_location_focus(request.owner_id, now=request.now)
        if focus is None:
            return source_snapshot(request, status="empty", total=0, coverage_kind="signal")
        async with open_discussion_weather(request.owner_id) as client:
            if client is None:
                return closed_source(request, disabled=False, reason="provider")
            if isinstance(client, GoogleWeatherClient):
                if self.authorize_paid is None:
                    return closed_source(request, disabled=False, reason="budget")
                await self.authorize_paid()
            scope = semantic_version(
                (type(client).__name__, f"{focus.lat:.5f}", f"{focus.lon:.5f}")
            )
            if request.request.operation == "future":
                raw = await client.get_forecast(
                    lat=focus.lat, lon=focus.lon, units="metric", cnt=request.item_limit
                )
                points = tuple(ForecastPage.model_validate(raw).points)
            else:
                points = (
                    WeatherPoint.model_validate(
                        await client.get_current_weather(
                            lat=focus.lat, lon=focus.lon, units="metric"
                        )
                    ),
                )
        forecast = request.request.operation == "future"
        items = tuple(
            _evidence(point, request, scope, forecast=forecast)
            for point in points
            if request.window_start <= datetime.fromtimestamp(point.dt, UTC) < request.window_end
            and datetime.fromtimestamp(point.dt, UTC) >= request.now - timedelta(minutes=90)
        )
        return source_snapshot(
            request,
            status="ok" if items else "empty",
            items=items,
            coverage_kind="signal",
            complete=False,
        )


def _bucket(value: float | None, step: float) -> int | None:
    """The step a measured value falls in; a missing value stays missing."""
    return None if value is None else round(value / step)


def _meaning(point: WeatherPoint) -> str:
    """What a weather point says, at the precision a discussion reads it (its version).

    The excerpt the model reads keeps every value; only what decides that the fact
    changed is rounded, as the location's version rounds its coordinates.
    """
    return json.dumps(
        {
            "temp": _bucket(point.main.temp, _DEGREES),
            "feels_like": _bucket(point.main.feels_like, _DEGREES),
            "humidity": _bucket(point.main.humidity, _HUMIDITY_POINTS),
            "pop": _bucket(point.pop, _CHANCE),
            "weather": [[condition.main, condition.description] for condition in point.weather],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _evidence(
    point: WeatherPoint, request: SourceReadRequest, scope: str, *, forecast: bool
) -> DiscussionEvidence:
    text = point.model_dump_json()
    moment = datetime.fromtimestamp(point.dt, UTC)
    # Measured on Google Weather: the current conditions' instant is the answer's
    # own clock, so it moved by the gap between two reads while every value held.
    instant = str(point.dt) if forecast else _CURRENT
    return DiscussionEvidence(
        reference=f"weather:{scope[:16]}:{instant}",
        source=SourceKey.WEATHER,
        object_id=instant,
        source_account=scope,
        version=semantic_version((_meaning(point),)),
        observed_at=request.now,
        occurred_at=moment,
        assertion="planned" if forecast else "observed",
        required_sources=(SourceKey.LOCATION,),
        expires_at=request.now + timedelta(minutes=30),
        excerpt=text[: request.item_max_chars],
        excerpt_truncated=len(text) > request.item_max_chars,
    )
