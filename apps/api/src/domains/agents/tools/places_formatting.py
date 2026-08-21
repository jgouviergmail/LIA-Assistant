"""Normalization of Google Places API payloads for the LLM, registry and cards.

Extracted from places_tools (2026-08, file-size ratchet): pure formatting of
raw Places API (New) responses into the normalized dicts consumed by the
planner, the Data Registry and PlaceCard.

Every field requested by the field masks must reach these dicts: the
Enterprise + Atmosphere attributes (dineIn, servesWine, ...) are PAID data —
dropping them silently wastes the SKU cost (2026-08 audit).

Distance calculation is delegated to src.domains.agents.utils.distance,
which provides an extensible architecture for future Google Routes API use.
"""

from typing import Any

import structlog

from src.core.config import settings
from src.core.constants import (
    PLACES_BUSINESS_STATUS_OPERATIONAL,
    PLACES_FEATURE_FIELD_TO_I18N_KEY,
    PLACES_MAX_GALLERY_PHOTOS,
)
from src.domains.agents.utils.distance import calculate_distance_sync
from src.domains.agents.utils.i18n_location import get_price_level
from src.domains.connectors.clients.google_api_tracker import track_google_api_call

logger = structlog.get_logger(__name__)


def _surface_status_and_identity(place: dict[str, Any], formatted: dict[str, Any]) -> None:
    """Surface businessStatus and primaryTypeDisplayName (shared by all formatters).

    OPERATIONAL stays silent: no key, no card badge, no LLM noise. Any other
    status (CLOSED_PERMANENTLY / CLOSED_TEMPORARILY) is a fact the user must
    see — a closed-forever place must never render as a normal one.
    """
    business_status = place.get("businessStatus")
    if business_status and business_status != PLACES_BUSINESS_STATUS_OPERATIONAL:
        formatted["business_status"] = business_status

    primary_type = place.get("primaryTypeDisplayName")
    if isinstance(primary_type, dict) and primary_type.get("text"):
        formatted["primary_type"] = primary_type["text"]


