"""The known servers are what the create door accepts — and nothing a catalogue must not carry.

A known server is offered to a person as « add this, no address to type ». Whatever is
offered must pass the door every typed address passes, name a server once, carry no
credential (a key or a token is the person's to type: the catalogue names its scheme and,
for a key, its header), be described on the screen in six languages, and show the vendor's
own icon, a file the web application serves.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.domains.user_mcp.models import UserMCPAuthType
from src.domains.user_mcp.schemas import UserMCPServerCreate
from src.infrastructure.mcp.known_servers import (
    KNOWN_MCP_SERVER_KEYS,
    KNOWN_MCP_SERVERS,
    KNOWN_SERVER_ICON_DIRECTORY,
    KnownMCPServer,
    find_known_server,
)
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

_WEB_LOCALES = ("en", "fr", "de", "es", "it", "zh")
#: What the person types in the form for a key or a token: never a catalogue value.
_TYPED_SECRET = "typed-by-the-person"
#: An HTTP header name (RFC 9110 token), as the create door forwards it.
_HEADER_TOKEN = re.compile(r"[A-Za-z0-9!#$%&'*+.^_`|~-]{1,100}")
#: An icon file: a lowercase slug and an image format the browser draws in an <img>.
_ICON_FILE = re.compile(r"[a-z][a-z0-9_]{0,31}\.(svg|png)")
#: An icon is a small file: a vendor's full press kit does not belong in a list's chip.
_ICON_MAX_BYTES = 32 * 1024
#: What an icon drawn in an <img> must never carry, even though the browser would not run it.
_SVG_FORBIDDEN = re.compile(
    r"<script|<foreignObject|<iframe|<object|<embed|\son[a-z]+\s*=|href\s*=\s*\"(?!#)",
    re.IGNORECASE,
)


def _create_payload(server: KnownMCPServer) -> UserMCPServerCreate:
    """The create request a person sends after picking ``server`` and typing a secret."""
    secret: dict[str, str] = {}
    if server.auth_type == "api_key":
        secret = {"api_key": _TYPED_SECRET, "header_name": server.header_name or ""}
    elif server.auth_type == "bearer":
        secret = {"bearer_token": _TYPED_SECRET}
    return UserMCPServerCreate(
        name=server.name,
        url=server.url,
        auth_type=UserMCPAuthType(server.auth_type),
        domain_description=server.domain_description,
        oauth_scopes=server.oauth_scopes,
        **secret,
    )


def _icons_directory() -> Path:
    return repo_root_or_skip() / "apps" / "web" / "public" / KNOWN_SERVER_ICON_DIRECTORY


class TestEveryKnownServerPassesTheCreateDoor:
    @pytest.mark.parametrize("server", KNOWN_MCP_SERVERS, ids=lambda server: server.key)
    def test_the_create_schema_accepts_it_as_it_is_offered(self, server: KnownMCPServer) -> None:
        created = _create_payload(server)

        assert created.url == server.url
        assert created.url.startswith("https://")
        assert created.auth_type.value == server.auth_type


class TestACatalogueCarriesNoSecret:
    @pytest.mark.parametrize("server", KNOWN_MCP_SERVERS, ids=lambda server: server.key)
    def test_its_address_is_public_whole(self, server: KnownMCPServer) -> None:
        # No query string, no user-info: a key carried in an address would be a secret
        # published to every account.
        assert "?" not in server.url and "@" not in server.url and "#" not in server.url

    @pytest.mark.parametrize("server", KNOWN_MCP_SERVERS, ids=lambda server: server.key)
    def test_a_header_name_belongs_to_a_key_and_is_a_header(self, server: KnownMCPServer) -> None:
        if server.auth_type != "api_key":
            assert server.header_name is None
            return
        assert server.header_name is not None
        assert _HEADER_TOKEN.fullmatch(server.header_name)
        # A key sent as « Authorization: Bearer » is a bearer server, declared as one.
        assert server.header_name.casefold() != "authorization"

    @pytest.mark.parametrize("server", KNOWN_MCP_SERVERS, ids=lambda server: server.key)
    def test_oauth_details_belong_to_an_oauth_server(self, server: KnownMCPServer) -> None:
        if server.auth_type != "oauth2":
            assert server.oauth_scopes is None
            assert server.own_oauth_client is False
            return
        if server.oauth_scopes is not None:
            assert server.oauth_scopes == " ".join(server.oauth_scopes.split())
            assert server.oauth_scopes


class TestACatalogueNamesAServerOnce:
    def test_keys_names_and_addresses_are_each_unique(self) -> None:
        for attribute in ("key", "name", "url"):
            values = [getattr(server, attribute) for server in KNOWN_MCP_SERVERS]
            assert len(values) == len(set(values)), f"duplicate {attribute}"

    def test_a_key_is_a_stable_slug(self) -> None:
        for server in KNOWN_MCP_SERVERS:
            assert re.fullmatch(r"[a-z][a-z0-9_]{1,31}", server.key), server.key

    def test_the_published_keys_are_the_catalogue_s_in_its_order(self) -> None:
        assert KNOWN_MCP_SERVER_KEYS == tuple(server.key for server in KNOWN_MCP_SERVERS)
        assert KNOWN_MCP_SERVERS, "an empty catalogue offers nothing"

    def test_it_is_offered_by_name(self) -> None:
        # The order declared is the order of the list on screen: a new entry is found
        # where a reader looks for it, not where it was appended.
        names = [server.name.casefold() for server in KNOWN_MCP_SERVERS]

        assert names == sorted(names)


class TestLookingAKnownServerUp:
    def test_a_known_key_answers_its_entry(self) -> None:
        first = KNOWN_MCP_SERVERS[0]

        assert find_known_server(first.key) is first

    @pytest.mark.parametrize("key", ["", "unknown_server", "NOTION", " notion "])
    def test_anything_else_answers_nothing(self, key: str) -> None:
        # No folding, no trimming: a key is what the catalogue published, exactly.
        assert find_known_server(key) is None


class TestTheScreenDescribesEveryKnownServer:
    @pytest.mark.parametrize("locale", _WEB_LOCALES)
    def test_each_key_has_its_sentence_in_the_web_locale(self, locale: str) -> None:
        """The gallery shows what a server is for from the web locales, by key: a key
        the catalogue publishes and the locale lacks would show a bare brand name."""
        path = repo_root_or_skip() / "apps" / "web" / "locales" / locale / "translation.json"
        described = json.loads(path.read_text(encoding="utf-8"))["settings"]["mcp"]["known"][
            "servers"
        ]

        assert set(described) == set(KNOWN_MCP_SERVER_KEYS)
        assert all(isinstance(text, str) and text.strip() for text in described.values())


class TestEveryKnownServerShowsItsVendorsIcon:
    @pytest.mark.parametrize("server", KNOWN_MCP_SERVERS, ids=lambda server: server.key)
    def test_its_icon_is_a_small_file_the_web_application_serves(
        self, server: KnownMCPServer
    ) -> None:
        assert _ICON_FILE.fullmatch(server.icon), server.icon
        icon = _icons_directory() / server.icon

        assert icon.is_file(), f"{server.key}: {icon} is missing"
        assert 0 < icon.stat().st_size <= _ICON_MAX_BYTES

    def test_no_icon_file_is_left_unreferenced(self) -> None:
        # A file nobody names is a vendor's mark published for nothing.
        named = {server.icon for server in KNOWN_MCP_SERVERS}
        present = {path.name for path in _icons_directory().iterdir() if path.is_file()}

        assert present == named

    def test_a_vector_icon_only_draws(self) -> None:
        # Drawn in an <img>, an SVG runs nothing; it still carries nothing that could
        # the day it is inlined: no script, no foreign content, no handler, no
        # reference outside itself.
        for path in sorted(_icons_directory().glob("*.svg")):
            text = path.read_text(encoding="utf-8")
            assert text.lstrip().startswith("<svg"), path.name
            assert "viewBox" in text, path.name
            assert not _SVG_FORBIDDEN.search(text), path.name
            assert "prefers-color-scheme" not in text, path.name

    def test_a_raster_icon_is_a_png(self) -> None:
        for path in sorted(_icons_directory().glob("*.png")):
            assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", path.name
