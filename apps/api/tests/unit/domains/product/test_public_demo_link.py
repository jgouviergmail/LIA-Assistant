"""The public link to the demonstrator: one switch, readable anonymously.

The landing page is anonymous, so whether it shows a link to the demonstrator
must be readable without credentials. And it must be switchable AT RUNTIME:
"take the demo offline" is the most urgent action an operator can need, and
it cannot wait for a rebuild of a `NEXT_PUBLIC_*` value.

Two values, two homes, on purpose:
- the URL is a DEPLOYMENT fact (environment) — it changes when the domain
  changes, which is to say almost never;
- the switch is an OPERATOR fact (settings store) — it changes in a hurry.

What must hold:
- off by default: a fresh instance never advertises a demonstrator;
- when off, the URL is NOT disclosed — hiding a link whose address is still
  served would be theatre;
- a failing store degrades to OFF: the landing simply shows no link, which is
  the safe direction for a link nobody can take down;
- reading it never requires a session.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _settings(url: str) -> MagicMock:
    fake = MagicMock()
    fake.demo_instance_public_url = url
    return fake


def _switch(enabled: bool) -> object:
    return patch(
        "src.domains.product.public_demo_link.read_setting",
        AsyncMock(return_value=enabled),
    )


async def test_the_link_is_hidden_by_default() -> None:
    from src.domains.product.public_demo_link import resolve_public_demo_link

    with (
        patch(
            "src.domains.product.public_demo_link.settings",
            _settings("https://demo.example.org"),
        ),
        _switch(False),
    ):
        link = await resolve_public_demo_link()

    assert link.enabled is False
    # The address stays undisclosed: a hidden link whose URL is still served
    # would only be hidden from people who do not look.
    assert link.url is None


async def test_the_link_is_served_when_switched_on() -> None:
    from src.domains.product.public_demo_link import resolve_public_demo_link

    with (
        patch(
            "src.domains.product.public_demo_link.settings",
            _settings("https://demo.example.org"),
        ),
        _switch(True),
    ):
        link = await resolve_public_demo_link()

    assert link.enabled is True
    assert link.url == "https://demo.example.org"


async def test_a_switch_on_without_a_configured_url_stays_off() -> None:
    from src.domains.product.public_demo_link import resolve_public_demo_link

    with patch("src.domains.product.public_demo_link.settings", _settings("")), _switch(True):
        link = await resolve_public_demo_link()

    # Advertising a link to nowhere is worse than advertising nothing.
    assert link.enabled is False
    assert link.url is None


async def test_a_failing_store_hides_the_link() -> None:
    from src.domains.product.public_demo_link import resolve_public_demo_link

    with (
        patch(
            "src.domains.product.public_demo_link.settings",
            _settings("https://demo.example.org"),
        ),
        patch(
            "src.domains.product.public_demo_link.read_setting",
            AsyncMock(side_effect=RuntimeError("store down")),
        ),
    ):
        link = await resolve_public_demo_link()

    # Safe direction: a link nobody can take down is worse than a missing one.
    assert link.enabled is False
    assert link.url is None


def test_the_switch_defaults_to_off_in_the_settings_store() -> None:
    from src.domains.system_settings.models import SystemSettingKey
    from src.domains.system_settings.registry import SETTING_SPECS

    spec = SETTING_SPECS[SystemSettingKey.PUBLIC_DEMO_LINK_ENABLED]
    # A fresh instance must never advertise a demonstrator it does not run.
    assert spec.default is False


def test_the_endpoint_requires_no_session() -> None:
    from src.domains.product.public_demo_link import router

    # The landing is anonymous: a credentialed endpoint would make the link
    # invisible to exactly the people it is for.
    assert not getattr(router, "dependencies", [])
    routes = [route for route in router.routes if getattr(route, "path", "")]
    assert routes, "the router must expose the read endpoint"
    for route in routes:
        for dependency in getattr(route, "dependencies", []):
            name = getattr(dependency.dependency, "__name__", "")
            assert "session" not in name and "current_user" not in name
