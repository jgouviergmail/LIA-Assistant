"""Pure photo markup, with an accessible static fallback and complete authors."""

import json

from src.core.i18n import resolve_language
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import escape_html, safe_url
from src.domains.agents.display.components.source_attribution import (
    GOOGLE_MAPS_ATTRIBUTION as GOOGLE_MAPS_ATTRIBUTION,
)
from src.domains.agents.display.urls import safe_image_url
from src.domains.agents.display.values import list_values, scalar_text


def place_source_without_photo(photo_html: str) -> str:
    """Keep the provider attribution when no image supplies its own caption."""
    return "" if photo_html else f'<div class="lia-place-source">{GOOGLE_MAPS_ATTRIBUTION}</div>'


def _authors(value: object) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for record in list_values(value):
        if not isinstance(record, dict):
            continue
        name = scalar_text(record.get("name"))
        if not name:
            continue
        url = scalar_text(record.get("url"))
        author = {"name": name, "url": url if safe_image_url(url) else ""}
        avatar = scalar_text(record.get("avatar_url"))
        if avatar and safe_image_url(avatar):
            author["avatar_url"] = avatar
        result.append(author)
    return result


def _author_links(value: object) -> str:
    links: list[str] = []
    for author in _authors(value):
        name = escape_html(author["name"])
        target = safe_url(author["url"])
        avatar = safe_image_url(author.get("avatar_url"))
        portrait = (
            f'<img class="lia-photo-author__avatar" src="{avatar}" alt="" loading="lazy">'
            if avatar
            else ""
        )
        links.append(
            f'{portrait}<a href="{target}" target="_blank" rel="noopener noreferrer">{name}</a>'
            if target
            else f"{portrait}{name}"
        )
    return ", ".join(links)


def render_place_photo(data: dict[str, object], name: str, language: str | None = None) -> str:
    gallery: list[dict[str, object]] = []
    for photo in list_values(data.get("photo_gallery")):
        if isinstance(photo, dict):
            url = scalar_text(photo.get("url"))
            if url and safe_image_url(url):
                gallery.append(
                    {
                        "url": url,
                        "authors": _authors(photo.get("authors")),
                        "source_url": (
                            scalar_text(photo.get("source_url"))
                            if safe_image_url(scalar_text(photo.get("source_url")))
                            else ""
                        ),
                    }
                )
    if not gallery:
        urls = list_values(data.get("photo_urls")) or [data.get("photo_url")]
        gallery = [
            {"url": url, "authors": []}
            for value in urls
            if (url := scalar_text(value)) and safe_image_url(url)
        ]
    if not gallery:
        return ""
    source = safe_url(scalar_text(gallery[0]["url"]))
    encoded = escape_html(json.dumps(gallery, ensure_ascii=False))
    authors = _author_links(gallery[0]["authors"])
    brand = GOOGLE_MAPS_ATTRIBUTION
    attribution = f"{brand} · {authors}" if authors else brand
    source_link = safe_url(scalar_text(gallery[0].get("source_url")))
    if source_link:
        label = escape_html(V3Messages.get_open_in_maps(resolve_language(language)))
        attribution += (
            f' · <a href="{source_link}" target="_blank" rel="noopener noreferrer">{label}</a>'
        )
    return (
        f'<div class="lia-place__photo lia-card-hero" data-place-photos="{encoded}" data-place-name="{escape_html(name)}">'
        f'<img src="{source}" alt="{escape_html(name)}" loading="lazy">'
        f'<div class="lia-photo-attribution">{attribution}</div></div>'
    )
