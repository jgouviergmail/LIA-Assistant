"""A post-selection presentation aggregate; never a registry entity or model input."""

import json
from collections.abc import Mapping
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from src.core.i18n import resolve_language
from src.domains.agents.data_registry.models import RegistryItem, RegistryItemType
from src.domains.agents.display.components.base import (
    render_card_top,
    wrap_with_response,
)
from src.domains.agents.display.escaping import escape_html
from src.domains.agents.display.urls import build_place_url, safe_image_url
from src.domains.agents.display.values import (
    first_present,
    list_values,
    nonnegative_integer,
    rating_value,
    scalar_text,
)

MAX_POSITION_PLACES = 64
MAX_POSITION_WIRE_CHARACTERS = 512 * 1024
_MAX_SAFE_INTEGER = 2**53 - 1
_TITLES = {
    "fr": "Position",
    "en": "Position",
    "de": "Position",
    "es": "Ubicación",
    "it": "Posizione",
    "zh-CN": "位置",
}


class PositionPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lng: float = Field(ge=-180, le=180, allow_inf_nan=False)


class PositionPlaceDetails(BaseModel):
    """Bounded facts already acquired for the selected place, without provider trees."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    address: str | None = Field(max_length=1000, description="Already acquired address, if any.")
    rating: float | None = Field(ge=0, le=5, allow_inf_nan=False, description="Provider score.")
    reviews_count: int | None = Field(
        ge=0, le=_MAX_SAFE_INTEGER, description="Already acquired review count, if any."
    )
    phone: str | None = Field(max_length=128, description="Already acquired telephone number.")
    website: str | None = Field(max_length=4096, description="Credential-free HTTP(S) website.")
    opening_hours: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        max_length=7, description="Supplied weekday descriptions."
    )


class PositionPlace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ref: str = Field(min_length=1, max_length=256)
    label: str = Field(min_length=1, max_length=200)
    url: str = Field(max_length=4096)
    position: PositionPoint | None
    details: PositionPlaceDetails | None = None


class PositionMapV2(BaseModel):
    """The Position map's second payload version: located places and what was left out.

    ``unlocated_count`` counts the listed places without coordinates (they get no
    pin), ``omitted_count`` the places beyond the map's bound (not listed at all).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal[2] = 2
    places: list[PositionPlace] = Field(min_length=1, max_length=MAX_POSITION_PLACES)
    unlocated_count: int = Field(ge=0)
    omitted_count: int = Field(ge=0)


def _coordinate(value: object, bound: int) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool) and -bound <= value <= bound:
        return float(value)
    return None


def _point(payload: Mapping[str, object]) -> PositionPoint | None:
    location = payload.get("location")
    if not isinstance(location, Mapping):
        return None
    lat = _coordinate(location.get("lat", location.get("latitude")), 90)
    lng = _coordinate(location.get("lon", location.get("lng", location.get("longitude"))), 180)
    if lat is None or lng is None:
        return None
    return PositionPoint(lat=lat, lng=lng)


def _source(value: object) -> Mapping[str, object] | None:
    if isinstance(value, RegistryItem):
        if value.type == RegistryItemType.PLACE and value.meta.source in {
            "google_places",
            "resolved_context",
        }:
            return value.payload
        return None
    if isinstance(value, Mapping) and value.get("type") == "PLACE":
        meta, payload = value.get("meta"), value.get("payload")
        if (
            isinstance(meta, Mapping)
            and meta.get("source") in ("google_places", "resolved_context")
            and isinstance(payload, Mapping)
        ):
            return payload
    return None


def _sources(
    registry: Mapping[str, object] | None, resolved: Mapping[str, object] | None
) -> list[tuple[str, Mapping[str, object]]]:
    if registry is not None:
        return [
            (ref, payload)
            for ref, value in registry.items()
            if (payload := _source(value)) is not None
        ]
    if resolved is None or resolved.get("source_domain") not in (
        None,
        "places",
        "place",
    ):
        return []
    items = resolved.get("items")
    if not isinstance(items, list):
        return []
    return [
        (f"reference-{index}", item)
        for index, item in enumerate(items)
        if isinstance(item, Mapping) and "place_id" in item
    ]


def _project_place(ref: str, payload: Mapping[str, object], identity: str) -> PositionPlace:
    display_name = payload.get("displayName")
    name = display_name.get("text") if isinstance(display_name, Mapping) else display_name
    label = (scalar_text(name) or scalar_text(payload.get("name")) or identity)[:200]
    address = scalar_text(payload.get("formatted_address") or payload.get("formattedAddress"))[:200]
    provider_id = scalar_text(payload.get("place_id") or payload.get("id"))
    url = build_place_url(
        place_id=provider_id if 0 < len(provider_id) <= 512 else None,
        query=f"{label} {address}",
    )
    return PositionPlace(
        ref=ref, label=label, url=url, position=_point(payload), details=_details(payload)
    )


