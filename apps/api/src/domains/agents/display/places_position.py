"""A post-selection presentation aggregate; never a registry entity or model input."""

import json
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.core.i18n import resolve_language
from src.domains.agents.data_registry.models import RegistryItem, RegistryItemType
from src.domains.agents.display.components.base import (
    render_card_top,
    wrap_with_response,
)
from src.domains.agents.display.escaping import escape_html
from src.domains.agents.display.urls import build_place_url
from src.domains.agents.display.values import scalar_text

MAX_POSITION_PLACES = 64
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


class PositionPlace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ref: str = Field(min_length=1, max_length=256)
    label: str = Field(min_length=1, max_length=200)
    url: str = Field(max_length=4096)
    position: PositionPoint | None


class PositionMapV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal[1] = 1
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
    return PositionPlace(ref=ref, label=label, url=url, position=_point(payload))


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
) -> PositionMapV1 | None:
    places = _places(registry, resolved)
    return _projection(places) if places else None


def _projection(places: list[PositionPlace]) -> PositionMapV1:
    return PositionMapV1(
        places=places[:MAX_POSITION_PLACES],
        unlocated_count=sum(place.position is None for place in places),
        omitted_count=max(0, len(places) - MAX_POSITION_PLACES),
    )


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
    wire = json.dumps(
        _projection(places).model_dump(mode="json"),
        ensure_ascii=True,
        separators=(",", ":"),
    )
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
