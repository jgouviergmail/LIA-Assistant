"""A demonstrator never lets a visitor link their real accounts.

The scenario this closes: a visitor gets a throwaway account on our public
instance, clicks "connect Gmail", and grants OUR instance access to THEIR
mailbox. Their data would land in a database that is wiped every night by a
service they have no relationship with — and we would be the ones holding it
in the meantime.

The network edge (lot 4) will not route these paths at all. This is the
second layer: even reachable, the application refuses.

What must hold:
- every account-linking path of the connectors router is refused in demo
  mode — checked against the ROUTER's real routes, so a connector added
  tomorrow is covered without anyone remembering this file;
- read-only connector endpoints keep working (the demo still shows which
  categories exist and that they are unconfigured);
- outside demo mode nothing changes at all.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.core.demo_mode import (
    forbid_account_linking_in_demo,
    is_account_linking_path,
)
from src.core.exceptions import BaseAPIException
from src.domains.connectors.router import router

pytestmark = pytest.mark.unit


def _request(path: str) -> MagicMock:
    request = MagicMock()
    request.url.path = path
    return request


def _settings(demo: bool) -> MagicMock:
    fake = MagicMock()
    fake.demo_mode_enabled = demo
    return fake


def _linking_paths() -> list[str]:
    """Every authorize/callback path the router actually exposes today."""
    return [
        route.path  # type: ignore[attr-defined]
        for route in router.routes
        if route.path.endswith(("/authorize", "/callback"))  # type: ignore[attr-defined]
    ]


def test_the_router_still_exposes_linking_paths_to_guard() -> None:
    # If this ever hits zero, the guard below became vacuous and the suite
    # would go green while protecting nothing.
    assert len(_linking_paths()) >= 10


async def test_every_linking_path_is_refused_in_demo_mode() -> None:
    with patch("src.core.demo_mode.settings", _settings(demo=True)):
        for path in _linking_paths():
            with pytest.raises(BaseAPIException) as excinfo:
                await forbid_account_linking_in_demo(_request(f"/api/v1/connectors{path}"))
            assert excinfo.value.status_code == 403, path


async def test_read_only_connector_endpoints_still_work_in_demo_mode() -> None:
    with patch("src.core.demo_mode.settings", _settings(demo=True)):
        # Real mounted paths only: this test used to assert on
        # /connectors/categories, which the router does not expose — a
        # guard over an imaginary route proves nothing (found by the
        # lot-6 census).
        for path in ("/api/v1/connectors", "/api/v1/connectors/types"):
            # The demo shows which categories exist and that they are
            # unconfigured — that IS part of what it demonstrates.
            await forbid_account_linking_in_demo(_request(path))


async def test_nothing_is_refused_outside_demo_mode() -> None:
    with patch("src.core.demo_mode.settings", _settings(demo=False)):
        for path in _linking_paths():
            await forbid_account_linking_in_demo(_request(f"/api/v1/connectors{path}"))


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/v1/connectors/gmail/authorize", True),
        ("/api/v1/connectors/gmail/callback", True),
        ("/api/v1/connectors/philips-hue/authorize", True),
        ("/api/v1/connectors/", False),
        ("/api/v1/connectors/categories", False),
        ("/api/v1/connectors/abc-123/preferences", False),
        # A path that merely CONTAINS the word must not be caught by accident.
        ("/api/v1/connectors/callback-history", False),
        ("/api/v1/connectors/authorized-apps", False),
    ],
)
def test_path_classification_matches_the_segment_not_the_substring(
    path: str, expected: bool
) -> None:
    assert is_account_linking_path(path) is expected


def test_the_guard_is_wired_on_the_connectors_router() -> None:
    # A guard nobody depends on is a guard that does nothing.
    dependencies = getattr(router, "dependencies", [])
    assert any(
        getattr(dep.dependency, "__name__", "") == "forbid_account_linking_in_demo"
        for dep in dependencies
    )


#: Connector routes that are NOT account linking, each with why it may stay
#: open on a demonstrator. Frozen: a new route must be classified, because the
#: guard recognises linking by its final segment and a connector arriving with
#: `/link` or `/connect` would slip past unnoticed — the edge would still
#: refuse it, but this second layer has to hold on its own.
READ_ONLY_ROUTES: dict[str, str] = {
    # Seeing what exists, and that it is unconfigured, IS the demonstration.
    "/connectors": "lists the visitor's connectors — empty on a demonstrator",
    "/connectors/types": "the catalogue of connector types, no credential involved",
    "/connectors/health": "whether the configured connectors answer",
    "/connectors/health/settings": "the health thresholds the UI renders",
    # Operations on an ALREADY linked connector. A demonstrator has none, so
    # they resolve to 404 — and none of them can create a link.
    "/connectors/{connector_id}": "read, update preferences, or delete one's own connector",
    "/connectors/{connector_id}/preferences": "preferences of an existing connector",
    "/connectors/{connector_id}/calendars": "calendars of an existing connector",
    "/connectors/{connector_id}/task-lists": "task lists of an existing connector",
    "/connectors/{connector_id}/refresh": "refresh an existing connector's token",
    "/connectors/api-key/{connector_id}/info": "metadata of an existing API-key connector",
    # Content proxies, each scoped to a connector that must already exist.
    "/connectors/gmail/attachment/{message_id}/{attachment_id}": "attachment of one's own mail",
    "/connectors/google-drive/thumbnail/{file_id}": "thumbnail of one's own file",
    "/connectors/google-places/photo/{photo_name:path}": "photo of a place already returned",
    "/connectors/google-location/static-map": "map image for a location already resolved",
    "/connectors/google-routes/static-map": "map image for a route already computed",
    "/connectors/street-view": "street view image for a location already resolved (lot SV)",
    # Administration, already behind a superuser dependency.
    "/connectors/admin/global-config": "operator configuration, superuser only",
    "/connectors/admin/global-config/{connector_type}": "same, one type",
}


@pytest.mark.parametrize(
    "path",
    [
        # Credentials typed by the visitor: "Tests credentials, then creates
        # connectors" is exactly what must never happen on a demonstrator.
        "/api/v1/connectors/apple/activate",
        "/api/v1/connectors/apple/validate",
        "/api/v1/connectors/api-key/activate",
        "/api/v1/connectors/api-key/validate",
        "/api/v1/connectors/api-key/{connector_id}/rotate",
        "/api/v1/connectors/google-contacts/activate",
        "/api/v1/connectors/google-places/activate",
        # Local-network pairing and discovery: a visitor has no bridge here,
        # and the demonstrator's egress is search-only (owner arbitration 2).
        "/api/v1/connectors/philips-hue/pair",
        "/api/v1/connectors/philips-hue/discover",
        "/api/v1/connectors/philips-hue/test",
        # The verb is not always the LAST segment.
        "/api/v1/connectors/philips-hue/activate/local",
    ],
)
def test_credential_paths_are_linking_too(path: str) -> None:
    """Linking is not only OAuth.

    Lot 2 closed authorize/callback. The route census (lot 6) found the other
    half: Apple and API-key connectors are activated by TYPING credentials,
    and Hue pairs over the local network. Same risk, different verb.
    """
    assert is_account_linking_path(path) is True


def _all_router_paths() -> list[str]:
    return [str(route.path) for route in router.routes]  # type: ignore[attr-defined]


def test_every_connector_route_is_classified() -> None:
    """No connector route escapes the linking/read-only decision.

    The guard classifies by final segment. That covers every connector we
    have, and the day one arrives with a differently named linking verb this
    fails until somebody looks at it.
    """
    unclassified = [
        path
        for path in _all_router_paths()
        if not is_account_linking_path(f"/api/v1/connectors{path}") and path not in READ_ONLY_ROUTES
    ]
    assert not unclassified, (
        f"unclassified connector routes: {sorted(unclassified)} — if one of them starts or "
        "completes an account linking, the guard must refuse it; otherwise add it to "
        "READ_ONLY_ROUTES with the reason it may stay open on a demonstrator"
    )


def test_no_stale_read_only_classification() -> None:
    """A route that left the router must leave the classification too."""
    stale = set(READ_ONLY_ROUTES) - set(_all_router_paths())
    assert not stale, f"classified but no longer mounted: {sorted(stale)}"


async def test_every_read_only_route_really_stays_open() -> None:
    with patch("src.core.demo_mode.settings", _settings(demo=True)):
        for path in READ_ONLY_ROUTES:
            await forbid_account_linking_in_demo(_request(f"/api/v1/connectors{path}"))


@pytest.mark.parametrize(
    "path",
    [
        # Ordinary words on other routers: "test", "validate" and "discover"
        # are not connector verbs there, and a guard from `core` must not bite
        # outside the domain it was written for.
        "/api/v1/skills/test",
        "/api/v1/mcp/servers/validate",
        "/api/v1/agents/discover",
        "/api/v1/auth/google/callback",
    ],
)
def test_the_guard_does_not_reach_beyond_the_connectors_router(path: str) -> None:
    assert is_account_linking_path(path) is False
