"""Map tile sources a page the model writes may load (ADR-370 amendment 2026-11-12).

A page runs with no network. A map is the one thing it cannot hold in itself, so
its tiles are the one request allowed out, and only towards the sources declared
here. ``INTERACTIVE_PAGE_MAP_PROVIDERS`` chooses among them; nothing an operator
types reaches a content policy or a prompt unread, which is why the choice is a
list of KEYS and never of hosts.

What a source must be, measured inside the page's frame (2026-11-12):

- **Tiles as images.** ``img-src`` gains the source's origin and no other
  directive gains anything: the page still makes no request of its own, frames
  nothing and runs no outside code.
- **Served with ``Access-Control-Allow-Origin: *``.** Under
  ``Cross-Origin-Embedder-Policy: require-corp`` an image loads only when it is
  requested with ``crossorigin="anonymous"`` and answered that way; under
  ``credentialless`` it loads either way. The writer is told to always ask so.
- **Keyless.** A key in a page is a key in its downloadable file and in the
  conversation. This is why no source here is a vendor that bills per tile.
- **One origin, whole.** A tile host serves tiles and nothing that fetches a
  third party on request, so its origin is the boundary. A host that also serves
  other things would need a path, and a path is not a property of this table.
- **Serves a browser that sends no referrer.** Chromium sends none from the
  page's frame, whatever referrer policy the page asks for; Firefox and WebKit
  send the instance's origin.

**A source is admitted on what a person's browser is SHOWN, never on a status.**
Two hosts answered ``200`` with an image and neither image was a map, and both
had passed a headless engine and a command line that read the status alone:

- OpenStreetMap's own tile server serves its « access blocked » tile to a browser
  that sends no referrer (``x-blocked: No referer sent``). A bundled test engine
  was served the map: it does not name itself as a person's browser does.
- CARTO's basemaps serve an « API key required » tile to everyone.

So each source below was read on a real browser, in the frame, with no referrer,
and its zoom range is the one it answered with a map.

What a source learns: the address of whoever looks at the page and the tiles of
the area looked at. Chromium sends it no referrer; Firefox sends the origin of
this instance; WebKit sends that origin, or the whole address of the page the
conversation is on when the page asks for it. No cookie reaches it on any engine.

Every source here is run by volunteers under a fair-use policy, with a credit to
show: allowing one is the operator's decision, and the credit travels to the
writer with the pattern. A source may change its terms as these two did, which is
one more reason the list is a setting.

Adding a source is one entry: its origin and its line in the writer's prompt are
both derived from it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class MapTileProvider:
    """One source of map tiles.

    Attributes:
        key: What ``INTERACTIVE_PAGE_MAP_PROVIDERS`` names.
        label: What the writer reads, its look included.
        url_template: The tile URL, with ``{z}``, ``{x}`` and ``{y}``.
        credit: The attribution the source's terms require on the map.
        min_zoom: Smallest zoom the source serves.
        max_zoom: Largest zoom the source serves.
    """

    key: str
    label: str
    url_template: str
    credit: str
    min_zoom: int
    max_zoom: int

    @property
    def origin(self) -> str:
        """The scheme and host of the tiles: what a content policy names."""
        parts = urlsplit(self.url_template)
        return f"{parts.scheme}://{parts.netloc}"


_PROVIDERS: Final = (
    MapTileProvider(
        key="osm_hot",
        label="OpenStreetMap, humanitarian style (clear streets, the everyday map)",
        url_template="https://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png",
        credit=(
            "© OpenStreetMap contributors, style by Humanitarian OpenStreetMap Team, "
            "hosted by OpenStreetMap France"
        ),
        min_zoom=0,
        max_zoom=18,
    ),
    MapTileProvider(
        key="osm_fr",
        label="OpenStreetMap France (detailed streets and transport, labels in French)",
        url_template="https://a.tile.openstreetmap.fr/osmfr/{z}/{x}/{y}.png",
        credit="© OpenStreetMap contributors, tiles by OpenStreetMap France",
        min_zoom=0,
        max_zoom=20,
    ),
    MapTileProvider(
        key="osm_de",
        label="OpenStreetMap Germany (classic style, labels in German)",
        url_template="https://tile.openstreetmap.de/{z}/{x}/{y}.png",
        credit="© OpenStreetMap contributors",
        min_zoom=0,
        max_zoom=18,
    ),
    MapTileProvider(
        key="opentopomap",
        label="OpenTopoMap (relief and contour lines)",
        url_template="https://tile.opentopomap.org/{z}/{x}/{y}.png",
        credit="© OpenStreetMap contributors, SRTM, © OpenTopoMap (CC-BY-SA)",
        min_zoom=0,
        max_zoom=17,
    ),
    MapTileProvider(
        key="cyclosm",
        label="CyclOSM (cycle routes and lanes)",
        url_template="https://a.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png",
        credit="© OpenStreetMap contributors, CyclOSM, hosted by OpenStreetMap France",
        min_zoom=0,
        max_zoom=20,
    ),
)

#: Every declared source, by key, in the order the writer reads them.
MAP_TILE_PROVIDERS: Final = MappingProxyType({provider.key: provider for provider in _PROVIDERS})


def parse_map_provider_keys(configured: str | Iterable[str]) -> list[str]:
    """Read the configured sources, refusing one nobody declared.

    Args:
        configured: The keys, or their comma-separated spelling.

    Returns:
        The keys in the table's order, without duplicates; empty for no source.

    Raises:
        ValueError: An entry names no declared source.
    """
    entries = configured.split(",") if isinstance(configured, str) else configured
    chosen = {entry.strip().casefold() for entry in entries if entry.strip()}
    unknown = chosen - set(MAP_TILE_PROVIDERS)
    if unknown:
        raise ValueError(
            "INTERACTIVE_PAGE_MAP_PROVIDERS entries must each name one of "
            f"{', '.join(MAP_TILE_PROVIDERS)}, got {sorted(unknown)!r}"
        )
    return [key for key in MAP_TILE_PROVIDERS if key in chosen]


def map_tile_providers(configured: str | Iterable[str]) -> tuple[MapTileProvider, ...]:
    """The sources a deployment allows.

    Args:
        configured: The keys, or their comma-separated spelling.

    Returns:
        The sources, in the table's order.

    Raises:
        ValueError: An entry names no declared source.
    """
    return tuple(MAP_TILE_PROVIDERS[key] for key in parse_map_provider_keys(configured))
