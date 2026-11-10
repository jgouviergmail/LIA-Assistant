"""Bounded address-map presentation from received coordinates, without geocoding."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.domains.agents.display.escaping import escape_html


class LocationMapPoint(BaseModel):
    """A finite, supplied geographic point, including valid zero coordinates."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False, description="Received latitude.")
    lng: float = Field(ge=-180, le=180, allow_inf_nan=False, description="Received longitude.")


class LocationMapV1(BaseModel):
    """One display-only address, never a PLACE registry item or route request."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Literal[1] = Field(default=1, description="Address-map wire version.")
    label: str = Field(min_length=1, max_length=200, description="Received display name.")
    address: str = Field(max_length=1000, description="Complete received address, if supplied.")
    position: LocationMapPoint = Field(description="Received location; never inferred.")


def location_map_point(latitude: object, longitude: object) -> LocationMapPoint | None:
    """Validate received coordinates without coercing text or booleans."""
    try:
        return LocationMapPoint.model_validate({"lat": latitude, "lng": longitude})
    except ValidationError:
        return None


def render_location_map(
    point: LocationMapPoint | None, label: str, address: str, fallback: str
) -> str:
    """Enhance a valid bounded address while preserving its static fallback.

    Args:
        point: Validated source coordinates, or no usable point.
        label: Existing location display name.
        address: Complete existing address text.
        fallback: Already rendered static map HTML.

    Returns:
        A versioned marker wrapping the unchanged fallback, or the fallback alone.
    """
    if point is None:
        return fallback
    try:
        projection = LocationMapV1(label=label, address=address, position=point)
    except ValidationError:
        return fallback
    wire = escape_html(projection.model_dump_json())
    return f'<div class="lia-location-map" data-location-map="{wire}">{fallback}</div>'
