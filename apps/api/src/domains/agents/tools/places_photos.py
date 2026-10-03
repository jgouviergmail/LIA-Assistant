"""Signed Places photo URLs and display-only author attribution."""

from src.core.config import settings
from src.core.constants import PLACES_MAX_GALLERY_PHOTOS
from src.core.field_names import FIELD_DISPLAY_ONLY
from src.domains.connectors.media_attribution import with_attribution


def _authors(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    authors: list[dict[str, str]] = []
    for record in value:
        if not isinstance(record, dict):
            continue
        name = record.get("displayName")
        if not isinstance(name, str) or not name.strip():
            continue
        url = record.get("uri")
        author = {"name": name, "url": url if isinstance(url, str) else ""}
        avatar = record.get("photoUri")
        if isinstance(avatar, str) and avatar:
            author["avatar_url"] = avatar
        authors.append(author)
    return authors


def photo_fields(place: dict[str, object], *, include_names: bool = False) -> dict[str, object]:
    """Never fetch here; each image is accounted when its proxy serves it."""
    value = place.get("photos")
    if not isinstance(value, list):
        return {}
    photos = [
        record
        for record in value
        if isinstance(record, dict)
        and isinstance(record.get("name"), str)
        and record["name"].strip()
    ]
    if not photos:
        return {}
    limit = PLACES_MAX_GALLERY_PHOTOS if settings.place_carousel_enabled else 1
    gallery = [
        {
            "url": with_attribution(f'/api/v1/connectors/google-places/photo/{photo["name"]}'),
            "authors": _authors(photo.get("authorAttributions")),
            "source_url": (
                photo.get("googleMapsUri") if isinstance(photo.get("googleMapsUri"), str) else ""
            ),
        }
        for photo in photos[:limit]
    ]
    fields = {
        "photo_url": gallery[0]["url"],
        "photo_urls": [photo["url"] for photo in gallery],
        FIELD_DISPLAY_ONLY: {"photo_gallery": gallery},
    }
    if include_names:
        fields["photos"] = [photo["name"] for photo in photos]
    return fields