def _website(value: object) -> str | None:
    candidate = scalar_text(value).strip()
    # Reuse the display URL guard's strict HTTP(S) lexical checks, then exclude
    # site-relative paths and credentials from this archived external link.
    if not candidate or len(candidate) > 4096 or not safe_image_url(candidate):
        return None
    try:
        parsed = urlsplit(candidate)
        _ = parsed.port  # Invalid/non-numeric ports must not poison the frontend archive parser.
        return (
            candidate if parsed.hostname and not parsed.username and not parsed.password else None
        )
    except ValueError:
        return None


def _opening_hours(payload: Mapping[str, object]) -> list[str]:
    candidates: list[object] = []
    for key in ("currentOpeningHours", "regularOpeningHours", "openingHours"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            candidates.append(value.get("weekdayDescriptions", value.get("weekday_text")))
    candidates.append(payload.get("opening_hours"))
    for candidate in candidates:
        lines = []
        for line in list_values(candidate):
            if isinstance(line, str) and line.strip():
                lines.append(line[:500])
                if len(lines) == 7:
                    break
        if lines:
            return lines
    return []


def _details(payload: Mapping[str, object]) -> PositionPlaceDetails:
    count = nonnegative_integer(
        first_present(payload, "userRatingCount", "rating_count", "reviews_count")
    )
    return PositionPlaceDetails(
        address=scalar_text(
            first_present(payload, "formattedAddress", "formatted_address", "address")
        )[:1000]
        or None,
        rating=rating_value(payload.get("rating")),
        reviews_count=count if count is not None and count <= _MAX_SAFE_INTEGER else None,
        phone=scalar_text(
            first_present(payload, "internationalPhoneNumber", "phone_international", "phone")
        )[:128]
        or None,
        website=_website(first_present(payload, "websiteUri", "website")),
        opening_hours=_opening_hours(payload),
    )


def _places(
    registry: Mapping[str, object] | None, resolved: Mapping[str, object] | None
) -> list[PositionPlace]:
    result: list[PositionPlace] = []
    seen: set[str] = set()
    for ref, payload in _sources(registry, resolved):
        identity = scalar_text(payload.get("place_id") or payload.get("id")) or ref
        if identity in seen or not isinstance(ref, str) or not 1 <= len(ref) <= 256:
            continue
        seen.add(identity)
        result.append(_project_place(ref, payload, identity))
    return result


def project_positions(
    registry: Mapping[str, object] | None,
    *,
    resolved: Mapping[str, object] | None = None,
) -> PositionMapV2 | None:
    places = _places(registry, resolved)
    return _projection(places) if places else None


def _projection(places: list[PositionPlace]) -> PositionMapV2:
    projection = PositionMapV2(
        places=places[:MAX_POSITION_PLACES],
        unlocated_count=sum(place.position is None for place in places),
        omitted_count=max(0, len(places) - MAX_POSITION_PLACES),
    )
    remaining = len(_wire(projection))
    bounded = list(projection.places)
    for index in reversed(range(len(bounded))):
        if remaining <= MAX_POSITION_WIRE_CHARACTERS:
            break
        details = bounded[index].details
        if details is not None:
            remaining -= len(_wire(details)) - len("null")
            bounded[index] = bounded[index].model_copy(update={"details": None})
    return projection.model_copy(update={"places": bounded})


def _wire(value: BaseModel) -> str:
    return json.dumps(value.model_dump(mode="json"), ensure_ascii=True, separators=(",", ":"))


def render_positions(
    registry: Mapping[str, object] | None,
    *,
    language: str,
    resolved: Mapping[str, object] | None = None,
) -> str:
    try:
        return _render_positions(registry, language=language, resolved=resolved)
    except ValueError, TypeError, AttributeError, OverflowError:
        # Malformed optional geometry cannot discard the already rendered cards.
        return ""


def _render_positions(
    registry: Mapping[str, object] | None,
    *,
    language: str,
    resolved: Mapping[str, object] | None = None,
) -> str:
    places = _places(registry, resolved)
    if not places:
        return ""
    wire = _wire(_projection(places))
    fallback = (
        '<ol class="lia-place-position__fallback">'
        + "".join(
            f'<li><a href="{escape_html(place.url)}" target="_blank" rel="noopener noreferrer">'
            f"{escape_html(place.label)}</a></li>"
            for place in places
        )
        + "</ol>"
    )
    header = render_card_top(
        icon_name="map",
        illus_color="blue",
        title_html=f'<div class="lia-card-top__title">{escape_html(_TITLES[resolve_language(language)])}</div>',
    )
    card = (
        f'<div class="lia-card lia-places-position">{header}'
        f'<div class="lia-place-position" data-place-position="{escape_html(wire)}">{fallback}</div></div>'
    )
    return wrap_with_response(
        card_html=card, assistant_comment=None, suggested_actions=[], domain="places"
    )
