"""Small, strict wire contract for the Position map's selected-place route."""

import re
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domains.agents.utils.polyline import decode_polyline

BROWSER_ORIGIN_MAX_AGE_MS = 5 * 60 * 1000
BROWSER_ORIGIN_CLOCK_SKEW_MS = 30 * 1000
MAX_ROUTE_POLYLINE_LENGTH = 50_000


class RouteDestination(BaseModel):
    """The selected place's coordinates."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    lat: float = Field(ge=-90, le=90, description="Selected place latitude in degrees")
    lng: float = Field(ge=-180, le=180, description="Selected place longitude in degrees")


class RouteBrowserOrigin(BaseModel):
    """The browser position the person consented to share, with its age bounded."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    lat: float = Field(ge=-90, le=90, description="Consented browser latitude in degrees")
    lon: float = Field(ge=-180, le=180, description="Consented browser longitude in degrees")
    accuracy: float | None = Field(default=None, ge=0, description="Browser accuracy in meters")
    timestamp: float = Field(
        ge=0,
        description="Capture time in epoch milliseconds; at most five minutes old with 30 seconds of clock skew",
    )

    @field_validator("timestamp")
    @classmethod
    def fresh_capture(cls, value: float) -> float:
        """Refuse a capture older than five minutes or more than 30 seconds ahead."""
        age_ms = time.time() * 1000 - value
        if not -BROWSER_ORIGIN_CLOCK_SKEW_MS <= age_ms <= BROWSER_ORIGIN_MAX_AGE_MS:
            raise ValueError(
                "Browser origin must be at most five minutes old and no more than 30 seconds ahead"
            )
        return value


class PlaceRouteRequest(BaseModel):
    """A route request: the selected place, and the browser origin when consented."""

    model_config = ConfigDict(extra="forbid", strict=True)
    destination: RouteDestination = Field(description="Already acquired selected place coordinates")
    origin: RouteBrowserOrigin | None = Field(
        default=None,
        description="Optional consented browser origin; otherwise use the account cascade",
    )


class PlaceRouteResponse(BaseModel):
    """The computed route, the origin the server chose and the mode its distance gave."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    origin_source: Literal["browser", "last_known", "home"] = Field(
        description="Authoritative source selected by the server location cascade"
    )
    origin_as_of: str | None = Field(
        default=None,
        description="ISO capture time for a last-known origin; never a live-position claim",
    )
    travel_mode: Literal["WALK", "DRIVE"] = Field(
        description="Travel mode selected by the server's distance rule for this selected place"
    )
    polyline: str = Field(
        min_length=4,
        max_length=MAX_ROUTE_POLYLINE_LENGTH,
        description="Validated Google encoded route polyline",
    )
    distance_meters: int = Field(ge=0, le=2**31 - 1, description="Route distance in whole meters")
    duration_seconds: int = Field(
        ge=0, le=2**31 - 1, description="Route duration rounded up to whole seconds"
    )

    @field_validator("polyline")
    @classmethod
    def usable_polyline(cls, value: str) -> str:
        """Refuse a polyline that is malformed, truncated or outside the globe."""
        # Each coordinate delta occupies at most six groups; validating before
        # decoding also bounds integer growth on corrupt continuation bytes.
        if re.fullmatch(r"(?:[\x5f-\x7e]{0,5}[\x3f-\x5e])+", value) is None:
            raise ValueError("Invalid encoded route")
        try:
            points = decode_polyline(value)
        except IndexError as exc:
            raise ValueError("Incomplete encoded route") from exc
        if len(points) < 2 or any(
            not (-90 <= lat <= 90 and -180 <= lng <= 180) for lat, lng in points
        ):
            raise ValueError("Invalid route coordinates")
        return value