def _normalize_price_range(price_range: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize the Places API `priceRange` object to {start, end, currency}.

    Google money objects carry `units` as a string; an open-ended range has
    only one bound. Returns None when neither bound is usable.
    """

    def _units(bound: Any) -> int | None:
        if not isinstance(bound, dict):
            return None
        units = bound.get("units")
        try:
            return int(units) if units is not None else None
        except TypeError, ValueError:
            return None

    start_bound = price_range.get("startPrice") or {}
    end_bound = price_range.get("endPrice") or {}
    start = _units(start_bound)
    end = _units(end_bound)
    if start is None and end is None:
        return None
    currency = None
    if isinstance(start_bound, dict):
        currency = start_bound.get("currencyCode")
    if not currency and isinstance(end_bound, dict):
        currency = end_bound.get("currencyCode")
    return {"start": start, "end": end, "currency": currency}


def _distance_fields(
    place_lat: Any,
    place_lon: Any,
    center_lat: float | None,
    center_lon: float | None,
    distance_source: str | None,
    language: str,
) -> dict[str, Any]:
    """Distance payload from the user's position, or {} when unresolvable."""
    if (
        center_lat is None
        or center_lon is None
        or distance_source is None
        or place_lat is None
        or place_lon is None
    ):
        return {}
    return calculate_distance_sync(
        origin_lat=center_lat,
        origin_lon=center_lon,
        dest_lat=place_lat,
        dest_lon=place_lon,
        source=distance_source,
        language=language,
    ).to_dict()


def _photo_fields(place: dict[str, Any], *, include_names: bool = False) -> dict[str, Any]:
    """Photo proxy URLs (and optionally raw resource names) for a place.

    Tracks the billed thumbnail photo call. Carousel photos follow
    settings.place_carousel_enabled: when disabled, one photo per place keeps
    the billing exact (carousel photos are NOT tracked).
    """
    photos = place.get("photos", [])
    photo_names = [p.get("name") for p in photos if p.get("name")]
    fields: dict[str, Any] = {}
    if include_names and photos:
        fields["photos"] = photo_names
    if not photo_names:
        return fields
    fields["photo_url"] = f"/api/v1/connectors/google-places/photo/{photo_names[0]}"
    track_google_api_call("places", "/{photo}/media", cached=False)
    if settings.place_carousel_enabled:
        fields["photo_urls"] = [
            f"/api/v1/connectors/google-places/photo/{name}"
            for name in photo_names[:PLACES_MAX_GALLERY_PHOTOS]
        ]
    else:
        # Single photo mode: photo_urls contains only the thumbnail
        fields["photo_urls"] = [fields["photo_url"]]
    return fields


def _review_entries(
    reviews: list[dict[str, Any]], *, limit: int, include_author: bool
) -> list[dict[str, Any]]:
    """Most-recent reviews, normalized (publishTime is ISO 8601: lexicographic sort)."""
    entries: list[dict[str, Any]] = []
    for review in sorted(reviews, key=lambda r: r.get("publishTime", ""), reverse=True)[:limit]:
        text = review.get("text", "")
        entry: dict[str, Any] = {
            "rating": review.get("rating"),
            "text": (text.get("text", "") if isinstance(text, dict) else str(text))[:200],
            "relative_time": review.get("relativePublishTimeDescription"),
        }
        if include_author:
            author = review.get("authorAttribution", {})
            entry["author_name"] = author.get("displayName", "") if isinstance(author, dict) else ""
        entries.append(entry)
    return entries


def _attribute_fields(place: dict[str, Any]) -> dict[str, Any]:
    """Paid Enterprise + Atmosphere attributes: feature keys + option groups."""
    fields: dict[str, Any] = {}
    features = [
        i18n_key
        for api_field, i18n_key in PLACES_FEATURE_FIELD_TO_I18N_KEY.items()
        if place.get(api_field) is True
    ]
    if features:
        fields["features"] = features
    # Structured option groups pass through under their API names
    # (PlaceCard renders each as a dedicated collapsible section)
    for option_group in ("accessibilityOptions", "paymentOptions", "parkingOptions"):
        value = place.get(option_group)
        if isinstance(value, dict) and value:
            fields[option_group] = value
    return fields


def _format_place(
    place: dict[str, Any],
    center_lat: float | None = None,
    center_lon: float | None = None,
    distance_source: str | None = None,
    language: str = settings.default_language,
) -> dict[str, Any]:
    """
    Format a place for consistent output.

    Args:
        place: Raw place data from Google Places API
        center_lat: Optional center latitude for distance calculation
        center_lon: Optional center longitude for distance calculation
        distance_source: Source of center coordinates ("browser", "home", or None)
        language: Language for distance reference text

    Returns:
        Formatted place dict with optional distance fields
    """
    display_name = place.get("displayName", {})
    location = place.get("location", {})
    hours = place.get("currentOpeningHours", {})

    place_id = place.get("id")
    place_lat = location.get("latitude")
    place_lon = location.get("longitude")

    formatted = {
        "id": place_id,
        "place_id": place_id,  # Alias for planner compatibility
        "name": display_name.get("text", "Unknown"),
        "address": place.get("formattedAddress", ""),
        "location": {
            "lat": place_lat,
            "lon": place_lon,
        },
        "types": place.get("types", []),
        "google_maps_url": place.get("googleMapsUri"),
    }

    distance = _distance_fields(
        place_lat, place_lon, center_lat, center_lon, distance_source, language
    )
    formatted.update(distance)
    if center_lat is not None and distance_source is not None and not distance:
        # Place has no coordinates - log warning and skip distance
        logger.warning(
            "place_missing_coordinates_for_distance",
            place_id=place_id,
            place_name=formatted.get("name"),
            has_location=bool(location),
        )

    # Optional fields
    if place.get("rating"):
        formatted["rating"] = place.get("rating")
        formatted["rating_count"] = place.get("userRatingCount", 0)

    if place.get("priceLevel"):
        # Use i18n for price level translation
        formatted["price_level"] = get_price_level(place.get("priceLevel"), language)

    if place.get("nationalPhoneNumber"):
        formatted["phone"] = place.get("nationalPhoneNumber")

    if place.get("websiteUri"):
        formatted["website"] = place.get("websiteUri")

    if hours.get("openNow") is not None:
        formatted["open_now"] = hours.get("openNow")

    # Opening hours (weekday descriptions)
    if hours.get("weekdayDescriptions"):
        formatted["opening_hours"] = hours.get("weekdayDescriptions")

    # Editorial summary / description
    summary = place.get("editorialSummary", {})
    if summary.get("text"):
        formatted["description"] = summary.get("text")

    formatted.update(_photo_fields(place))

    reviews = place.get("reviews", [])
    if reviews:
        formatted["reviews"] = _review_entries(reviews, limit=5, include_author=True)

    _surface_status_and_identity(place, formatted)

    return formatted


def format_place_details(
    place: dict[str, Any],
    *,
    language: str,
    center_lat: float | None = None,
    center_lon: float | None = None,
    distance_source: str | None = None,
) -> dict[str, Any]:
    """
    Format a full place-details payload for the LLM, the registry and the card.

    Args:
        place: Raw place details from Google Places API (New).
        language: User language for localized derived fields.
        center_lat: Optional user latitude for distance calculation.
        center_lon: Optional user longitude for distance calculation.
        distance_source: Source of center coordinates ("browser", "home", ...).

    Returns:
        Normalized details dict (snake_case derived keys; structured option
        groups pass through under their API names, consumed by PlaceCard).
    """
    display_name = place.get("displayName", {})
    location = place.get("location", {})
    hours = place.get("regularOpeningHours", {})

    place_lat = location.get("latitude")
    place_lon = location.get("longitude")

    place_id_value = place.get("id")
    details: dict[str, Any] = {
        "id": place_id_value,
        "place_id": place_id_value,  # Alias for planner compatibility
        "name": display_name.get("text", "Unknown"),
        "address": place.get("formattedAddress", ""),
        "location": {
            "lat": place_lat,
            "lon": place_lon,
        },
        "types": place.get("types", []),
        "google_maps_url": place.get("googleMapsUri"),
    }

    details.update(
        _distance_fields(place_lat, place_lon, center_lat, center_lon, distance_source, language)
    )

    # Contact info
    if place.get("nationalPhoneNumber"):
        details["phone"] = place.get("nationalPhoneNumber")
    if place.get("internationalPhoneNumber"):
        details["phone_international"] = place.get("internationalPhoneNumber")
    if place.get("websiteUri"):
        details["website"] = place.get("websiteUri")

    # Ratings
    if place.get("rating"):
        details["rating"] = place.get("rating")
        details["rating_count"] = place.get("userRatingCount", 0)

    # Price level (i18n) and exact price range (audit-added)
    if place.get("priceLevel"):
        details["price_level"] = get_price_level(place.get("priceLevel"), language)
    price_range_raw = place.get("priceRange")
    if isinstance(price_range_raw, dict):
        price_range = _normalize_price_range(price_range_raw)
        if price_range:
            details["price_range"] = price_range

    # Opening hours
    if hours.get("weekdayDescriptions"):
        details["opening_hours"] = hours.get("weekdayDescriptions")

    current_hours = place.get("currentOpeningHours", {})
    if current_hours.get("openNow") is not None:
        details["open_now"] = current_hours.get("openNow")

    # Editorial summary
    summary = place.get("editorialSummary", {})
    if summary.get("text"):
        details["description"] = summary.get("text")

    # Short address (audit-added)
    if place.get("shortFormattedAddress"):
        details["short_address"] = place.get("shortFormattedAddress")

    # Business status + primary type (audit-added, shared helper)
    _surface_status_and_identity(place, details)

    # Paid attribute booleans + structured option groups (audit-added)
    details.update(_attribute_fields(place))

    details.update(_photo_fields(place, include_names=True))

    reviews = place.get("reviews", [])
    if reviews:
        details["reviews"] = _review_entries(reviews, limit=3, include_author=False)

    return details
