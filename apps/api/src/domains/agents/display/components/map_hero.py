"""The static map a place or route card opens on.

Both cards drew it alike, each with its own copy: the image, a link into the
maps application when there is one, and an alternative text that says where the
link leads — the image is the link's only content — or what it shows when it
leads nowhere.
"""

from src.core.constants import STATIC_MAP_DESKTOP_HEIGHT, STATIC_MAP_DESKTOP_WIDTH
from src.domains.agents.display.components.base import escape_html, safe_url


def _map_image(map_url: str, alt: str) -> str:
    """The map image itself."""
    return (
        f'<img src="{safe_url(map_url)}" alt="{escape_html(alt)}" '
        f'class="lia-route__map-image" loading="lazy" />'
    )


def render_map_hero(static_map_url: str, maps_url: str, *, linked_alt: str, plain_alt: str) -> str:
    """The card's static map, linked into the maps application when it can be.

    Args:
        static_map_url: The static map image, without its size.
        maps_url: Where the map leads, or empty when it leads nowhere.
        linked_alt: The alternative text when the image is a link: where it leads.
        plain_alt: The alternative text when it is not: what it shows.

    Returns:
        The hero's HTML.
    """
    map_url = (
        f"{static_map_url}&width={STATIC_MAP_DESKTOP_WIDTH}&height={STATIC_MAP_DESKTOP_HEIGHT}"
    )
    if maps_url:
        return (
            f'<a href="{safe_url(maps_url)}" target="_blank" rel="noopener" '
            f'class="lia-route__map-link">{_map_image(map_url, linked_alt)}</a>'
        )
    return f'<div class="lia-route__map">{_map_image(map_url, plain_alt)}</div>'
